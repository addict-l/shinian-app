from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.life_overview import LifeOverview
from app.schemas.chat import ChatMessage, ChatSession
from app.schemas.memory import MemoryCreate
from app.schemas.story_information import InformationDimension
from app.schemas.media import MediaResponse
from app.schemas.story_guidance import StoryReadiness, GroundedDraft, GenerationOffer

class ChatState(BaseModel):
    life_overview: LifeOverview | None = None
    session: ChatSession
    messages: list[ChatMessage]
    can_generate: bool
    current_message_ids: list[UUID] | None = None
    generation_offer: GenerationOffer | None = None
    readiness: StoryReadiness = Field(default_factory=StoryReadiness)

class DraftResponse(BaseModel):
    id: UUID
    session_id: UUID
    revision: UUID
    memory: MemoryCreate
    saved_memory_id: UUID | None = None
    evidence: GroundedDraft | None = None
    manually_edited: bool = False
    time_review_from: InformationDimension | None = None

class DraftConfirmation(BaseModel):
    revision: UUID

class HealthResponse(BaseModel):
    status: str
    database: str
    llm_configured: bool

class DraftUpdate(BaseModel):
    revision: UUID
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=100000)

    time: InformationDimension | None = None

class DraftRegeneration(BaseModel):
    revision: UUID
    replace_confirmed: bool = False
