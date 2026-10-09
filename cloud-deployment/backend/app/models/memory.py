from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Integer, JSON,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.db.base import Base


class MemoryModel(Base):

    __tablename__ = "memories"
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    information: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primary_person_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('family_members.id', ondelete='SET NULL'), nullable=True)

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

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    raw_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    memory_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    family: Mapped["FamilyModel"] = relationship(
        back_populates="memories",
    )

    people: Mapped[list["FamilyMemberModel"]] = relationship(
        secondary="memory_persons",
        back_populates="memories",
    )

    media_assets: Mapped[list["MediaAssetModel"]] = relationship(
        back_populates="memory",
    )

    source_session_id: Mapped[str | None] = mapped_column(
    String(36),
    ForeignKey(
        "chat_sessions.id",
        ondelete="SET NULL",
    ),
    nullable=True,
    unique=True,
    )
