#!/usr/bin/env python3
"""Read-only independent audit of frozen full-scope DS/GPT runs, not a scorer.

Counts distinct people only when a saved successful provider call exists.
It never upgrades a failed extraction, changes gold, or certifies semantics.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def audit(folder):
    freeze = read(folder / 'freeze.json')
    data = read(folder / 'dataset.json')
    errors = []
    provider_failures = []
    for name, expected in freeze['files'].items():
        path = folder / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append('changed_or_missing_frozen_file:' + name)
    frozen_model=freeze.get('model')
    openai = freeze.get('provider_settings', {}).get('provider') == 'openai'
    if frozen_model not in {'deepseek-flash','deepseek-v4-pro','gpt-6.1-sol'} or freeze.get('source_kind') != 'published_transcript':
        errors.append('unexpected_model_or_source_kind')
    if (frozen_model == 'gpt-6.1-sol') != openai:
        errors.append('model_provider_mismatch')
    if freeze.get('question_context_mode') != 'independent':
        errors.append('unexpected_question_context_mode')
    raw_calls = Counter()
    kinds = Counter()
    allowed_prompts={(folder/'runtime/extractor-prompt.txt').read_text()}
    review_prompt=folder/'runtime/reviewer-prompt.txt'
    if review_prompt.exists():
        allowed_prompts.add(review_prompt.read_text())
    control_prompt=folder/'runtime/control-prompt.txt'
    if control_prompt.exists():allowed_prompts.add(control_prompt.read_text())
    for path in sorted((folder/'batches').glob('*.request.json')):
        if read(path).get('prompt') not in allowed_prompts:
            errors.append('non_generic_or_unfrozen_prompt:' + path.name)
    for path in sorted((folder / 'batches').glob('*.raw.jsonl')):
        configured = False
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                errors.append('unreadable_transport_line:' + path.name)
                continue
            kinds[row.get('kind')] += 1
            if row.get('kind') == 'run_start':
                configured = (row.get('model') == frozen_model and
                              row.get('source_kind') == 'published_transcript' and
                              row.get('jobs', 100) <= 4 and row.get('database_used') is False)
                if openai:
                    configured = configured and (row.get('provider') == 'openai' and row.get('api') == 'responses'
                        and row.get('endpoint') == 'https://api.openai.com/v1/responses'
                        and row.get('provider_settings') == freeze.get('provider_settings'))
                if not configured:
                    errors.append('unexpected_transport_configuration:' + path.name)
            if row.get('kind') == 'model_call':
                if not configured:
                    errors.append('call_without_valid_run_start:' + path.name)
                if frozen_model=='deepseek-v4-pro' and row.get('response_model')!=frozen_model:
                    errors.append('provider_response_model_not_frozen_pro:' + path.name)
                if openai and (row.get('response_model') != frozen_model or row.get('provider') != 'openai'
                               or row.get('provider_settings') != freeze.get('provider_settings')):
                    errors.append('provider_response_not_frozen_openai_profile:' + path.name)
                raw_calls[fingerprint(row)] += 1
    narrators = {n['id']: n for n in data['narrators']}
    people = set()
    executed_cases = set()
    question_ids = set()
    successful = 0
    attempts = 0
    for case in data['cases']:
        for path in sorted((folder / 'cases' / case['id']).glob('turn-*/response-*.json')):
            attempts += 1
            response = read(path)
            if response.get('kind') != 'model_call':
                continue
            successful += 1
            key = fingerprint(response)
            if raw_calls[key] <= 0:
                errors.append('response_not_witnessed_by_transport:' + str(path.relative_to(folder)))
            else:
                raw_calls[key] -= 1
            payload = response.get('input') or {}
            qid = case['question_id']
            turn_index = int(path.parent.name.removeprefix('turn-'))
            available = {t['source']['id']: t['source']['text']
                         for t in case['turns'][:turn_index + 1]}
            if payload.get('question_id') != qid:
                errors.append('wrong_question_payload:' + case['id'])
            if {'gold', 'expected', 'expected_fields', 'annotation_note', 'value_groups'} & payload.keys():
                errors.append('evaluation_answer_leaked_to_model:' + case['id'])
            for source in payload.get('sources', []):
                if source.get('question_id', qid) != qid:
                    errors.append('cross_question_source:' + case['id'])
                if source.get('text') != available.get(source.get('id')):
                    errors.append('source_not_from_own_frozen_turns:' + case['id'])
            unit_ids=set()
            for unit in payload.get('evidence_units',[]):
                uid=unit.get('id')
                text=unit.get('text')
                original=available.get(unit.get('source_id'))
                if not uid or uid in unit_ids or not text or original is None or text not in original:
                    errors.append('evidence_unit_not_from_own_frozen_source:' + case['id'])
                unit_ids.add(uid)
            frozen_fields=read(folder/'contracts.snapshot.json')['fields']
            for fid in (payload.get('previous_fields') or {}):
                if frozen_fields.get(fid,{}).get('question_id') != qid:
                    errors.append('cross_question_cache:' + case['id'])
            review=(payload.get('semantic_review') or {}).get('unverified_candidate') or {}
            if isinstance(review,dict):
                for fid in review.get('fields',{}):
                    if frozen_fields.get(fid,{}).get('question_id') != qid:
                        errors.append('cross_question_review_candidate:' + case['id'])
            if response.get('test_double'):
                errors.append('test_double_response:' + case['id'])
            if not response.get('raw_content'):
                # A witnessed HTTP response with empty content is a real
                # provider failure, not evidence of fabricated transport.
                # The scorer still retains its failed extraction and the
                # single permitted repair; this audit never upgrades either.
                provider_failures.append({'kind': 'empty_provider_content',
                                          'path': str(path.relative_to(folder)),
                                          'case_id': case['id']})
            people.add(case['narrator_id'])
            executed_cases.add(case['id'])
            question_ids.add(qid)
    return {'run': folder.name, 'model':frozen_model, 'freeze_sha256': hashlib.sha256((folder / 'freeze.json').read_bytes()).hexdigest(),
            'actual_people': [{'id': nid, 'name': narrators[nid]['name']} for nid in sorted(people)],
            'actual_cases': len(executed_cases), 'actual_question_ids': sorted(question_ids),
            'attempt_files': attempts, 'successful_call_records': successful,
            'raw_transport_kinds': dict(kinds), 'provider_failures': provider_failures,
            'errors': errors, 'passed': not errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    folders = ([args.folder] if (args.folder / 'freeze.json').is_file() else
               [p for p in sorted(args.folder.glob('run-*')) if (p / 'freeze.json').is_file()])
    if not folders:
        parser.error('no frozen runs found; an empty audit cannot pass')
    runs = [audit(p) for p in folders]
    people = {p['id']: p['name'] for run in runs for p in run['actual_people']}
    names = {}
    for nid, name in people.items():
        names.setdefault(''.join(name.split()), []).append(nid)
    duplicate_names = {n: ids for n, ids in names.items() if len(ids) > 1}
    result = {'scope': 'Immutable files, raw provider transport, executed identities, question isolation only; not semantic accuracy or acceptance.',
              'runs': runs, 'actual_distinct_narrator_ids': len(people),
              'actual_distinct_names': len(names), 'same_name_identity_review': duplicate_names,
              'successful_call_records': sum(r['successful_call_records'] for r in runs),
              'provider_failure_records': sum(len(r['provider_failures']) for r in runs),
              'errors': sum(len(r['errors']) for r in runs),
              'passed': all(r['passed'] for r in runs) and not duplicate_names}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('actual_distinct_narrator_ids', 'actual_distinct_names',
                     'successful_call_records', 'errors', 'passed')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
