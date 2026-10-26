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
- an answer followed by "这段我不想多讲" (decision of 2026-10-23, C02, reason
  'declined_partial', also for the engine's limited with a declined field next
  to an answered one) is not a refusal: the question closes as answered
  (status known, fallback "我记下了。" + next question); the
  speaking layer is told '老人不想多说'. Signals count only as the elder's own
  present intent (C01, interview_speaker.elder_signal).
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
from app.ai import interview_story as story
from app.ai.contract_interview_v3j import V3jPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.services.contract_interview_state import V3J_FLOWS, configured_pipeline, flow_runtime
from app.services.contract_v3j_interview import (append_source, clean_dz, context_for, dialogue_from, finish, keep_log,
                                                 marker, question_answers, try_deepen, v5f)
from app.services.interview_controls import SKIP_ACK, skips_question


def question_flow(data, qid):
    local = data['questions'][qid]
    if local.get('pipeline'):
        return local['pipeline']
    if local.get('sources') or local.get('audit') or local.get('last_result') or local.get('status') != 'pending':
        return 'v2'
    configured = configured_pipeline()
    if configured in V3J_FLOWS and data.get('runtime_version') == flow_runtime(configured).version:
        return configured
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
    if reason == 'declined_partial':  # answered, then did not want to go on (C02): not a refusal
        return 'known'
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
    from app.services.contract_life_overview import question_ids, question_text
    following = next((k for k in question_ids(data) if k != qid and data['questions'][k]['status'] == 'pending'), None)
    return question_text(data, following) if following else None


def seen_closes(data):
    """v5f template_guard "repeat": the closes already shown in this skeleton (the questions' audits)."""
    return story.earlier_closes([r for local in data['questions'].values() for r in (local.get('audit') or [])])


