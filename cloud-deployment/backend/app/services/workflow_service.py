"""Local single-worker workflow: durable messages, replayable requests and confirmed drafts."""
import hashlib
import threading
import weakref
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.chat_message import ChatMessageModel
from app.models.chat_session import ChatSessionModel
from app.models.memory import MemoryModel
from app.models.memory_person import MemoryPersonModel
from app.models.memory_draft import MemoryDraftModel
from app.models.media_asset import MediaAssetModel
from app.schemas.chat import ChatSessionCreate
from app.schemas.memory import MemoryCreate
from app.schemas.workflow import ChatState, DraftResponse
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService

_lock_guard = threading.Lock()
_locks = weakref.WeakValueDictionary()

@contextmanager
def serialized(key):
    # Launch configuration intentionally runs ONE worker. Different sessions remain concurrent.
    with _lock_guard:
        lock = _locks.get(str(key))
        if lock is None:
            lock = threading.RLock()
            _locks[str(key)] = lock
    with lock:
        yield

class WorkflowService:
    def __init__(self):
        self.chat = ChatService()
        self.memories = MemoryService()

    def create_session(self, data: ChatSessionCreate):
        key = data.client_request_id or uuid4()
        with serialized(key):
            existing = self.chat.session_repository.get(key)
            if existing:
                if (existing.family_id, existing.primary_person_id, existing.title) != (data.family_id, data.primary_person_id, data.title):
                    raise HTTPException(409, '同一个请求标识不能创建不同会话')
                return existing
            return self.chat.create_session(data)

    def state(self, session_id):
        session = self.chat.get_session(session_id)
        messages = self.chat.message_repository.list_by_session(session_id)
        return ChatState(session=session, messages=messages,
                         can_generate=session.status != 'completed' and any(m.role == 'user' and m.content.strip() for m in messages))

    def start(self, session_id):
        with serialized(session_id):
            state = self.state(session_id)
            if not state.messages:
                content = self.chat._get_llm_client().chat([
                    {'role':'system','content':self.chat._build_system_prompt(state.session)},
                    {'role':'user','content':'请提出一个简短、自然的开场问题，引导我讲述关于这位家人的真实回忆。不要代替我回答。'}])
                self.chat.message_repository.create(session_id, 'assistant', content)
            return self.state(session_id)

    def send(self, session_id, body):
        request_id = body.client_request_id or uuid4()
        assistant_id = uuid5(NAMESPACE_URL, 'ai-memories:reply:' + str(request_id))
        content = body.content.strip()
        if not content:
            raise HTTPException(422, '消息不能为空')
        with serialized(session_id):
            session = self.chat.get_session(session_id)
            with SessionLocal() as db:
                previous = db.get(ChatMessageModel, str(request_id))
                if previous and (previous.session_id != str(session_id) or previous.role != 'user' or previous.content != content):
                    raise HTTPException(409, '请求标识与已有消息不一致')
                # Check completed reply before session status, so a late retry replays correctly.
                if previous and db.get(ChatMessageModel, str(assistant_id)):
                    return self.state(session_id)
            if session.status == 'completed':
                raise HTTPException(409, '这段回忆已保存，请开始新的对话')
            if previous is None:
                self.chat.message_repository.create(session_id, 'user', content, message_id=request_id)
            messages = self.chat.message_repository.list_by_session(session_id)
            prompt = self.chat._build_system_prompt(session)
            prompt += '\n图片目前仅作为附件保存；你不能声称看见照片中的内容。用户可随时选择生成回忆，无须固定问满几轮。'
            response = self.chat._get_llm_client().chat(
                [{'role':'system','content':prompt}] + [{'role':m.role,'content':m.content} for m in messages])
            self.chat.message_repository.create(session_id, 'assistant', response, message_id=assistant_id)
            self.chat.session_repository.touch_updated_at(session_id)
            return self.state(session_id)

    @staticmethod
    def _draft_response(model):
        return DraftResponse(id=model.id, session_id=model.session_id, revision=model.revision,
                             memory=MemoryCreate.model_validate(model.payload), saved_memory_id=model.saved_memory_id)

    def generate(self, session_id):
        with serialized(session_id):
            session = self.chat.get_session(session_id)
            if session.primary_person_id is None:
                raise HTTPException(400, '请先选择家庭人物')
            raw = self.memories._build_raw_content(session_id)
            if not raw:
                raise HTTPException(400, '请先讲述一段回忆')
            digest = hashlib.sha256(raw.encode()).hexdigest()
            with SessionLocal() as db:
                old = db.scalar(select(MemoryDraftModel).where(MemoryDraftModel.session_id == str(session_id)))
                if old and old.source_hash == digest:
                    return self._draft_response(old)
                if session.status == 'completed':
                    raise HTTPException(409, '这段回忆已保存')
            extraction = self.memories._get_llm_client().extract_memory(raw)
            people = self.memories._match_people_to_member_ids(session.family_id, extraction.people, session.primary_person_id)
            payload = MemoryCreate(family_id=session.family_id, person_ids=people, title=extraction.title,
                                   primary_person_id=session.primary_person_id,
                                   raw_content=raw, summary=extraction.summary, memory_date=extraction.memory_date, location=extraction.location)
            self.memories._validate_create(payload)
            with SessionLocal.begin() as db:
                draft = db.scalar(select(MemoryDraftModel).where(MemoryDraftModel.session_id == str(session_id)))
                if draft is None:
                    draft = MemoryDraftModel(session_id=str(session_id))
                    db.add(draft)
                draft.revision = str(uuid4())
                draft.source_hash = digest
                draft.payload = payload.model_dump(mode='json')
                db.flush()
                result = self._draft_response(draft)
            return result

    def confirm(self, draft_id, revision):
        with SessionLocal() as db:
            draft = db.get(MemoryDraftModel, str(draft_id))
            if draft is None:
                raise HTTPException(404, '草稿不存在')
            session_id = UUID(draft.session_id)
        with serialized(session_id):
            raw = self.memories._build_raw_content(session_id)
            with SessionLocal.begin() as db:
                draft = db.get(MemoryDraftModel, str(draft_id), with_for_update=True)
                if draft.revision != str(revision):
                    raise HTTPException(409, '草稿已更新，请重新预览')
                if draft.saved_memory_id:
                    memory_id = draft.saved_memory_id
                else:
                    if draft.source_hash != hashlib.sha256(raw.encode()).hexdigest():
                        raise HTTPException(409, '对话已有新内容，请重新生成回忆')
                    data = MemoryCreate.model_validate(draft.payload)
                    self.memories._validate_create(data)
                    existing = db.scalar(select(MemoryModel).where(MemoryModel.source_session_id == str(session_id)))
                    if existing:
                        memory_id = existing.id
                    else:
                        now = datetime.now(timezone.utc)
                        model = MemoryModel(family_id=str(data.family_id), source_session_id=str(session_id),
                            primary_person_id=str(data.primary_person_id) if data.primary_person_id else None,
                            information=data.information.model_dump(mode='json'),
                            title=data.title, raw_content=data.raw_content, summary=data.summary,
                            memory_date=data.memory_date, location=data.location, created_at=now, updated_at=now)
                        db.add(model)
                        db.flush()
                        memory_id = model.id
                        for person_id in data.person_ids:
                            db.add(MemoryPersonModel(memory_id=memory_id, family_member_id=str(person_id)))
                    for media in db.scalars(select(MediaAssetModel).where(MediaAssetModel.session_id == str(session_id))):
                        media.memory_id = memory_id
                    draft.saved_memory_id = memory_id
                    session = db.get(ChatSessionModel, str(session_id))
                    session.status = 'completed'
                    session.updated_at = datetime.now(timezone.utc)
            return self.memories.get_memory(UUID(memory_id))
