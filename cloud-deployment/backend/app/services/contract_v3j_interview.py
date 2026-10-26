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

Decisions of 2026-10-23 (C01-C03), this flow only:
- the elder's signals are read for his own present intent (interview_speaker.elder_signal).
- an answer followed by "这段我不想多讲" is not a refusal (C02, reason
  'declined_partial'): no more follow-ups, the draft step as for a finished
  question (also when the engine returns limited with a declined field next
  to an answered one), with the speaking layer told '老人不想多说'. A decline
  before any real answer is still a refusal.
- after the draft offer (supplement step, C03): "没有了，就这些" and other
  general wording that nothing more is to be added goes straight to the existing
  review step, without a judgment call; a real addition is judged and recorded,
  then answered by one acknowledgement and a short "anything else" question,
  keeping the draft offer; an addition that also says it is all is recorded and
  goes to the review step. No follow-ups are asked in the supplement step.

The skeleton questions (life overview) use the same marker, judgment and
speaking-layer pieces from contract_v3j_life_overview.
"""
from copy import deepcopy

from app.ai import interview_speaker as speaker
from app.ai import interview_story as story
from app.ai.contract_interview_v3j import V3jPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.schemas.guided_interview import GuidedQuestion
from app.schemas.story_guidance import ConversationReply
from app.services.contract_interview_state import (V3J_FLOWS, V5F_PIPELINE, configured_pipeline, flow_runtime,
                                                   fresh_question)
from app.services.interview_controls import SKIP_ACK

DRAFT_TEXT = '这段可以先整理成草稿了。您还有什么想补充的吗？'
PAUSE_TEXT = '好，先休息。您的讲述和采访位置都已保留。'
REVIEW_TEXT = '好，先核对这段草稿，您确认后再保存。'  # the existing review step (contract_guided_interview.turn)
SUPPLEMENT_TEXT = '您还有别的想补充的吗？'  # after a recorded addition (C03); the draft sentence is not repeated


def question_flow(state):
    local = state.contract_state or {}
    if local:
        return local.get('pipeline') or 'v2'
    # Only the catalog the bundle was evaluated on; older catalogs stay on v2.
    configured = configured_pipeline()
    if configured in V3J_FLOWS and state.runtime_version == flow_runtime(configured).version:
        return configured
    return 'v2'


def marker(rt):
    """Flow marker and speaking-layer counters saved in a question's own state when it starts in this flow
    (v3j_v4d or v3j_v5f: the bundle's own pipeline name, so the question keeps that bundle)."""
    return {'pipeline': rt.pipeline, 'pipeline_runtime': rt.runtime_version,
            'pipeline_manifest_sha256': rt.manifest_sha256, 'followups': 0, 'asked_target': None}


def fresh(qid, rt):
    local = fresh_question(qid)
    local.update(marker(rt))
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
    candidates = ([state.pending_question.text] if state.pending_question else []) + [entry, DRAFT_TEXT, SUPPLEMENT_TEXT]
    for candidate in candidates:
        if speaker._norm(candidate) and shown_norm.endswith(speaker._norm(candidate)):
            return candidate
    return shown


def dialogue_for(messages, local, latest, entry):
    """This question's dialogue as the speaking layer was evaluated with: the entry question, then each answer
    preceded by the full message the narrator answered (v5f: answers to detail questions included)."""
    order = {str(m.id): k for k, m in enumerate(messages)}
    return dialogue_from(entry, question_answers(local, order), shown_before(messages), latest.id, latest.content)


def question_answers(local, order):
    """Judged sources and (v5f) answers to detail questions, in the order they were given."""
    extra = (local.get('deepen') or {}).get('sources') or []
    if not extra:
        return local['sources']
    return sorted(local['sources'] + extra, key=lambda s: order.get(s['id'], len(order)))


def dialogue_from(entry, sources, before, latest_id, latest_text):
    """``before`` maps each answer id to the full message shown before it (session messages or overview turns)."""
    texts = {s['id']: s['text'] for s in sources}
    asked = {s['id']: s.get('question') or '' for s in sources}
    if str(latest_id) not in texts:  # a control such as an explicit skip is the elder's last words here
        texts[str(latest_id)] = latest_text
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


def v5f(rt):
    return rt.pipeline == V5F_PIPELINE


def seen_closes(state):
    """v5f template_guard "repeat": the closes already shown in this interview (earlier questions' audits)."""
    records = [r for local in (state.contract_history or {}).values() for r in (local.get('audit') or [])]
    return story.earlier_closes(records + list((state.contract_state or {}).get('audit') or []))


def _transition(rt, client, state, qid, dialogue, fields, reason, holder, session_id):
    next_text, menu = upcoming(state)
    elder_words = ''.join(text for role, text in dialogue if role == 'elder')
    user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text,
                                prev_close=state.speaker_last_close)
    row, entry = _speak(rt, client, user, holder, session_id, state)
    reply, _ = speaker.parse_speaker(row)
    if menu:
        # The module menu is not a single question: keep the acknowledgement, then the menu as it is.
        if v5f(rt):
            ack = story.draft_ack(rt, reply, None, elder_words, seen_closes(state))
        else:
            ack = speaker.lead_ack(rt, reply, None, elder_words, drop_transition=False)
        text, ok, notes = (speaker.join(ack, next_text), True, []) if ack else (None, False, ['empty'])
    elif v5f(rt):
        text, ack, notes, ok = story.close_reply(rt, reply, next_text, elder_words, seen_closes(state))
    else:
        text, ack, notes, ok = speaker.compose_close(rt, reply, next_text, elder_words)
    if not ok:
        text = SKIP_ACK + '\n' + next_text
    if rt.speaker_config.get('listen_first') and ack == speaker.LISTENING_FALLBACK and 'ack_fallback' not in notes:
        notes.append('ack_fallback')
    return text, {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '',
                  'notes': notes, 'fallback': not ok or 'ack_fallback' in notes, 'text': text, 'raw': row.get('content'), 'call': entry}


