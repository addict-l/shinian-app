"""Six independent skeleton questions through the existing life-overview API."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import re
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import HTTPException
from app.ai.contract_interview import ContractInterviewPipeline
from app.ai.llm_client import LLMResponseFormatError
from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.schemas.life_overview import LifeOverview, LifeField
from app.services.contract_interview_state import (
    runtime, questions, fresh_question, context_for, append_source, finish_question_turn, V3J_PIPELINE,
)
from app.services.interview_controls import skips_question, SKIP_ACK

INTRO = '我们先聊几个简单的问题，了解您的人生。记不清或暂时不想讲的，可以先跳过。'
PAUSE_TEXT = '好，先休息。您的回答和采访位置都已保留。'
NOTED_TEXT = '我记下了。'
REVIEW_TEXT = '这些是您提供的人生线索。请先核对，有需要更正的地方可以告诉我；确认后再选想聊的部分。'


def now():
    return datetime.now(timezone.utc).isoformat()


def new_data(required=True):
    catalog = questions('skeleton')
    return {'schema_version': 2, 'runtime_version': runtime().version,
        'runtime_manifest_sha256': runtime().manifest_sha256,
        'version': 1, 'status': 'collecting', 'required': required, 'paused': False,
        'questions': {q['id']: {**fresh_question(q['id']), 'status': 'pending'} for q in catalog},
        'turns': [{'id': str(uuid4()), 'role': 'assistant',
                   'content': INTRO + '\n' + catalog[0]['main_question'], 'created_at': now()}],
        'requests': {}, 'pending': None, 'confirmed_version': None, 'editing_question_id': None}


def question_ids(data):
    # MySQL JSON object order is not the frozen interview order.
    return [q['id'] for q in questions('skeleton', data.get('runtime_version', 'full-interview-v1.29.1'))
            if q['id'] in data['questions']]


def active_id(data):
    return data.get('editing_question_id') or (data.get('pending') or {}).get('question_id') or next(
        (qid for qid in question_ids(data) if data['questions'][qid]['status'] == 'pending'), None)


def question_text(data, qid):
    if not qid:
        return None
    if data['questions'][qid].get('pipeline') == V3J_PIPELINE:
        # The question part last shown (the speaking layer's follow-up), else the entry question.
        asked = data['questions'][qid].get('asked_question')
        if asked is not None:
            return asked
        return runtime(data.get('runtime_version', 'full-interview-v1.29.1')).questions[qid]['main_question']
    latest = data['questions'][qid].get('last_result') or {}
    if latest.get('decision') in ('ask', 'ask_defer'):
        return latest['question']
    return runtime(data.get('runtime_version', 'full-interview-v1.29.1')).questions[qid]['main_question']


def view(data):
    qid = active_id(data)
    keys = question_ids(data)
    projected = []
    for key in keys:
        item = data['questions'][key]
        refs = {}
        for field in item.get('fields', {}).values():
            for ref in field.get('evidence', []):
                refs[(ref['source_id'], ref['quote'])] = {'message_id': ref['source_id'], 'quote': ref['quote']}
        projected.append(LifeField(topic_id=key, status=item['status'], evidence=list(refs.values())))
    return LifeOverview(version=data['version'], status=data['status'], required=data['required'],
        paused=data['paused'], fields=projected, turns=data['turns'], question_id=qid,
        question=question_text(data, qid), question_number=keys.index(qid) + 1 if qid else len(keys),
        total_questions=len(keys), confirmed_version=data['confirmed_version'],
        pending_request_id=data['pending']['request_id'] if data['pending'] else None,
        pending_action=data['pending']['request'] if data['pending'] else None)


def _save(person_id, data):
    with SessionLocal.begin() as db:
        person = db.get(FamilyMemberModel, str(person_id), with_for_update=True)
        if person is None:
            raise HTTPException(404, '人物不存在')
        person.life_interview = deepcopy(data)


def _reply(data, rid, text):
    data['turns'].append({'id': str(uuid5(NAMESPACE_URL, 'life-reply:' + rid)),
                          'role': 'assistant', 'content': text, 'created_at': now()})


def perform(person_id, action, client):
    """Caller owns the person lock. Durable raw input precedes all model calls."""
    rid = str(action.client_request_id)
    fingerprint = sha256(action.model_dump_json().encode()).hexdigest()
    with SessionLocal.begin() as db:
        person = db.get(FamilyMemberModel, str(person_id), with_for_update=True)
        if person is None:
            raise HTTPException(404, '人物不存在')
        data = deepcopy(person.life_interview)
        created = data is None
        if data is None:
            if action.action != 'begin' or action.expected_version != 0:
                raise HTTPException(409, '请先开始了解人生骨架')
            data = new_data(required=False)
        if rid in data['requests']:
            if data['requests'][rid] != fingerprint:
                raise HTTPException(409, '同一个请求标识不能更改操作内容')
            return view(data)
        pending = data.get('pending')
        if pending and pending['request_id'] != rid and action.action == 'answer' and skips_question(action.text):
            # Explicit opt-out may leave a failed provider request. Keep its
            # complete trace and raw turn, then process the skip idempotently.
            data.setdefault('abandoned_pending_requests', []).append(deepcopy(pending))
            data['pending'] = None
            pending = None
        if pending:
            if pending['request_id'] != rid or pending['hash'] != fingerprint:
                raise HTTPException(409, '上次回答已保留，请先重试完成该回答')
        else:
            if not created and data['version'] != action.expected_version:
                raise HTTPException(409, '人生概览已更新，请重新读取后核对')
            if action.action == 'begin':
                data['paused'] = False
            elif action.action in ('answer', 'correct'):
                if action.action == 'answer' and data['status'] != 'collecting':
                    raise HTTPException(409, '请在概览中选择需要更正的内容')
                text = action.text.strip()
                if not text:
                    raise HTTPException(422, '请填写回答或选择跳过')
                qid = action.topic_id if action.action == 'correct' else active_id(data)
                if qid not in data['questions']:
                    raise HTTPException(422, '请选择本版人生骨架中的问题')
                asked = question_text(data, qid)
                if action.action == 'correct':
                    data['editing_question_id'] = qid
                    data['status'] = 'collecting'
                data['turns'].append({'id': rid, 'role': 'user', 'content': text, 'created_at': now()})
                data['pending'] = {'request_id': rid, 'hash': fingerprint, 'question_id': qid,
                    'asked_question': asked, 'text': text, 'request': action.model_dump(mode='json'), 'calls': {}}
                data['confirmed_version'] = None
            elif action.action == 'confirm':
                if data['status'] != 'review':
                    raise HTTPException(409, '请先完成或跳过骨架问题，再核对概览')
                data['status'] = 'confirmed'
                data['confirmed_version'] = data['version'] + 1
            elif action.action in ('pause', 'resume'):
                data['paused'] = action.action == 'pause'
            if data.get('pending') is None:
                data['requests'][rid] = fingerprint
                data['version'] += 1
            person.life_interview = deepcopy(data)
    if data.get('pending') is None:
        return view(data)
    pending = data['pending']
    qid, text = pending['question_id'], pending['text']
    local = data['questions'][qid]
    pause = bool(re.fullmatch(r'(?:先休息|先暂停|暂停|今天先不聊|暂时不想聊)[。！!\s]*', text))
    resume = bool(data['paused'] and re.fullmatch(r'(?:继续|继续聊|接着讲)[。！!\s]*', text))
    if pause or resume:
        data['paused'] = pause
        data['pending'] = None
        data['requests'][rid] = fingerprint
        data['version'] += 1
        _reply(data, rid, PAUSE_TEXT if pause else '好，我们接着聊。' + question_text(data, qid))
        _save(person_id, data)
        return view(data)
    from app.services.contract_v3j_life_overview import question_flow, turn
    if question_flow(data, qid) == V3J_PIPELINE:
        return turn(person_id, data, rid, fingerprint, client)
    skip = skips_question(text)
    if skip:
        # A user skip closes the question without inventing unavailable facts.
        local['status'] = 'skipped'
    else:
        append_source(local, rid, text, pending['asked_question'])
        _save(person_id, data)

        def save_call(stage, entry):
            data['pending']['calls'][stage] = entry
            _save(person_id, data)

        outcome = ContractInterviewPipeline(runtime(data.get('runtime_version', 'full-interview-v1.29.1')), client() if callable(client) else client).run(
            qid, local['sources'], context_for(local), saved_calls=pending['calls'], save_call=save_call)
        if outcome['result']['decision'] == 'invalid':
            pending['invalid_result'] = outcome
            pending.setdefault('failed_attempts', []).append(outcome)
            local['audit'].append(deepcopy(outcome))
            pending['calls'] = {}
            _save(person_id, data)
            raise LLMResponseFormatError('Interview evidence remains invalid after one internal repair')
        finish_question_turn(local, outcome)
        decision = outcome['result']['decision']
        if decision == 'ready':
            local['status'] = 'known'
        elif decision == 'limited':
            local['status'] = 'declined' if 'declined' in outcome['result'].get('effective', {}).values() else 'unknown'
        elif decision in ('skipped', 'deferred'):
            local['status'] = 'skipped'
        else:
            local['status'] = 'pending'
        data['paused'] = decision == 'paused'
    if local['status'] != 'pending':
        data['editing_question_id'] = None
    data['pending'] = None
    data['requests'][rid] = fingerprint
    data['version'] += 1
    data['status'] = 'collecting' if active_id(data) else 'review'
    next_question = question_text(data, active_id(data))
    reply = PAUSE_TEXT if data['paused'] else (
        ((SKIP_ACK + '\n') if skip or local['status'] in ('skipped', 'declined') else NOTED_TEXT if local['status'] != 'pending' else '') + next_question if next_question else
        REVIEW_TEXT)
    _reply(data, rid, reply)
    _save(person_id, data)
    return view(data)
