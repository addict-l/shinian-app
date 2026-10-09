from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.schemas.family_member import (
    FamilyMember,
    FamilyMemberCreate,
)


class FamilyMemberRepository:

    @staticmethod
    def _to_schema(
        model: FamilyMemberModel,
    ) -> FamilyMember:

        return FamilyMember(
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
            session.commit()
            session.refresh(model)

            return self._to_schema(model)

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

            return self._to_schema(model)

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
                    self._to_schema(model)
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
