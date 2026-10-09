"""Photo storage: additive uploads, stable identities, and protected message attachments."""
import hashlib
import io
import os
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.db.database import ROOT, SessionLocal
from app.models.chat_session import ChatSessionModel
from app.models.media_asset import MediaAssetModel
from app.schemas.media import MediaResponse
from app.services.workflow_service import serialized

MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(ROOT / '.runtime/media')))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def receipt(asset):
    return MediaResponse(id=asset.id, session_id=asset.session_id, memory_id=asset.memory_id,
                         message_id=asset.message_id, position=asset.position,
                         url=asset.file_url, mime_type=asset.mime_type)


def upload(session_id, request_id, file):
    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, '图片不能超过 8 MB')
    digest = hashlib.sha256(data).hexdigest()
    with serialized(session_id), serialized('media:' + str(request_id)):
        with SessionLocal() as db:
            session = db.get(ChatSessionModel, str(session_id))
            if session is None:
                raise HTTPException(404, '会话不存在')
            existing = db.get(MediaAssetModel, str(request_id))
            if existing:
                if existing.session_id != str(session_id) or (existing.content_hash and existing.content_hash != digest):
                    raise HTTPException(409, '同一个照片请求标识不能上传不同内容')
                return receipt(existing)
            if session.status == 'completed':
                raise HTTPException(409, '已保存的回忆不能追加会话附件')
        temporary = MEDIA_ROOT / (str(uuid4()) + '.upload')
        path = MEDIA_ROOT / (str(request_id) + '.jpg')
        try:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(data)) as picture:
                        if picture.format not in ('JPEG', 'PNG', 'WEBP'):
                            raise HTTPException(415, '图片格式不支持')
                        picture.load()
                        picture = ImageOps.exif_transpose(picture).convert('RGB')
                        picture.thumbnail((2560, 2560))
                        picture.save(temporary, 'JPEG', quality=88)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise HTTPException(415, '无法读取图片')
            if temporary.stat().st_size > MAX_BYTES:
                raise HTTPException(413, '图片压缩后仍超过 8 MB')
            os.replace(temporary, path)
            try:
                with SessionLocal.begin() as db:
                    asset = MediaAssetModel(id=str(request_id), memory_id=None, session_id=str(session_id),
                                            type='image', file_url='/api/v1/media/' + str(request_id),
                                            original_filename=None, mime_type='image/jpeg', content_hash=digest)
                    db.add(asset)
                    db.flush()
                    result = receipt(asset)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return result
        finally:
            temporary.unlink(missing_ok=True)


def remove_pending(session_id, media_id=None):
    with serialized(session_id):
        with SessionLocal.begin() as db:
            session = db.get(ChatSessionModel, str(session_id))
            if session is None:
                raise HTTPException(404, '会话不存在')
            if session.status == 'completed':
                raise HTTPException(409, '已保存的回忆不能移除附件')
            query = select(MediaAssetModel).where(MediaAssetModel.session_id == str(session_id))
            if media_id:
                query = query.where(MediaAssetModel.id == str(media_id))
            assets = list(db.scalars(query))
            if media_id and any(asset.message_id for asset in assets):
                raise HTTPException(409, '已经发送的照片不能从输入区移除')
            ids = [asset.id for asset in assets if asset.message_id is None]
            for asset in assets:
                if asset.id in ids:
                    db.delete(asset)
        for asset_id in ids:
            (MEDIA_ROOT / (asset_id + '.jpg')).unlink(missing_ok=True)
