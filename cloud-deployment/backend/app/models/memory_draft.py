from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class MemoryDraftModel(Base):
    __tablename__ = 'memory_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey('chat_sessions.id', ondelete='CASCADE'), unique=True, nullable=False)
    revision: Mapped[str] = mapped_column(String(36), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    saved_memory_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('memories.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
