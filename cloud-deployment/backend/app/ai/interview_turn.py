"""Compact wire format for one analysis-and-reply request.

Short indices are scoped to this request only. Persistent evidence still uses
canonical UUIDs and verbatim source ranges, with the existing validators.
"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.ai.evidence import SelectedAnalysis, resolve_analysis, source_fragments
from app.ai.llm_client import LLMResponseFormatError
from app.ai.prompts import STORY_INFORMATION_PROMPT, NATURAL_CONVERSATION_PROMPT
from app.schemas.story_guidance import ConversationReply, StoryAnalysis, SourceQuote
from app.schemas.story_information import StoryInformation
from app.services.story_guidance import (
    validate_analysis, validate_information, readiness, reply_policy, validate_interview_reply,
    safe_interview_fallback, user_texts, _direct_generation_command,
    is_factual_supplement, is_explicit_continuation,
)

Index = Annotated[int, Field(strict=True, ge=1)]
Reference = tuple[Index, Index, Index]
Fact = tuple[Literal['known', 'approximate', 'unknown', 'withheld'], Index, Index, Index]
DIMENSIONS = ('people', 'event', 'time', 'place', 'feeling', 'detail')


def control_turn(messages, history, person, previous, primary_person_id):
    """Unambiguous controls need no fresh model inference or new story facts."""
    latest = messages[-1] if messages else None
    texts = user_texts(messages)
    if not latest or latest.id not in texts or set(previous.analyzed_message_ids) != set(texts)-{latest.id}:
        return None
    import re
    clauses = [clause.strip() for clause in re.split(r'[，。！？,!?\n]',latest.content) if clause.strip()]
    pause = bool(clauses) and all(re.fullmatch(
        r'(?:好(?:的)?|(?:今天|现在|暂时|先|我|这个细节|这个话题|这件事|感受)*(?:我)?(?:先|暂时)?'
        r'(?:不想讲|不想说|不想聊|不聊|不说|不讲|想休息|先休息|想安静)(?:了|一下|一会儿|会儿)?)',clause) for clause in clauses)
    request = _direct_generation_command(latest.content)
    closing = bool(re.fullmatch(r'(?:这段|这件事)?(?:就)?(?:讲完了|说完了|讲到这里|讲到这里了)[。！!\s]*',latest.content))
    result = readiness(previous,messages[:-1],primary_person_id)
    if not pause and not ((request or closing) and result.ready):
        return None
    information = validate_information(previous.model_copy(deep=True),messages,previous)
    result = readiness(information,messages,primary_person_id)
    analysis = StoryAnalysis.model_validate(information.model_dump())
    if request:
        analysis.generation_request = SourceQuote(message_id=latest.id,quote=latest.content)
    policy = reply_policy(information,result,history,request,record_subject=person)
    if policy['required_offer']:
        reply = ConversationReply(text='好，我先整理成草稿，您看过、确认后再保存。',action='offer_generation')
    else:
        reply = ConversationReply(text='好，先聊到这里。您想继续的时候再讲。')
    return analysis,information,result,validate_interview_reply(reply,history,policy)


class CompactConflict(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dimension: Literal['people', 'event', 'time', 'place', 'feeling', 'detail']
    alternatives: list[Fact] = Field(min_length=2, max_length=4)


class CompactBoundary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['independent', 'return']
    previous_event: Reference
    current_event: Reference


class CompactInterviewAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    people: Fact | None
    event: Fact | None
    time: Fact | None
    place: Fact | None
    feeling: Fact | None
    detail: Fact | None
    latest_has_narrative: bool = Field(strict=True, description='最新消息含真实经过或事实补充；纯暂停、整理安排为 false')
    conflicts: list[CompactConflict] = Field(default_factory=list, max_length=6)
    compatible_times: list[Reference] = Field(default_factory=list, max_length=8)
    compatible_places: list[Reference] = Field(default_factory=list, max_length=8)
    generation_request: Reference | None = None
    narrative_sources: list[Reference] = Field(default_factory=list, max_length=60)
    event_boundary: CompactBoundary | None = None


class CompactInterviewTurn(CompactInterviewAnalysis):
    reply: ConversationReply


def resolve_facts(value, transcript, messages, previous, primary_person_id):
    def reference(ref):
        index, start, end = ref
        if index > len(transcript):
            raise LLMResponseFormatError('消息编号必须存在于当前输入 messages')
        return {'message_id': transcript[index - 1]['id'],
                'start_fragment': start, 'end_fragment': end}

    def dimension(fact):
        return {'status': fact[0], 'source': reference(fact[1:])} if fact else {'status': 'missing'}

    fields = {key: dimension(getattr(value, key)) for key in DIMENSIONS}
    fields.update(
        conflicts=[{'dimension': c.dimension, 'alternatives': [dimension(f) for f in c.alternatives]}
                   for c in value.conflicts],
        compatible_times=[reference(r) for r in value.compatible_times],
        compatible_places=[reference(r) for r in value.compatible_places],
        guidance_hint='',
        generation_request=reference(value.generation_request) if value.generation_request else None,
        narrative_sources=[reference(r) for r in value.narrative_sources],
        latest_has_narrative=value.latest_has_narrative or is_factual_supplement(
            transcript[-1]['content'],previous.event.status.value!='missing'),
        event_boundary={'kind':value.event_boundary.kind,
                        'previous_event':reference(value.event_boundary.previous_event),
                        'current_event':reference(value.event_boundary.current_event)} if value.event_boundary else None,
    )
    texts = {m.id: m.content for m in messages if m.role == 'user' and m.type != 'notice'}
    analysis = resolve_analysis(SelectedAnalysis.model_validate(fields),texts)
    # Failed sends stay durable. A later command must also retain an earlier,
    # explicit factual supplement that has not yet been analyzed successfully.
    for message in messages:
        if (message.id in texts and message.id not in previous.analyzed_message_ids
            and is_factual_supplement(message.content,previous.event.status.value!='missing')):
            quote = message.content.strip()
            if not any(s.message_id==message.id and quote in s.quote for s in analysis.narrative_sources):
                analysis.narrative_sources = [s for s in analysis.narrative_sources
                    if s.message_id!=message.id or s.quote not in quote]
                analysis.narrative_sources.append(SourceQuote(message_id=message.id,quote=quote))
    analysis = validate_analysis(analysis,[m for m in messages if m.id in texts],previous)
    information = StoryInformation.model_validate(analysis.model_dump())
    information.conversation = previous.conversation.model_copy(deep=True)
    information = validate_information(information, messages, previous,
                                       analysis.compatible_places, analysis.compatible_times)
    result = readiness(information, messages, primary_person_id)
    return analysis,information,result


def resolve_turn(value, transcript, messages, history, previous, primary_person_id, person=None):
    analysis,information,result = resolve_facts(value,transcript,messages,previous,primary_person_id)
    policy = reply_policy(information, result, history, analysis.generation_request is not None, analysis.event_boundary, person)
    # Neither the model's readiness inference nor its action can grant permission.
    reply = validate_interview_reply(value.reply, history, policy)
    return analysis, information, result, reply


def build_interview_request(transcript, messages, history, person, previous, include_reply=True):
    # Preserve full fact and interview rules; compact the data, not the policy.
    rules = '\n'.join(line for line in STORY_INFORMATION_PROMPT.splitlines()
                      if not any(marker in line for marker in ('source={', 'source.message_id', '例如 time=', 'guidance_hint')))
    instruction = rules + """
