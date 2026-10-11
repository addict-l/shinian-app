"""Local single-worker workflow: durable messages, replayable requests and confirmed drafts."""
import hashlib
import threading
import weakref
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import or_, select
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
from app.schemas.story_guidance import GenerationOffer
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService
from app.services.conversation_opening import OPENING_SESSION_TYPE, publish_prepared_opening
from app.schemas.story_information import InformationStatus, StoryInformation
from app.services.story_guidance import (user_texts, validate_information, readiness, conversation_history, validate_analysis, validate_reply, reply_policy,
                                        draft_evidence, validate_draft, exact_date)

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

    def person_state(self, session_id):
        state = self.state(session_id)
        if state.session.primary_person_id is None:
            raise HTTPException(400, '请先选择家庭人物')
        state.current_message_ids = [message.id for message in state.messages]
        state.messages = self.chat.message_repository.recent_for_person(
            state.session.family_id, state.session.primary_person_id)
        return state

    def open_person(self, family_id, person_id):
        person = self.chat.family_member_service.get_family_member(person_id)
        if person.family_id != family_id:
            raise HTTPException(409, '人物不属于当前家庭')
        # The deployment has one worker; serialize by person across devices.
        # Sessions are internal story segments, never a user-facing conversation list.
        with serialized(f'person:{family_id}:{person_id}'):
            sessions = [value for value in self.chat.list_sessions(family_id)
                        if value.primary_person_id == person_id and value.session_type != OPENING_SESSION_TYPE]
            completed = next((value for value in sessions if value.status == 'completed'), None)
            active = [value for value in sessions if value.status != 'completed'
                      and (completed is None or value.updated_at > completed.updated_at)]
            # Prefer meaningful legacy dialogue over empty sessions left by prior launches.
            current = next((value for value in active if any(message.role == 'user'
                for message in self.chat.message_repository.list_by_session(value.id))), None)
            current = current or next((value for value in active if value.status != 'prepared'), None)
            current = current or (active[0] if active else None)
            if current is None:
                anchor = str(completed.id) if completed else 'initial'
                current = self.create_session(ChatSessionCreate(family_id=family_id,
                    primary_person_id=person_id, title=f'与{person.name}的回忆',
                    client_request_id=uuid5(NAMESPACE_URL, f'ai-memories:person:{family_id}:{person_id}:{anchor}')))
            history = self.chat.message_repository.recent_for_person(family_id, person_id)
            if not history:
                self.start(current.id)
            return self.person_state(current.id)

    def state(self, session_id):
        session = self.chat.get_session(session_id)
        messages = self.chat.message_repository.list_by_session(session_id)
        result = readiness(session.information, messages, session.primary_person_id, session.status == 'completed')
        latest_user = next((m for m in reversed(messages) if m.role == 'user'), None)
        progress = session.information.conversation
        # A failed reply never exposes an older offer or an apparently completed turn.
        replied = latest_user is None or (messages[-1].role == 'assistant')
        if not replied:
            result.ready = False
            result.needs_analysis = True
            result.message = '刚才的讲述已保留，请重试完成这一轮对话。'
        offer = progress.offer_message_id
        show_offer = (result.ready and replied and offer is not None and messages[-1].id == offer
                      and latest_user is not None and progress.replied_user_message_id == latest_user.id)
        return ChatState(session=session, messages=messages, can_generate=result.ready, readiness=result,
                         generation_offer=GenerationOffer(message_id=offer) if show_offer else None)

    def _record_subject(self, session):
        if session.primary_person_id is None:
            return {'name': '尚未选择', 'relationship': ''}
        person = self.chat.family_member_service.get_family_member(session.primary_person_id)
        return {'name': person.name, 'relationship': person.relationship}

    def _analyze(self, session, messages):
        question = ''
        transcript = []
        texts = user_texts(messages)
        for message in messages:
            if message.role == 'assistant' and message.type != 'notice':
                question = message.content
            elif message.id in texts:
                transcript.append({'id': str(message.id), 'content': message.content, 'question': question})
        analysis = self.chat._get_llm_client().analyze_story(
            transcript, self._record_subject(session), session.information)
        validate_analysis(analysis, [m for m in messages if m.id in texts])
        information = StoryInformation.model_validate(analysis.model_dump())
        information.conversation = session.information.conversation.model_copy(deep=True)
        information = validate_information(information, messages, session.information)
        return information, readiness(information, messages, session.primary_person_id), analysis

    def _ensure_analysis(self, session, messages):
        if set(user_texts(messages)) != set(session.information.analyzed_message_ids):
            information, _, _ = self._analyze(session, messages)
            with SessionLocal.begin() as db:
                model = db.get(ChatSessionModel, str(session.id))
                model.information = information.model_dump(mode='json')
                model.version += 1
                model.updated_at = datetime.now(timezone.utc)
            return self.chat.get_session(session.id)
        return session

    @staticmethod
    def _source_digest(raw, information):
        return hashlib.sha256((raw + '\n' + information.model_dump_json(exclude={'conversation'})).encode()).hexdigest()

    def start(self, session_id):
        session = self.chat.get_session(session_id)
        with serialized(f'person:{session.family_id}:{session.primary_person_id}'), serialized(session_id):
            state = self.state(session_id)
            if state.session.primary_person_id is not None:
                history = self.chat.message_repository.recent_for_person(state.session.family_id, state.session.primary_person_id)
                if history:
                    return state
                with SessionLocal.begin() as db:
                    target = db.get(ChatSessionModel, str(session_id), with_for_update=True)
                    published = publish_prepared_opening(db, target)
                if published:
                    return self.state(session_id)
            if not state.messages:
                subject = self._record_subject(state.session)
                reply = self.chat._get_llm_client().converse([], subject, state.session.information, state.readiness)
                policy = {'allowed': False, 'explicit_request': False}
                validate_reply(reply, [], policy)
                self.chat.message_repository.create(session_id, 'assistant', reply.text, message_type='opening')
            return self.state(session_id)

    def send(self, session_id, body):
        request_id = body.client_request_id or uuid4()
        assistant_id = uuid5(NAMESPACE_URL, 'ai-memories:reply:' + str(request_id))
        content = body.content.strip()
        attachment_ids = [str(value) for value in body.attachment_ids]
        with serialized(session_id):
            session = self.chat.get_session(session_id)
            with SessionLocal() as db:
                previous = db.get(ChatMessageModel, str(request_id))
                if previous and (previous.session_id != str(session_id) or previous.role != 'user' or previous.content != content
                                 or [asset.id for asset in previous.attachments] != attachment_ids):
                    raise HTTPException(409, '请求标识与已有消息不一致')
                # Check completed reply before session status, so a late retry replays correctly.
                if previous and db.get(ChatMessageModel, str(assistant_id)):
                    return self.state(session_id)
            if session.status == 'completed':
                raise HTTPException(409, '这段回忆已保存，请开始新的对话')
            if previous is None:
                with SessionLocal.begin() as db:
                    assets = [db.get(MediaAssetModel, media_id) for media_id in attachment_ids]
                    if any(asset is None or asset.session_id != str(session_id) or asset.message_id is not None for asset in assets):
                        raise HTTPException(409, '照片不存在、属于其他故事或已经发送，请重新加载')
                    db.add(ChatMessageModel(id=str(request_id), session_id=str(session_id), role='user',
                                            type='text' if content else 'media', content=content,
                                            created_at=datetime.now(timezone.utc)))
                    db.flush()
                    for position, asset in enumerate(assets):
                        asset.message_id = str(request_id)
                        asset.position = position
                    saved_session = db.get(ChatSessionModel, str(session_id))
                    saved_information = StoryInformation.model_validate(saved_session.information or {})
                    saved_information.conversation.offer_message_id = None
                    saved_session.information = saved_information.model_dump(mode='json')
                    saved_session.updated_at = datetime.now(timezone.utc)
                    saved_session.version += 1
            if not content:
                self.chat.message_repository.create(session_id, 'assistant',
                    '照片已保存，您可以继续讲讲与这些照片有关的故事。', message_id=assistant_id, message_type='notice')
                self.chat.session_repository.touch_updated_at(session_id)
                return self.state(session_id)
            messages = self.chat.message_repository.list_by_session(session_id)
            latest_user = next((m for m in reversed(messages) if m.role == 'user'), None)
            if latest_user is None or latest_user.id != request_id:
                raise HTTPException(409, '这条讲述后已有新内容，请以当前对话为准。')
            # A failed model call leaves the durable user message and the prior evidence intact.
            information, result, analysis = self._analyze(session, messages)
            explicit_request = getattr(analysis, 'generation_request', None) is not None
            history = conversation_history(messages)
            if session.primary_person_id is not None:
                current_ids = {message.id for message in messages}
                earlier = [message for message in self.chat.message_repository.recent_for_person(
                    session.family_id, session.primary_person_id) if message.id not in current_ids]
                if earlier:
                    # Previous messages provide conversational continuity only. Analysis,
                    # readiness and draft evidence above still use the full current segment.
                    history = conversation_history(earlier) + [{'id': 'current-story-boundary', 'role': 'system',
                        'content': '以上是同一人物较早的聊天，仅供自然承接；以下才是当前尚未保存的回忆。'
                                   '不得把较早故事混入当前草稿，也不要再次邀请整理已保存的故事。'}] + history
            policy = reply_policy(information, result, history, explicit_request)
            reply = self.chat._get_llm_client().converse(history, self._record_subject(session), information, result,
                getattr(analysis, 'guidance_hint', ''), explicit_request)
            validate_reply(reply, history, policy)
            progress = information.conversation
            progress.replied_user_message_id = request_id
            progress.offer_message_id = assistant_id if reply.action == 'offer_generation' else None
            if reply.action == 'offer_generation':
                # A requested first offer also ends future unsolicited reminders.
                progress.automatic_offer_used = True
            with SessionLocal.begin() as db:
                model = db.get(ChatSessionModel, str(session_id))
                model.information = information.model_dump(mode='json')
                model.updated_at = datetime.now(timezone.utc)
                model.version += 1
                db.add(ChatMessageModel(id=str(assistant_id), session_id=str(session_id), role='assistant',
                                        type='text', content=reply.text, created_at=datetime.now(timezone.utc)))
            return self.state(session_id)

    @staticmethod
    def _draft_response(model):
        return DraftResponse(id=model.id, session_id=model.session_id, revision=model.revision,
                             memory=MemoryCreate.model_validate(model.payload), saved_memory_id=model.saved_memory_id,
                             evidence=model.payload.get('_evidence'), manually_edited=model.payload.get('_manually_edited', False))

    def generate(self, session_id, expected_revision=None, replace_confirmed=False):
        with serialized(session_id):
            session = self.chat.get_session(session_id)
            if session.status == 'completed':
                raise HTTPException(409, '这段回忆已保存')
            if session.primary_person_id is None:
                raise HTTPException(400, '请先选择家庭人物')
            raw = self.memories._build_raw_content(session_id)
            if not raw:
                raise HTTPException(400, '请先讲述一段回忆')
            messages = self.chat.message_repository.list_by_session(session_id)
            if messages[-1].role == 'user':
                raise HTTPException(409, '刚才的讲述已保留，请先重试完成对话。')
            session = self._ensure_analysis(session, messages)
            result = readiness(session.information, messages, session.primary_person_id)
            if not result.ready:
                raise HTTPException(409, result.message)
            digest = self._source_digest(raw, session.information)
            with SessionLocal() as db:
                old = db.scalar(select(MemoryDraftModel).where(MemoryDraftModel.session_id == str(session_id)))
                if expected_revision is not None and (old is None or old.revision != str(expected_revision)):
                    raise HTTPException(409, '草稿已在其他设备更新，请读取最新版本；你的修改可以保留核对')
                if old and old.source_hash == digest and expected_revision is None:
                    return self._draft_response(old)
                if old and old.payload.get('_manually_edited') and not replace_confirmed:
                    raise HTTPException(409, '草稿包含手动修改，请确认后再重新生成')
                if session.status == 'completed':
                    raise HTTPException(409, '这段回忆已保存')
            evidence = draft_evidence(session.information, messages)
            composition = validate_draft(self.memories._get_llm_client().compose_story(
                evidence, self._record_subject(session), session.information), evidence, self._record_subject(session), session.information)
            # Link only family names/relationships that occur in accepted user excerpts.
            accepted = '\n'.join(item['content'] for item in evidence)
            members = self.memories.family_member_service.list_family_members(session.family_id)
            names = [name for member in members for name in (member.name, member.relationship) if name and name in accepted]
            people = self.memories._match_people_to_member_ids(session.family_id, names, session.primary_person_id)
            payload = MemoryCreate(family_id=session.family_id, person_ids=people, title=composition.title.text,
                                   primary_person_id=session.primary_person_id,
                                   information=session.information, raw_content=raw,
                                   summary='\n\n'.join(paragraph.text for paragraph in composition.paragraphs),
                                   memory_date=exact_date(session.information),
                                   location=session.information.place.value if session.information.place.status in
                                       (InformationStatus.known, InformationStatus.approximate) else None)
            self.memories._validate_create(payload)
            with SessionLocal.begin() as db:
                draft = db.scalar(select(MemoryDraftModel).where(MemoryDraftModel.session_id == str(session_id)))
                if draft is None:
                    draft = MemoryDraftModel(session_id=str(session_id))
                    db.add(draft)
                draft.revision = str(uuid4())
                draft.source_hash = digest
                draft.payload = {**payload.model_dump(mode='json'), '_evidence': composition.model_dump(mode='json')}
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
            current = self.chat.get_session(session_id)
            with SessionLocal.begin() as db:
                draft = db.get(MemoryDraftModel, str(draft_id), with_for_update=True)
                if draft is None:
                    raise HTTPException(404, '草稿不存在')
                if draft.revision != str(revision):
                    raise HTTPException(409, '草稿已更新，请重新预览')
                if draft.saved_memory_id:
                    memory_id = draft.saved_memory_id
                else:
                    if draft.source_hash != self._source_digest(raw, current.information):
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
                    # New uploads join a saved story only after the user sends their message.
                    # Preserve legacy session photos created before message attachment identities.
                    for media in db.scalars(select(MediaAssetModel).where(
                            MediaAssetModel.session_id == str(session_id),
                            or_(MediaAssetModel.message_id.is_not(None), MediaAssetModel.content_hash.is_(None)))):
                        media.memory_id = memory_id
                    draft.saved_memory_id = memory_id
                    session = db.get(ChatSessionModel, str(session_id))
                    session.status = 'completed'
                    session.updated_at = datetime.now(timezone.utc)
            return self.memories.get_memory(UUID(memory_id))

    def get_draft(self, draft_id):
        with SessionLocal() as db:
            draft = db.get(MemoryDraftModel, str(draft_id))
            if draft is None:
                raise HTTPException(404, '草稿不存在')
            return self._draft_response(draft)

    def edit_draft(self, draft_id, body):
        current = self.get_draft(draft_id)
        with serialized(current.session_id):
            session = self.chat.get_session(current.session_id)
            raw = self.memories._build_raw_content(current.session_id)
            with SessionLocal.begin() as db:
                draft = db.get(MemoryDraftModel, str(draft_id), with_for_update=True)
                if draft is None:
                    raise HTTPException(404, '草稿不存在')
                if draft.revision != str(body.revision):
                    raise HTTPException(409, '草稿已在其他设备更新，请读取最新版本；你的修改可以保留核对')
                if draft.saved_memory_id or session.status == 'completed':
                    raise HTTPException(409, '草稿已保存，请到回忆详情编辑')
                if draft.source_hash != self._source_digest(raw, session.information):
                    raise HTTPException(409, '对话已有新内容，请核对后重新生成；你的修改仍可保留')
                title, summary = body.title.strip(), body.summary.strip()
                if not title or not summary:
                    raise HTTPException(422, '标题和正文不能为空')
                draft.payload = {**draft.payload, 'title': title, 'summary': summary, '_manually_edited': True,
                    '_original_evidence': draft.payload.get('_original_evidence') or draft.payload.get('_evidence'), '_evidence': None}
                draft.revision = str(uuid4())
                db.flush()
                return self._draft_response(draft)

    def regenerate_draft(self, draft_id, body):
        current = self.get_draft(draft_id)
        if not body.replace_confirmed:
            raise HTTPException(409, '请确认重新生成会替换当前标题和正文')
        return self.generate(current.session_id, body.revision, body.replace_confirmed)
