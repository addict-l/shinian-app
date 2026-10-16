from app.api.authentication import current_session
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends

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
    family_id: UUID | None = None, principal=Depends(current_session),
) -> list[Memory]:
    return memory_service.list_memories(UUID(principal.family_id))


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

from fastapi import File, UploadFile, Response, Query
from app.schemas.memory import MemoryUpdate, MemoryDeletion
from app.schemas.media import MediaResponse
from app.services import memory_maintenance, media_service

@router.patch('/{memory_id}', response_model=Memory)
def update_memory(memory_id: UUID, body: MemoryUpdate):
    return memory_maintenance.update(memory_id, body)

@router.delete('/{memory_id}', response_model=MemoryDeletion)
def delete_memory(memory_id: UUID, family_id: UUID, version: int = Query(ge=1)):
    return memory_maintenance.remove(memory_id, family_id, version)

@router.post('/{memory_id}/media', response_model=MediaResponse, status_code=201)
def upload_memory_photo(memory_id: UUID, family_id: UUID, client_request_id: UUID, file: UploadFile = File(...)):
    return media_service.upload(None, client_request_id, file.file, memory_id, family_id)

@router.delete('/{memory_id}/media/{media_id}', status_code=204)
def discard_memory_photo(memory_id: UUID, media_id: UUID, family_id: UUID):
    memory_maintenance.discard_photo(memory_id, family_id, media_id)
    return Response(status_code=204)


from app.schemas.time_linkage import MemoryTimePreviewRequest, TimePreview

@router.post('/{memory_id}/time-preview', response_model=TimePreview)
def memory_time_preview(memory_id: UUID, body: MemoryTimePreviewRequest):
    return memory_maintenance.preview_time(memory_id, body)