本次引用格式：每条输入 messages 有 message_index（从 1 开始）和真实编号 fragments。
有事实的维度为 [status,消息编号,起始片段,末尾片段]。编号均必须存在，末尾不能小于起始，同一消息连续原文由后台恢复；禁止改写引文或输出 UUID。
六项维度均须返回；missing 为 null。known/approximate/unknown/withheld 仍需引用真实原话，时间优先选择单独日期片段。
latest_has_narrative 必填：最新消息含当年真实经过、事实补充或更正时为 true，后台保留完整原文用于草稿，不能只留下六项摘要。纯暂停、整理请求、会话安排为 false。短回答结合前问判断是否在补充实际经过。
conflicts.alternatives 同样为四项数组。compatible_times、compatible_places、narrative_sources 每项及 generation_request 为 [消息编号,起始片段,末尾片段]。
latest_has_narrative=true 时后台已保留最新完整原文，narrative_sources 通常省略；只有需要补充此前尚未收录的原文或明确选择局部叙事范围时再提供，不必重复给出整段长文的首尾编号。整理指令、停聊安排、明确拒绝的内容不选。
generation_request 只能引用最新消息中的真实整理请求。旧信息仅帮助理解，本轮重新选择编号。
先判断本轮事件关系：是同一事件的经过延伸、更正，还是另一件独立经历／回到先前一件事。独立或回到旧事时返回 event_boundary={kind:independent或return,previous_event:[旧消息编号,起始,末尾],current_event:[最新消息编号,起始,末尾]}，两处都选择有具体经过的原文。same 不返回 event_boundary。同一事件改年份、第二天继续练习、补充细节都不是 independent。
independent 的 reply 必须自然说清是另一段往事，最多问用户想先讲哪段或怎样记录；action=continue，不直接追问另一事件的细节。return 直接顺着回到的事交流，不重复提醒拆篇。边界只能提醒，不能自动改变原故事的六项信息、消掉既有矛盾或保存。旧故事 facts 继续引用原文，新事经过保留在 narrative_sources。
"""
    if include_reply:
        instruction += NATURAL_CONVERSATION_PROMPT.replace(
        '只返回 ConversationReply JSON，text 是本轮完整自然回复，action 与文字一致。',
        '自然回复放在 reply 字段，和原文分析一起返回。') + """
