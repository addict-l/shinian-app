#!/usr/bin/env python3
"""Isolated answer-gate experiment over the frozen single-question-v2 corpus.

The existing contract engine, source material and scorer are reused unchanged.
Model outputs remain untrusted; the compiler copies only numbered source units.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import run_full_interview_eval as baseline  # noqa: E402

baseline.ROOT = ROOT
PROTOTYPE_ID = 'answer-gate-v1.1'
STATES = {'known', 'ambiguous', 'none', 'unknown', 'declined', 'deferred', 'not_applicable', 'missing'}
CLARIFICATIONS = {'referent', 'actor', 'period', 'meaning', 'link'}
PERIODS = {'birth', 'childhood', 'school_years', 'youth', 'middle_age', 'adulthood', 'lifelong', 'now', 'unspecified', 'as_stated'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_contract(payload: dict) -> dict:
    keys = ('id', 'label', 'type', 'question', 'usable_answer', 'requirement', 'activation',
            'scope', 'allowed_states', 'answer_format', 'link', 'notes')
    return {fid: {key: field[key] for key in keys if key in field}
            for fid, field in payload['field_contract'].items()
            if field['requirement'] != 'optional'}


def model_context(payload: dict, *, locator=None, retry=None) -> dict:
    out = {'question_id': payload['question_id'], 'main_question': payload['main_question'],
           'current_question': payload['current_question'], 'focus': payload.get('focus'),
           'field_contract': compact_contract(payload), 'sources': payload['sources'],
           'evidence_units': payload['evidence_units'], 'previous_fields': payload['previous_fields']}
    if locator is not None:
        out['locator_candidates_unverified'] = locator
    if retry is not None:
        out['internal_retry'] = retry
    return out


def numbered_ids(value, allowed: set[str], name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or x not in allowed for x in value):
        raise ValueError(name + ': invalid evidence unit IDs')
    return value


def compile_verdict(payload: dict, verdict: dict) -> dict:
    """Copy pointers and structure; never infer an answer from a label or question."""
    if not isinstance(verdict, dict) or not isinstance(verdict.get('fields'), dict):
        raise ValueError('invalid verdict root')
    allowed = {unit['id'] for unit in payload['evidence_units']}
    contract = compact_contract(payload)
    control = verdict.get('control', {'action': 'continue', 'evidence_unit_ids': []})
    if not isinstance(control, dict) or control.get('action') not in {'continue', 'pause', 'skip_question', 'defer_question'}:
        raise ValueError('invalid control action')
    ctrl_ids = numbered_ids(control.get('evidence_unit_ids', []), allowed, 'control')
    proposal = {'control': {'action': control['action'], 'evidence_unit_ids': ctrl_ids}, 'fields': {}}
    for fid, row in verdict['fields'].items():
        if fid not in contract or not isinstance(row, dict) or row.get('state') not in STATES:
            raise ValueError('invalid field or state: ' + str(fid))
        state = row['state']
        if state == 'missing':
            continue
        field = contract[fid]
        if state not in field.get('allowed_states', ()):
            raise ValueError('state forbidden by contract: ' + fid)
        proof = numbered_ids(row.get('proof_unit_ids', []), allowed, fid + '.proof')
        if not proof:
            raise ValueError('nonmissing field requires source evidence: ' + fid)
        subject, period = row.get('subject'), row.get('period')
        if subject not in field['scope']['subjects'] or period not in PERIODS:
            raise ValueError('invalid source attribution: ' + fid)
        entry = {'state': state, 'evidence_unit_ids': proof,
                 'scope': {'subject': subject, 'period': period, 'relation_unit_ids': 'same_as_evidence'}}
        if state == 'known':
            value_ids = numbered_ids(row.get('value_unit_ids', []), allowed, fid + '.value')
            if not value_ids:
                raise ValueError('known field requires selected original value: ' + fid)
            entry['value_unit_ids'] = value_ids
        else:
            entry['value'] = None
        if state == 'ambiguous':
            clarifications = row.get('clarifications')
            if not isinstance(clarifications, list) or not clarifications or any(c not in CLARIFICATIONS for c in clarifications):
                raise ValueError('ambiguous field requires a valid clarification: ' + fid)
            entry['clarifications'] = clarifications
        for key in ('precision', 'stance', 'links', 'supersedes'):
            if key in row and row[key] is not None:
                entry[key] = row[key]
        for key in ('object_role', 'object_unit_ids'):
            if key in row and row[key] is not None:
                entry['scope'][key] = row[key]
        proposal['fields'][fid] = entry
    return proposal


def frozen_prototype(session: Path) -> dict:
    meta = session / 'answer-gate-prototype.json'
    expected = {'prototype': PROTOTYPE_ID,
                'code_sha256': digest(HERE / 'run.py'),
                'locator_prompt_sha256': digest(HERE / 'locator-prompt.txt'),
                'judge_prompt_sha256': digest(HERE / 'judge-prompt.txt'),
                'dataset_sha256': digest(session / 'dataset.json'),
                'contracts_sha256': digest(session / 'runtime/contracts.json'),
                'provider_settings': baseline.load(session / 'freeze.json')['provider_settings']}
    if meta.exists():
        if baseline.load(meta) != expected:
            raise ValueError('prototype changed after session began; prepare a new session')
    else:
        baseline.save(meta, expected)
    return expected


def batch(session: Path, prompt: str, jobs: list[dict], serial: int) -> dict:
    return baseline.batch_call(session, prompt, jobs, session / 'batches' / f'{serial:05d}.raw.jsonl')


def run(session: Path, concurrency: int, max_cases: int | None) -> None:
    baseline.MODEL = baseline.load(session / 'freeze.json')['model']
    baseline.verify(session)
    frozen_prototype(session)
    dataset = baseline.load(session / 'dataset.json')
    defs = baseline.load(session / 'contracts.snapshot.json')
    active: list[dict] = []
    for case in dataset['cases']:
        previous, counts = {}, {}
        index = 0
        for index in range(len(case['turns'])):
            path = session / 'cases' / case['id'] / f'turn-{index:03d}' / 'result.json'
            if not path.exists():
                break
            record = baseline.load(path)
            if record['kind'] != 'evaluated' or record['result']['decision'] == 'invalid':
                break
            previous = record['result']['fields']
            if record['result']['decision'] == 'ask' and record['result']['target']:
                target = record['result']['target']
                counts[target] = counts.get(target, 0) + 1
        else:
            continue
        if not path.exists():
            active.append({'case': case, 'index': index, 'previous': previous, 'counts': counts})
    print(json.dumps({'prototype_started': baseline.now(), 'eligible_cases': len(dataset['cases']),
                      'remaining_cases': len(active), 'model': baseline.MODEL,
                      'thinking': 'disabled'}, ensure_ascii=False), flush=True)
    serial = baseline.last_batch_number(session)
    completed = 0
    locator_prompt = (HERE / 'locator-prompt.txt').read_text()
    judge_prompt = (HERE / 'judge-prompt.txt').read_text()
    while active and (max_cases is None or completed < max_cases):
        wave, active = active[:concurrency], active[concurrency:]
        locate_jobs, binding = [], {}
        for item in wave:
            case, index = item['case'], item['index']
            turn_dir = session / 'cases' / case['id'] / f'turn-{index:03d}'
            turn_dir.mkdir(parents=True, exist_ok=True)
            payload = baseline.payload_for(case, index, defs, item['previous'], item['counts'], session / 'runtime')
            request = {'id': f"{case['id']}-t{index:03d}-locate", 'payload': model_context(payload)}
            baseline.save(turn_dir / 'request-000.json', request)
            locate_jobs.append(request)
            binding[request['id']] = (item, turn_dir, payload)
        serial += 1
        locates = batch(session, locator_prompt, locate_jobs, serial)
        judge_jobs = []
        for request in locate_jobs:
            item, turn_dir, payload = binding[request['id']]
            call = locates[request['id']]
            baseline.save(turn_dir / 'response-000.json', call)
            # A failed locator is a processing fault, not proof the narrator left the field blank.
            if call.get('kind') != 'model_call' or not isinstance(call.get('output'), dict):
                baseline.save(turn_dir / 'result.json', {'kind': 'call_error', 'stage': 'locator', 'call_kind': call.get('kind')})
                continue
            judge = {'id': request['id'].replace('-locate', '-judge'),
                     'payload': model_context(payload, locator=call['output'])}
            baseline.save(turn_dir / 'request-000-review.json', judge)
            judge_jobs.append(judge)
            binding[judge['id']] = (item, turn_dir, payload)
        for offset in range(0, len(judge_jobs), concurrency):
            group = judge_jobs[offset:offset + concurrency]
            serial += 1
            judged = batch(session, judge_prompt, group, serial)
            repairs = []
            for request in group:
                item, turn_dir, payload = binding[request['id']]
                call = judged[request['id']]
                baseline.save(turn_dir / 'response-000-review.json', call)
                if call.get('kind') != 'model_call':
                    baseline.save(turn_dir / 'result.json', {'kind': 'call_error', 'stage': 'judge', 'call_kind': call.get('kind')})
                    continue
                try:
                    proposal = compile_verdict(payload, call.get('output'))
                    result = baseline.analyze(session, payload, proposal, turn_dir / 'engine-input-000-review.json', call)
                    baseline.save(turn_dir / 'decision-000-review.json', result)
                    errors = (result.get('errors') or ['invalid_decision']) if result['decision'] == 'invalid' else []
                except (ValueError, TypeError, KeyError) as exc:
                    result, errors = None, [str(exc)]
                if not errors:
                    baseline.save(turn_dir / 'result.json', {'kind': 'evaluated', 'result': result,
                                  'internal_repairs': 0, 'semantic_review_calls': 1,
                                  'processing_status': 'verified', 'at': baseline.now()})
                    continue
                # Exactly one internal retry; no new question is sent to the narrator.
                retry = {'id': request['id'] + '-repair1',
                         'payload': model_context(payload, locator=locates[request['id'].replace('-judge', '-locate')]['output'],
                                                  retry={'errors': errors, 'previous_verdict': call.get('output')})}
                baseline.save(turn_dir / 'request-000-repair1.json', retry)
                repairs.append(retry)
                binding[retry['id']] = (item, turn_dir, payload)
            for restart in repairs:
                serial += 1
                repaired = batch(session, judge_prompt, [restart], serial)[restart['id']]
                item, turn_dir, payload = binding[restart['id']]
                baseline.save(turn_dir / 'response-000-repair1.json', repaired)
                if repaired.get('kind') != 'model_call':
                    baseline.save(turn_dir / 'result.json', {'kind': 'call_error', 'stage': 'judge_repair',
                                  'call_kind': repaired.get('kind'), 'internal_repairs': 1})
                    continue
                try:
                    proposal = compile_verdict(payload, repaired.get('output'))
                    result = baseline.analyze(session, payload, proposal, turn_dir / 'engine-input-000-repair1.json', repaired)
                    baseline.save(turn_dir / 'decision-000-repair1.json', result)
                except (ValueError, TypeError, KeyError) as exc:
                    result = {'decision': 'invalid', 'fields': {}, 'errors': [str(exc)]}
                baseline.save(turn_dir / 'result.json', {'kind': 'evaluated', 'result': result,
                              'internal_repairs': 1, 'semantic_review_calls': 1,
                              'processing_status': 'verified' if result['decision'] != 'invalid' else 'internal_failure',
                              'at': baseline.now()})
        completed += baseline.advance_wave(session, wave, active)
        report = baseline.score_session(session)
        print(json.dumps({'completed_cases': completed, 'remaining_cases': len(active),
                          'passed_checkpoints': report['overall']['all_critical_checkpoint_passes'],
                          'evaluated_checkpoints': report['overall']['evaluated_checkpoints']}, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--concurrency', type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument('--max-cases', type=int)
    args = parser.parse_args()
    session = args.session.resolve()
    started = dt.datetime.now(dt.timezone.utc)
    start = time.perf_counter()
    record = {'started_at': started.isoformat(), 'concurrency': args.concurrency,
              'model': baseline.load(session / 'freeze.json')['model'], 'prototype': PROTOTYPE_ID}
    try:
        run(session, args.concurrency, args.max_cases)
        record['status'] = 'completed'
        return 0
    except BaseException as exc:
        record.update(status='interrupted_or_error', error_type=type(exc).__name__)
        raise
    finally:
        record.update(ended_at=baseline.now(), wall_seconds=round(time.perf_counter() - start, 3))
        baseline.save(session / 'run-executions' / (started.strftime('%Y%m%dT%H%M%S%f') + '.json'), record)
        baseline.score_session(session)


if __name__ == '__main__':
    raise SystemExit(main())
