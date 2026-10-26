"""62-question runtime behind the existing App guided-interview entry points."""
from copy import deepcopy
import re
from uuid import UUID
from app.ai.contract_interview import ContractInterviewPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.schemas.guided_interview import GuidedInterviewState, GuidedQuestion
from app.schemas.story_guidance import ConversationReply, StoryReadiness
from app.schemas.story_information import SourceQuote
from app.services.contract_interview_state import (
    runtime, questions, fresh_question, context_for, append_source, finish_question_turn, V3J_FLOWS,
)
from app.services.interview_controls import skips_question, SKIP_ACK


def coverage(state):
    result = (state.contract_state or {}).get('last_result') or {}
    values = result.get('effective', {})
    state.coverage = {key: values.get(key) in ('known', 'none') for key in result.get('active', [])}
    return state.coverage


def readiness(state, messages, person_id, completed=False):
    from app.services.guided_interview import current_sources
    values = coverage(state)
    result = (state.contract_state or {}).get('last_result') or {}
    conflicts = [key for key, value in result.get('effective', {}).items() if value == 'conflict']
    has_text = bool(current_sources(messages))
    valid = result.get('decision') not in (None, 'invalid')
    ready = has_text and valid and person_id is not None and not conflicts and not completed and not state.last_topic_skipped
    return StoryReadiness(ready=ready, missing_dimensions=[k for k, v in values.items() if not v],
        conflicting_dimensions=conflicts, message='这段回忆已保存。' if completed else
        '可以先整理现有讲述，也可以继续补充。' if ready else '请先讲述您想留下的回忆。')


def _project(previous, state, messages):
    from app.services.guided_interview import current_sources
    information = previous.model_copy(deep=True)
    sources = current_sources(messages)
    information.narrative_sources = [SourceQuote(message_id=s['message_id'], quote=s['content']) for s in sources][-60:]
    information.analyzed_message_ids = [UUID(s['message_id']) for s in sources]
    information.guided_interview = state
    return information


def _persist_pending(session_id, state):
    from app.db.database import SessionLocal
    from app.models.chat_session import ChatSessionModel
    from app.schemas.story_information import StoryInformation
    with SessionLocal.begin() as db:
        model = db.get(ChatSessionModel, str(session_id), with_for_update=True)
        info = StoryInformation.model_validate(model.information or {})
        info.guided_interview = state.model_copy(deep=True)
        model.information = info.model_dump(mode='json')


