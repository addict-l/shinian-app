"""Versioned edits and transactional story deletion; files are cleaned after commit."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, delete, or_
from app.db.database import SessionLocal
from app.models.memory import MemoryModel
from app.models.chat_session import ChatSessionModel
from app.models.chat_message import ChatMessageModel
from app.models.memory_draft import MemoryDraftModel
from app.models.memory_person import MemoryPersonModel
from app.models.media_asset import MediaAssetModel
from app.models.maintenance import MediaCleanupModel, MemoryDeletionModel
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryDeletion
from app.schemas.story_information import StoryInformation, InformationStatus
from app.services.workflow_service import serialized
from app.services.conversation_opening import preserve_opening


def owned(db, memory_id, family_id, lock=False):
    value = db.get(MemoryModel, str(memory_id), with_for_update=lock)
    if value is None or value.family_id != str(family_id):
        raise HTTPException(404, '回忆不存在')
    return value


def queue(db, asset, family_id):
    if db.get(MediaCleanupModel, asset.id) is None:
        db.add(MediaCleanupModel(id=asset.id, family_id=str(family_id)))
    db.delete(asset)


def drain_cleanup(limit=100):
    # Keep jobs until both remote objects and active local copies are removed.
    # Deletion is idempotent, including after a worker/process crash.
    from app.services.media_service import storage
    with serialized('maintenance:cleanup'):
        with SessionLocal() as db:
            ids = list(db.scalars(select(MediaCleanupModel.id).order_by(MediaCleanupModel.attempts, MediaCleanupModel.created_at).limit(limit)))
        for asset_id in ids:
            with serialized('media:' + asset_id), SessionLocal.begin() as db:
                job = db.get(MediaCleanupModel, asset_id, with_for_update=True)
                if job is None:
                    continue
                if db.get(MediaAssetModel, asset_id) is not None:
                    # A reused upload identity must never lose its current file.
                    db.delete(job)
                    continue
                try:
                    storage().delete(str(UUID(asset_id)))
                except OSError:
                    job.attempts += 1
                else:
                    db.delete(job)


def cleanup_after_request():
    # Preserve immediate local cleanup. Remote retries belong to the existing
    # background worker, so a slow OSS request cannot stall a committed edit.
    from app.services.media_service import storage
    try:
        if storage().backend != 'local':
            return
    except OSError:
        return
    drain_cleanup()


def update(memory_id, body):
    with serialized('memory:' + str(memory_id)):
        with SessionLocal.begin() as db:
            model = owned(db, memory_id, body.family_id, lock=True)
            if model.version != body.version:
                raise HTTPException(409, '回忆已在其他设备更新，请读取最新版本；本机修改仍可保留核对')
            title, summary = body.title.strip(), body.summary.strip()
            if not title or not summary:
                raise HTTPException(422, '标题和正文不能为空')
            ids = [str(value) for value in body.media_ids]
            if len(ids) != len(set(ids)):
                raise HTTPException(422, '照片不能重复')
            assets = [db.get(MediaAssetModel, value, with_for_update=True) for value in ids]
            if any(value is None or not (value.memory_id == model.id or value.editing_memory_id == model.id or
                    (model.source_session_id and value.session_id == model.source_session_id and value.message_id is not None and value.memory_id is None)) for value in assets):
                raise HTTPException(409, '照片不存在或属于其他回忆，请核对照片')
            info = StoryInformation.model_validate(model.information or {})
            for name in ('time', 'place', 'feeling'):
                incoming = getattr(body, name).model_copy(deep=True)
                previous = getattr(info, name)
                if (previous.status, previous.value) != (incoming.status, incoming.value):
                    incoming.source_message_ids = []  # User edit is not an original-chat quotation.
                    incoming.user_edited = True
                else:
                    incoming.source_message_ids = previous.source_message_ids
                    incoming.user_edited = previous.user_edited
                setattr(info, name, incoming)
            info.conflicts = [item for item in info.conflicts if item.dimension not in ('time', 'place', 'feeling')]
            if body.memory_date is not None and (info.time.status != InformationStatus.known or info.time.value != body.memory_date.isoformat()):
                raise HTTPException(422, '精确日期需与已确定的时间一致')
            model.title, model.summary = title, summary
            model.information = info.model_dump(mode='json')
            from app.services.time_linkage import time_date
            model.memory_date = time_date(info)
            model.location = info.place.value if info.place.status in (InformationStatus.known, InformationStatus.approximate) else None
            model.version += 1
            model.updated_at = datetime.now(timezone.utc)
            for old in db.scalars(select(MediaAssetModel).where(MediaAssetModel.memory_id == model.id)):
                if old.id not in ids:
                    if old.session_id is not None:
                        old.memory_id = None  # Preserve the original chat attachment.
                    else:
                        queue(db, old, body.family_id)
            for index, asset in enumerate(assets):
                asset.memory_id = model.id
                asset.editing_memory_id = None
                # Message attachment positions belong to the original dialogue.
                # Memory photo order remains creation order for chat photos.
                if asset.message_id is None:
                    asset.position = index
    cleanup_after_request()
    return MemoryRepository().get(memory_id)


def remove(memory_id, family_id, version):
    with SessionLocal() as db:
        initial = db.get(MemoryModel, str(memory_id))
        person_key = f'person:{family_id}:{initial.primary_person_id}' if initial else f'deleted:{memory_id}'
        source_key = initial.source_session_id if initial and initial.source_session_id else f'deleted:{memory_id}'
    with serialized(person_key), serialized(source_key), serialized('memory:' + str(memory_id)):
        with SessionLocal.begin() as db:
            receipt = db.get(MemoryDeletionModel, str(memory_id), with_for_update=True)
            if receipt is not None:
                if receipt.family_id != str(family_id):
                    raise HTTPException(404, '回忆不存在')
                if receipt.version != version:
                    raise HTTPException(409, '删除请求版本不一致，请核对')
            else:
                model = owned(db, memory_id, family_id, lock=True)
                if model.version != version:
                    raise HTTPException(409, '回忆已在其他设备更新，请读取最新版本后再确认删除')
                source = model.source_session_id
                if source:
                    preserve_opening(db, source)
                selectors = [MediaAssetModel.memory_id == model.id, MediaAssetModel.editing_memory_id == model.id]
                if source:
                    selectors.append(MediaAssetModel.session_id == source)
                for asset in db.scalars(select(MediaAssetModel).where(or_(*selectors)).with_for_update()):
                    # A legacy asset linked to a different saved story must be retained.
                    if asset.memory_id and asset.memory_id != model.id:
                        asset.session_id = None
                        asset.message_id = None
                    else:
                        queue(db, asset, family_id)
                db.flush()
                db.execute(delete(MemoryDraftModel).where(or_(MemoryDraftModel.saved_memory_id == model.id,
                    MemoryDraftModel.session_id == source if source else False)))
                db.execute(delete(MemoryPersonModel).where(MemoryPersonModel.memory_id == model.id))
                db.execute(delete(MemoryModel).where(MemoryModel.id == model.id))
                if source:
                    db.execute(delete(ChatMessageModel).where(ChatMessageModel.session_id == source))
                    db.execute(delete(ChatSessionModel).where(ChatSessionModel.id == source))
                db.add(MemoryDeletionModel(id=str(memory_id), family_id=str(family_id), version=version))
    cleanup_after_request()
    with SessionLocal() as db:
        pending = db.scalar(select(MediaCleanupModel.id).where(MediaCleanupModel.family_id == str(family_id)).limit(1)) is not None
    return MemoryDeletion(id=memory_id, cleanup_pending=pending)


def discard_photo(memory_id, family_id, media_id):
    with serialized('memory:' + str(memory_id)), serialized('media:' + str(media_id)):
        with SessionLocal.begin() as db:
            owned(db, memory_id, family_id, lock=True)
            asset = db.get(MediaAssetModel, str(media_id), with_for_update=True)
            if asset is not None:
                if asset.editing_memory_id != str(memory_id) or asset.memory_id is not None:
                    raise HTTPException(409, '只能丢弃这次编辑中新上传的照片')
                queue(db, asset, family_id)
    cleanup_after_request()


def preview_time(memory_id, body):
    with serialized('memory:' + str(memory_id)), SessionLocal() as db:
        model = owned(db, memory_id, body.family_id)
        if model.version != body.version:
            raise HTTPException(409, '回忆已更新，请读取最新版本；本机修改仍保留')
        from app.services.time_linkage import preview
        return preview(body)