def turn(person_id, data, rid, fingerprint, client):
    """One answer (or explicit skip) of a skeleton question in a v3j flow (v3j_v4d / v3j_v5f). Caller owns the
    person lock. v5f: a story skeleton question (SK01c) whose elements are complete may get up to two detail
    questions before the close into the next skeleton question; their answers are kept as sources of the question
    without a judgment (interview_story)."""
    from app.services.contract_life_overview import NOTED_TEXT, PAUSE_TEXT, REVIEW_TEXT, _reply, _save, active_id, view
    pending = data['pending']
    qid, text = pending['question_id'], pending['text']
    local = data['questions'][qid]
    rt = flow_runtime(question_flow(data, qid))
    if not local.get('pipeline'):
        local.update(marker(rt))
        local['asked_question'] = None
    llm = client() if callable(client) else client

    def save_call(stage, record):
        data['pending']['calls'][stage] = record
        _save(person_id, data)

    entry = rt.questions[qid]['main_question']
    order = {item['id']: k for k, item in enumerate(data['turns'])}
    skip = skips_question(text)
    dz = local.get('deepen') or {}
    deepen_answer = bool(dz.get('awaiting'))
    outcome = None
    if deepen_answer:
        # Answer to a detail question (v5f): kept verbatim as a source of this question, not judged.
        dz.setdefault('sources', [])
        if not skip and not any(s['id'] == rid for s in dz['sources']):
            dz['sources'].append({'id': rid, 'text': text, 'question_id': qid, 'speaker': 'narrator',
                                  'question': pending['asked_question'], 'dimension': dz['dims'][-1], 'deepen_answer': True})
            _save(person_id, data)
        result = local.get('last_result') or {}
        if skip:  # the question was answered before the detail question: closes as answered (declined_partial)
            action, reason = 'close', 'declined_partial'
        else:
            cfg = rt.speaker_config
            words = [s['text'] for s in question_answers(local, order)]
            before = ''.join(words[:-1])
            scope = (pending['asked_question'], before, cfg.get('scope_min_chars', 15)) if cfg.get('signal_scope') else None
            action, reason = story.deepen_close(text, None, cfg['deepen'].get('extra_guards'), scope)
        rule = {'action': action, 'reason': reason, 'signal': speaker.elder_signal(text), 'deepen_answer': True}
    elif skip:
        # A user skip closes the question without inventing unavailable facts (no judgment, as in v2).
        result = local.get('last_result') or {}
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
        if rt.speaker_config.get('signal_scope'):  # read by signal_scope only (v5f)
            words = [s['text'] for s in question_answers(local, order)]
            st.update(asked=pending['asked_question'] or entry, before=''.join(words[:-1]),
                      last_target=local.get('asked_target'))
        action, reason = speaker.decide(rt.speaker_config, result, st, text)
        rule = {'action': action, 'reason': reason, 'signal': st['signal']}
        if st.get('scope'):
            rule['scope'] = st['scope'][0]
    paused = data['paused'] if skip else action == 'rest'
    if deepen_answer:
        status = 'pending' if action == 'rest' else dz.get('status') or 'known'
    else:
        status = 'pending' if action in ('ask', 'rest') else close_status(result, reason, skip)
    if status in ('skipped', 'declined') and reason not in ('declined', 'deferred'):
        reason = 'declined'  # a refusal is closed as one, as in the guided flow
    dialogue = dialogue_from(entry, question_answers(local, order), shown_before(data['turns']), rid, text)
    elder_words = ''.join(t for role, t in dialogue if role == 'elder')
    fields = speaker.recorded_fields(rt, result)
    # Question state that a retry recomputes from (sources' targets, asked question, counts, prev close)
    # changes only after the speaking-layer call has been saved with the pending request.
    question, spoken, close_text, deepen_log = None, None, None, None
    if action == 'rest' and deepen_answer:
        dz['stopped'] = 'rest'  # detail questions stop; on "继续" the question resumes at its entry question
    elif action == 'close' and not skip and not paused and status not in ('skipped', 'declined') and v5f(rt):
        asked_text = pending['asked_question'] or entry
        before = ''.join([t for role, t in dialogue if role == 'elder'][:-1])
        dim, ack, deepen_q, deepen_log = try_deepen(rt, llm, local, qid, reason, text, dialogue, pending, save_call,
                                                    asked_text, before)
        if deepen_log is not None:
            dz = local['deepen']
            keep_log(dz, deepen_log)
            clean_dz(dz)
            if deepen_q:
                dz['asked'] += 1
                dz['dims'].append(dim)
                dz['awaiting'] = True
                dz['status'] = status
                question, status = deepen_q, 'pending'
                spoken = {'task': 'deepen', **{k: v for k, v in deepen_log.items() if k != 'call'},
                          'text': speaker.join(ack, deepen_q), 'deepen_call': deepen_log.get('call')}
    if deepen_answer and question is None:
        dz['awaiting'] = False  # set only now: a retry after a saved call must read the answer as a deepen answer
    following = next_question(data, qid) if status != 'pending' else None
    if spoken is not None:
        pass
    elif action == 'ask':
        user = speaker.speaker_user(rt, qid, dialogue, fields, 'ask', reason, result.get('question'))
        row, call = V3jPipeline(rt, llm).speak(user, saved_calls=pending['calls'], save_call=save_call)
        reply, question, record = speaker.compose_ask(rt, row, result, reason, [s['question'] for s in local['sources']], elder_words)
        spoken = {'task': 'ask', **record, 'text': reply, 'raw': row.get('content'), 'call': call}
    elif status != 'pending' and following and not paused:
        user = speaker.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=following,
                                    prev_close=data.get('speaker_last_close'))
        row, call = V3jPipeline(rt, llm).speak(user, saved_calls=pending['calls'], save_call=save_call)
        said, _ = speaker.parse_speaker(row)
        if v5f(rt):
            close_text, ack, notes, ok = story.close_reply(rt, said, following, elder_words, seen_closes(data))
        else:
            close_text, ack, notes, ok = speaker.compose_close(rt, said, following, elder_words)
        if not ok:
            close_text = (SKIP_ACK + '\n' if status in ('skipped', 'declined') else NOTED_TEXT) + following
        spoken = {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '',
                  'notes': notes, 'fallback': not ok, 'text': close_text, 'raw': row.get('content'), 'call': call}
    elif status != 'pending':
        # Last skeleton question (or a skip while paused): the existing reply, no speaking-layer call.
        spoken = {'task': 'close', 'close_reason': reason, 'step': 'review' if not following else 'paused', 'fallback': False}
    if deepen_answer:
        record = {'pipeline': 'v5f', 'kind': 'skip_control' if skip else 'deepen_answer', 'request_id': rid,
                  'rule': rule, 'speaker': {k: v for k, v in (spoken or {}).items() if k not in ('call', 'deepen_call')},
                  'calls': deepcopy(pending['calls'])}
        local['audit'].append(record)
    elif skip:
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
    elif question is not None:
        reply = spoken['text']
    else:
        reply = close_text or REVIEW_TEXT
    _reply(data, rid, reply)
    _save(person_id, data)
    return view(data)
