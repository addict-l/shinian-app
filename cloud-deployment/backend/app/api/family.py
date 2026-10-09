from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.family import Family, FamilyCreate
from app.services.family_service import FamilyNotFoundError, FamilyService

router = APIRouter(
    prefix="/api/v1/families",
    tags=["families"],
)

family_service = FamilyService()


@router.post(
    "/",
    response_model=Family,
    status_code=201,
)
def create_family(data: FamilyCreate) -> Family:
    return family_service.create_family(data)


@router.get(
    "/{family_id}",
    response_model=Family,
)
def get_family(family_id: UUID) -> Family:
    try:
        return family_service.get_family(family_id)
    except FamilyNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
