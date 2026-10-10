"""Collected facts, distinct from information not yet asked about."""
from enum import Enum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class InformationStatus(str, Enum):
    missing = 'missing'
    known = 'known'
    approximate = 'approximate'
    unknown = 'unknown'
    withheld = 'withheld'


class InformationDimension(BaseModel):
    status: InformationStatus = InformationStatus.missing
    value: str | None = Field(default=None, max_length=2000)
    source_message_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode='after')
    def coherent(self):
        if self.status == InformationStatus.missing:
            if self.value is not None or self.source_message_ids:
                raise ValueError('未采集的信息不能包含值或原文依据')
        elif not self.value or not self.value.strip():
            raise ValueError('已采集信息必须保留可读说明，包括模糊或未知的表达')
        return self


class InformationConflict(BaseModel):
    dimension: Literal['people', 'event', 'time', 'place', 'feeling', 'detail']
    alternatives: list[InformationDimension] = Field(min_length=2, max_length=4)


class ConversationProgress(BaseModel):
    automatic_offer_used: bool = False
    offer_message_id: UUID | None = None
    replied_user_message_id: UUID | None = None


class StoryFacts(BaseModel):
    people: InformationDimension = Field(default_factory=InformationDimension)
    event: InformationDimension = Field(default_factory=InformationDimension)
    time: InformationDimension = Field(default_factory=InformationDimension)
    place: InformationDimension = Field(default_factory=InformationDimension)
    feeling: InformationDimension = Field(default_factory=InformationDimension)
    detail: InformationDimension = Field(default_factory=InformationDimension)
    conflicts: list[InformationConflict] = Field(default_factory=list, max_length=6)


class StoryInformation(StoryFacts):
    conversation: ConversationProgress = Field(default_factory=ConversationProgress)
    analyzed_message_ids: list[UUID] = Field(default_factory=list)
    excluded_values: list[str] = Field(default_factory=list)
