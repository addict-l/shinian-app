"""One mandatory authorization dependency for every family business route.

Resource IDs remain opaque: a missing resource and another family's resource
both return 404. The API never trusts a caller-supplied family_id as identity.
"""
from fastapi import Depends, HTTPException, Request
from uuid import UUID
from starlette.concurrency import run_in_threadpool
from app.api.authentication import current_session
from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.models.memory import MemoryModel
from app.models.chat_session import ChatSessionModel
from app.models.chat_message import ChatMessageModel
from app.models.memory_draft import MemoryDraftModel
from app.models.media_asset import MediaAssetModel
from app.models.maintenance import MemoryDeletionModel


def canonical_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, '内容不存在或不属于当前家庭。') from None


class FamilyAccess:
    def __init__(self, db, family_id):
        self.db = db
        self.family_id = family_id

    def family(self, value):
        if canonical_id(value) != canonical_id(self.family_id):
            raise HTTPException(404, '内容不存在或不属于当前家庭。')

    def resource(self, model, value, allow_missing=False):
        item = self.db.get(model, canonical_id(value))
        if item is None:
            if allow_missing:
                return
            raise HTTPException(404, '内容不存在或不属于当前家庭。')
        if isinstance(item, MediaAssetModel):
            owners = []
            for kind, identity in [(MemoryModel, item.memory_id), (MemoryModel, item.editing_memory_id),
                                   (FamilyMemberModel, item.memoir_person_id), (ChatSessionModel, item.session_id),
                                   (ChatMessageModel, item.message_id)]:
                if identity:
                    owner = self.db.get(kind, identity)
                    if owner:
                        owners.append(self.owner(owner))
            if not owners or any(owner != self.family_id for owner in owners):
                raise HTTPException(404, '内容不存在或不属于当前家庭。')
        else:
            self.family(self.owner(item))

    def owner(self, item):
        if isinstance(item, (ChatMessageModel, MemoryDraftModel)):
            parent = self.db.get(ChatSessionModel, item.session_id)
            return parent.family_id if parent else None
        return item.family_id


def check_request(principal, parameters, payload, path, method):
    models = {'family_member_id': FamilyMemberModel, 'person_id': FamilyMemberModel,
              'primary_person_id': FamilyMemberModel, 'session_id': ChatSessionModel,
              'draft_id': MemoryDraftModel, 'memory_id': MemoryModel, 'media_id': MediaAssetModel}
    lists = {'person_ids': FamilyMemberModel, 'attachment_ids': MediaAssetModel, 'media_ids': MediaAssetModel}
    with SessionLocal() as db:
        access = FamilyAccess(db, principal.family_id)
        for key, value in parameters:
            if key == 'family_id':
                access.family(value)
            elif key in models and value is not None:
                if key == 'memory_id' and method == 'DELETE' and path.endswith('/' + str(value)):
                    # A retried deletion may only return this family's durable receipt.
                    access.resource(MemoryModel if db.get(MemoryModel, canonical_id(value)) else MemoryDeletionModel, value)
                else:
                    access.resource(models[key], value)
        if isinstance(payload, dict):
            for key, value in payload.items():
                if value is None:
                    continue
                if key == 'family_id':
                    access.family(value)
                elif key in models:
                    access.resource(models[key], value)
                elif key in lists and isinstance(value, list):
                    if key == 'attachment_ids' and (len(value) > 9 or len(set(map(str, value))) != len(value)):
                        continue  # The declared message schema reports its 422 before resource lookup.
                    if len(value) > 1000:
                        raise HTTPException(422, '提交的人物或照片数量过多。')
                    for identity in value:
                        access.resource(lists[key], identity)
            # Existing idempotency IDs must not disclose another family's result.
            request_id = payload.get('client_request_id')
            if request_id:
                for model in [FamilyMemberModel, ChatSessionModel, ChatMessageModel, MediaAssetModel]:
                    access.resource(model, request_id, allow_missing=True)
        for key, value in parameters:
            if key == 'client_request_id':
                access.resource(MediaAssetModel, value, allow_missing=True)


async def authorize_business_request(request: Request, principal=Depends(current_session)):
    payload = None
    # FastAPI also accepts case variations, +json types, and JSON with no Content-Type.
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'multipart/form-data':
        try:
            payload = await request.json()
        except ValueError:
            pass  # Let the declared request schema produce its normal 422.
    await run_in_threadpool(check_request, principal,
        [*request.path_params.items(), *request.query_params.multi_items()], payload, request.url.path, request.method)
