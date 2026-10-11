from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from app.schemas.memory import Memory


class WireModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid')


class CoverPhoto(WireModel):
    id: UUID
    source_memory_id: UUID | None = None
    x: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    y: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    zoom: float = Field(default=1, ge=1, le=4, allow_inf_nan=False)


class MemoirSettings(WireModel):
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field(default='', max_length=300)
    cover_template: Literal['text', 'photo', 'collage'] = 'text'
    cover_photos: list[CoverPhoto] = Field(default_factory=list, max_length=3)
    ordering: Literal['time', 'manual'] = 'time'
    story_order: list[UUID] = Field(default_factory=list, max_length=10000)
    photo_orders: dict[UUID, list[UUID]] = Field(default_factory=dict, max_length=10000)
    excluded_photo_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    text_size: Literal[14, 16] = 16

    @model_validator(mode='after')
    def unique_values(self):
        if not self.title.strip():
            raise ValueError('书名不能为空')
        groups = [self.story_order, self.excluded_photo_ids, [p.id for p in self.cover_photos], *self.photo_orders.values()]
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError('顺序与照片不能重复')
        if any(len(values) > 1000 for values in self.photo_orders.values()):
            raise ValueError('单篇照片过多')
        return self


class MemoirUpdate(WireModel):
    version: int = Field(ge=0)
    request_id: UUID
    settings: MemoirSettings


class MemoirSnapshot(WireModel):
    person_id: UUID
    person_name: str
    version: int
    settings: MemoirSettings
    stories: list[Memory]
    content_revision: str
