"""Read a consistent book snapshot; optimistic settings writes never change stories."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.models.memory import MemoryModel
from app.models.media_asset import MediaAssetModel
from app.models.memoir import MemoirSettingsModel
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memoir import MemoirSettings, MemoirSnapshot
from app.services.workflow_service import serialized


def owned_person(db, family_id, person_id, lock=False):
    person = db.get(FamilyMemberModel, str(person_id), with_for_update=lock)
    if person is None or person.family_id != str(family_id):
        raise HTTPException(404, '人物不存在')
    return person


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def snapshot(family_id, person_id):
    with SessionLocal() as db:
        person = owned_person(db, family_id, person_id)
        book = db.get(MemoirSettingsModel, str(person_id))
        settings = MemoirSettings.model_validate(book.settings) if book else MemoirSettings(title=f'{person.name}的回忆录')
        # Primary authorship, not the many-to-many list of people appearing in a story.
        models = list(db.scalars(select(MemoryModel).where(MemoryModel.family_id == str(family_id),
            MemoryModel.primary_person_id == str(person_id)).order_by(MemoryModel.created_at, MemoryModel.id)))
        stories = [MemoryRepository._to_schema(model) for model in models]
        photo_hashes = [(a.id, a.content_hash) for model in models for a in model.media_assets]
        active_limit = {'text': 0, 'photo': 1, 'collage': 3}[settings.cover_template]
        for photo in settings.cover_photos[:active_limit]:
            asset = db.get(MediaAssetModel, str(photo.id))
            photo_hashes.append((str(photo.id), asset.content_hash if asset else None))
        version = book.version if book else 0
        revision = digest({'person': person.name, 'version': version, 'settings': settings.model_dump(mode='json', by_alias=True),
                           'stories': [s.model_dump(mode='json') for s in stories], 'photos': sorted(photo_hashes)})
        return MemoirSnapshot(person_id=person_id, person_name=person.name, version=version,
                              settings=settings, stories=stories, content_revision=revision)


def update(family_id, person_id, body):
    values = body.settings.model_dump(mode='json', by_alias=True)
    request_hash = digest({'version': body.version, 'settings': values})
    with serialized('memoir:' + str(person_id)), SessionLocal.begin() as db:
        owned_person(db, family_id, person_id, lock=True)
        book = db.get(MemoirSettingsModel, str(person_id), with_for_update=True)
        if book and book.request_id == str(body.request_id):
            if book.request_hash != request_hash:
                raise HTTPException(409, '同一保存标识不能用于不同设置')
        else:
            if (book.version if book else 0) != body.version:
                raise HTTPException(409, '回忆录已在另一设备调整，本机设置已保留，请选择使用哪个版本')
            previous = MemoirSettings.model_validate(book.settings) if book else None
            previous_limit = {'text': 0, 'photo': 1, 'collage': 3}[previous.cover_template] if previous else 0
            old_photos = {(p.id, p.source_memory_id) for p in previous.cover_photos[:previous_limit]} if previous else set()
            active_limit = {'text': 0, 'photo': 1, 'collage': 3}[body.settings.cover_template]
            for photo in body.settings.cover_photos[:active_limit]:
                # Existing references may become invalid after source deletion. Keep
                # them visible for replacement; reject newly attached foreign assets.
                if (photo.id, photo.source_memory_id) in old_photos:
                    continue
                asset = db.get(MediaAssetModel, str(photo.id))
                if photo.source_memory_id:
                    memory = db.get(MemoryModel, str(photo.source_memory_id))
                    valid = memory and memory.family_id == str(family_id) and memory.primary_person_id == str(person_id) and asset and asset.memory_id == memory.id
                else:
                    valid = asset and asset.memoir_person_id == str(person_id)
                if not valid:
                    raise HTTPException(422, '封面照片不存在或属于其他人物，请重新选择')
            if book is None:
                book = MemoirSettingsModel(person_id=str(person_id), family_id=str(family_id), version=0)
                db.add(book)
            book.version += 1
            book.settings, book.request_id, book.request_hash = values, str(body.request_id), request_hash
    return snapshot(family_id, person_id)
