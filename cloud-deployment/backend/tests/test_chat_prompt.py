from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.chat import ChatSession
from app.schemas.family import Family
from app.schemas.family_member import FamilyMember
from app.services.chat_service import ChatService
from app.services.family_member_service import FamilyMemberNotFoundError


def _make_session(
    *,
    family_id=None,
    primary_person_id=None,
) -> ChatSession:
    now = datetime.now(timezone.utc)
    return ChatSession(
        id=uuid4(),
        family_id=family_id or uuid4(),
        primary_person_id=primary_person_id,
        title="测试会话",
        session_type="memory_interview",
        status="active",
        llm_model="qwen-plus",
        created_at=now,
        updated_at=now,
    )


def test_build_system_prompt_includes_family_and_person():
    service = ChatService()

    family_id = uuid4()
    person_id = uuid4()
    chat_session = _make_session(
        family_id=family_id,
        primary_person_id=person_id,
    )

    service.family_service = MagicMock()
    service.family_service.get_family.return_value = Family(
        id=family_id,
        name="张家",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service.family_member_service = MagicMock()
    service.family_member_service.get_family_member.return_value = (
        FamilyMember(
            id=person_id,
            family_id=family_id,
            name="爷爷",
            relationship="祖父",
            birth_date=date(1940, 1, 1),
            created_at=datetime.now(timezone.utc),
        )
    )

    prompt = service._build_system_prompt(chat_session)

    assert "当前家庭：张家" in prompt
    assert "主要人物：爷爷" in prompt
    assert "祖父" in prompt
    assert "1940-01-01" in prompt
    assert "请优先围绕这位主要人物" in prompt


def test_build_system_prompt_without_primary_person():
    service = ChatService()
    family_id = uuid4()
    chat_session = _make_session(
        family_id=family_id,
        primary_person_id=None,
    )

    service.family_service = MagicMock()
    service.family_service.get_family.return_value = Family(
        id=family_id,
        name="李家",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    prompt = service._build_system_prompt(chat_session)

    assert "当前家庭：李家" in prompt
    assert "未指定主要人物" in prompt


def test_build_system_prompt_when_person_missing():
    service = ChatService()
    family_id = uuid4()
    person_id = uuid4()
    chat_session = _make_session(
        family_id=family_id,
        primary_person_id=person_id,
    )

    service.family_service = MagicMock()
    service.family_service.get_family.return_value = Family(
        id=family_id,
        name="王家",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service.family_member_service = MagicMock()
    service.family_member_service.get_family_member.side_effect = (
        FamilyMemberNotFoundError("gone")
    )

    prompt = service._build_system_prompt(chat_session)

    assert "主要人物记录已不存在" in prompt
