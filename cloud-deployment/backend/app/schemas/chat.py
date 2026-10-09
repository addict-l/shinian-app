from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from app.schemas.story_information import StoryInformation
from app.schemas.media import MessageAttachment


class ChatSessionCreate(BaseModel):
    client_request_id: UUID | None = None

    family_id: UUID

    primary_person_id: UUID | None = None

    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ChatSession(BaseModel):
    version: int = Field(default=1, ge=1)
    information: StoryInformation = Field(default_factory=StoryInformation)

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

    content: str = Field(default='', max_length=12000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=9)

    @model_validator(mode='after')
    def validate_message(self):
        self.content = self.content.strip()
        if not self.content and not self.attachment_ids:
            raise ValueError('请填写文字或选择照片')
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError('照片不能重复关联')
        return self


class ChatMessage(BaseModel):
    attachments: list[MessageAttachment] = Field(default_factory=list)

    id: UUID

    session_id: UUID

    role: str

    type: str

    content: str

    created_at: datetime


class ChatReply(BaseModel):

    user_message: ChatMessage

    assistant_message: ChatMessage
