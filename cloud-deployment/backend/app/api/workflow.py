from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy import select
from app.db.database import SessionLocal, ROOT
from app.models.family import FamilyModel
from app.models.media_asset import MediaAssetModel
from app.models.chat_session import ChatSessionModel
from app.schemas.family import Family
from app.api.authentication import current_session
from app.schemas.memory import Memory
from app.schemas.workflow import DraftConfirmation, MediaResponse, DraftResponse, DraftUpdate, DraftRegeneration
from app.repositories.family_repository import FamilyRepository
from app.services.workflow_service import WorkflowService, serialized

router = APIRouter(prefix='/api/v1', tags=['workflow'])
workflow = WorkflowService()
from app.services import media_service
from app.services.media_storage import MediaNotFoundError
LOCAL_FAMILY_ID = uuid5(NAMESPACE_URL, 'ai-memories:local-development-family')

@router.post('/local/bootstrap', response_model=Family)
def bootstrap(principal=Depends(current_session)):
    # Compatibility path for clients: identity determines the family, never a fixed UUID.
    return FamilyRepository().get(UUID(principal.family_id))

@router.post('/memory-drafts/{draft_id}/confirm', response_model=Memory)
def confirm(draft_id: UUID, body: DraftConfirmation):
    return workflow.confirm(draft_id, body.revision)

@router.post('/chat/sessions/{session_id}/media', response_model=MediaResponse, status_code=201)
def upload_media(session_id: UUID, client_request_id: UUID, file: UploadFile = File(...)):
    return media_service.upload(session_id, client_request_id, file.file)

@router.delete('/chat/sessions/{session_id}/media', status_code=204)
def remove_media(session_id: UUID):
    media_service.remove_pending(session_id)
    return Response(status_code=204)

@router.delete('/chat/sessions/{session_id}/media/{media_id}', status_code=204)
def remove_pending_photo(session_id: UUID, media_id: UUID):
    media_service.remove_pending(session_id, media_id)
    return Response(status_code=204)

@router.get('/media/{media_id}')
def get_media(media_id: UUID):
    with SessionLocal() as db:
        if db.get(MediaAssetModel, str(media_id)) is None:
            raise HTTPException(404, '图片不存在')
    try:
        data = media_service.storage().read(media_id)
    except MediaNotFoundError:
        raise HTTPException(404, '图片文件不存在') from None
    return Response(content=data, media_type='image/jpeg')

@router.get('/memory-drafts/{draft_id}', response_model=DraftResponse)
def get_draft(draft_id: UUID):
    return workflow.get_draft(draft_id)

@router.patch('/memory-drafts/{draft_id}', response_model=DraftResponse)
def edit_draft(draft_id: UUID, body: DraftUpdate):
    return workflow.edit_draft(draft_id, body)

@router.post('/memory-drafts/{draft_id}/regenerate', response_model=DraftResponse)
def regenerate_draft(draft_id: UUID, body: DraftRegeneration):
    return workflow.regenerate_draft(draft_id, body)


from app.schemas.time_linkage import DraftTimePreviewRequest, TimePreview

@router.post('/memory-drafts/{draft_id}/time-preview', response_model=TimePreview)
def draft_time_preview(draft_id: UUID, body: DraftTimePreviewRequest):
    return workflow.preview_time(draft_id, body)
