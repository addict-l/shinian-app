"""Keep the member's welcome separate from deletable story segments."""
from uuid import uuid5, NAMESPACE_URL
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.chat_message import ChatMessageModel
from app.models.chat_session import ChatSessionModel

OPENING_SESSION_TYPE = 'conversation_opening'


def publish_prepared_opening(db, target):
    """Publish the prepared welcome exactly once, without any model call."""
    prepared = db.scalar(select(ChatSessionModel).where(
        ChatSessionModel.family_id == target.family_id,
        ChatSessionModel.primary_person_id == target.primary_person_id,
        ChatSessionModel.status == 'prepared').with_for_update())
    if prepared is None:
        return False
    message = db.scalar(select(ChatMessageModel).where(ChatMessageModel.session_id == prepared.id,
        ChatMessageModel.type == 'opening').with_for_update())
    if message is None:
        return False
    message.created_at = datetime.now(timezone.utc)
    message.session_id = target.id
    target.status = 'active'
    db.flush()
    if prepared.id != target.id:
        db.delete(prepared)
    return True


def preserve_opening(db, source_id):
    """Move only the initial welcome, in the caller's deletion transaction.

    Legacy welcomes have type=text. They must be the first message before any
    user input; an assistant reply after a user message is never a welcome.
    """
    source = db.get(ChatSessionModel, source_id, with_for_update=True)
    if source is None or source.primary_person_id is None:
        return
    opening = db.scalar(select(ChatMessageModel).where(ChatMessageModel.session_id == source_id)
        .order_by(ChatMessageModel.created_at, ChatMessageModel.id).limit(1).with_for_update())
    if opening is None or opening.role != 'assistant' or opening.type not in ('text', 'opening') or opening.attachments:
        return
    identity = str(uuid5(NAMESPACE_URL,
        f'ai-memories:opening:{source.family_id}:{source.primary_person_id}'))
    container = db.get(ChatSessionModel, identity, with_for_update=True)
    if container is None:
        container = ChatSessionModel(id=identity, family_id=source.family_id,
            primary_person_id=source.primary_person_id, title='聊天开场白',
            session_type=OPENING_SESSION_TYPE, status='archived', llm_model=source.llm_model,
            created_at=opening.created_at, updated_at=opening.created_at)
        db.add(container)
        db.flush()
    previous = db.scalar(select(ChatMessageModel).where(ChatMessageModel.session_id == identity)
        .order_by(ChatMessageModel.created_at, ChatMessageModel.id).limit(1).with_for_update())
    if previous is not None:
        if (previous.created_at, previous.id) <= (opening.created_at, opening.id):
            return
        db.delete(previous)
    opening.session_id = identity
    opening.type = 'opening'
    # Flush the move before the bulk delete of messages in the old segment.
    db.flush()