def _draft_ack(rt, client, state, qid, dialogue, fields, reason, holder, session_id, closing=DRAFT_TEXT, step='draft'):
    # Same speaker input as a close into the next question (so the evaluated
    # wording applies); only its acknowledgement is shown before the fixed
    # sentence (the draft sentence, or the short supplement question).
    next_text, menu = upcoming(state)
    elder_words = ''.join(text for role, text in dialogue if role == 'elder')
    user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text,
                                prev_close=state.speaker_last_close)
    row, entry = _speak(rt, client, user, holder, session_id, state)
    reply, _ = speaker.parse_speaker(row)
    if v5f(rt):  # the simulator's close with the v5f guards, then only its acknowledgement
        ack = story.draft_ack(rt, reply, None if menu else next_text, elder_words, seen_closes(state))
    else:
        ack = speaker.lead_ack(rt, reply, None if menu else next_text, elder_words)
    notes = []
    if ack and step == 'supplement' and speaker._norm(ack) == speaker._norm(state.speaker_last_close):
        ack, notes = '', ['repeat_ack']  # the same acknowledgement as last time is not said again
    ack, why = speaker.listening_ack(rt, ack, elder_words)
    notes += why
    if rt.speaker_config.get('listen_first') and ack == speaker.LISTENING_FALLBACK and 'ack_fallback' not in notes:
        notes.append('ack_fallback')
    text = speaker.join(ack, closing) if ack else closing
    return ack, text, {'task': 'close', 'close_reason': reason, 'step': step, 'ack': ack, 'fallback': not ack or 'ack_fallback' in notes,
                       'notes': notes, 'text': text, 'raw': row.get('content'), 'call': entry}


def review_step(previous, state, messages):
    """The existing review step: the elder has nothing more to add (no model call)."""
    from app.services.contract_guided_interview import _project
    state.phase = 'review'
    state.pending_question = None
    return _project(previous, state, messages), ConversationReply(text=REVIEW_TEXT, action='offer_generation')


def finish(local, outcome, spoken, asked=None, *, calls=None):
    result = outcome['result']
    # A deepen call can finish without a question (failure, rejected output or
    # model skip), so it is not necessarily attached to ``spoken``. Archive the
    # whole request before clearing pending. Skeleton turns own their pending
    # holder at overview level and pass it explicitly.
    if calls is None:
        calls = (local.get('pending') or {}).get('calls') or {}
    outcome = {**outcome, 'speaker': spoken, 'calls': {**calls, **outcome['calls']}}
    if spoken and spoken.get('call'):
        outcome['calls'] = {**outcome['calls'], 'speaker': spoken.pop('call')}
    if spoken and spoken.get('deepen_call'):
        outcome['calls'] = {**outcome['calls'], 'deepen': spoken.pop('deepen_call')}
    local['audit'].append(deepcopy(outcome))
    local['last_result'] = deepcopy(result)
    local['pending'] = None
    local['fields'] = deepcopy(result['fields'])
    # Counts are the follow-ups actually asked, as the speaking layer's ending rules read them.
    if asked:
        local['ask_counts'][asked] = local['ask_counts'].get(asked, 0) + 1
        local['followups'] = local.get('followups', 0) + 1
    local['asked_target'] = asked


