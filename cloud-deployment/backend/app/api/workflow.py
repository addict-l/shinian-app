from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from pathlib import Path
import io
import os
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
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
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(ROOT / '.runtime/media')))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = 25_000_000
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
    with serialized(session_id):
        with SessionLocal() as db:
            session = db.get(ChatSessionModel, str(session_id))
            if session is None:
                raise HTTPException(404, '会话不存在')
            existing = db.get(MediaAssetModel, str(client_request_id))
            if existing:
                if existing.session_id != str(session_id):
                    raise HTTPException(409, '附件请求标识不匹配')
                return MediaResponse(id=existing.id, session_id=session_id, memory_id=existing.memory_id, url=existing.file_url, mime_type=existing.mime_type)
            if session.status == 'completed':
                raise HTTPException(409, '已保存的回忆不能追加会话附件')
        data = file.file.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, '图片不能超过 8 MB')
        path = MEDIA_ROOT / (str(client_request_id) + '.jpg')
        try:
            picture = Image.open(io.BytesIO(data))
            if picture.format not in ['JPEG', 'PNG', 'WEBP']:
                raise HTTPException(415, '图片格式不支持')
            picture.load()
            picture.convert('RGB').save(path, 'JPEG', quality=88)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(415, '无法读取图片')
        url = '/api/v1/media/' + str(client_request_id)
        try:
            with SessionLocal.begin() as db:
                old_assets = list(db.scalars(select(MediaAssetModel).where(MediaAssetModel.session_id == str(session_id))))
                old_ids = [asset.id for asset in old_assets]
                for asset in old_assets:
                    db.delete(asset)
                db.add(MediaAssetModel(id=str(client_request_id), memory_id=None, session_id=str(session_id),
                                      type='image', file_url=url, original_filename=None, mime_type='image/jpeg'))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        for old_id in old_ids:
            (MEDIA_ROOT / (old_id + '.jpg')).unlink(missing_ok=True)
        return MediaResponse(id=client_request_id, session_id=session_id, memory_id=None, url=url, mime_type='image/jpeg')

@router.delete('/chat/sessions/{session_id}/media', status_code=204)
def remove_media(session_id: UUID):
    with serialized(session_id):
        with SessionLocal.begin() as db:
            session = db.get(ChatSessionModel, str(session_id))
            if session is None:
                raise HTTPException(404, '会话不存在')
            if session.status == 'completed':
                raise HTTPException(409, '已保存的回忆不能移除附件')
            assets = list(db.scalars(select(MediaAssetModel).where(MediaAssetModel.session_id == str(session_id))))
            ids = [asset.id for asset in assets]
            for asset in assets:
                db.delete(asset)
        for asset_id in ids:
            (MEDIA_ROOT / (asset_id + '.jpg')).unlink(missing_ok=True)
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
