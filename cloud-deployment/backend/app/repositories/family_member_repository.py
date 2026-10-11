from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.models.chat_message import ChatMessageModel
from app.models.chat_session import ChatSessionModel
from app.repositories.chat_message_repository import ChatMessageRepository
from app.schemas.family_member import (
    FamilyMember,
    FamilyMemberCreate,
)


class FamilyMemberRepository:

    @staticmethod
    def _to_schema(
        model: FamilyMemberModel,
        session,
    ) -> FamilyMember:

        opening = session.scalar(select(ChatMessageModel).join(ChatSessionModel).where(
            ChatSessionModel.family_id == model.family_id, ChatSessionModel.primary_person_id == model.id,
            ChatMessageModel.type == 'opening').order_by(ChatMessageModel.created_at, ChatMessageModel.id).limit(1))
        history = session.scalar(select(ChatMessageModel.id).join(ChatSessionModel).where(
            ChatSessionModel.family_id == model.family_id, ChatSessionModel.primary_person_id == model.id,
            ChatSessionModel.status != 'prepared').limit(1)) is not None
        return FamilyMember(
            opening_message=ChatMessageRepository._to_schema(opening) if opening else None,
            has_chat_history=history,
            id=model.id,
            family_id=model.family_id,
            name=model.name,
            relationship=model.relationship,
            birth_date=model.birth_date,
            created_at=model.created_at,
        )

    def create(
        self,
        data: FamilyMemberCreate,
        opening_text: str | None = None,
        llm_model: str = '',
    ) -> FamilyMember:

        model = FamilyMemberModel(
            id=str(data.client_request_id) if data.client_request_id else None,
            family_id=str(data.family_id),
            name=data.name,
            relationship=data.relationship,
            birth_date=data.birth_date,
            created_at=datetime.now(
                timezone.utc
            ),
        )

        with SessionLocal() as session:

            session.add(model)
            session.flush()
            if opening_text:
                identity = str(uuid5(NAMESPACE_URL, f'ai-memories:person:{model.family_id}:{model.id}:initial'))
                session.add(ChatSessionModel(id=identity, family_id=model.family_id, primary_person_id=model.id,
                    title=f'与{model.name}的回忆', status='prepared', llm_model=llm_model))
                session.flush()
                session.add(ChatMessageModel(session_id=identity, role='assistant', type='opening',
                    content=opening_text))
            session.commit()
            session.refresh(model)

            return self._to_schema(model, session)

    def get(
        self,
        member_id: UUID,
    ) -> FamilyMember | None:

        with SessionLocal() as session:

            model = session.get(
                FamilyMemberModel,
                str(member_id),
            )

            if model is None:
                return None

            return self._to_schema(model, session)

    def list(
    self,
    family_id: UUID | None = None,
) -> list[FamilyMember]:

        with SessionLocal() as session:

            statement = select(FamilyMemberModel)

            if family_id is not None:
                statement = statement.where(
                    FamilyMemberModel.family_id
                    == str(family_id)
                )

            statement = statement.order_by(
                FamilyMemberModel.created_at.asc()
            )

            models = session.scalars(
                statement
            ).all()

            result: list[FamilyMember] = []

            for model in models:
                result.append(
                    self._to_schema(model, session)
                )

            return result

    def delete(self, member_id: UUID) -> bool:
        with SessionLocal() as session:
            model = session.get(FamilyMemberModel, str(member_id))
            if model is None:
                return False
            session.delete(model)
            session.commit()
            return True
