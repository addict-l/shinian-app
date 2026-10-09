from uuid import UUID
from pydantic import BaseModel, Field


class MessageAttachment(BaseModel):
    id: UUID
    url: str
    position: int = Field(default=0, ge=0)


class MediaResponse(MessageAttachment):
    session_id: UUID | None
    memory_id: UUID | None
    message_id: UUID | None = None
    mime_type: str
