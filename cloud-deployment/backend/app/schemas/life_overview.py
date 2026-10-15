"""Person-level onboarding, separate from saved story material."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.guided_interview import GuidedQuote

TopicID = Literal['home', 'learning', 'early_work', 'later_work', 'family', 'changes', 'present']

class LifeField(BaseModel):
    topic_id: TopicID
    status: Literal['pending', 'known', 'unknown', 'declined', 'skipped'] = 'pending'
    evidence: list[GuidedQuote] = Field(default_factory=list)

class LifeExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: list[LifeField] = Field(min_length=7, max_length=7)

class LifeTurn(BaseModel):
    id: UUID
    role: Literal['user', 'assistant']
    content: str
    created_at: str

class LifeOverview(BaseModel):
    version: int = 0
    status: Literal['not_started', 'collecting', 'review', 'confirmed'] = 'not_started'
    required: bool = False
    paused: bool = False
    fields: list[LifeField] = Field(default_factory=list)
    turns: list[LifeTurn] = Field(default_factory=list)
    question_id: TopicID | None = None
    question: str | None = None
    question_number: int = 0
    total_questions: int = 7
    confirmed_version: int | None = None
    pending_request_id: UUID | None = None
    pending_action: dict | None = None

class LifeAction(BaseModel):
    action: Literal['begin', 'answer', 'confirm', 'correct', 'pause', 'resume']
    expected_version: int = Field(ge=0)
    client_request_id: UUID
    text: str = Field(default='', max_length=12000)
    topic_id: TopicID | None = None
