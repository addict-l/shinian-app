from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):

    family_id: UUID

    person_ids: list[UUID] = Field(
        min_length=1,)

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    raw_content: str = Field(
        min_length=1,
    )

    summary: str | None = None

    memory_date: date | None = None

    location: str | None = None


class Memory(BaseModel):
    media_urls: list[str] = Field(default_factory=list)
    family_id: UUID

    id: UUID

    person_ids: list[UUID]

    source_session_id: UUID | None

    title: str

    raw_content: str

    summary: str | None

    memory_date: date | None

    location: str | None

    created_at: datetime

    updated_at: datetime

class MemoryExtraction(BaseModel):

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    summary: str | None = None

    memory_date: date | None = None

    location: str | None = None

    people: list[str] = Field(
        default_factory=list,
    )