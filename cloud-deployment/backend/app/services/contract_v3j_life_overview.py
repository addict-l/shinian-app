"""v3j judgment + v4d speaking layer behind the life-overview (skeleton) API.

Same judgment implementation and pinned bundle as the guided interview
(contract_v3j_interview). The flow is chosen per skeleton question: the marker is
saved in the question's own entry of ``life_interview['questions']``; a question
that already has sources, audit records or a status was started by the v2 flow
and keeps it, and a question not yet started follows INTERVIEW_PIPELINE
(default v2), for the catalog the bundle was evaluated on only.

The skeleton has no draft step, so a finished question closes the way the v4d
simulated interviews were tested: one acknowledgement, then the next skeleton
question in the same message (compose_close). Decisions of 2026-10-22:
- follow-up (engine ask/ask_defer): the speaking layer writes ack + question;
  failure falls back to the engine question.
- question finished (ready, limited, the v4d endings: cannot remember, caps):
  speaking-layer close into the next skeleton question; failure falls back to
  the existing "我记下了。" + next question.
- explicit refusal (skip control, engine skipped/deferred/limited+declined, the
  v4d signal that the elder does not want to talk about it): the same close
  with reason declined/deferred; failure falls back to SKIP_ACK + next question.
- after the last skeleton question: the existing review text, no speaker call.
- pause (engine paused, or the elder says he is tired): the existing pause; the
  question stays open and resumes with its entry question.

All provider calls of one answer are kept in ``life_interview['pending']['calls']``
(judge, verify, speaker) and saved before the next step, so a retry of the same
request reuses them; pending calls never cross flows because a question keeps
the flow it started with.
"""
from copy import deepcopy

from app.ai import interview_speaker as speaker
from app.ai.contract_interview_v3j import V3jPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.services.contract_interview_state import V3J_PIPELINE, configured_pipeline, v3j_runtime
from app.services.contract_v3j_interview import append_source, context_for, dialogue_from, finish, marker
from app.services.interview_controls import SKIP_ACK, skips_question


def question_flow(data, qid):
    local = data['questions'][qid]
    if local.get('pipeline'):
        return local['pipeline']
    if local.get('sources') or local.get('audit') or local.get('last_result') or local.get('status') != 'pending':
        return 'v2'
    if configured_pipeline() == V3J_PIPELINE and data.get('runtime_version') == v3j_runtime().version:
        return V3J_PIPELINE
    return 'v2'


def shown_before(turns):
    """For each overview turn, the latest assistant turn shown before it."""
    out, last = {}, ''
    for item in turns:
        out[item['id']] = last
        if item['role'] == 'assistant':
            last = item['content']
    return out


def close_status(result, reason, skip):
    """Overview status of a closed question, as the v2 path maps engine decisions; a close the ending rules
    make on an engine follow-up keeps what the elder said: declined, cannot remember, or what is known."""
    if skip:
        return 'skipped'
    decision = result.get('decision')
    effective = result.get('effective') or {}
    if decision == 'ready':
        return 'known'
    if decision == 'limited':
        return 'declined' if 'declined' in effective.values() else 'unknown'
    if decision in ('skipped', 'deferred'):
        return 'skipped'
    if reason in ('declined', 'unknown'):
        return reason
    return 'known' if any(v in ('known', 'none') for v in effective.values()) else 'unknown'


def next_question(data, qid):
    """The skeleton question shown after ``qid`` closes (the v2 path's active_id with this one no longer pending)."""
    from app.services.contract_life_overview import question_text
    following = next((k for k, q in data['questions'].items() if k != qid and q['status'] == 'pending'), None)
    return question_text(data, following) if following else None


