"""Photo storage: additive uploads, stable identities, and protected message attachments."""
import hashlib
import io
import os
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.db.database import ROOT, SessionLocal
from app.models.chat_session import ChatSessionModel
from app.models.media_asset import MediaAssetModel
from app.models.maintenance import MediaCleanupModel
from app.schemas.media import MediaResponse
from app.services.media_storage import MAX_MEDIA_BYTES, get_storage
from app.services.workflow_service import serialized

MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(ROOT / '.runtime/media')))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
MAX_BYTES = MAX_MEDIA_BYTES
Image.MAX_IMAGE_PIXELS = 25_000_000


def storage():
    return get_storage(MEDIA_ROOT)


def receipt(asset):
    return MediaResponse(id=asset.id, session_id=asset.session_id, memory_id=asset.memory_id,
                         message_id=asset.message_id, position=asset.position,
                         url=asset.file_url, mime_type=asset.mime_type)


def upload(session_id, request_id, file, editing_memory_id=None, family_id=None, memoir_person_id=None):
    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, '图片不能超过 8 MB')
    digest = hashlib.sha256(data).hexdigest()
    owner_key = 'memoir:' + str(memoir_person_id) if memoir_person_id else ('memory:' + str(editing_memory_id) if editing_memory_id else session_id)
    with serialized(owner_key), serialized('media:' + str(request_id)):
        with SessionLocal() as db:
            session = None
            if memoir_person_id:
                from app.services.memoir_service import owned_person
                owner_family = owned_person(db, family_id, memoir_person_id).family_id
            elif editing_memory_id:
                from app.services.memory_maintenance import owned
                owner_family = owned(db, editing_memory_id, family_id).family_id
            else:
                session = db.get(ChatSessionModel, str(session_id))
                if session is None:
                    raise HTTPException(404, '会话不存在')
                owner_family = session.family_id
            existing = db.get(MediaAssetModel, str(request_id))
            if existing:
                owner_matches = existing.memoir_person_id == str(memoir_person_id) if memoir_person_id else (
                    existing.editing_memory_id == str(editing_memory_id) or existing.memory_id == str(editing_memory_id) if editing_memory_id else existing.session_id == str(session_id))
                if not owner_matches or (existing.content_hash and existing.content_hash != digest):
                    raise HTTPException(409, '同一个照片请求标识不能上传不同内容')
                return receipt(existing)
            if session and session.status == 'completed':
                raise HTTPException(409, '已保存的回忆不能追加会话附件')
        output = io.BytesIO()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as picture:
                    if picture.format not in ('JPEG', 'PNG', 'WEBP'):
                        raise HTTPException(415, '图片格式不支持')
                    picture.load()
                    picture = ImageOps.exif_transpose(picture).convert('RGB')
                    picture.thumbnail((2560, 2560))
                    picture.save(output, 'JPEG', quality=88)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(415, '无法读取图片') from None
        jpeg = output.getvalue()
        if len(jpeg) > MAX_BYTES:
            raise HTTPException(413, '图片压缩后仍超过 8 MB')
        photo_store = storage()
        # Reserve durable cleanup before external I/O. If upload or the later
        # media transaction fails (even on a process crash), the worker can
        # reclaim the otherwise unreferenced local/OSS object.
        with SessionLocal.begin() as db:
            pending = db.get(MediaCleanupModel, str(request_id), with_for_update=True)
            if pending and pending.family_id != owner_family:
                raise HTTPException(409, '照片请求标识正在清理，请使用新的标识')
            if pending is None:
                db.add(MediaCleanupModel(id=str(request_id), family_id=owner_family))
        photo_store.put(request_id, jpeg)
        # On an uncertain commit outcome, never delete here: the database may
        # have committed before losing its response. Cleanup checks for a live
        # media row under the same media lock before touching either copy.
        with SessionLocal.begin() as db:
            asset = MediaAssetModel(id=str(request_id), memory_id=None, session_id=str(session_id) if session_id else None,
                                    editing_memory_id=str(editing_memory_id) if editing_memory_id else None,
                                    memoir_person_id=str(memoir_person_id) if memoir_person_id else None,
                                    type='image', file_url='/api/v1/media/' + str(request_id),
                                    original_filename=None, mime_type='image/jpeg', content_hash=digest)
            db.add(asset)
            db.flush()
            result = receipt(asset)
            pending = db.get(MediaCleanupModel, str(request_id))
            if pending is not None:
                db.delete(pending)
        return result


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
            from app.services.memory_maintenance import queue
            for asset in assets:
                if asset.id in ids:
                    queue(db, asset, session.family_id)
    from app.services.memory_maintenance import cleanup_after_request
    cleanup_after_request()