def turn(client, previous, messages):
    from app.services.guided_interview import current_sources, opening_text
    from app.services.interview_modules import module_menu, requested_module, topic_for
    state = previous.guided_interview.model_copy(deep=True)
    latest = next(m for m in reversed(messages) if m.role == 'user')
    text = latest.content.strip()
    if not state.module_selected:
        return _project(previous, state, messages), ConversationReply(text='您的讲述已保留。' + module_menu())
    if requested_module(text) == state.module:
        return _project(previous, state, messages), ConversationReply(
            text=state.pending_question.text if state.pending_question else opening_text(state))
    if re.fullmatch(r'(?:先休息|先暂停|暂停|今天先不聊|暂时不想讲)[。！!\s]*', text):
        state.resume_phase = state.phase
        state.phase = 'paused'
        return _project(previous, state, messages), ConversationReply(text='好，先休息。您的讲述和采访位置都已保留。')
    if state.phase == 'paused':
        state.phase = state.resume_phase or 'exploring'
        state.resume_phase = None
        if re.fullmatch(r'(?:继续|继续聊|接着讲)[。！!\s]*', text):
            return _project(previous, state, messages), ConversationReply(
                text=state.pending_question.text if state.pending_question else opening_text(state))
    if state.topic_index >= len(questions(state.module, state.runtime_version)):
        state.phase = 'finished'
        return _project(previous, state, messages), ConversationReply(text='这部分的问题已经聊过了。' + module_menu())
    if skips_question(text):
        return skip_topic(previous, state, messages, client)
    state.last_topic_skipped = False
    if state.phase in ('supplement', 'review') and re.fullmatch(
            r'(?:没有(?:了|补充了)?|没有别的补充了|先保存|确认保存|保存吧|就这些)[。！!\s]*', text):
        state.phase = 'review'
        state.pending_question = None
        return _project(previous, state, messages), ConversationReply(
            text='好，先核对这段草稿，您确认后再保存。', action='offer_generation')
    from app.services.contract_v3j_interview import question_flow, question_turn
    if question_flow(state) in V3J_FLOWS:
        return question_turn(client, previous, state, messages, latest)
    qid = topic_for(state).id
    if not state.contract_state:
        state.contract_state = fresh_question(qid)
    local = state.contract_state
    if local['question_id'] != qid:
        raise LLMResponseFormatError('Interview checkpoint belongs to a different question')
    # The latest preceding assistant message is the actual question shown in the
    # App; the stored prior target supplies only the same-question follow-up role.
    asked = ''
    for message in messages:
        if message.id == latest.id:
            break
        if message.role == 'assistant' and message.type != 'notice':
            asked = message.content
    append_source(local, latest.id, latest.content, asked)
    if local.get('pending') is None:
        local['pending'] = {'request_id': str(latest.id), 'calls': {}}
    if local['pending']['request_id'] != str(latest.id):
        raise LLMResponseFormatError('Retry the retained pending answer first')
    _persist_pending(latest.session_id, state)

    def save_call(stage, entry):
        local['pending']['calls'][stage] = entry
        _persist_pending(latest.session_id, state)

    outcome = ContractInterviewPipeline(runtime(state.runtime_version), client).run(qid, local['sources'], context_for(local),
        saved_calls=local['pending']['calls'], save_call=save_call)
    if outcome['result']['decision'] == 'invalid':
        # One repair ends this attempt. A later explicit API retry may start a
        # fresh attempt from the retained answer; failed attempts are never erased
        # or automatically retried in a loop, and the user need not retype it.
        local['pending']['invalid_result'] = outcome
        local['pending'].setdefault('failed_attempts', []).append(outcome)
        local['audit'].append(deepcopy(outcome))
        local['pending']['calls'] = {}
        _persist_pending(latest.session_id, state)
        raise LLMResponseFormatError('Interview evidence remains invalid after one internal repair')
    finish_question_turn(local, outcome)
    result = outcome['result']
    decision = result['decision']
    if decision in ('skipped', 'deferred') or (decision == 'limited' and 'declined' in result.get('effective', {}).values()):
        return skip_topic(previous, state, messages)
    state.pending_question = None
    if decision in ('ask', 'ask_defer'):
        state.phase = 'exploring'
        state.pending_question = GuidedQuestion(key=result['target'], target=result['target'],
            text=result['question'], accept_rule='按本题已冻结要素合同判断。')
        reply = ConversationReply(text=result['question'])
    elif decision == 'paused':
        state.resume_phase = state.phase
        state.phase = 'paused'
        reply = ConversationReply(text='好，先休息。您的讲述和采访位置都已保留。')
    else:
        state.phase = 'supplement'
        reply = ConversationReply(text='这段可以先整理成草稿了。您还有什么想补充的吗？', action='offer_generation')
    coverage(state)
    return _project(previous, state, messages), reply


def skip_topic(previous, state, messages, client=None, text=None):
    """Close the question as skipped. ``text`` is a reply already composed by a v3j flow (v3j_v4d / v3j_v5f); with
    a client, an explicit skip in a question of such a flow is acknowledged by its speaking layer first."""
    from app.services.guided_interview import opening_text
    from app.services.interview_modules import topic_for
    if text is None and client is not None:
        from app.services.contract_v3j_interview import question_flow, skip_turn
        if question_flow(state) in V3J_FLOWS:
            return skip_turn(client, previous, state, messages)
    state.processed_topics[topic_for(state).id] = 'skipped'
    # following archives raw sources, provider failures and old fields intact.
    state = following(state)
    state.last_topic_skipped = True
    from app.services.interview_modules import module_menu
    next_text = module_menu() if state.phase == 'module_review' else opening_text(state)
    return _project(previous, state, messages), ConversationReply(text=SKIP_ACK + '\n' + next_text if text is None else text)


def following(previous):
    state = previous.model_copy(deep=True)
    state.topic_index = min(previous.topic_index + 1, len(questions(previous.module, previous.runtime_version)))
    state.contract_history = {**state.contract_history}
    if state.contract_state:
        state.contract_history[state.contract_state['question_id']] = deepcopy(state.contract_state)
    state.contract_state = {}
    state.facts = []; state.units = []; state.links = []
    state.pending_question = None; state.answered_targets = []; state.asked_targets = {}
    state.unavailable_targets = []; state.coverage = {}; state.process_closed = False
    state.answer_status = None; state.resume_phase = None
    state.phase = 'opening'
    if state.topic_index == len(questions(state.module, state.runtime_version)):
        state.phase = 'module_review'
        if state.module not in state.completed_modules:
            state.completed_modules.append(state.module)
    return state


def assess_module(state):
    # Module completion is the declared question coverage, never an arbitrary
    # count of stories and never a second model deciding which facts exist.
    all_ids = {q['id'] for q in questions(state.module, state.runtime_version)}
    processed = set(state.processed_topics)
    state.chapter_ready = all_ids.issubset(processed) and bool(state.material_memory_ids)
    state.module_assessed_count = len(state.saved_memory_ids)
    return state
