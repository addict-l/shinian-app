from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Integer, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatSessionModel(Base):

    __tablename__ = "chat_sessions"
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    information: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "families.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    primary_person_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "family_members.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    session_type: Mapped[str] = mapped_column(
        String(50),
        default="memory_interview",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    llm_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