def turn(person_id, data, rid, fingerprint, client):
    """One answer (or explicit skip) of a skeleton question in the v3j_v4d flow. Caller owns the person lock."""
    from app.services.contract_life_overview import NOTED_TEXT, PAUSE_TEXT, REVIEW_TEXT, _reply, _save, active_id, view
    rt = v3j_runtime()
    pending = data['pending']
    qid, text = pending['question_id'], pending['text']
    local = data['questions'][qid]
    if not local.get('pipeline'):
        local.update(marker(rt))
        local['asked_question'] = None
    llm = client() if callable(client) else client

    def save_call(stage, record):
        data['pending']['calls'][stage] = record
        _save(person_id, data)

    entry = rt.questions[qid]['main_question']
    skip = skips_question(text)
    if skip:
        # A user skip closes the question without inventing unavailable facts (no judgment, as in v2).
        outcome, result = None, local.get('last_result') or {}
        action, reason, rule = 'close', 'declined', None
    else:
        append_source(local, rid, text, pending['asked_question'])
        _save(person_id, data)
        outcome = V3jPipeline(rt, llm).run(qid, local['sources'], context_for(local),
                                           saved_calls=pending['calls'], save_call=save_call)
        result = outcome['result']
        if result['decision'] == 'invalid':
            pending['invalid_result'] = outcome
            pending.setdefault('failed_attempts', []).append(outcome)
            local['audit'].append(deepcopy(outcome))
            pending['calls'] = {}
            _save(person_id, data)
            raise LLMResponseFormatError('Interview evidence remains invalid')
        st = {'followups': local.get('followups', 0), 'ask_counts': local.get('ask_counts', {}),
              'prev_eff': dict((local.get('last_result') or {}).get('effective') or {})}
        action, reason = speaker.decide(rt.speaker_config, result, st, text)
        rule = {'action': action, 'reason': reason, 'signal': st['signal']}
    paused = data['paused'] if skip else action == 'rest'
    status = 'pending' if action in ('ask', 'rest') else close_status(result, reason, skip)
    if status in ('skipped', 'declined') and reason not in ('declined', 'deferred'):
        reason = 'declined'  # a refusal is closed as one, as in the guided flow
    following = next_question(data, qid) if status != 'pending' else None
    dialogue = dialogue_from(entry, local['sources'], shown_before(data['turns']), rid, text)
    elder_words = ''.join(t for role, t in dialogue if role == 'elder')
    fields = speaker.recorded_fields(rt, result)
    # Question state that a retry recomputes from (sources' targets, asked question, counts, prev close)
    # changes only after the speaking-layer call has been saved with the pending request.
    question, spoken, close_text = None, None, None
    if action == 'ask':
        user = speaker.speaker_user(rt, qid, dialogue, fields, 'ask', reason, result.get('question'))
        row, call = V3jPipeline(rt, llm).speak(user, saved_calls=pending['calls'], save_call=save_call)
        reply, question, record = speaker.compose_ask(rt, row, result, reason, [s['question'] for s in local['sources']], elder_words)
        spoken = {'task': 'ask', **record, 'text': reply, 'raw': row.get('content'), 'call': call}
    elif status != 'pending' and following and not paused:
        user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=following,
                                    prev_close=data.get('speaker_last_close'))
        row, call = V3jPipeline(rt, llm).speak(user, saved_calls=pending['calls'], save_call=save_call)
        said, _ = speaker.parse_speaker(row)
        close_text, ack, notes, ok = speaker.compose_close(rt, said, following, elder_words)
        if not ok:
            close_text = (SKIP_ACK + '\n' if status in ('skipped', 'declined') else NOTED_TEXT) + following
        spoken = {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '',
                  'notes': notes, 'fallback': not ok, 'text': close_text, 'raw': row.get('content'), 'call': call}
    elif status != 'pending':
        # Last skeleton question (or a skip while paused): the existing reply, no speaking-layer call.
        spoken = {'task': 'close', 'close_reason': reason, 'step': 'review' if not following else 'paused', 'fallback': False}
    if skip:
        if spoken and 'call' in spoken:
            spoken['call'] = None
        local['audit'].append({'pipeline': 'v4d', 'kind': 'skip_control', 'request_id': rid,
                               'speaker': spoken, 'calls': deepcopy(pending['calls'])})
        local['asked_target'] = None
    else:
        finish(local, outcome, {**(spoken or {}), **rule}, asked=reason if action == 'ask' else None)
    local['asked_question'] = question
    local['status'] = status
    if not skip:
        data['paused'] = paused
    if close_text is not None:
        data['speaker_last_close'] = close_text
    if status != 'pending':
        data['editing_question_id'] = None
    data['pending'] = None
    data['requests'][rid] = fingerprint
    data['version'] += 1
    data['status'] = 'collecting' if active_id(data) else 'review'
    if data['paused']:
        reply = PAUSE_TEXT
    elif action == 'ask':
        reply = spoken['text']
    else:
        reply = close_text or REVIEW_TEXT
    _reply(data, rid, reply)
    _save(person_id, data)
    return view(data)