# --------------------------------------------------------------------------- v5f story deepening
DEEPEN_KEY = 'deepen'  # GuidedQuestion key/target of a detail question (not an element of the contract)


def try_deepen(rt, client, local, qid, reason, text, dialogue, holder, save_call, asked_text, before):
    """v5f: one more detail question on a story question, before the close (interview.session's deepen branch).
    Returns (dimension, ack, question, record) when one is asked, else (None, None, None, record): the normal close
    follows. The deepen call is saved with the pending request like every other call."""
    if not v5f(rt) or qid not in rt.story:
        return None, None, None, None
    dz = local.setdefault('deepen', story.new_deepen(rt, qid))
    elder_words = ''.join(t for role, t in dialogue if role == 'elder')
    dz['asked_text'], dz['before'], dz['last'] = asked_text, before, text  # read by signal_scope / check_deepen
    k = len(local['sources']) + len(dz.get('sources') or [])
    if dz.get('stopped'):
        ok, why, info = False, 'stopped_' + dz['stopped'], {}
    else:
        ok, why, info = story.deepen_gate(rt.speaker_config, reason, text, elder_words, dz, k)
    log = {'k': k, 'decision': 'asked' if ok else 'skip', 'reason': why, **info}
    if not ok:
        return None, None, None, log
    # the question parts asked so far in this question (the simulator's question_part of each system message)
    prior = [s.get('question') for s in question_answers(local, {})]
    user = story.deepen_user(rt, qid, dialogue, dz)
    row, call = V3jPipeline(rt, client).deepen(user, saved_calls=holder['calls'], save_call=save_call)
    dim, ack, question, errs, repairs = story.compose_deepen(rt, row, dz, prior, elder_words)
    log.update({'dimension': dim, 'ack': ack, 'question': question, 'errors': errs, 'repairs': repairs,
                'raw': row.get('content'), 'input': user, 'call': call})
    if errs:
        log['decision'] = 'skip'
        log['reason'] = 'invalid' if errs[0] not in ('call_failed', 'model_skip') else errs[0]
        return None, None, None, log
    return dim, ack, question, log


def saver(holder, session_id, state):
    def save_call(stage, entry):
        from app.services.contract_guided_interview import _persist_pending
        holder['calls'][stage] = entry
        _persist_pending(session_id, state)
    return save_call


def keep_log(dz, log):
    if log is not None:
        dz['log'].append({k: v for k, v in log.items() if k != 'call'})


def ask_deepen(state, local, dim, ack, question):
    """Show a detail question and wait for its answer (no judgment of that answer)."""
    dz = local['deepen']
    dz['asked'] += 1
    dz['dims'].append(dim)
    dz['awaiting'] = True
    state.phase = 'exploring'
    state.pending_question = GuidedQuestion(key=DEEPEN_KEY, target=DEEPEN_KEY, text=question,
                                            accept_rule='细节问答，原话记入本题来源，不再判定。')
    return ConversationReply(text=speaker.join(ack, question))


def clean_dz(dz):
    for key in ('asked_text', 'before', 'last', 'partial'):
        dz.pop(key, None)


