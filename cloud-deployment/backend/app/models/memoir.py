from sqlalchemy import ForeignKey, String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MemoirSettingsModel(Base):
    __tablename__ = 'memoir_settings'
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey('family_members.id', ondelete='CASCADE'), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey('families.id', ondelete='CASCADE'), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
