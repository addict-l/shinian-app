from uuid import UUID, uuid4
import os

from app.repositories.family_member_repository import FamilyMemberRepository
from app.schemas.family_member import FamilyMember, FamilyMemberCreate
from app.services.family_service import FamilyService


class FamilyMemberNotFoundError(Exception):
    pass


class FamilyMemberService:

    def __init__(self) -> None:
        self.repository = FamilyMemberRepository()
        self.family_service = FamilyService()

    def _get_llm_client(self):
        from app.ai.llm_client import LLMClient
        return LLMClient()

    def _generate_opening(self, member):
        from app.schemas.story_information import StoryInformation
        from app.services.story_guidance import readiness, validate_reply
        information = StoryInformation()
        result = readiness(information, [], member.client_request_id, False)
        reply = self._get_llm_client().converse([], {'name': member.name, 'relationship': member.relationship}, information, result,
            '这是首次开场白。只写一句称呼和问候，最多12字，例如“爷爷，您好。”不提问，不介绍系统或流程，不邀请展开故事，不预设经历或感受，不建议生成或保存。')
        validate_reply(reply, [], {'allowed': False, 'explicit_request': False})
        return reply.text

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
            data = family_member.model_copy(update={'client_request_id': family_member.client_request_id or uuid4()})
            # Prepare before committing: a failed AI request leaves the editable
            # form retryable, without an incomplete member or half welcome.
            from app.ai.llm_client import LLMServiceError, LLMResponseFormatError
            try:
                opening = self._generate_opening(data)
            except (LLMServiceError, LLMResponseFormatError) as error:
                raise HTTPException(502, '开场白暂时未能准备好，人物尚未创建；填写内容仍可保留重试') from error
            return self.repository.create(data, opening_text=opening, llm_model=os.getenv('LLM_MODEL', ''))

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
