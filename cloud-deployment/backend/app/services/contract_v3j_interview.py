"""v3j judgment + v4d speaking layer behind the existing guided-interview turn.

The flow is chosen per question. A question keeps the flow it started with: the
marker is saved in its own contract_state together with its sources, pending
calls and fields, and questions are independent, so no pending call or earlier
answer ever crosses flows. A question not yet started follows INTERVIEW_PIPELINE
(default v2). States without the marker were written by the v2 flow.

Replies keep the existing steps (decisions of 2026-10-22):
- follow-up (engine ask/ask_defer): the speaking layer writes ack + question;
  the engine still decides the target; failure falls back to the engine question.
- question finished (ready, limited, and the v4d natural endings: elder says he
  cannot remember, follow-up caps): the speaking layer adds one acknowledgement
  in front of the existing draft sentence, which keeps action offer_generation.
- explicit refusal (skip control, engine skipped/deferred/limited+declined, and
  the v4d signal that the elder does not want to talk about it): the speaking
  layer acknowledges and moves to the next entry; failure falls back to
  SKIP_ACK + next entry. No save offer; the skip state logic is unchanged.
- pause (engine paused, or the elder says he is tired): existing fixed text.
"""
from copy import deepcopy

from app.ai import interview_speaker as speaker
from app.ai.contract_interview_v3j import V3jPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.schemas.guided_interview import GuidedQuestion
from app.schemas.story_guidance import ConversationReply
from app.services.contract_interview_state import V3J_PIPELINE, configured_pipeline, fresh_question, v3j_runtime
from app.services.interview_controls import SKIP_ACK

DRAFT_TEXT = '这段可以先整理成草稿了。您还有什么想补充的吗？'
PAUSE_TEXT = '好，先休息。您的讲述和采访位置都已保留。'


def question_flow(state):
    local = state.contract_state or {}
    if local:
        return local.get('pipeline') or 'v2'
    # Only the catalog the bundle was evaluated on; older catalogs stay on v2.
    if configured_pipeline() == V3J_PIPELINE and state.runtime_version == v3j_runtime().version:
        return V3J_PIPELINE
    return 'v2'


def fresh(qid, rt):
    local = fresh_question(qid)
    local.update({'pipeline': V3J_PIPELINE, 'pipeline_runtime': rt.runtime_version,
                  'pipeline_manifest_sha256': rt.manifest_sha256, 'followups': 0, 'asked_target': None})
    return local


def context_for(local):
    return {'previous_fields': deepcopy(local.get('fields', {})), 'ask_counts': deepcopy(local.get('ask_counts', {})),
            'focus': {'field_id': local['asked_target']} if local.get('asked_target') else None}


def append_source(local, identity, text, asked):
    source = {'id': str(identity), 'text': text, 'question_id': local['question_id'], 'speaker': 'narrator', 'question': asked}
    if local.get('asked_target'):
        source['target_field_id'] = local['asked_target']
    prior = next((s for s in local['sources'] if s['id'] == str(identity)), None)
    if prior is None:
        local['sources'].append(source)
    elif prior != source:
        raise LLMResponseFormatError('A saved answer cannot be changed during retry')


def shown_before(messages):
    """For each message, the latest non-notice assistant message shown before it."""
    out, last = {}, ''
    for message in messages:
        out[str(message.id)] = last
        if message.role == 'assistant' and message.type != 'notice':
            last = message.content
    return out


def asked_part(shown, state, entry):
    """The question part of what was last shown, which is what the judgment was evaluated with: a follow-up
    without its acknowledgement, a transition without its close, the draft sentence alone."""
    shown_norm = speaker._norm(shown)
    candidates = ([state.pending_question.text] if state.pending_question else []) + [entry, DRAFT_TEXT]
    for candidate in candidates:
        if speaker._norm(candidate) and shown_norm.endswith(speaker._norm(candidate)):
            return candidate
    return shown


def dialogue_for(messages, local, latest, entry):
    """This question's dialogue as the speaking layer was evaluated with: the entry question, then each answer
    preceded by the full message the narrator answered."""
    before = shown_before(messages)
    texts = {s['id']: s['text'] for s in local['sources']}
    asked = {s['id']: s.get('question') or '' for s in local['sources']}
    if str(latest.id) not in texts:  # a control such as an explicit skip is the elder's last words here
        texts[str(latest.id)] = latest.content
    out = [('system', entry)]
    for k, identity in enumerate(texts):
        if k:
            out.append(('system', before.get(identity) or asked.get(identity, '')))
        out.append(('elder', texts[identity]))
    return out


