"""Read-only, versioned suggestions for the current editor snapshot."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.story_information import InformationDimension

class TimePreviewRequest(BaseModel):
    title: str = Field(max_length=200)
    summary: str = Field(max_length=100000)
    old_time: InformationDimension
    new_time: InformationDimension

class DraftTimePreviewRequest(TimePreviewRequest):
    revision: UUID

class MemoryTimePreviewRequest(TimePreviewRequest):
    family_id: UUID
    version: int = Field(ge=1)

class TimeSuggestion(BaseModel):
    id: str
    field: Literal['title', 'summary']
    start: int  # UTF-16 offset, shared with native iOS strings.
    length: int
    before: str
    after: str | None = None
    context: str
    ambiguous: bool
    reason: str

class TimePreview(BaseModel):
    snapshot: str
    suggestions: list[TimeSuggestion]
    message: str
