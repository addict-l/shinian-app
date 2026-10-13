from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import SessionLocal
from app.models.chat_message import ChatMessageModel
from app.models.chat_session import ChatSessionModel
from app.schemas.chat import ChatMessage


class ChatMessageRepository:

    def recent_for_person(self, family_id: UUID, person_id: UUID):
        with SessionLocal() as db:
            rows = db.scalars(select(ChatMessageModel).options(selectinload(ChatMessageModel.attachments)).join(ChatSessionModel)
                .where(ChatSessionModel.family_id == str(family_id),
                       ChatSessionModel.primary_person_id == str(person_id))
                .where(ChatSessionModel.status != 'prepared')
                .order_by(ChatMessageModel.created_at.desc(), ChatMessageModel.id.desc()).limit(20)).all()
            return [self._to_schema(row) for row in reversed(rows)]

    @staticmethod
    def _to_schema(
        model: ChatMessageModel,
    ) -> ChatMessage:

        return ChatMessage(
            attachments=[{'id': asset.id, 'url': asset.file_url, 'position': asset.position} for asset in model.attachments],
            id=model.id,
            session_id=model.session_id,
            role=model.role,
            type=model.type,
            content=model.content,
            created_at=model.created_at,
        )

    def create(
        self,
        session_id: UUID,
        role: str,
        content: str,
        message_id: UUID | None = None,
        message_type: str = 'text',
    ) -> ChatMessage:

        model = ChatMessageModel(
            id=str(message_id) if message_id else None,
            session_id=str(session_id),
            role=role,
            type=message_type,
            content=content,
            created_at=datetime.now(timezone.utc),
        )

        with SessionLocal() as session:

            session.add(model)
            session.commit()
            session.refresh(model)

            return self._to_schema(model)

    def delete(
        self,
        message_id: UUID,
    ) -> None:

        with SessionLocal() as session:

            model = session.get(
                ChatMessageModel,
                str(message_id),
            )

            if model is None:
                return

            session.delete(model)
            session.commit()

    def list_by_session(
        self,
        session_id: UUID,
    ) -> list[ChatMessage]:

        with SessionLocal() as session:

            statement = (
                select(ChatMessageModel)
                .options(selectinload(ChatMessageModel.attachments))
                .where(
                    ChatMessageModel.session_id
                    == str(session_id)
                )
                .order_by(
                    ChatMessageModel.created_at.asc(), ChatMessageModel.id.asc()
                )
            )

            models = session.scalars(statement).all()

            result: list[ChatMessage] = []
            for model in models:
                result.append(self._to_schema(model))

            return result
