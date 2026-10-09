import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatMessage, ChatSession
from app.schemas.family_member import FamilyMember
from app.schemas.memory import Memory, MemoryCreate, MemoryExtraction
from app.services.memory_service import (
    DuplicateFamilyMemberError,
    InvalidFamilyMemberError,
    MemoryService,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _member(
    family_id: UUID,
    name: str,
    relationship: str,
    member_id: UUID | None = None,
) -> FamilyMember:
    return FamilyMember(
        id=member_id or uuid4(),
        family_id=family_id,
        name=name,
        relationship=relationship,
        birth_date=None,
        created_at=_now(),
    )


def _match_service(members: list[FamilyMember]) -> MemoryService:
    service = MemoryService()
    service.family_member_service = MagicMock()
    service.family_member_service.list_family_members.return_value = members
    return service


def test_memory_create_schema_rejects_empty_person_ids():
    with pytest.raises(ValidationError):
        MemoryCreate(
            family_id=uuid4(),
            person_ids=[],
            title="一条回忆",
            raw_content="内容",
        )


def test_create_memory_rejects_duplicate_person_ids():
    service = MemoryService()
    service.family_service = MagicMock()
    service.family_member_service = MagicMock()
    service.repository = MagicMock()

    family_id = uuid4()
    person_id = uuid4()

    with pytest.raises(DuplicateFamilyMemberError):
        service.create_memory(
            MemoryCreate(
                family_id=family_id,
                person_ids=[person_id, person_id],
                title="一条回忆",
                raw_content="内容",
            )
        )

    service.repository.create.assert_not_called()


def test_create_memory_rejects_person_from_other_family():
    service = MemoryService()
    service.family_service = MagicMock()
    service.family_member_service = MagicMock()
    service.repository = MagicMock()

    family_id = uuid4()
    other_family_id = uuid4()
    person_id = uuid4()

    service.family_member_service.get_family_member.return_value = (
        FamilyMember(
            id=person_id,
            family_id=other_family_id,
            name="外人",
            relationship="朋友",
            birth_date=None,
            created_at=datetime.now(timezone.utc),
        )
    )

    with pytest.raises(InvalidFamilyMemberError):
        service.create_memory(
            MemoryCreate(
                family_id=family_id,
                person_ids=[person_id],
                title="一条回忆",
                raw_content="内容",
            )
        )

    service.repository.create.assert_not_called()


def test_create_memory_ok_when_validation_passes():
    service = MemoryService()
    service.family_service = MagicMock()
    service.family_member_service = MagicMock()
    service.repository = MagicMock()

    family_id = uuid4()
    person_id = uuid4()
    now = datetime.now(timezone.utc)

    service.family_member_service.get_family_member.return_value = (
        FamilyMember(
            id=person_id,
            family_id=family_id,
            name="爷爷",
            relationship="祖父",
            birth_date=None,
            created_at=now,
        )
    )
    service.repository.create.return_value = Memory(
        id=uuid4(),
        family_id=family_id,
        person_ids=[person_id],
        source_session_id=None,
        title="一条回忆",
        raw_content="内容",
        summary=None,
        memory_date=None,
        location=None,
        created_at=now,
        updated_at=now,
    )

    result = service.create_memory(
        MemoryCreate(
            family_id=family_id,
            person_ids=[person_id],
            title="一条回忆",
            raw_content="内容",
        )
    )

    assert result.title == "一条回忆"
    service.repository.create.assert_called_once()


def test_match_people_keeps_primary_when_people_empty():
    family_id = uuid4()
    primary_id = uuid4()
    service = _match_service([
        _member(family_id, "张建国", "爷爷", primary_id),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=[],
        primary_person_id=primary_id,
    )

    assert result == [primary_id]


def test_match_people_by_unique_name():
    family_id = uuid4()
    primary_id = uuid4()
    grandpa_id = uuid4()
    service = _match_service([
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "张建国", "爷爷", grandpa_id),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["张建国"],
        primary_person_id=primary_id,
    )

    assert result == [primary_id, grandpa_id]


def test_match_people_by_unique_relationship():
    family_id = uuid4()
    primary_id = uuid4()
    grandma_id = uuid4()
    service = _match_service([
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "李秀英", "奶奶", grandma_id),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["奶奶"],
        primary_person_id=primary_id,
    )

    assert result == [primary_id, grandma_id]


def test_match_people_normalizes_whitespace_and_case():
    family_id = uuid4()
    primary_id = uuid4()
    grandpa_id = uuid4()
    service = _match_service([
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "Zhang", "grandpa", grandpa_id),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["  ZHANG  ", " Grandpa "],
        primary_person_id=primary_id,
    )

    assert result == [primary_id, grandpa_id]


def test_match_people_skips_ambiguous_relationship():
    family_id = uuid4()
    primary_id = uuid4()
    service = _match_service([
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "张大", "叔叔"),
        _member(family_id, "张二", "叔叔"),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["叔叔"],
        primary_person_id=primary_id,
    )

    assert result == [primary_id]


def test_match_people_skips_unknown_person():
    family_id = uuid4()
    primary_id = uuid4()
    service = _match_service([
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "张建国", "爷爷"),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["隔壁老王"],
        primary_person_id=primary_id,
    )

    assert result == [primary_id]


def test_match_people_deduplicates_primary_person():
    family_id = uuid4()
    primary_id = uuid4()
    grandma_id = uuid4()
    service = _match_service([
        _member(family_id, "张建国", "爷爷", primary_id),
        _member(family_id, "李秀英", "奶奶", grandma_id),
    ])

    result = service._match_people_to_member_ids(
        family_id=family_id,
        people=["爷爷", "张建国", "奶奶"],
        primary_person_id=primary_id,
    )

    assert result == [primary_id, grandma_id]


def test_create_from_chat_session_attaches_uniquely_matched_people():
    service = MemoryService()
    service.chat_session_repository = MagicMock()
    service.chat_message_repository = MagicMock()
    service.family_member_service = MagicMock()
    service.repository = MagicMock()
    service._llm_client = MagicMock()

    family_id = uuid4()
    session_id = uuid4()
    primary_id = uuid4()
    grandpa_id = uuid4()
    grandma_id = uuid4()
    uncle_a_id = uuid4()
    uncle_b_id = uuid4()
    now = _now()

    chat_session = ChatSession(
        id=session_id,
        family_id=family_id,
        primary_person_id=primary_id,
        title="童年回忆",
        session_type="memory_interview",
        status="active",
        llm_model="qwen-plus",
        created_at=now,
        updated_at=now,
    )
    user_message = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role="user",
        type="text",
        content="小时候爷爷奶奶带我去公园，叔叔也在。",
        created_at=now,
    )
    assistant_message = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role="assistant",
        type="text",
        content="哪个公园？",
        created_at=now,
    )
    extraction = MemoryExtraction(
        title="去公园",
        summary="爷爷奶奶带我去公园",
        memory_date=None,
        location="公园",
        people=["爷爷", "李秀英", "叔叔", "隔壁老王"],
    )
    members = [
        _member(family_id, "小明", "孙子", primary_id),
        _member(family_id, "张建国", "爷爷", grandpa_id),
        _member(family_id, "李秀英", "奶奶", grandma_id),
        _member(family_id, "张大", "叔叔", uncle_a_id),
        _member(family_id, "张二", "叔叔", uncle_b_id),
    ]

    service.chat_session_repository.get.return_value = chat_session
    service.repository.get_by_source_session.return_value = None
    service.chat_message_repository.list_by_session.return_value = [
        user_message,
        assistant_message,
    ]
    service._llm_client.extract_memory.return_value = extraction
    service.family_member_service.list_family_members.return_value = members

    def fake_create(
        data: MemoryCreate,
        source_session_id=None,
    ) -> Memory:
        return Memory(
            id=uuid4(),
            family_id=data.family_id,
            person_ids=list(data.person_ids),
            source_session_id=source_session_id,
            title=data.title,
            raw_content=data.raw_content,
            summary=data.summary,
            memory_date=data.memory_date,
            location=data.location,
            created_at=now,
            updated_at=now,
        )

    service.repository.create.side_effect = fake_create

    result = service.create_from_chat_session(session_id)

    create_kwargs = service.repository.create.call_args
    memory_create = create_kwargs.args[0]

    input_payload = {
        "chat_session": chat_session.model_dump(mode="json"),
        "messages": [
            user_message.model_dump(mode="json"),
            assistant_message.model_dump(mode="json"),
        ],
        "llm_extraction": extraction.model_dump(mode="json"),
        "family_members": [
            member.model_dump(mode="json") for member in members
        ],
        "memory_create_written_to_db": memory_create.model_dump(mode="json"),
        "source_session_id": str(
            create_kwargs.kwargs["source_session_id"]
        ),
    }
    output_payload = {
        "type": "Memory",
        "data": result.model_dump(mode="json"),
    }

    print("\n===== 真实输入 =====")
    print(json.dumps(input_payload, ensure_ascii=False, indent=2))
    print("\n===== 创建后返回的 Memory 原始数据 =====")
    print(json.dumps(output_payload, ensure_ascii=False, indent=2))

    assert memory_create.person_ids == [
        primary_id,
        grandpa_id,
        grandma_id,
    ]
    assert create_kwargs.kwargs["source_session_id"] == session_id
    assert result.person_ids == [primary_id, grandpa_id, grandma_id]
    service.family_member_service.list_family_members.assert_called_once_with(
        family_id
    )
