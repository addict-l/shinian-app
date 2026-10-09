from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MediaAssetModel(Base):

    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    memory_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "memories.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True)

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    file_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    memory: Mapped["MemoryModel"] = relationship(
        back_populates="media_assets",
    )