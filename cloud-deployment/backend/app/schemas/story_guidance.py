"""Model output carries evidence; readiness is calculated by the application."""
from uuid import UUID
from typing import Literal
from app.schemas.story_information import StoryFacts
from pydantic import BaseModel, Field, ConfigDict


class StoryReadiness(BaseModel):
    ready: bool = False
    missing_dimensions: list[str] = Field(default_factory=list)
    conflicting_dimensions: list[str] = Field(default_factory=list)
    needs_analysis: bool = False
    message: str = ''


class SourceQuote(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    message_id: UUID
    quote: str = Field(min_length=1, max_length=12000, description='逐字复制提供的 content 中连续片段；不改人称，不拼接，不改标点')


class GroundedPassage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=12000)
    sources: list[SourceQuote] = Field(min_length=1, max_length=30)


class GroundedTitle(GroundedPassage):
    text: str = Field(min_length=1, max_length=200)


class GroundedDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: GroundedTitle
    paragraphs: list[GroundedPassage] = Field(min_length=1, max_length=30)


class StoryAnalysis(StoryFacts):
    guidance_hint: str = Field(default='', max_length=800, description='贴合当前讲述的引导参考；不规定固定问题顺序')
    generation_request: SourceQuote | None = Field(default=None, description='仅当最新用户消息明确要求整理或保存本段回忆时，引用该消息的连续原文；提及往事中的保存不算请求')


class ConversationReply(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=1200, description='面向记录对象，用您及自然中文。最多一个问题、一个问号；停顿时只回应；不推断未表达的感受。')
    action: Literal['continue', 'offer_generation'] = 'continue'


class GenerationOffer(BaseModel):
    message_id: UUID