本次返回一个 CompactInterviewTurn JSON，reply 字段是完整自然回复，其余字段是分析。
本轮用户意图只以 messages 最后一条为准。history 仅包含当前段，earlier_conversation_context 仅为少量此前聊天的承接参考；不能将其中旧故事的暂停、整理请求或经过带到本轮。当前讲述更优先。
后台在收到后计算就绪及生成策略：people/event 有可理解的基本经过且无矛盾才可整理；时间地点感受可以未提供。
conversation 给出此前自动提醒使用情况。用户正在讲述时通常 continue；最新明确整理请求或明确收尾且可以整理时 offer_generation；自动提醒已用过且无最新明确请求时 continue。
用户暂停时只回应，不追问。reply 用您，最多一个问题，不推断感受，不复述整个故事。action=continue 时不提整理或保存建议。
六项维度必填，不得为缩短输出省略已提供的事实；只有尚未提供的维度为 null。直接返回 reply，不额外写引导参考或 guidance_hint。空的 conflicts、compatible_times、compatible_places、generation_request 省略。
"""
    else:
        instruction += ('\n本次仅返回 CompactInterviewAnalysis，不生成 reply 或采访文字。保留原文信息、边界和最新整理请求。'
                        '六项维度和 latest_has_narrative 必填；空 conflicts、compatible_times、compatible_places、narrative_sources 及 null 的 event_boundary、generation_request 全部省略。'
                        '已有真实事实不能为省字漏掉，引用数组只需规定的短编号，不重复字段或数据。')
    # UUIDs are for server-side provenance, not facts the model must repeat.
    previous_payload = previous.model_dump(mode='json', exclude={'conversation', 'analyzed_message_ids', 'narrative_sources'})
    for key in DIMENSIONS:
        previous_payload[key].pop('source_message_ids', None)
    for conflict in previous_payload['conflicts']:
        for alternative in conflict['alternatives']:
            alternative.pop('source_message_ids', None)
    current_ids = {str(m.id) for m in messages}
    current_history = [item for item in history if item.get('id') in current_ids]
    earlier = [item for item in history if item.get('id') not in current_ids and item['role'] != 'system']
    payload = {
        'record_subject': person,
        'earlier_conversation_context': [{key: item[key] for key in ('role', 'content')} for item in earlier[-2:]],
        'previous_information': previous_payload,
        'conversation': previous.conversation.model_dump(mode='json'),
        'history': [{key: item[key] for key in ('role', 'content')} for item in current_history],
        'messages': [{'message_index': index, 'content': item['content'], 'question': item.get('question', ''),
                      'fragments': [{'index': f['index'], 'text': f['text']} for f in source_fragments(item['content'])]}
                     for index, item in enumerate(transcript, 1)],
    }
    if not include_reply:
        # Earlier chats help a conversational hand-off, but are not evidence
        # for this story or the uncertainty of its information dimensions.
        payload.pop('earlier_conversation_context')
        payload.pop('history')
        # Prior messages remain verbatim, ordered fragments with their nearest
        # question; repeating their complete text adds no evidence. The latest
        # full text is retained for request-intent and scope checks.
        for message in payload['messages'][:-1]:
            message.pop('content')
    return instruction,payload


def interview_turn(client, transcript, messages, history, person, previous, primary_person_id):
    instruction,payload = build_interview_request(transcript,messages,history,person,previous)
    return client._structured(instruction,payload,CompactInterviewTurn,
                              lambda value:resolve_turn(value,transcript,messages,history,previous,primary_person_id,person))


def parallel_tasks(analysis_client, reply_client, transcript, messages, history, person, previous, primary_person_id):
    """Analyze provenance and interview concurrently; publish only after both checks."""
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context

    instruction,payload = build_interview_request(transcript,messages,history,person,previous,False)
    if transcript and is_explicit_continuation(transcript[-1]['content']):
        instruction += '\n最新用户用相对时间及明确指代承接原经过，是 same 的延伸；不要返回 independent 边界，不因第二天或动作发展制造时间矛盾。'
    provisional = previous.model_copy(deep=True)
    provisional.analyzed_message_ids = list(user_texts(messages))
    prior_result = readiness(previous,messages[:-1],primary_person_id)
    policy_hint = reply_policy(provisional,prior_result,history,record_subject=person)
    from app.services.story_guidance import needs_boundary_notice
    if transcript and needs_boundary_notice(transcript[-1]['content'],previous.event.status.value!='missing'):
        policy_hint.update(allowed=False,required_offer=False,boundary_reminder_required=True)
    reply_payload = {'record_subject':person,'history':history,
                     'information':previous.model_dump(mode='json',exclude={'conversation','narrative_sources','analyzed_message_ids'}),
                     'readiness':prior_result.model_dump(mode='json'),'generation_policy':policy_hint}
    for dimension in DIMENSIONS:
        reply_payload['information'][dimension].pop('source_message_ids',None)
    pool = ThreadPoolExecutor(max_workers=2,thread_name_prefix='interview-task')
    try:
        analysis_future = pool.submit(copy_context().run,analysis_client._structured,instruction,payload,
            CompactInterviewAnalysis,lambda value:resolve_facts(value,transcript,messages,previous,primary_person_id))
        reply_future = pool.submit(copy_context().run,reply_client._structured,NATURAL_CONVERSATION_PROMPT,
                                   reply_payload,ConversationReply,
                                   lambda value:validate_interview_reply(value,history,policy_hint))
        analysis,information,result = analysis_future.result()
        policy = reply_policy(information,result,history,analysis.generation_request is not None,analysis.event_boundary,person)
        try:
            reply = reply_future.result()
        except LLMResponseFormatError:
            # A second rejected interview line should not turn a saved user
            # message into an apparent send failure. Keep the response brief,
            # grounded and within the same final policy.
            reply = safe_interview_fallback(history,policy)
        try:
            reply = validate_interview_reply(reply,history,policy)
        except LLMResponseFormatError as error:
            # Only the small reply task is repaired after actual policy exists;
            # validated evidence analysis is not regenerated or relaxed.
            reply_payload['information'] = information.model_dump(mode='json',exclude={'conversation','narrative_sources','analyzed_message_ids'})
            for dimension in DIMENSIONS:
                reply_payload['information'][dimension].pop('source_message_ids',None)
            reply_payload.update(readiness=result.model_dump(mode='json'),generation_policy=policy,
                analysis_hint=analysis.guidance_hint,repair_reason=str(error))
            try:
                reply = reply_client._structured(NATURAL_CONVERSATION_PROMPT+
                    '\n上一份采访文字被原文校验拒绝，repair_reason 是具体原因。此次直接避开该错误，不再重复预设；根据实际 generation_policy 返回合格回复。',
                    reply_payload,ConversationReply,lambda value:validate_interview_reply(value,history,policy))
            except LLMResponseFormatError:
                reply = safe_interview_fallback(history,policy)
        return analysis,information,result,reply
    finally:
        pool.shutdown(wait=False,cancel_futures=True)
