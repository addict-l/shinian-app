from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.memory import Memory, MemoryCreate
from app.services.family_member_service import FamilyMemberNotFoundError
from app.services.family_service import FamilyNotFoundError
from app.services.memory_service import (
    DuplicateFamilyMemberError,
    InvalidFamilyMemberError,
    MemoryNotFoundError,
    MemoryService,
)

router = APIRouter(
    prefix="/api/v1/memories",
    tags=["memories"],
)

memory_service = MemoryService()


@router.get(
    "/",
    response_model=list[Memory],
)
def list_memories(
    family_id: UUID | None = None,
) -> list[Memory]:
    return memory_service.list_memories(family_id)


@router.post(
    "/",
    response_model=Memory,
    status_code=201,
)
def create_memory(memory: MemoryCreate) -> Memory:
    try:
        return memory_service.create_memory(memory)
    except FamilyNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except FamilyMemberNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except InvalidFamilyMemberError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error
    except DuplicateFamilyMemberError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.get(
    "/{memory_id}",
    response_model=Memory,
)
def get_memory(memory_id: UUID) -> Memory:
    try:
        return memory_service.get_memory(memory_id)
    except MemoryNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
