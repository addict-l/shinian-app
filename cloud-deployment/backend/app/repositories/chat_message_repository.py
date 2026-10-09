from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.chat_message import ChatMessageModel
from app.schemas.chat import ChatMessage


class ChatMessageRepository:

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
    ) -> ChatMessage:

        model = ChatMessageModel(
            id=str(message_id) if message_id else None,
            session_id=str(session_id),
            role=role,
            type="text",
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
