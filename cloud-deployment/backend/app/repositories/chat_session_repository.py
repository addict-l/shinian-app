from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.chat_session import ChatSessionModel
from app.schemas.chat import ChatSession, ChatSessionCreate


class ChatSessionRepository:

    @staticmethod
    def _to_schema(
        model: ChatSessionModel,
    ) -> ChatSession:

        primary_person_id = None
        if model.primary_person_id is not None:
            primary_person_id = UUID(str(model.primary_person_id))

        return ChatSession(
            version=model.version,
            information=model.information or {},
            id=model.id,
            family_id=model.family_id,
            primary_person_id=primary_person_id,
            title=model.title,
            session_type=model.session_type,
            status=model.status,
            llm_model=model.llm_model,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def create(
        self,
        data: ChatSessionCreate,
        llm_model: str,
    ) -> ChatSession:

        now = datetime.now(timezone.utc)

        primary_person_id = None
        if data.primary_person_id is not None:
            primary_person_id = str(data.primary_person_id)

        model = ChatSessionModel(
            id=str(data.client_request_id) if data.client_request_id else None,
            family_id=str(data.family_id),
            primary_person_id=primary_person_id,
            title=data.title,
            llm_model=llm_model,
            created_at=now,
            updated_at=now,
        )

        with SessionLocal() as session:

            session.add(model)
            session.commit()
            session.refresh(model)

            return self._to_schema(model)

    def touch_updated_at(
        self,
        session_id: UUID,
    ) -> None:
        """刷新会话的 updated_at（例如刚完成一轮对话）。"""

        with SessionLocal() as session:

            model = session.get(
                ChatSessionModel,
                str(session_id),
            )

            if model is None:
                return

            model.updated_at = datetime.now(timezone.utc)
            model.version += 1
            session.commit()

    def get(
        self,
        session_id: UUID,
    ) -> ChatSession | None:

        with SessionLocal() as session:

            model = session.get(
                ChatSessionModel,
                str(session_id),
            )

            if model is None:
                return None

            return self._to_schema(model)

    def list(
        self,
        family_id: UUID | None = None,
    ) -> list[ChatSession]:

        with SessionLocal() as session:

            statement = select(ChatSessionModel)

            if family_id is not None:
                statement = statement.where(
                    ChatSessionModel.family_id == str(family_id)
                )

            statement = statement.order_by(
                ChatSessionModel.updated_at.desc()
            )

            models = session.scalars(statement).all()

            result: list[ChatSession] = []
            for model in models:
                result.append(self._to_schema(model))

            return result
