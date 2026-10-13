"""Resolve model-selected evidence against original text; never paraphrase quotes."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.ai.llm_client import LLMResponseFormatError
from app.schemas.story_information import InformationStatus, InformationDimension, InformationConflict
from app.schemas.story_guidance import StoryAnalysis, SourceQuote, GroundedDraft, GroundedPassage, GroundedTitle, EventBoundary


def source_fragments(text):
    """Number original clauses and calendar dates without changing source text."""
    import re
    fragments = []
    cursor = 0
    pattern = r'\d{4}(?:-\d{1,2}-\d{1,2}|年(?:\d{1,2}月(?:\d{1,2}日)?)?)|[，。！？；,\n!?;]+'
    def append(start, end):
        if text[start:end].strip('，。！？；,\n!?; \t'):
            fragments.append({'index': len(fragments)+1, 'text': text[start:end], 'start': start, 'end': end})
    for match in re.finditer(pattern, text):
        if match.group()[0].isdigit():
            append(cursor, match.start())
            append(match.start(), match.end())
        else:
            append(cursor, match.end())
        cursor = match.end()
    append(cursor, len(text))
    return fragments


class SourceRange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: UUID
    start_fragment: int = Field(ge=1, description='messages 中该消息 fragments 的起始 index')
    end_fragment: int = Field(ge=1, description='同一消息的末尾 index，不得小于 start_fragment；单片段两者相同')


def resolve_range(source, texts):
    text = texts.get(source.message_id)
    if text is None:
        raise LLMResponseFormatError('message_id 必须引用输入的用户消息')
    fragments = source_fragments(text)
    if not 1 <= source.start_fragment <= source.end_fragment <= len(fragments):
        raise LLMResponseFormatError('start_fragment/end_fragment 必须是该用户消息 fragments 中实际存在、按先后排列的 index')
    first, last = fragments[source.start_fragment-1], fragments[source.end_fragment-1]
    return SourceQuote(message_id=source.message_id, quote=text[first['start']:last['end']])


class SelectedDimension(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: InformationStatus = InformationStatus.missing
    source: SourceRange | None = None

    @model_validator(mode='after')
    def coherent(self):
        if (self.status == InformationStatus.missing) != (self.source is None):
            raise ValueError('missing 不带 source；其他状态必须选择用户原文')
        return self


class SelectedConflict(BaseModel):
    dimension: Literal['people', 'event', 'time', 'place', 'feeling', 'detail']
    alternatives: list[SelectedDimension] = Field(min_length=2, max_length=4)


class SelectedBoundary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['independent', 'return']
    previous_event: SourceRange
    current_event: SourceRange


class SelectedAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    people: SelectedDimension = Field(default_factory=SelectedDimension)
    event: SelectedDimension = Field(default_factory=SelectedDimension)
    time: SelectedDimension = Field(default_factory=SelectedDimension)
    place: SelectedDimension = Field(default_factory=SelectedDimension)
    feeling: SelectedDimension = Field(default_factory=SelectedDimension)
    detail: SelectedDimension = Field(default_factory=SelectedDimension)
    conflicts: list[SelectedConflict] = Field(default_factory=list, max_length=6)
    compatible_times: list[SourceRange] = Field(default_factory=list, max_length=8,
        description='同一事件时间的兼容补充：选择所有相关用户原文；不同明确年份或无法确认兼容则为空')
    compatible_places: list[SourceRange] = Field(default_factory=list, max_length=8,
        description='同一地点的兼容说法或补充细节：选择所有相关用户原文；互斥或无法确认兼容则为空')
    guidance_hint: str = Field(default='', max_length=800)
    generation_request: SourceRange | None = Field(default=None, description='仅最新用户明确要求整理、生成、保存或更新草稿时选择请求原文；否定、保存照片和往事中的保存不算')
    narrative_sources: list[SourceRange] = Field(default_factory=list, max_length=60,
        description='完整讲述经过的连续原文范围，保留六项摘要以外的关键动作和转折，不含整理指令')
    event_boundary: SelectedBoundary | None = None
    latest_has_narrative: bool = Field(default=False, strict=True)


def resolve_analysis(selected, texts):
    def dimension(item, key):
        if item.source is None:
            return InformationDimension()
        try:
            quote = resolve_range(item.source, texts)
        except LLMResponseFormatError as exc:
            raise LLMResponseFormatError(f'{key}.source 无效：{exc}') from exc
        return InformationDimension(status=item.status, value=quote.quote, source_message_ids=[quote.message_id])
    values = {key: dimension(getattr(selected, key), key) for key in ('people', 'event', 'time', 'place', 'feeling', 'detail')}
    request = None
    if selected.generation_request:
        try:
            request = resolve_range(selected.generation_request, texts)
        except LLMResponseFormatError:
            # Invalid optional intent cannot enable an offer or interrupt
            # narration; every story dimension still requires valid evidence.
            pass
    boundary = selected.event_boundary
    narration = [resolve_range(source, texts) for source in selected.narrative_sources]
    if selected.latest_has_narrative and texts:
        latest_id = next(reversed(texts))
        narration.append(SourceQuote(message_id=latest_id,quote=texts[latest_id]))
    return StoryAnalysis(**values, conflicts=[InformationConflict(dimension=c.dimension,
        alternatives=[dimension(item, f'conflicts.{c.dimension}') for item in c.alternatives]) for c in selected.conflicts],
        guidance_hint=selected.guidance_hint,
        compatible_times=[resolve_range(source, texts) for source in selected.compatible_times],
        compatible_places=[resolve_range(source, texts) for source in selected.compatible_places],
        narrative_sources=narration,
        event_boundary=EventBoundary(kind=boundary.kind,
            previous_event=resolve_range(boundary.previous_event,texts),
            current_event=resolve_range(boundary.current_event,texts)) if boundary else None,
        generation_request=request)


class SelectedPassage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=12000)
    source_indices: list[Annotated[int, Field(strict=True)]] = Field(min_length=1, max_length=30, description='选择 accepted_user_excerpts 的 index，引用能支持整段事实的原文，不能编造索引')


class SelectedTitle(SelectedPassage):
    text: str = Field(min_length=1, max_length=200)


class SelectedDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: SelectedTitle
    paragraphs: list[SelectedPassage] = Field(min_length=1, max_length=30)


def resolve_draft(selected, evidence):
    def sources(passage):
        if any(index < 1 or index > len(evidence) for index in passage.source_indices):
            raise LLMResponseFormatError('source_indices 必须选输入原文的 index；不能引用不存在的原文')
        return [SourceQuote(message_id=evidence[index-1]['id'], quote=evidence[index-1]['content'])
                for index in dict.fromkeys(passage.source_indices)]
    return GroundedDraft(title=GroundedTitle(text=selected.title.text, sources=sources(selected.title)),
        paragraphs=[GroundedPassage(text=p.text, sources=sources(p)) for p in selected.paragraphs])
