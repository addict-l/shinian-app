from datetime import datetime, timezone
from uuid import UUID

from app.db.database import SessionLocal
from app.models.family import FamilyModel
from app.schemas.family import Family, FamilyCreate


class FamilyRepository:

    def create(
        self,
        data: FamilyCreate,
    ) -> Family:

        now = datetime.now(timezone.utc)

        model = FamilyModel(
            name=data.name,
            created_at=now,
            updated_at=now,
        )

        with SessionLocal() as session:

            session.add(model)

            session.commit()

            session.refresh(model)

        return self._to_schema(model)


    def get(
        self,
        family_id: UUID,
    ) -> Family | None:

        with SessionLocal() as session:

            model = session.get(
                FamilyModel,
                str(family_id),
            )

        if model is None:
            return None

        return self._to_schema(model)


    @staticmethod
    def _to_schema(
        model: FamilyModel,
    ) -> Family:

        return Family(
            id=model.id,
            name=model.name,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )