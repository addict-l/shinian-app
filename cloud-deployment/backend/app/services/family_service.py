from uuid import UUID

from app.repositories.family_repository import FamilyRepository
from app.schemas.family import Family, FamilyCreate


class FamilyNotFoundError(Exception):
    pass


class FamilyService:

    def __init__(self) -> None:
        self.repository = FamilyRepository()

    def create_family(
        self,
        data: FamilyCreate,
    ) -> Family:
        return self.repository.create(data)

    def get_family(
        self,
        family_id: UUID,
    ) -> Family:
        family = self.repository.get(family_id)
        if family is None:
            raise FamilyNotFoundError(
                f"家庭不存在：{family_id}"
            )
        return family
