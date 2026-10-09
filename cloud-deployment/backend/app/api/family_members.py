from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.family_member import FamilyMember, FamilyMemberCreate
from app.services.family_member_service import (
    FamilyMemberNotFoundError,
    FamilyMemberService,
)
from app.services.family_service import FamilyNotFoundError

router = APIRouter(
    prefix="/api/v1/family-members",
    tags=["family-members"],
)

family_member_service = FamilyMemberService()


@router.post(
    "/",
    response_model=FamilyMember,
    status_code=201,
)
def create_family_member(
    family_member: FamilyMemberCreate,
) -> FamilyMember:
    try:
        return family_member_service.create_family_member(
            family_member
        )
    except FamilyNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@router.get(
    "/",
    response_model=list[FamilyMember],
)
def list_family_members(family_id: UUID | None = None) -> list[FamilyMember]:
    return family_member_service.list_family_members(family_id)


@router.get(
    "/{family_member_id}",
    response_model=FamilyMember,
)
def get_family_member(family_member_id: UUID) -> FamilyMember:
    try:
        return family_member_service.get_family_member(family_member_id)
    except FamilyMemberNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@router.delete(
    "/{family_member_id}",
    status_code=204,
)
def delete_family_member(family_member_id: UUID) -> None:
    try:
        family_member_service.delete_family_member(family_member_id)
    except FamilyMemberNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