def upcoming(state):
    """The text that follows this question, exactly as skip_topic shows it: next entry or the module menu."""
    from app.services.contract_guided_interview import following
    from app.services.guided_interview import opening_text
    from app.services.interview_modules import module_menu
    state = following(state)
    return (module_menu(), True) if state.phase == 'module_review' else (opening_text(state), False)


def _speak(rt, client, user, holder, session_id, state):
    from app.services.contract_guided_interview import _persist_pending

    def save_call(stage, entry):
        holder['calls'][stage] = entry
        _persist_pending(session_id, state)

    row, entry = V3jPipeline(rt, client).speak(user, saved_calls=holder['calls'], save_call=save_call)
    return row, entry


def _transition(rt, client, state, qid, dialogue, fields, reason, holder, session_id):
    next_text, menu = upcoming(state)
    elder_words = ''.join(text for role, text in dialogue if role == 'elder')
    user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text,
                                prev_close=state.speaker_last_close)
    row, entry = _speak(rt, client, user, holder, session_id, state)
    reply, _ = speaker.parse_speaker(row)
    if menu:
        # The module menu is not a single question: keep the acknowledgement, then the menu as it is.
        ack = speaker.lead_ack(rt, reply, None, elder_words, drop_transition=False)
        text, ok, notes = (speaker.join(ack, next_text), True, []) if ack else (None, False, ['empty'])
    else:
        text, ack, notes, ok = speaker.compose_close(rt, reply, next_text, elder_words)
    if not ok:
        text = SKIP_ACK + '\n' + next_text
    return text, {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '',
                  'notes': notes, 'fallback': not ok, 'text': text, 'raw': row.get('content'), 'call': entry}


def _draft_ack(rt, client, state, qid, dialogue, fields, reason, holder, session_id):
    # Same speaker input as a close into the next question (so the evaluated
    # wording applies); only its acknowledgement is shown before the draft sentence.
    next_text, menu = upcoming(state)
    elder_words = ''.join(text for role, text in dialogue if role == 'elder')
    user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text,
                                prev_close=state.speaker_last_close)
    row, entry = _speak(rt, client, user, holder, session_id, state)
    reply, _ = speaker.parse_speaker(row)
    ack = speaker.lead_ack(rt, reply, None if menu else next_text, elder_words)
    text = speaker.join(ack, DRAFT_TEXT) if ack else DRAFT_TEXT
    return ack, text, {'task': 'close', 'close_reason': reason, 'step': 'draft', 'ack': ack, 'fallback': not ack,
                       'text': text, 'raw': row.get('content'), 'call': entry}


def finish(local, outcome, spoken, asked=None):
    result = outcome['result']
    outcome = {**outcome, 'speaker': spoken}
    if spoken and spoken.get('call'):
        outcome['calls'] = {**outcome['calls'], 'speaker': spoken.pop('call')}
    local['audit'].append(deepcopy(outcome))
    local['last_result'] = deepcopy(result)
    local['pending'] = None
    local['fields'] = deepcopy(result['fields'])
    # Counts are the follow-ups actually asked, as the speaking layer's ending rules read them.
    if asked:
        local['ask_counts'][asked] = local['ask_counts'].get(asked, 0) + 1
        local['followups'] = local.get('followups', 0) + 1
    local['asked_target'] = asked


