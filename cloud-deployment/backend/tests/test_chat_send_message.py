from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.ai.llm_client import LLMServiceError
from app.schemas.chat import ChatMessage, ChatSession
from app.services.chat_service import ChatService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session() -> ChatSession:
    return ChatSession(
        id=uuid4(),
        family_id=uuid4(),
        primary_person_id=None,
        title="测试",
        session_type="memory_interview",
        status="active",
        llm_model="qwen-plus",
        created_at=_now(),
        updated_at=_now(),
    )


def _user_message(session_id, content: str) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role="user",
        type="text",
        content=content,
        created_at=_now(),
    )


def _assistant_message(session_id, content: str) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role="assistant",
        type="text",
        content=content,
        created_at=_now(),
    )


def _build_service() -> ChatService:
    service = ChatService()
    service.session_repository = MagicMock()
    service.message_repository = MagicMock()
    service.family_service = MagicMock()
    service.family_member_service = MagicMock()
    service._llm_client = MagicMock()
    service._build_system_prompt = MagicMock(
        return_value="system prompt"
    )
    return service


def test_send_message_reuses_orphan_user_on_retry():
    service = _build_service()
    chat_session = _session()
    content = "小时候爷爷带我去公园"

    orphan = _user_message(chat_session.id, content)
    assistant = _assistant_message(chat_session.id, "哪个公园？")

    service.session_repository.get.return_value = chat_session
    # 第一次读：末尾是孤儿 user；第二次读：仍是这条 user（拼 prompt）
    service.message_repository.list_by_session.side_effect = [
        [orphan],
        [orphan],
    ]
    service._llm_client.chat.return_value = "哪个公园？"
    service.message_repository.create.return_value = assistant

    reply = service.send_message(chat_session.id, content)

    # 不应再 create user，只 create assistant
    create_calls = service.message_repository.create.call_args_list
    assert len(create_calls) == 1
    assert create_calls[0].kwargs["role"] == "assistant"
    assert reply.user_message.id == orphan.id
    assert reply.assistant_message.content == "哪个公园？"
    service.session_repository.touch_updated_at.assert_called_once_with(
        chat_session.id
    )


def test_send_message_creates_user_when_last_is_assistant():
    service = _build_service()
    chat_session = _session()
    content = "新的一句"

    previous_assistant = _assistant_message(
        chat_session.id,
        "上一轮回复",
    )
    new_user = _user_message(chat_session.id, content)
    new_assistant = _assistant_message(
        chat_session.id,
        "新的追问",
    )

    service.session_repository.get.return_value = chat_session
    service.message_repository.list_by_session.side_effect = [
        [previous_assistant],
        [previous_assistant, new_user],
    ]
    service.message_repository.create.side_effect = [
        new_user,
        new_assistant,
    ]
    service._llm_client.chat.return_value = "新的追问"

    reply = service.send_message(chat_session.id, content)

    create_calls = service.message_repository.create.call_args_list
    assert create_calls[0].kwargs["role"] == "user"
    assert create_calls[1].kwargs["role"] == "assistant"
    assert reply.user_message.content == content


def test_send_message_keeps_user_when_llm_fails():
    service = _build_service()
    chat_session = _session()
    content = "这句话要留下来"

    new_user = _user_message(chat_session.id, content)

    service.session_repository.get.return_value = chat_session
    service.message_repository.list_by_session.side_effect = [
        [],
        [new_user],
    ]
    service.message_repository.create.return_value = new_user
    service._llm_client.chat.side_effect = LLMServiceError(
        "LLM request failed"
    )

    with pytest.raises(LLMServiceError):
        service.send_message(chat_session.id, content)

    # user 已写入；assistant 未写；不 touch updated_at
    service.message_repository.create.assert_called_once()
    assert (
        service.message_repository.create.call_args.kwargs["role"]
        == "user"
    )
    service.session_repository.touch_updated_at.assert_not_called()
    service.message_repository.delete.assert_not_called()
