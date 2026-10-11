from uuid import UUID
from fastapi import APIRouter, File, UploadFile
from app.schemas.memoir import MemoirSnapshot, MemoirUpdate
from app.schemas.media import MediaResponse
from app.services import memoir_service, media_service

router = APIRouter(prefix='/api/v1/families/{family_id}/members/{person_id}/memoir', tags=['memoirs'])


@router.get('', response_model=MemoirSnapshot)
def read_book(family_id: UUID, person_id: UUID):
    return memoir_service.snapshot(family_id, person_id)


@router.put('', response_model=MemoirSnapshot)
def save_book(family_id: UUID, person_id: UUID, body: MemoirUpdate):
    return memoir_service.update(family_id, person_id, body)


@router.post('/photos', response_model=MediaResponse, status_code=201)
def upload_cover(family_id: UUID, person_id: UUID, client_request_id: UUID, file: UploadFile = File(...)):
    return media_service.upload(None, client_request_id, file.file, family_id=family_id, memoir_person_id=person_id)
