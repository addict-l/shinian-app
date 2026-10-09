from uuid import UUID

from app.ai.llm_client import LLMClient
from app.repositories.chat_message_repository import (
    ChatMessageRepository,
)
from app.repositories.chat_session_repository import (
    ChatSessionRepository,
)
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import Memory, MemoryCreate
from app.services.family_member_service import FamilyMemberService
from app.services.family_service import FamilyService


class MemoryNotFoundError(Exception):
    pass


class ChatSessionNotFoundError(Exception):
    """生成回忆时找不到来源会话。"""
    pass


class InvalidFamilyMemberError(Exception):
    """人物不属于该家庭。"""
    pass


class DuplicateFamilyMemberError(Exception):
    """person_ids 中存在重复家庭成员。"""
    pass


class EmptyChatMemoryError(Exception):
    """会话中没有用户说的话。"""
    pass


class MemoryAlreadyCreatedError(Exception):
    """回忆已存在。"""
    pass


class MissingPrimaryPersonError(Exception):
    """会话未指定主要人物，无法生成回忆。"""
    pass


class MemoryService:

    def __init__(self) -> None:
        self.repository = MemoryRepository()

        self.chat_session_repository = (
            ChatSessionRepository()
        )

        self.chat_message_repository = (
            ChatMessageRepository()
        )

        self.family_service = FamilyService()
        self.family_member_service = FamilyMemberService()
        self._llm_client: LLMClient | None = None

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def create_memory(
        self,
        memory: MemoryCreate,
    ) -> Memory:
        """
        业务规则：
        1. family_id 对应的家庭必须存在
        2. person_ids 不能有重复
        3. person_ids 里每个人必须存在
        4. 这些人必须都属于同一个 family_id
        通过后交给 repository 写 memories + memory_persons
        """
        self._validate_create(memory)
        return self.repository.create(memory)

    def _validate_create(
        self,
        memory: MemoryCreate,
    ) -> None:
        # 1) 家庭是否存在（不存在会抛 FamilyNotFoundError）
        self.family_service.get_family(memory.family_id)

        # 2) person_ids 不能重复
        if len(memory.person_ids) != len(set(memory.person_ids)):
            raise DuplicateFamilyMemberError(
                "person_ids 中存在重复家庭成员"
            )

        # 3) 每个人是否存在，且属于这个家庭
        for person_id in memory.person_ids:
            person = self.family_member_service.get_family_member(
                person_id
            )

            if person.family_id != memory.family_id:
                raise InvalidFamilyMemberError(
                    f"成员 {person_id} 不属于家庭 {memory.family_id}"
                )

    def get_memory(
        self,
        memory_id: UUID,
    ) -> Memory:
        memory = self.repository.get(memory_id)
        if memory is None:
            raise MemoryNotFoundError(
                f"回忆不存在：{memory_id}"
            )
        return memory

    def list_memories(
        self,
        family_id: UUID | None = None,
    ) -> list[Memory]:
        return self.repository.list(family_id)

    def _build_raw_content(
        self,
        chat_session_id: UUID,
    ) -> str:

        messages = (
            self.chat_message_repository
            .list_by_session(chat_session_id)
        )

        user_contents: list[str] = []
        for message in messages:
            # 只要用户说的话；助手追问不写进回忆正文
            if message.role != "user":
                continue

            text = message.content.strip()
            if not text:
                continue

            user_contents.append(text)

        return "\n".join(user_contents)

    def create_from_chat_session(
        self,
        session_id: UUID,
    ) -> Memory:

        # 1. Session 必须存在
        chat_session = (
            self.chat_session_repository
            .get(session_id)
        )

        if chat_session is None:
            raise ChatSessionNotFoundError(
                f"会话不存在：{session_id}"
            )

        # 2. 不能重复生成
        existing_memory = (
            self.repository
            .get_by_source_session(session_id)
        )

        if existing_memory is not None:
            raise MemoryAlreadyCreatedError(
                "该会话已经生成过回忆"
            )

        # 3. 组合用户原始内容
        raw_content = self._build_raw_content(
            session_id
        )

        if not raw_content:
            raise EmptyChatMemoryError(
                "该会话没有用户消息"
            )

        # 4. 必须有主要人物（回忆至少关联一个人）
        if chat_session.primary_person_id is None:
            raise MissingPrimaryPersonError(
                "该会话未指定主要人物，无法生成回忆"
            )

        # 5. 调 LLM
        extraction = (
        self._get_llm_client()
        .extract_memory(raw_content)
        )

        person_ids = (
        self._match_people_to_member_ids(
        family_id=chat_session.family_id,
        people=extraction.people,
        primary_person_id=(
            chat_session.primary_person_id
        ),
    )
)


        # 6. 构造 MemoryCreate
        memory_create = MemoryCreate(
            family_id=chat_session.family_id,
            person_ids=person_ids,
            title=extraction.title,
            raw_content=raw_content,
            summary=extraction.summary,
            memory_date=extraction.memory_date,
            location=extraction.location,
        )

        # 7. 保存
        return self.repository.create(
            memory_create,
            source_session_id=session_id,
        )


    def _normalize_person_text(
    self,
    value: str,
) -> str:
        return value.strip().lower()


    def _match_people_to_member_ids(
    self,
    family_id: UUID,
    people: list[str],
    primary_person_id: UUID,
) -> list[UUID]:

        members = (
            self.family_member_service
            .list_family_members(family_id)
        )

        result: list[UUID] = [
            primary_person_id
        ]

        seen = {
            primary_person_id
        }

        for person_text in people:

            target = self._normalize_person_text(
                person_text
            )

            matches = []

            for member in members:

                member_name = (
                    self._normalize_person_text(
                        member.name
                    )
                )

                relationship = (
                    self._normalize_person_text(
                        member.relationship
                    )
                )

                if (
                    target == member_name
                    or target == relationship
                ):
                    matches.append(member)

            # 只有唯一匹配时才自动建立关系
            if len(matches) != 1:
                continue

            member_id = matches[0].id

            if member_id in seen:
                continue

            result.append(member_id)
            seen.add(member_id)

        return result