def deepen_answer_turn(client, previous, state, messages, latest, rt, qid, entry):
    """The elder answered a detail question: kept verbatim as a source of this question, not judged, no field
    changes (deepen_close); then one more detail question or the question's normal close (draft step)."""
    from app.services.contract_guided_interview import _persist_pending, _project, coverage
    local = state.contract_state
    dz = local['deepen']
    if local.get('pending') is None:
        local['pending'] = {'request_id': str(latest.id), 'calls': {}, 'kind': 'deepen_answer'}
    if local['pending']['request_id'] != str(latest.id):
        raise LLMResponseFormatError('Retry the retained pending answer first')
    asked = asked_part(shown_before(messages).get(str(latest.id), ''), state, entry)
    dz.setdefault('sources', [])
    if not any(s['id'] == str(latest.id) for s in dz['sources']):
        dz['sources'].append({'id': str(latest.id), 'text': latest.content, 'question_id': qid, 'speaker': 'narrator',
                              'question': asked, 'dimension': dz['dims'][-1], 'deepen_answer': True})
    _persist_pending(latest.session_id, state)
    dialogue = dialogue_for(messages, local, latest, entry)
    elder = [t for role, t in dialogue if role == 'elder']
    before = ''.join(elder[:-1])
    cfg = rt.speaker_config
    scope = (asked, before, cfg.get('scope_min_chars', 15)) if cfg.get('signal_scope') else None
    action, reason = story.deepen_close(latest.content, None, cfg['deepen'].get('extra_guards'), scope)
    rule = {'action': action, 'reason': reason, 'signal': speaker.elder_signal(latest.content)}
    holder = local['pending']
    record = {'pipeline': 'v5f', 'kind': 'deepen_answer', 'request_id': str(latest.id), 'rule': rule}
    # dz['awaiting'] stays set until this request ends: a retry after a saved call must come back here
    if action == 'rest':
        # The existing pause; detail questions stop here (on "继续" the question resumes at its entry question).
        dz['stopped'], dz['awaiting'] = 'rest', False
        clean_dz(dz)
        record['calls'] = deepcopy(holder['calls'])
        local['audit'].append(record)
        local['pending'] = None
        state.pending_question = None
        state.resume_phase = state.phase
        state.phase = 'paused'
        return _project(previous, state, messages), ConversationReply(text=PAUSE_TEXT)
    dim, ack, question, log = try_deepen(rt, client, local, qid, reason, latest.content, dialogue, holder,
                                         saver(holder, latest.session_id, state), asked, before)
    keep_log(dz, log)
    if question:
        record['deepen'] = {k: v for k, v in log.items() if k != 'call'}
        record['calls'] = deepcopy(holder['calls'])
        local['audit'].append(record)
        local['pending'] = None
        clean_dz(dz)
        reply = ask_deepen(state, local, dim, ack, question)
        return _project(previous, state, messages), reply
    clean_dz(dz)
    fields = speaker.recorded_fields(rt, local.get('last_result'))
    ack, text, spoken = _draft_ack(rt, client, state, qid, dialogue, fields, reason, holder, latest.session_id)
    dz['awaiting'] = False
    spoken.pop('call', None)
    record.update({'speaker': {**spoken, **rule}, 'calls': deepcopy(holder['calls'])})
    local['audit'].append(record)
    local['pending'] = None
    state.pending_question = None
    if ack:
        state.speaker_last_close = ack
    state.phase = 'supplement'
    coverage(state)
    return _project(previous, state, messages), ConversationReply(text=text, action='offer_generation')


