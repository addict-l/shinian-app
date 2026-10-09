from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MemoryPersonModel(Base):

    __tablename__ = "memory_persons"

    memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "memories.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    family_member_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "family_members.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
