from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    client_request_id: UUID | None = None

    family_id: UUID

    primary_person_id: UUID | None = None

    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ChatSession(BaseModel):

    id: UUID

    family_id: UUID

    primary_person_id: UUID | None

    title: str

    session_type: str

    status: str

    llm_model: str

    created_at: datetime

    updated_at: datetime


class ChatMessageCreate(BaseModel):
    client_request_id: UUID | None = None

    content: str = Field(
        min_length=1, max_length=12000,
    )


class ChatMessage(BaseModel):

    id: UUID

    session_id: UUID

    role: str

    type: str

    content: str

    created_at: datetime


class ChatReply(BaseModel):

    user_message: ChatMessage

    assistant_message: ChatMessage