def question_turn(client, previous, state, messages, latest):
    from app.services.contract_guided_interview import _persist_pending, _project, coverage, skip_topic
    from app.services.interview_modules import topic_for
    topic = topic_for(state)
    qid, entry = topic.id, topic.text
    rt = flow_runtime(question_flow(state))
    # After the draft offer: an answer that only says there is nothing more goes to the review step (C03).
    supplementing = state.phase in ('supplement', 'review')
    ending = (speaker.supplement_end(latest.content, listen_first=bool(rt.speaker_config.get('listen_first')))
              if supplementing else None)
    if ending == 'only':
        if state.contract_state:
            state.contract_state['audit'].append({'pipeline': 'v4d', 'kind': 'supplement_end', 'request_id': str(latest.id),
                                                  'supplement_end': ending})
        return review_step(previous, state, messages)
    if not state.contract_state:
        state.contract_state = fresh(qid, rt)
    local = state.contract_state
    if local['question_id'] != qid:
        raise LLMResponseFormatError('Interview checkpoint belongs to a different question')
    if (local.get('deepen') or {}).get('awaiting') and not supplementing:
        return deepen_answer_turn(client, previous, state, messages, latest, rt, qid, entry)
    asked_now = asked_part(shown_before(messages).get(str(latest.id), ''), state, entry)
    append_source(local, latest.id, latest.content, asked_now)
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
    dialogue = dialogue_for(messages, local, latest, entry)
    before = ''.join([t for role, t in dialogue if role == 'elder'][:-1])
    st = {'followups': local.get('followups', 0), 'ask_counts': local.get('ask_counts', {}),
          'prev_eff': dict((local.get('last_result') or {}).get('effective') or {})}
    if rt.speaker_config.get('signal_scope'):  # read by signal_scope only (v5f)
        st.update(asked=asked_now, before=before, last_target=local.get('asked_target'))
    action, arg = speaker.decide(rt.speaker_config, result, st, latest.content)
    # decide closes engine skipped / limited+declined as 'declined' unless the elder had already answered
    # ('declined_partial', C02), so the reason alone tells a refusal.
    refused = arg in ('declined', 'deferred')
    fields = speaker.recorded_fields(rt, result)
    holder = local['pending']
    rule = {'action': action, 'reason': arg, 'signal': st['signal']}
    if st.get('scope'):
        rule['scope'] = st['scope'][0]
    if supplementing:
        rule['supplement_end'] = ending
    # The speaking-layer call is persisted with the pending request; question
    # state that a retry recomputes from (pending question, sources) changes
    # only after it.
    if supplementing and action != 'rest' and not (refused and not speaker.has_content(result)):
        # Supplement step (C03): the addition is recorded; no follow-up is asked and the draft offer stays.
        # "That's all" with an addition, or not wanting to go on: recorded, then the review step.
        if ending == 'with_content' or refused or arg == 'declined_partial' or st['signal'] == 'declined':
            finish(local, outcome, {'task': 'review', 'step': 'review', **rule})
            coverage(state)
            return review_step(previous, state, messages)
        reason = arg if action == 'close' else 'limited'
        ack, text, spoken = _draft_ack(rt, client, state, qid, dialogue, fields, reason, holder, latest.session_id,
                                       closing=SUPPLEMENT_TEXT, step='supplement')
        finish(local, outcome, {**spoken, **rule})
        state.pending_question = None
        if ack:
            state.speaker_last_close = ack
        state.phase = 'supplement'
        reply = ConversationReply(text=text, action='offer_generation')
        coverage(state)
        return _project(previous, state, messages), reply
    if action == 'close' and not refused:
        # v5f: a story question whose elements are complete may get a detail question before the draft step.
        dim, ack, question, log = try_deepen(rt, client, local, qid, arg, latest.content, dialogue, holder,
                                             save_call, asked_now, before)
        if log is not None:
            dz = local['deepen']
            keep_log(dz, log)
            clean_dz(dz)
            if question:
                finish(local, outcome, {'task': 'deepen', **{k: v for k, v in log.items() if k != 'call'},
                                        'deepen_call': log.get('call'), **rule})
                reply = ask_deepen(state, local, dim, ack, question)
                coverage(state)
                return _project(previous, state, messages), reply
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
    """Explicit skip control in a v3j question: acknowledged by the speaking layer, then the existing skip.
    v5f: a skip while a detail question waits is not a refusal (the question was answered before it): the draft
    step follows, as the simulator closes it ('declined_partial')."""
    from app.services.contract_guided_interview import _project, coverage, skip_topic
    from app.services.interview_modules import topic_for
    latest = next(m for m in reversed(messages) if m.role == 'user')
    topic = topic_for(state)
    qid, entry = topic.id, topic.text
    rt = flow_runtime(question_flow(state))
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
    dz = local.get('deepen') or {}
    if dz.get('awaiting') and state.phase not in ('supplement', 'review'):
        ack, text, spoken = _draft_ack(rt, client, state, qid, dialogue_for(messages, local, latest, entry), fields,
                                       'declined_partial', holder, latest.session_id)
        spoken['call'] = None
        dz['awaiting'] = False
        dz['log'].append({'k': len(local['sources']) + len(dz.get('sources') or []) + 1, 'decision': 'stop',
                          'reason': 'answer_skip_control'})
        local['audit'].append({'pipeline': 'v5f', 'kind': 'skip_control', 'request_id': str(latest.id),
                               'speaker': spoken, 'calls': deepcopy(holder['calls'])})
        state.pending_question = None
        if ack:
            state.speaker_last_close = ack
        state.phase = 'supplement'
        coverage(state)
        return _project(previous, state, messages), ConversationReply(text=text, action='offer_generation')
    text, spoken = _transition(rt, client, state, qid, dialogue_for(messages, local, latest, entry), fields, 'declined',
                               holder, latest.session_id)
    spoken['call'] = None
    local['audit'].append({'pipeline': 'v4d', 'kind': 'skip_control', 'request_id': str(latest.id),
                           'speaker': spoken, 'calls': deepcopy(holder['calls'])})
    state.speaker_last_close = text
    return skip_topic(previous, state, messages, text=text)
