from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.chat import ChatMessage, ChatSession
from app.schemas.memory import MemoryCreate
from app.schemas.media import MediaResponse

class ChatState(BaseModel):
    session: ChatSession
    messages: list[ChatMessage]
    can_generate: bool

class DraftResponse(BaseModel):
    id: UUID
    session_id: UUID
    revision: UUID
    memory: MemoryCreate
    saved_memory_id: UUID | None = None

class DraftConfirmation(BaseModel):
    revision: UUID

class HealthResponse(BaseModel):
    status: str
    database: str
    llm_configured: bool
