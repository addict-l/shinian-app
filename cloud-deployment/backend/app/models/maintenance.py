"""Durable file cleanup and retry receipts survive request/process failures."""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class MediaCleanupModel(Base):
    __tablename__ = 'media_cleanup_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey('families.id', ondelete='CASCADE'))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MemoryDeletionModel(Base):
    __tablename__ = 'memory_deletions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey('families.id', ondelete='CASCADE'))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
