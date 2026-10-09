from uuid import UUID

from app.repositories.family_member_repository import FamilyMemberRepository
from app.schemas.family_member import FamilyMember, FamilyMemberCreate
from app.services.family_service import FamilyService


class FamilyMemberNotFoundError(Exception):
    pass


class FamilyMemberService:

    def __init__(self) -> None:
        self.repository = FamilyMemberRepository()
        self.family_service = FamilyService()

    def create_family_member(
        self,
        family_member: FamilyMemberCreate,
    ) -> FamilyMember:
        from app.services.workflow_service import serialized
        from fastapi import HTTPException
        self.family_service.get_family(family_member.family_id)
        with serialized(family_member.client_request_id or "member-create"):
            if family_member.client_request_id:
                existing = self.repository.get(family_member.client_request_id)
                if existing:
                    if (existing.family_id, existing.name, existing.relationship, existing.birth_date) != (family_member.family_id, family_member.name, family_member.relationship, family_member.birth_date):
                        raise HTTPException(409, '人物请求标识与已保存内容不一致')
                    return existing
            return self.repository.create(family_member)

    def get_family_member(
        self,
        family_member_id: UUID,
    ) -> FamilyMember:
        member = self.repository.get(family_member_id)
        if member is None:
            raise FamilyMemberNotFoundError(
                f"家庭成员不存在：{family_member_id}"
            )
        return member

    def list_family_members(
    self,
    family_id: UUID | None = None,
) -> list[FamilyMember]:

        return self.repository.list(
            family_id
        )

    def delete_family_member(self, family_member_id: UUID) -> None:
        if not self.repository.delete(family_member_id):
            raise FamilyMemberNotFoundError(
                f"家庭成员不存在：{family_member_id}"
            )