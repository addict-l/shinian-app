import os
from uuid import UUID

from app.ai.llm_client import LLMClient, LLMConfigurationError
from app.ai.prompts import MEMORY_INTERVIEW_SYSTEM_PROMPT
from app.repositories.chat_message_repository import ChatMessageRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.schemas.chat import (
    ChatMessage,
    ChatReply,
    ChatSession,
    ChatSessionCreate,
)
from app.services.family_member_service import (
    FamilyMemberNotFoundError,
    FamilyMemberService,
)
from app.services.family_service import FamilyService
from app.services.memory_service import InvalidFamilyMemberError


class ChatSessionNotFoundError(Exception):
    pass


class ChatService:

    def __init__(self) -> None:
        self.session_repository = ChatSessionRepository()
        self.message_repository = ChatMessageRepository()
        self.family_service = FamilyService()
        self.family_member_service = FamilyMemberService()
        # 懒加载：不要在构造时强依赖 LLM，否则缺配置时整个 app 起不来
        self._llm_client: LLMClient | None = None

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _build_system_prompt(
        self,
        chat_session: ChatSession,
    ) -> str:
        """固定采访规则 + 本会话的家庭 / 主要人物上下文。"""

        lines: list[str] = [
            MEMORY_INTERVIEW_SYSTEM_PROMPT.strip(),
            "",
            "【本会话上下文】",
        ]

        family = self.family_service.get_family(
            chat_session.family_id
        )
        lines.append(f"当前家庭：{family.name}")

        if chat_session.primary_person_id is None:
            lines.append(
                "本次未指定主要人物，请根据用户叙述自然追问相关家人。"
            )
            return "\n".join(lines)

        try:
            person = self.family_member_service.get_family_member(
                chat_session.primary_person_id
            )
        except FamilyMemberNotFoundError:
            lines.append(
                "主要人物记录已不存在，请根据用户叙述继续采访。"
            )
            return "\n".join(lines)

        lines.append(
            f"本次采访的主要人物：{person.name}"
            f"（与用户关系：{person.relationship}）"
        )

        if person.birth_date is not None:
            lines.append(f"出生日期：{person.birth_date}")

        lines.append(
            "请优先围绕这位主要人物展开采访，"
            "也可以自然延伸到相关家人；不要编造未提及的事实。"
        )

        return "\n".join(lines)

    def create_session(
        self,
        data: ChatSessionCreate,
    ) -> ChatSession:
        """
        创建 Session：
        1. family 是否存在
        2. primary person 是否存在（若传了）
        3. person 是否属于该 family（若传了）
        4. 创建 ChatSession
        """
        # 1) 家庭是否存在
        self.family_service.get_family(data.family_id)

        # 2) + 3) 若指定了主要人物，则必须存在且属于该家庭
        if data.primary_person_id is not None:
            person = self.family_member_service.get_family_member(
                data.primary_person_id
            )

            if person.family_id != data.family_id:
                raise InvalidFamilyMemberError(
                    f"成员 {data.primary_person_id} "
                    f"不属于家庭 {data.family_id}"
                )

        # 4) 创建会话（llm_model 由 service 从配置传入）
        llm_model = os.getenv("LLM_MODEL")
        if not llm_model:
            raise LLMConfigurationError(
                "LLM_MODEL is not configured"
            )

        return self.session_repository.create(
            data,
            llm_model=llm_model,
        )

    def get_session(
        self,
        session_id: UUID,
    ) -> ChatSession:
        session = self.session_repository.get(session_id)
        if session is None:
            raise ChatSessionNotFoundError(
                f"会话不存在：{session_id}"
            )
        return session

    def list_sessions(
        self,
        family_id: UUID | None = None,
    ) -> list[ChatSession]:
        return self.session_repository.list(family_id)

    def send_message(
        self,
        session_id: UUID,
        content: str,
    ) -> ChatReply:
        """
        发送消息 + AI 回复（先存 user，失败可重试）：
        1. 查 ChatSession
        2. 若末尾已是未配对的 ChatMessage(user)：内容相同则复用；不同则替换
           否则新建 user 并 commit（用户原文先落库，不必重打）
        3. 读取本会话全部 ChatMessage，拼 System Prompt
        4. 调用 LLM（失败时 user 仍在，客户端 Retry 同一 content 即可）
        5. 保存 Assistant
        6. 返回 User + Assistant
        """
        # 1) 查 ChatSession（后面拼 Prompt 也要用人物上下文）
        chat_session = self.get_session(session_id)

        existing_messages = self.message_repository.list_by_session(
            session_id
        )

        # 2) 先落库 / 复用 User（不跨事务调 LLM）
        if (
            existing_messages
            and existing_messages[-1].role == "user"
        ):
            # 上次 LLM 失败留下的孤儿：Retry 时复用，避免重复插入
            user_message = existing_messages[-1]
            if user_message.content != content:
                # 用户改发了新内容：去掉旧孤儿，再写新 user
                self.message_repository.delete(user_message.id)
                user_message = self.message_repository.create(
                    session_id=session_id,
                    role="user",
                    content=content,
                )
        else:
            user_message = self.message_repository.create(
                session_id=session_id,
                role="user",
                content=content,
            )

        # 3) 再读本会话全部 ChatMessage（含本轮 user），拼给 LLM
        session_messages = self.message_repository.list_by_session(
            session_id
        )

        llm_messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": self._build_system_prompt(chat_session),
            }
        ]

        for message in session_messages:
            llm_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        # 4) 调 LLM；失败则 user 仍在库中，可 Retry
        assistant_content = self._get_llm_client().chat(llm_messages)

        # 5) 存 Assistant
        assistant_message = self.message_repository.create(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
        )

        # 一轮对话成功后再刷新 Session.updated_at
        self.session_repository.touch_updated_at(session_id)

        # 6) 返回
        return ChatReply(
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def list_messages(
        self,
        session_id: UUID,
    ) -> list[ChatMessage]:
        self.get_session(session_id)
        return self.message_repository.list_by_session(
            session_id
        )
