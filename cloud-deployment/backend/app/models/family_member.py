from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.db.base import Base


class FamilyMemberModel(Base):

    __tablename__ = "family_members"

    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "families.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 字段名 relationship 会遮蔽 sqlalchemy.orm.relationship
    relationship: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    birth_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    family: Mapped["FamilyModel"] = orm_relationship(
        back_populates="members",
    )

    memories: Mapped[list["MemoryModel"]] = orm_relationship(
        secondary="memory_persons",
        back_populates="people",
    )