def question_turn(client, previous, state, messages, latest):
    from app.services.contract_guided_interview import _persist_pending, _project, coverage, skip_topic
    from app.services.interview_modules import topic_for
    rt = v3j_runtime()
    topic = topic_for(state)
    qid, entry = topic.id, topic.text
    if not state.contract_state:
        state.contract_state = fresh(qid, rt)
    local = state.contract_state
    if local['question_id'] != qid:
        raise LLMResponseFormatError('Interview checkpoint belongs to a different question')
    append_source(local, latest.id, latest.content, asked_part(shown_before(messages).get(str(latest.id), ''), state, entry))
    if local.get('pending') is None:
        local['pending'] = {'request_id': str(latest.id), 'calls': {}}
    if local['pending']['request_id'] != str(latest.id):
        raise LLMResponseFormatError('Retry the retained pending answer first')
    _persist_pending(latest.session_id, state)

    def save_call(stage, entry_):
        local['pending']['calls'][stage] = entry_
        _persist_pending(latest.session_id, state)

    outcome = V3jPipeline(rt, client).run(qid, local['sources'], context_for(local),
                                          saved_calls=local['pending']['calls'], save_call=save_call)
    result = outcome['result']
    if result['decision'] == 'invalid':
        # Same as the v2 flow: the answer and failure stay; an explicit retry
        # starts a new bounded attempt; nothing is asked from an invalid result.
        local['pending']['invalid_result'] = outcome
        local['pending'].setdefault('failed_attempts', []).append(outcome)
        local['audit'].append(deepcopy(outcome))
        local['pending']['calls'] = {}
        _persist_pending(latest.session_id, state)
        raise LLMResponseFormatError('Interview evidence remains invalid')
    st = {'followups': local.get('followups', 0), 'ask_counts': local.get('ask_counts', {}),
          'prev_eff': dict((local.get('last_result') or {}).get('effective') or {})}
    action, arg = speaker.decide(rt.speaker_config, result, st, latest.content)
    decision = result['decision']
    refused = arg in ('declined', 'deferred') or (decision == 'limited' and 'declined' in result.get('effective', {}).values())
    dialogue = dialogue_for(messages, local, latest, entry)
    fields = speaker.recorded_fields(rt, result)
    holder = local['pending']
    rule = {'action': action, 'reason': arg, 'signal': st['signal']}
    # The speaking-layer call is persisted with the pending request; question
    # state that a retry recomputes from (pending question, sources) changes
    # only after it.
    if action == 'ask':
        user = speaker.speaker_user(rt, qid, dialogue, fields, 'ask', arg, result.get('question'))
        row, entry_ = _speak(rt, client, user, holder, latest.session_id, state)
        text, question, spoken = speaker.compose_ask(rt, row, result, arg, [s['question'] for s in local['sources']],
                                                     ''.join(t for role, t in dialogue if role == 'elder'))
        finish(local, outcome, {'task': 'ask', **spoken, 'text': text, 'raw': row.get('content'), 'call': entry_, **rule}, asked=arg)
        state.phase = 'exploring'
        state.pending_question = GuidedQuestion(key=arg, target=arg, text=question, accept_rule='按本题已冻结要素合同判断。')
        reply = ConversationReply(text=text)
    elif action == 'rest':
        finish(local, outcome, rule)
        state.pending_question = None
        state.resume_phase = state.phase
        state.phase = 'paused'
        reply = ConversationReply(text=PAUSE_TEXT)
    elif refused:
        text, spoken = _transition(rt, client, state, qid, dialogue, fields, arg if arg in ('declined', 'deferred') else 'declined',
                                   holder, latest.session_id)
        finish(local, outcome, {**spoken, **rule})
        state.speaker_last_close = text
        return skip_topic(previous, state, messages, text=text)
    else:
        ack, text, spoken = _draft_ack(rt, client, state, qid, dialogue, fields, arg, holder, latest.session_id)
        finish(local, outcome, {**spoken, **rule})
        state.pending_question = None
        if ack:
            state.speaker_last_close = ack
        state.phase = 'supplement'
        reply = ConversationReply(text=text, action='offer_generation')
    coverage(state)
    return _project(previous, state, messages), reply


def skip_turn(client, previous, state, messages):
    """Explicit skip control in a v3j question: acknowledged by the speaking layer, then the existing skip."""
    from app.services.contract_guided_interview import skip_topic
    from app.services.interview_modules import topic_for
    rt = v3j_runtime()
    latest = next(m for m in reversed(messages) if m.role == 'user')
    topic = topic_for(state)
    qid, entry = topic.id, topic.text
    if not state.contract_state:
        state.contract_state = fresh(qid, rt)
    local = state.contract_state
    if local['question_id'] != qid:
        raise LLMResponseFormatError('Interview checkpoint belongs to a different question')
    # Kept beside (never inside) a pending failed answer, which is archived intact.
    if (local.get('skip') or {}).get('request_id') != str(latest.id):
        local['skip'] = {'request_id': str(latest.id), 'calls': {}}
    holder = local['skip']
    fields = speaker.recorded_fields(rt, local.get('last_result'))
    text, spoken = _transition(rt, client, state, qid, dialogue_for(messages, local, latest, entry), fields, 'declined',
                               holder, latest.session_id)
    spoken['call'] = None
    local['audit'].append({'pipeline': 'v4d', 'kind': 'skip_control', 'request_id': str(latest.id),
                           'speaker': spoken, 'calls': deepcopy(holder['calls'])})
    state.speaker_last_close = text
    return skip_topic(previous, state, messages, text=text)
