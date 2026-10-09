from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from app.db.database import SessionLocal, ROOT
from app.models.family import FamilyModel
from app.models.media_asset import MediaAssetModel
from app.models.chat_session import ChatSessionModel
from app.schemas.family import Family
from app.schemas.memory import Memory
from app.schemas.workflow import DraftConfirmation, MediaResponse
from app.repositories.family_repository import FamilyRepository
from app.services.workflow_service import WorkflowService, serialized

router = APIRouter(prefix='/api/v1', tags=['workflow'])
workflow = WorkflowService()
from app.services import media_service
from app.services.media_service import MEDIA_ROOT
LOCAL_FAMILY_ID = uuid5(NAMESPACE_URL, 'ai-memories:local-development-family')

@router.post('/local/bootstrap', response_model=Family)
def bootstrap():
    with serialized('bootstrap'):
        with SessionLocal.begin() as db:
            if db.get(FamilyModel, str(LOCAL_FAMILY_ID)) is None:
                now = datetime.now(timezone.utc)
                db.add(FamilyModel(id=str(LOCAL_FAMILY_ID), name='我的家庭', created_at=now, updated_at=now))
    return FamilyRepository().get(LOCAL_FAMILY_ID)

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
    path = MEDIA_ROOT / (str(media_id) + '.jpg')
    if not path.is_file():
        raise HTTPException(404, '图片文件不存在')
    return FileResponse(path, media_type='image/jpeg')
