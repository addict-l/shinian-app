#!/usr/bin/env python3
"""Frozen, audited published-transcript evaluation through actual DS or GPT APIs.

Gold is authored before model calls. The script never creates or revises gold from
model output, and each case is a fresh question with its own retained turn state.
"""
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'deepseek-flash'
ALLOWED_DS_MODELS = {'deepseek-flash', 'deepseek-v4-pro'}
ALLOWED_OPENAI_MODELS = {'gpt-6.1-sol'}
LOCK = Path('/tmp/shinian-interview-model-transport.lock')
RUN_BUDGET = None
SCHEMA = 'full-interview-eval-v1'
TERMINAL_STATES = {'known', 'none', 'unknown', 'declined', 'not_applicable', 'deferred'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relay_source():
    spec = importlib.util.spec_from_file_location('actual_ds_transport', ROOT / 'docs/prototypes/skeleton-constraints/run-model.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REMOTE


def configured_relay(runtime):
    """Only an explicit frozen provider experiment may change inference effort.

    Host, model, credential handling, concurrency, original logs and retry limit
    are inherited unchanged. Never prints or reads a credential locally.
    """
    path = runtime / 'provider-settings.json'
    if path.exists() and load(path).get('provider') == 'openai':
        settings = load(path)
        if (set(settings) != {'provider', 'api', 'model', 'reasoning_effort', 'max_output_tokens', 'json_mode', 'store'}
            or settings['api'] != 'responses' or settings['model'] not in ALLOWED_OPENAI_MODELS
            or settings['reasoning_effort'] not in {'low', 'medium', 'high', 'xhigh', 'max'}
            or type(settings['max_output_tokens']) is not int or not 2400 <= settings['max_output_tokens'] <= 16384
            or settings['json_mode'] != 'json_object' or settings['store'] is not False):
            raise ValueError('unsupported OpenAI experiment settings')
        source = (ROOT / 'tools/openai_interview_transport.py').read_text()
        return 'SETTINGS = ' + repr(settings) + '\n' + source, settings
    text = relay_source()
    if not path.exists():
        return text, {'thinking': 'disabled', 'max_tokens': 2400, 'temperature': 0.2}
    settings = load(path)
    enabled = False
    disabled = (set(settings) in ({'model', 'thinking', 'max_tokens'}, {'model', 'thinking', 'max_tokens', 'temperature'})
                and settings.get('thinking') == 'disabled'
                and ('temperature' not in settings or (type(settings['temperature']) in (int, float) and 0 <= settings['temperature'] <= 1)))
    if not disabled or type(settings.get('max_tokens')) is not int or not 2400 <= settings['max_tokens'] <= 16384:
        raise ValueError('Interview thinking must be disabled')
    selected_model=settings.get('model', 'deepseek-flash')
    if selected_model not in ALLOWED_DS_MODELS:
        raise ValueError('unsupported DeepSeek model')
    if selected_model!='deepseek-flash':
        # The server configuration stays untouched; only this frozen request
        # explicitly selects another verified DeepSeek model. Do not read keys.
        text=text.replace("model=os.environ.get('LLM_TURN_MODEL') or os.environ.get('LLM_MODEL')",
                          "configured_model=os.environ.get('LLM_TURN_MODEL') or os.environ.get('LLM_MODEL')\nmodel="+repr(selected_model))
        text=text.replace("or model!='deepseek-flash'", "or configured_model!='deepseek-flash'")
    old = "'thinking':{'type':'disabled'},'max_tokens':2400,'temperature':0.2"
    if text.count(old) != 1:
        raise ValueError('base transport changed; provider experiment requires review')
    if enabled:
        new = ("'thinking':{'type':'enabled'},'reasoning_effort':" + repr(settings['reasoning_effort']) +
               ",'max_tokens':" + str(settings['max_tokens']))
    else:
        new = ("'thinking':{'type':'disabled'},'max_tokens':"+str(settings['max_tokens'])+
               (",'temperature':"+repr(settings['temperature']) if 'temperature' in settings else ''))
    text = text.replace(old, new)
    text = text.replace('urlopen(req,timeout=45)', 'urlopen(req,timeout=90)')
    text = text.replace("emit({'kind':'run_start','model':model,",
                        "emit({'kind':'run_start','provider_settings':" + repr(settings) + ",'model':model,")
    text = text.replace("'finish_reason':raw['choices'][0].get('finish_reason')",
                        "'finish_reason':raw['choices'][0].get('finish_reason'),'response_model':raw.get('model'),'provider_settings':" + repr(settings))
    return text, settings


def fatal_provider_error(response):
    return response.get('http_status') == 402 or response.get('fatal_provider_error') is True


def provider_stop_path(session):
    provider = load(session / 'freeze.json').get('provider_settings', {}).get('provider', 'deepseek')
    return session / ('stopped-provider.json' if provider == 'openai' else 'stopped-402.json')


class DevelopmentBudgetStop(RuntimeError):
    pass


def raw_usage(session):
    """Count original transport logs once, including unassembled paid work."""
    total = {'total_tokens': 0, 'scheduled_requests': 0, 'reported_calls': 0, 'calls_without_usage': 0}
    for path in (session / 'batches').glob('*.request.json'):
        total['scheduled_requests'] += len(load(path).get('jobs', []))
    for path in (session / 'batches').glob('*.raw.jsonl'):
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('kind') not in ('model_call', 'call_error'):
                continue
            total['reported_calls'] += 1
            usage = row.get('usage') or {}
            tokens = usage.get('total_tokens')
            if isinstance(tokens, int):
                total['total_tokens'] += tokens
            else:
                total['calls_without_usage'] += 1
    return total


def budget_stop(session, reason, **details):
    save(session / 'budget-stop.json', {'at': now(), 'reason': reason, 'limits': RUN_BUDGET,
        'raw_usage': raw_usage(session), 'not_complete_or_accepted': True, **details})
    raise DevelopmentBudgetStop(reason)


def check_dispatch_budget(session, next_calls):
    if not RUN_BUDGET:
        return
    used = raw_usage(session)
    token_limit = RUN_BUDGET.get('token_budget')
    call_limit = RUN_BUDGET.get('call_budget')
    if token_limit and used['total_tokens'] >= token_limit:
        budget_stop(session, 'observed_token_budget', next_calls=next_calls)
    if call_limit and used['scheduled_requests'] + next_calls > call_limit:
        budget_stop(session, 'request_count_budget', next_calls=next_calls)


def check_checkpoint_budget(session):
    if not RUN_BUDGET or not (session / 'scores.json').exists():
        return
    report = load(session / 'scores.json')
    rows = report['rows']
    failures = sum(r['execution'] == 'evaluated' and not r['passed'] for r in rows)
    limit = RUN_BUDGET.get('critical_failure_limit')
    if limit and failures >= limit:
        budget_stop(session, 'development_failure_limit', evaluated_failures=failures)
    if RUN_BUDGET.get('stop_when_impossible') and 100 * failures >= 5 * len(rows):
        budget_stop(session, 'strict95_mathematically_impossible', evaluated_failures=failures, planned=len(rows))


def node_json(script, *args):
    p = subprocess.run(['node', '-e', script, *map(str, args)], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError('engine_execution_error: ' + p.stderr[:1000])
    return json.loads(p.stdout)


def review_input(runtime, model_input, candidate, checked):
    """Use the frozen engine's pure A/B feedback builder, with legacy parity."""
    script = r"""
const fs=require('fs'),g=require(process.argv[1]),j=JSON.parse(fs.readFileSync(0,'utf8'));
const out=typeof g.reviewInput==='function'?g.reviewInput(j.payload,j.candidate,j.checked):{
 ...j.payload,semantic_review:{unverified_candidate:j.candidate,
 code_validation_errors:[...(j.checked.errors||[]),...(j.checked.semantic_rejections||[]).map(x=>x.field_id+':'+x.reason)],
 instruction:'Audit all fields against own sources and contract, including omissions; no gold supplied.'}};
process.stdout.write(JSON.stringify(out));
"""
    proc = subprocess.run(['node', '-e', script, str(runtime / 'engine.js')],
                          input=json.dumps({'payload': model_input, 'candidate': candidate, 'checked': checked}, ensure_ascii=False),
                          capture_output=True, text=True, timeout=30, check=True)
    return json.loads(proc.stdout)


def last_batch_number(session):
    """Reserve past requests too: a local lock failure may have no raw log."""
    numbers = [int(path.name.split('.', 1)[0]) for path in (session / 'batches').glob('*')
               if re.fullmatch(r'\d+\.raw\.(?:jsonl|request\.json)', path.name)]
    return max(numbers, default=0)


def contracts(runtime):
    return node_json("const g=require(process.argv[1]),protocol=g.getContract().output_protocol||{};process.stdout.write(JSON.stringify({fields:g.fields,questions:g.baseQuestion,evidence_unit_protocol:protocol.evidence_units||null,model_source_fields:protocol.model_source_fields||null,model_input_projection:protocol.model_input_projection||null,review_mode:protocol.review_mode||null,workflow:protocol.workflow||null,field_verification:protocol.field_verification||null,model_field_contract_keys:protocol.model_field_contract_keys||null,question_contracts:Object.fromEntries(Object.keys(g.baseQuestion).map(id=>{const q=g.getContract(id);return [id,{premise:q.premise,success:q.success,notes:q.notes,material_type:q.material_type}]}))}));", runtime / 'engine.js')


def all_refs(obj):
    """Only explicit evidence objects; labels and arbitrary free text are not evidence."""
    refs = []
    if isinstance(obj, dict):
        if 'source_id' in obj and 'quote' in obj:
            refs.append(obj)
        else:
            for value in obj.values():
                refs.extend(all_refs(value))
    elif isinstance(obj, list):
        for value in obj:
            refs.extend(all_refs(value))
    return refs


def requirements_for_state(gold, state):
    """Choose the predeclared state branch; never infer expectations from output."""
    return {**gold, **gold.get('state_requirements', {}).get(state, {})}


def fact_variants(fact):
    """Pre-registered alternative witnesses, each internally coherent."""
    base={key:value for key,value in fact.items() if key!='alternatives'}
    return [base, *[{**base, **alternative} for alternative in fact.get('alternatives',[])]]


def validate_dataset(data, defs, require_full=False):
    if data.get('schema') != SCHEMA:
        raise ValueError('unsupported dataset schema')
    narrators = {n['id']: n for n in data['narrators']}
    if len(narrators) != len(data['narrators']):
        raise ValueError('duplicate narrator id')
    seen, coverage, positive = set(), set(), defaultdict(int)
    used_narrators = set()
    by_split = defaultdict(set)
    for case in data['cases']:
        cid, qid, nid = case['id'], case['question_id'], case['narrator_id']
        if cid in seen or qid not in defs['questions'] or nid not in narrators:
            raise ValueError('duplicate/unknown case, question, or narrator: ' + cid)
        seen.add(cid)
        used_narrators.add(nid)
        coverage.add(qid)
        narrator = narrators[nid]
        if narrator.get('split') not in ('development', 'holdout', 'new_holdout'):
            raise ValueError('split must be assigned by entire narrator: ' + nid)
        by_split[narrator['split']].add(nid)
        if not narrator.get('source_url') or not narrator.get('name'):
            raise ValueError('published source identity missing: ' + nid)
        source_ids = set()
        if not case.get('turns'):
            raise ValueError('no turns: ' + cid)
        for turn_index, turn in enumerate(case['turns']):
            source = turn['source']
            if not source.get('text') or source['id'] in source_ids:
                raise ValueError('empty/repeated source id: ' + cid)
            source_ids.add(source['id'])
            # No project question is invented as the historical prompt. A narrative may have question=null.
            if 'question' not in source:
                raise ValueError('source.question must be original interviewer words or null: ' + cid)
            if source.get('question_id', qid) != qid:
                raise ValueError('cross-question source: ' + cid)
            focus = turn.get('focus')
            if focus and defs['fields'].get(focus['field_id'], {}).get('question_id') != qid:
                raise ValueError('cross-question focus: ' + cid)
            expected = turn.get('expected')
            if not expected or not expected.get('fields') or not expected.get('followup'):
                raise ValueError('gold fields and followup required at every checkpoint: ' + cid)
            text_by_source = {t['source']['id']: t['source']['text'] for t in case['turns'][:turn_index + 1]}
            question_fields = {fid for fid, definition in defs['fields'].items() if definition['question_id'] == qid}
            if set(expected['fields']) != question_fields:
                raise ValueError('gold must explicitly cover every field in the question: ' + cid)
            for fid, gold in expected['fields'].items():
                if fid not in defs['fields'] or defs['fields'][fid]['question_id'] != qid:
                    raise ValueError('unknown/cross-question gold field: ' + fid)
                states = gold.get('states', [gold.get('state')])
                if not states or any(s not in {'missing','known','none','unknown','declined','ambiguous','conflict','deferred','not_applicable'} for s in states):
                    raise ValueError('invalid gold state: ' + fid)
                if gold.get('state_requirements'):
                    if set(gold['state_requirements'])!=set(states):
                        raise ValueError('every allowed state must have one explicit branch: '+cid+'/'+fid)
                    for state,branch in gold['state_requirements'].items():
                        if state=='missing' and (all_refs(branch) or branch.get('value_groups') or branch.get('facts')):
                            raise ValueError('missing branch cannot require a factual claim: '+cid+'/'+fid)
                        if state not in ('missing','not_applicable') and (not branch.get('evidence') or not branch.get('relation_evidence') or not branch.get('scope',{}).get('subject')):
                            raise ValueError('nonmissing state branch needs evidence and fixed relations: '+cid+'/'+fid)
                for ref in all_refs(gold):
                    if not ref.get('quote') or ref['source_id'] not in text_by_source or any(option not in text_by_source[ref['source_id']] for option in ref.get('quote_options',[ref['quote']])):
                        raise ValueError('gold evidence is not verbatim: ' + cid + '/' + fid)
                if gold.get('inactive_unscored') and defs['fields'][fid].get('requirement')!='conditional':
                    raise ValueError('only a declared inactive conditional field may use inactive_unscored: ' + fid)
                if gold.get('optional_unscored'):
                    if defs['fields'][fid].get('requirement') != 'optional':
                        raise ValueError('only optional fields may be unscored: ' + fid)
                    continue
                if 'known' in states:
                    selected=requirements_for_state(gold,'known')
                    facts=[variant for fact in (selected.get('facts') or [selected]) for variant in fact_variants(fact)]
                    if any(not fact.get('value_groups') or not fact.get('evidence') for fact in facts):
                        raise ValueError('known gold needs value_groups and evidence: ' + cid + '/' + fid)
                    for fact in facts:
                        for group in fact['value_groups']:
                            if not group or any(not isinstance(fragment,str) or not any(fragment in text for text in text_by_source.values()) for fragment in group):
                                raise ValueError('gold value alternatives must be literal source fragments: ' + cid + '/' + fid)
                        for pattern in fact.get('forbidden_value_patterns',[]):
                            try:re.compile(pattern)
                            except re.error as exc:raise ValueError('invalid predeclared forbidden-value expression: '+cid+'/'+fid) from exc
                    if not gold.get('inactive_unscored') and 'missing' not in states:positive[qid] += 1
                    if any(not fact.get('relation_evidence') or not fact.get('scope',{}).get('subject') for fact in facts):
                        raise ValueError('known gold requires independently fixed subject and relation evidence: ' + cid + '/' + fid)
                    if defs['fields'][fid].get('type') in ('time','duration') and any(not fact.get('precision') for fact in facts):
                        raise ValueError('time/duration gold requires precision declaration: ' + cid + '/' + fid)
                if set(states) - {'missing'} and not all_refs(gold) and 'not_applicable' not in states:
                    raise ValueError('nonmissing gold needs explicit evidence: ' + cid + '/' + fid)
    if require_full:
        if len(used_narrators) < 50:
            raise ValueError('full run needs >=50 distinct narrators')
        if coverage != set(defs['questions']):
            raise ValueError('full run must cover all questions: ' + ','.join(sorted(set(defs['questions']) - coverage)))
        if set(positive) != set(defs['questions']):
            raise ValueError('full run must include positive gold in all questions: ' + ','.join(sorted(set(defs['questions'])-set(positive))))
        if len(by_split['holdout']) < 10:
            raise ValueError('full run needs >=10 held-out complete narrators')
    return {'narrators': len(used_narrators), 'declared_narrators': len(narrators), 'cases': len(seen), 'question_coverage': len(coverage),
            'questions': sorted(coverage), 'narrators_by_split': {k: len(v) for k,v in by_split.items()},
            'positive_checkpoints_per_question': dict(positive)}


def prepare(args):
    runtime, out = args.runtime.resolve(), args.out.resolve()
    if out.exists():
        raise ValueError('output already exists; never overwrite a frozen run')
    defs = contracts(runtime)
    data = load(args.dataset)
    inventory = validate_dataset(data, defs, args.require_full)
    out.mkdir(parents=True)
    shutil.copytree(runtime, out / 'runtime')
    shutil.copy2(args.dataset, out / 'dataset.json')
    source_manifest = data.get('authoring',{}).get('source_manifest')
    if source_manifest:
        manifest_path=ROOT/source_manifest
        expected_hash=data['authoring'].get('source_manifest_sha256')
        if expected_hash and sha(manifest_path)!=expected_hash:
            raise ValueError('source manifest changed since gold authoring')
        manifest=load(manifest_path)
        selected_manifest={k:copy.deepcopy(v) for k,v in manifest.items() if k!='narrators'}
        selected_manifest['narrators']=[]
        source_base=ROOT/data['authoring'].get('source_base','docs/test-materials/full-interview-50')
        used_source_ids={turn['source'].get('source_id') for case in data['cases'] for turn in case['turns']}
        for narrator in data['narrators']:
            for doc in narrator.get('sources',[]):
                if doc['id'] not in used_source_ids:continue
                for path_key,hash_key in [('raw_path','raw_sha256'),('body_path','body_sha256')]:
                    if not doc.get(path_key):continue
                    original=source_base/doc[path_key]
                    if doc.get(hash_key) and sha(original)!=doc[hash_key]:
                        raise ValueError('published source document changed: '+doc['id'])
                    dest=out/'source-documents'/Path(doc[path_key]).name
                    dest.parent.mkdir(exist_ok=True)
                    shutil.copy2(original,dest)
        used_narrator_ids={case['narrator_id'] for case in data['cases']}
        for narrator in manifest['narrators']:
            if narrator['id'] not in used_narrator_ids:continue
            selected=copy.deepcopy(narrator)
            selected['sources']=[doc for doc in selected['sources'] if doc['id'] in used_source_ids]
            for doc in selected['sources']:
                for key in ('raw_path','body_path'):
                    if doc.get(key):doc[key]='source-documents/'+Path(doc[key]).name
            selected['excerpts']=[excerpt for excerpt in selected['excerpts'] if excerpt['source_id'] in used_source_ids]
            selected_manifest['narrators'].append(selected)
        selected_manifest['freeze_note']='Selected source documents only; original narrator words and questions unchanged. Paths relocated to frozen source-documents.'
        selected_manifest['original_manifest_sha256']=sha(manifest_path)
        save(out/'source-manifest.snapshot.json',selected_manifest)
    shutil.copy2(__file__, out / 'runner.snapshot.py')
    save(out / 'contracts.snapshot.json', defs)
    transport, provider_settings = configured_relay(runtime)
    (out / 'transport-remote.py').write_text(transport)
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    freeze = {'schema': SCHEMA, 'created_at': now(), 'model': MODEL,
              'source_kind': 'published_transcript', 'question_context_mode': 'independent',
              'protocol_retry_limit': 1, 'provider_settings': provider_settings, 'dataset_authoring': data.get('authoring', {}),
              'files': files, 'inventory': inventory, 'scoring': 'all frozen checks per field; macro by question/case/narrator; missing controls separate',
              'max_parallel_model_calls': 4, 'runner_sha256': sha(__file__)}
    save(out / 'freeze.json', freeze)
    print(json.dumps({'prepared': str(out), **inventory}, ensure_ascii=False))


def verify(session):
    freeze = load(session / 'freeze.json')
    if freeze['model'] != MODEL or freeze['question_context_mode'] != 'independent':
        raise ValueError('invalid frozen model/context')
    for name, expected in freeze['files'].items():
        if sha(session / name) != expected:
            raise ValueError('frozen file changed: ' + name)
    if sha(__file__) != freeze['runner_sha256']:
        raise ValueError('runner changed; use frozen runner.snapshot.py with --root project directory')
    return freeze


def batch_call(session, prompt, jobs, raw_path):
    if not 1 <= len(jobs) <= 4:
        raise ValueError('strict batch concurrency 1..4')
    check_dispatch_budget(session, len(jobs))
    remote = (session / 'transport-remote.py').read_text()
    encoded = base64.b64encode(remote.encode()).decode()
    inner = "exec(__import__('base64').b64decode(" + repr(encoded) + '))'
    command = 'sudo -n docker exec -i shinian-b03-isolated python -c ' + shlex.quote(inner)
    cmd = ['ssh','-i','/Users/student03/.ssh/id_ed25519_shinian','-o','IdentitiesOnly=yes','-o','BatchMode=yes',
           '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
           '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=6','admin@47.82.83.74',command]
    provider = load(session / 'freeze.json').get('provider_settings', {}).get('provider', 'deepseek')
    lock_path = LOCK
    if provider == 'openai':
        cmd = [sys.executable, '-c', inner]
        lock_path = Path('/tmp/shinian-interview-openai-transport.lock')
    request = {'prompt': prompt, 'jobs': jobs, 'source_kind': 'published_transcript'}
    request_path = raw_path.with_suffix('.request.json')
    if raw_path.exists() or request_path.exists():
        raise ValueError('Never replace a previous transport request or raw log')
    save(request_path, request)
    with lock_path.open('a') as lock:
        deadline = time.monotonic() + 180
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    errors = {j['id']: {'kind':'call_error','id':j['id'],'exception':'TransportBusy'} for j in jobs}
                    # These are local dispatch failures, not provider responses.
                    # Retain them in the transport history as well as turn files.
                    with raw_path.open('x') as output:
                        for error in errors.values():
                            output.write(json.dumps(error, ensure_ascii=False) + '\n')
                    return errors
                time.sleep(.2)
        try:
            with raw_path.open('w') as output:
                proc = subprocess.run(cmd, input=json.dumps(request, ensure_ascii=False), stdout=output,
                                      stderr=subprocess.PIPE, text=True, timeout=110)
            transport_error = None if proc.returncode == 0 else ('LocalTransportError' if provider == 'openai' else 'SSHTransportError')
        except (OSError, subprocess.TimeoutExpired) as exc:
            transport_error = type(exc).__name__
    rows = []
    if raw_path.exists():
        for line in raw_path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    confirmed = any(r.get('kind')=='run_start' and r.get('model')==MODEL and r.get('source_kind')=='published_transcript' for r in rows)
    result = {}
    for job in jobs:
        calls = [r for r in rows if r.get('id')==job['id'] and r.get('kind') in ('model_call','call_error')]
        if confirmed and len(calls)==1:
            result[job['id']] = calls[0]
        else:
            result[job['id']] = {'kind':'call_error','id':job['id'], 'exception':transport_error or 'InvalidTransportResponse'}
    return result


def payload_for(case, turn_index, defs, previous, ask_counts, runtime=None):
    qid = case['question_id']
    turn = case['turns'][turn_index]
    sources = []
    for t in case['turns'][:turn_index+1]:
        source = copy.deepcopy(t['source'])
        source.update(question_id=qid, speaker='narrator')
        source.setdefault('question', None)
        if t.get('focus'):
            source['target_field_id'] = t['focus']['field_id']
        if defs.get('model_source_fields'):
            source={key:source[key] for key in defs['model_source_fields'] if key in source}
        sources.append(source)
    payload = {'question_id':qid, 'main_question':defs['questions'][qid], 'question_context_mode':'independent',
               'current_question':sources[-1]['question'] or '', 'source_kind':'published_transcript', 'historical_question_verified':bool(sources[-1]['question']), 'focus':turn.get('focus'),
               'field_contract':{k:v for k,v in defs['fields'].items() if v['question_id']==qid},
               'question_contract':defs.get('question_contracts',{}).get(qid,{}),
               'sources':sources, 'previous_fields':copy.deepcopy(previous), 'ask_counts':copy.deepcopy(ask_counts)}
    if defs.get('model_field_contract_keys'):
        payload['field_contract']={fid:{key:value for key,value in field.items() if key in defs['model_field_contract_keys']}
                                   for fid,field in payload['field_contract'].items()}
    if defs.get('evidence_unit_protocol'):
        if defs['evidence_unit_protocol']!='sentence_units_v1' or runtime is None:
            raise ValueError('explicit frozen evidence-unit runtime is required')
        payload['evidence_units']=node_json(
            "const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.evidenceUnits(process.argv[2],JSON.parse(process.argv[3]))));",
            runtime/'engine.js',qid,json.dumps(sources,ensure_ascii=False))
    if any(defs['fields'].get(f,{}).get('question_id')!=qid for f in previous):
        raise ValueError('cross-question state prohibited')
    source_ids = {s['id'] for s in sources}
    if any(r['source_id'] not in source_ids for r in all_refs(previous)):
        raise ValueError('cross-question evidence prohibited')
    return payload


def model_input(payload, defs, runtime):
    """Pure runtime-defined model view; retain the original controller context."""
    if not defs.get('model_input_projection'):
        return copy.deepcopy(payload)
    if defs['model_input_projection']!='target_fields_v1':
        raise ValueError('unsupported explicit model input projection')
    return node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.modelInput(JSON.parse(process.argv[2]))));",
                     runtime/'engine.js',json.dumps(payload,ensure_ascii=False))


def analyze(session, payload, proposal, path, call=None):
    save(path, {'payload':payload, 'proposal':proposal,'raw_model_response':{k:(call or {}).get(k) for k in ('raw_content','parse_error','finish_reason')}})
    return node_json("const fs=require('fs'),g=require(process.argv[1]),j=JSON.parse(fs.readFileSync(process.argv[2]));let r,proposal=j.proposal,parseAudit=null;if(proposal==null&&j.raw_model_response?.parse_error&&typeof g.parseProposal==='function'){parseAudit=g.parseProposal(j.raw_model_response.raw_content,{finish_reason:j.raw_model_response.finish_reason});if(parseAudit.ok)proposal=parseAudit.proposal;}try{r=g.analyze(j.payload.question_id,j.payload.sources,proposal,{current_question:j.payload.current_question,focus:j.payload.focus,previous_fields:j.payload.previous_fields,ask_counts:j.payload.ask_counts});}catch(e){r={decision:'invalid',errors:['engine_exception:'+e.message],fields:{}}};if(parseAudit){r.transport_parse_audit={ok:parseAudit.ok,original_parse_error:parseAudit.original_parse_error,normalizations:parseAudit.normalizations,errors:parseAudit.errors};}process.stdout.write(JSON.stringify(r));", session/'runtime/engine.js', path)


def advance_wave(session,wave,active):
    completed=0
    for item in wave:
        case,index=item['case'],item['index']
        path=session/'cases'/case['id']/('turn-%03d'%index)/'result.json'
        if not path.exists():continue
        record=load(path)
        if record['kind']=='evaluated' and record['result'].get('decision')!='invalid':
            item['previous']=record['result'].get('fields',{})
            target=record['result'].get('target')
            if record['result'].get('decision')=='ask' and target:item['counts'][target]=item['counts'].get(target,0)+1
            if index+1<len(case['turns']):item['index']+=1;active.append(item)
            else:completed+=1
        else:completed+=1
    return completed


def run_field_steps_wave(session,jobs,bindings,batch_number,concurrency):
    """Execute same-question field dependencies, no redundant full draft."""
    runtime=session/'runtime'
    field_audit=load(session/'contracts.snapshot.json').get('field_verification')=='source_audit_v1'
    states={j['id']:{'job':j,'controller':bindings[j['id']][3],'entries':[],'done':[],
        'control':None,'errors':[],'field_calls':0,'control_calls':0,'response_ids':[],
        'review_calls':0,'failure':None,'finished':False} for j in jobs}
    def save_call(state,tag,job,call):
        _,tdir,attempt,_=bindings[state['job']['id']]
        save(tdir/('request-%03d-%s.json'%(attempt,tag)),job)
        save(tdir/('response-%03d-%s.json'%(attempt,tag)),call)
        state['response_ids'].append(job['id'])
    def dispatch(prompt,jobs):
        nonlocal batch_number
        out={}
        for offset in range(0,len(jobs),concurrency):
            batch_number+=1
            out.update(batch_call(session,prompt,jobs[offset:offset+concurrency],session/'batches'/('%05d.raw.jsonl'%batch_number)))
            if any(fatal_provider_error(c) for c in out.values()):break
        return out
    controls=[];control_owners={}
    for original_id,state in states.items():
        plan=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.controlStep(JSON.parse(process.argv[2]))));",runtime/'engine.js',json.dumps(state['job']['payload'],ensure_ascii=False))
        if plan['needs_model']:
            job={'id':original_id+'-control','payload':plan['payload']};controls.append(job);control_owners[job['id']]=original_id
        else:state['control']=plan['proposal']['control']
    responses=dispatch((runtime/'control-prompt.txt').read_text(),controls)
    for job in controls:
        if job['id'] not in responses:continue
        state=states[control_owners[job['id']]];call=responses[job['id']]
        save_call(state,'control',job,call);state['control_calls']+=1
        if call['kind']!='model_call':state['failure']=call;continue
        output=call.get('output');state['control']=output.get('control') if isinstance(output,dict) else None
        if not isinstance(output,dict) or set(output)-{'control','fields','extra_material'} or output.get('fields')!={}:state['errors'].append('invalid_control_classifier_shape')
        _,tdir,attempt,payload=bindings[state['job']['id']]
        checked=analyze(session,payload,{'control':state['control'],'fields':{}},tdir/('control-engine-input-%03d.json'%attempt))
        save(tdir/('control-decision-%03d.json'%attempt),checked)
        if checked['decision'] in ('paused','skipped','deferred'):
            save(tdir/'result.json',{'kind':'evaluated','result':checked,'internal_repairs':0,'semantic_review_calls':0,
                'field_model_calls':0,'control_model_calls':state['control_calls'],'workflow':'field_steps_v1','at':now()});state['finished']=True
    stopped=any(fatal_provider_error(c) for c in responses.values())
    step=0
    while not stopped:
        planned=[];owners={}
        for original_id,state in states.items():
            if state['finished'] or state['failure']:continue
            _,tdir,attempt,payload=bindings[original_id]
            assembled=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.assembleFieldReviews(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))));",runtime/'engine.js',json.dumps({'control':state['control']},ensure_ascii=False),json.dumps(state['entries'],ensure_ascii=False))
            checked=analyze(session,payload,assembled['proposal'],tdir/('step-engine-input-%03d-%03d.json'%(attempt,step)))
            frontier=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.stepFrontier(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]),JSON.parse(process.argv[4]))));",runtime/'engine.js',json.dumps(state['job']['payload'],ensure_ascii=False),json.dumps(checked,ensure_ascii=False),json.dumps(state['done']))
            for field in frontier:
                fid=field['field_id']
                if fid in state['done']:raise ValueError('field step repeated')
                state['done'].append(fid)
                job={'id':original_id+'-field-'+fid,'payload':field['payload']};planned.append(job);owners[job['id']]=(original_id,fid)
        if not planned:break
        responses=dispatch((runtime/'reviewer-prompt.txt').read_text(),planned)
        audits=[];audit_owners={}
        for job in planned:
            if job['id'] not in responses:continue
            original_id,fid=owners[job['id']];state=states[original_id];call=responses[job['id']]
            save_call(state,'field-'+fid,job,call);state['field_calls']+=1
            if call['kind']!='model_call':state['failure']=call
            elif field_audit:
                view=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.fieldVerification(JSON.parse(process.argv[2]),process.argv[3],JSON.parse(process.argv[4]))));",runtime/'engine.js',json.dumps(job['payload'],ensure_ascii=False),fid,json.dumps(call.get('output'),ensure_ascii=False))
                audit_job={'id':original_id+'-review-'+fid,'payload':view};audits.append(audit_job);audit_owners[audit_job['id']]=(original_id,fid)
            else:state['entries'].append({'field_id':fid,'output':call.get('output')})
        stopped=any(fatal_provider_error(c) for c in responses.values())
        if audits and not stopped:
            verified=dispatch((runtime/'reviewer-prompt.txt').read_text(),audits)
            for job in audits:
                if job['id'] not in verified:continue
                original_id,fid=audit_owners[job['id']];state=states[original_id];call=verified[job['id']]
                save_call(state,'review-'+fid,job,call);state['review_calls']+=1
                if call['kind']!='model_call':state['failure']=call
                else:state['entries'].append({'field_id':fid,'output':call.get('output')})
            stopped=any(fatal_provider_error(c) for c in verified.values())
        step+=1
        if step>max(len(s['job']['payload']['field_contract']) for s in states.values()):raise ValueError('field step cycle')
    repairs=[];repair_states={}
    for original_id,state in states.items():
        if state['finished']:continue
        _,tdir,attempt,payload=bindings[original_id]
        if state['failure']:
            save(tdir/'result.json',{**state['failure'],'at':now(),'workflow':'field_steps_v1'})
            continue
        if stopped:continue
        assembled=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.assembleFieldReviews(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))));",runtime/'engine.js',json.dumps({'control':state['control']},ensure_ascii=False),json.dumps(state['entries'],ensure_ascii=False))
        save(tdir/('assembled-initial-%03d.json'%attempt),{**assembled,'actual_response_ids':state['response_ids'],'note':'Deterministic initial field-step assembly, not a provider response.'})
        result=analyze(session,payload,assembled['proposal'],tdir/('engine-input-%03d.json'%attempt))
        extra=state['errors']+assembled['errors']
        if extra:result.update(decision='invalid',target=None,question=None);result.setdefault('errors',[]).extend(extra)
        save(tdir/('decision-%03d.json'%attempt),result)
        if result['decision']=='invalid':
            repair_context=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.repairContext(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))));",runtime/'engine.js',json.dumps(payload,ensure_ascii=False),json.dumps(result,ensure_ascii=False))
            save(tdir/('protocol-repair-context-%03d.json'%attempt),repair_context)
            state['repair_controller']=repair_context['payload']
            job=copy.deepcopy(state['job']);job['id']+='-repair1'
            job['payload']=model_input(state['repair_controller'],load(session/'contracts.snapshot.json'),runtime)
            job['payload']['extraction_retry']={'attempt':1,'validation_errors':result['errors'],'previous_proposal':assembled['proposal']}
            repairs.append(job);repair_states[job['id']]=state
        else:
            save(tdir/'result.json',{'kind':'evaluated','result':result,'internal_repairs':0,'semantic_review_calls':state['review_calls'],
                'field_model_calls':state['field_calls'],'control_model_calls':state['control_calls'],'workflow':'field_steps_v1','at':now()})
    if repairs and not stopped:
        responses=dispatch((runtime/'reviewer-prompt.txt').read_text(),repairs)
        for job in repairs:
            if job['id'] not in responses:continue
            state=repair_states[job['id']];call=responses[job['id']];save_call(state,'repair1',job,call)
            _,tdir,attempt,payload=bindings[state['job']['id']]
            if call['kind']=='model_call':
                result=analyze(session,state.get('repair_controller',payload),call.get('output'),tdir/('engine-input-%03d-repair1.json'%attempt),call)
                save(tdir/('decision-%03d-repair1.json'%attempt),result)
                record={'kind':'evaluated','result':result,'internal_repairs':1,'semantic_review_calls':state['review_calls'],
                    'field_model_calls':state['field_calls'],'control_model_calls':state['control_calls'],'workflow':'field_steps_v1','at':now()}
            else:record={**call,'internal_repairs':1,'workflow':'field_steps_v1','at':now()}
            save(tdir/'result.json',record)
        stopped=any(fatal_provider_error(c) for c in responses.values())
    return batch_number,stopped


def run_impl(args):
    session = args.session.resolve()
    verify(session)
    if (session / 'budget-stop.json').exists():
        raise ValueError('budget-stopped diagnostic is retained; prepare a new explicit run rather than silently extending its budget')
    if (provider_stop_path(session)).exists() and not args.retry_errors:
        raise ValueError('previous provider stop retained; explicit operator --retry-errors required after external restoration')
    data, defs = load(session/'dataset.json'), load(session/'contracts.snapshot.json')
    narrators = {n['id']:n for n in data['narrators']}
    cases = [c for c in data['cases'] if args.split=='all' or narrators[c['narrator_id']]['split']==args.split]
    prompt = (session/'runtime/extractor-prompt.txt').read_text()
    review_path = session/'runtime/reviewer-prompt.txt'
    review_prompt = review_path.read_text() if review_path.exists() else None
    active, skipped = [], 0
    for case in cases:
        case_dir = session/'cases'/case['id']
        case_dir.mkdir(parents=True, exist_ok=True)
        previous, counts, index = {}, {}, 0
        blocked = False
        for index in range(len(case['turns'])):
            result_path = case_dir/('turn-%03d'%index)/'result.json'
            if not result_path.exists():
                break
            record = load(result_path)
            if record['kind']!='evaluated' or record.get('result',{}).get('decision')=='invalid':
                if not args.retry_errors or record.get('result',{}).get('decision')=='invalid':
                    blocked=True
                    break
                break
            previous = record['result'].get('fields', {})
            target = record['result'].get('target')
            if record['result'].get('decision')=='ask' and target:
                counts[target]=counts.get(target,0)+1
        else:
            skipped += 1
            continue
        if not blocked:
            active.append({'case':case,'index':index,'previous':previous,'counts':counts})
    print(json.dumps({'run_started':now(),'eligible_cases':len(cases),'already_finished_cases':skipped,'remaining_cases':len(active),'split':args.split,'model':MODEL},ensure_ascii=False),flush=True)
    batch_number = last_batch_number(session)
    executed = 0
    while active and (not args.max_cases or executed < args.max_cases):
        check_checkpoint_budget(session)
        wave, active = active[:args.concurrency], active[args.concurrency:]
        jobs, bindings = [], {}
        for item in wave:
            case, index = item['case'], item['index']
            tdir=session/'cases'/case['id']/('turn-%03d'%index)
            tdir.mkdir(parents=True,exist_ok=True)
            payload=payload_for(case,index,defs,item['previous'],item['counts'],session/'runtime')
            attempt=len(list(tdir.glob('response-*.json')))
            jid=case['id']+'-t%03d-a%03d'%(index,attempt)
            job={'id':jid,'payload':model_input(payload,defs,session/'runtime')}
            save(tdir/(('controller-plan-%03d.json' if defs.get('workflow')=='field_steps_v1' else 'request-%03d.json')%attempt),job)
            bindings[jid]=(item,tdir,attempt,payload)
            jobs.append(job)
        if defs.get('workflow')=='field_steps_v1':
            batch_number,stopped=run_field_steps_wave(session,jobs,bindings,batch_number,args.concurrency)
            if stopped:
                save(provider_stop_path(session),{'at':now(),'automatic_recharge':False})
                score_session(session);return 3
            executed+=advance_wave(session,wave,active)
            print(json.dumps({'batch':batch_number,'completed_or_blocked_cases_this_run':executed,'remaining_cases':len(active),'workflow':'field_steps_v1'},ensure_ascii=False),flush=True)
            score_session(session)
            continue
        batch_number+=1
        raw_path=session/'batches'/('%05d.raw.jsonl'%batch_number)
        raw_path.parent.mkdir(exist_ok=True)
        responses=batch_call(session,prompt,jobs,raw_path)
        # A frozen optional second semantic pass audits every successful first
        # response, including valid-looking omissions. It is not a hidden retry:
        # both provider calls and both code decisions are retained and scored.
        reviewed_ids=set()
        review_counts={}
        assembly_failures={}
        if review_prompt:
            review_jobs=[]
            review_bindings={}
            for job in jobs:
                item,tdir,attempt,payload=bindings[job['id']]
                call=responses[job['id']]
                save(tdir/('response-%03d.json'%attempt),call)
                if call['kind']!='model_call':
                    continue
                first=analyze(session,payload,call.get('output'),tdir/('engine-input-%03d.json'%attempt),call)
                save(tdir/('decision-%03d.json'%attempt),first)
                if defs.get('review_mode')=='per_field_v1':
                    planned=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.reviewPlan(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))));",
                        session/'runtime/engine.js',json.dumps(job['payload'],ensure_ascii=False),json.dumps(first,ensure_ascii=False))
                    for field_review in planned:
                        rid=job['id']+'-field-'+field_review['field_id']+'-review'
                        review_jobs.append({'id':rid,'payload':field_review['payload']})
                        review_bindings[rid]=(job['id'],field_review['field_id'])
                elif defs.get('review_mode') is None:
                    review=copy.deepcopy(job)
                    review['id']+='-review'
                    review['payload']=review_input(session/'runtime',job['payload'],call.get('output'),first)
                    review_jobs.append(review)
                    review_bindings[review['id']]=(job['id'],None)
                else:raise ValueError('unknown frozen semantic review mode')
            review_responses={}
            for offset in range(0,len(review_jobs),args.concurrency):
                batch_number+=1
                review_raw=session/'batches'/('%05d.raw.jsonl'%batch_number)
                review_responses.update(batch_call(session,review_prompt,review_jobs[offset:offset+args.concurrency],review_raw))
            grouped={}
            for review in review_jobs:
                original_id,fid=review_bindings[review['id']]
                item,tdir,attempt,payload=bindings[original_id]
                call=review_responses[review['id']]
                suffix=('-field-'+fid+'-review') if fid else '-review'
                save(tdir/('request-%03d%s.json'%(attempt,suffix)),review)
                save(tdir/('response-%03d%s.json'%(attempt,suffix)),call)
                reviewed_ids.add(original_id)
                review_counts[original_id]=review_counts.get(original_id,0)+1
                grouped.setdefault(original_id,[]).append((fid,call))
            for original_id,entries in grouped.items():
                item,tdir,attempt,payload=bindings[original_id]
                failed=next((call for _,call in entries if call['kind']!='model_call'),None)
                if failed:
                    responses[original_id]=failed
                elif defs.get('review_mode')=='per_field_v1':
                    assembled=node_json("const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.assembleFieldReviews(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))));",
                        session/'runtime/engine.js',json.dumps(responses[original_id].get('output'),ensure_ascii=False),
                        json.dumps([{'field_id':fid,'output':call.get('output')} for fid,call in entries],ensure_ascii=False))
                    save(tdir/('assembled-review-%03d.json'%attempt),{**assembled,'actual_response_ids':[call['id'] for _,call in entries],
                        'note':'Deterministic assembly of saved actual field responses, not a provider response.'})
                    assembly_failures[original_id]=assembled['errors']
                    responses[original_id]={'kind':'model_call','output':assembled['proposal'],'deterministic_assembly':True}
                else:responses[original_id]=entries[0][1]
        repairs=[]
        for job in jobs:
            item,tdir,attempt,payload=bindings[job['id']]
            call=responses[job['id']]
            if not review_prompt:
                save(tdir/('response-%03d.json'%attempt),call)
            if call['kind']=='model_call':
                suffix='-review' if job['id'] in reviewed_ids else ''
                result=analyze(session,payload,call.get('output'),tdir/('engine-input-%03d%s.json'%(attempt,suffix)),call)
                if assembly_failures.get(job['id']):
                    result['decision']='invalid';result['target']=None;result['question']=None
                    result.setdefault('errors',[]).extend(assembly_failures[job['id']])
                save(tdir/('decision-%03d%s.json'%(attempt,suffix)),result)
                if result.get('decision')=='invalid':
                    repair=copy.deepcopy(job)
                    repair['id']+='-repair1'
                    repair['payload']['extraction_retry']={'attempt':1,'validation_errors':result.get('errors',[]),'previous_proposal':call.get('output')}
                    repairs.append(repair)
                    bindings[repair['id']]=(item,tdir,attempt,payload)
                    continue
                record={'kind':'evaluated','result':result,'internal_repairs':0,'semantic_review_calls':review_counts.get(job['id'],0),'at':now()}
            else:
                record={**call,'at':now()}
            save(tdir/'result.json',record)
        if any(fatal_provider_error(r) for r in responses.values()):
            save(provider_stop_path(session),{'at':now(),'batch':batch_number,'automatic_recharge':False})
            print('Provider rejected requests: stopped; errors and unexecuted cases retained.',flush=True)
            score_session(session)
            return 3
        if repairs:
            batch_number+=1
            repair_raw=session/'batches'/('%05d.raw.jsonl'%batch_number)
            repaired=batch_call(session,review_prompt or prompt,repairs,repair_raw)
            for job in repairs:
                item,tdir,attempt,payload=bindings[job['id']]
                call=repaired[job['id']]
                save(tdir/('response-%03d-repair1.json'%attempt),call)
                save(tdir/('request-%03d-repair1.json'%attempt),job)
                if call['kind']=='model_call':
                    result=analyze(session,payload,call.get('output'),tdir/('engine-input-%03d-repair1.json'%attempt),call)
                    save(tdir/('decision-%03d-repair1.json'%attempt),result)
                    record={'kind':'evaluated','result':result,'internal_repairs':1,'semantic_review_calls':review_counts.get(job['id'].removesuffix('-repair1'),0),'at':now()}
                else:
                    record={**call,'at':now(),'internal_repairs':1}
                save(tdir/'result.json',record)
            if any(fatal_provider_error(r) for r in repaired.values()):
                save(provider_stop_path(session),{'at':now(),'batch':batch_number,'automatic_recharge':False})
                score_session(session)
                return 3
        executed+=advance_wave(session,wave,active)
        print(json.dumps({'batch':batch_number,'completed_or_blocked_cases_this_run':executed,'remaining_cases':len(active)},ensure_ascii=False),flush=True)
        score_session(session)
    return 0


def run(args):
    global RUN_BUDGET
    RUN_BUDGET = {key: getattr(args, key, None) for key in
                  ('token_budget', 'call_budget', 'critical_failure_limit', 'stop_when_impossible')}
    if not any(RUN_BUDGET.values()):
        RUN_BUDGET = None
    if RUN_BUDGET:
        policy = args.session / 'execution-budget.json'
        if policy.exists() and load(policy) != RUN_BUDGET:
            raise ValueError('existing run budget cannot be silently changed')
        if not policy.exists():
            save(policy, RUN_BUDGET)
    if load(args.session / 'freeze.json').get('provider_settings', {}).get('provider') == 'openai':
        # Credential presence is checked before the run creates any case calls.
        # This is local-only and never puts secrets in the frozen package.
        namespace = {'__name__': 'credential_preflight'}
        exec((args.session / 'transport-remote.py').read_text(), namespace)
        namespace['credentials']()
    started=dt.datetime.now(dt.timezone.utc)
    wall_start=time.perf_counter()
    record={'started_at':started.isoformat(),'split':args.split,'model':MODEL,'concurrency':args.concurrency}
    try:
        code=run_impl(args)
        record.update(exit_code=code,status='completed' if code==0 else 'stopped')
        return code
    except DevelopmentBudgetStop as exc:
        record.update(exit_code=4, status='development_budget_stop', reason=str(exc))
        print(json.dumps({'stopped_for_budget': str(exc), 'raw_usage': raw_usage(args.session),
                          'not_complete_or_accepted': True}, ensure_ascii=False), flush=True)
        return 4
    except BaseException as exc:
        record.update(status='interrupted_or_error',error_type=type(exc).__name__)
        raise
    finally:
        record.update(ended_at=now(),wall_seconds=round(time.perf_counter()-wall_start,3))
        if args.session.exists() and (args.session/'freeze.json').exists():
            save(args.session/'run-executions'/(started.strftime('%Y%m%dT%H%M%S%f')+'.json'),record)
            score_session(args.session.resolve())


def value_text(value):
    if isinstance(value,str):
        return value
    if isinstance(value,list):
        return ' '.join(value_text(x) for x in value)
    if isinstance(value,dict):
        return ' '.join(value_text(x) for x in value.values())
    return ''


def value_fragments(value):
    """Match the contract's literal scalar/keyword-array/text-entry shapes.

    Separate selected keywords need not be adjacent with invented spaces in an
    original quote. Each fragment must still have its own literal witness in
    the same claim's evidence; no history or another claim can supply it.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [piece for item in value for piece in
                ([item] if isinstance(item, str) else
                 [item['text']] if isinstance(item, dict) and isinstance(item.get('text'), str) else [])]
    return []


def score_field(fid, gold, got, sources):
    state=got.get('state','missing')
    effective_gold=requirements_for_state(gold,state)
    if gold.get('inactive_unscored') and state=='missing':
        return {'field_id':fid,'positive':False,'substantive':False,'missed':False,'false_accept':False,'inactive_unscored':True,'passed':True,'checks':[{'dimension':'inactive_conditional_not_required','passed':True}],'expected':gold,'actual':got}
    if gold.get('optional_unscored'):
        refs=all_refs(got.get('evidence',[]))
        valid=state=='missing' or bool(refs) and all(r.get('quote') and r.get('source_id') in sources and r['quote'] in sources[r['source_id']] for r in refs)
        return {'field_id':fid,'positive':False,'substantive':False,'missed':False,'false_accept':False,'optional_unscored':True,'passed':valid,'checks':[{'dimension':'optional_evidence_if_present','passed':valid}],'expected':gold,'actual':got}

    def refs_valid(refs):
        return bool(refs) and all(r.get('quote') and r.get('source_id') in sources and r['quote'] in sources[r['source_id']] for r in refs)
    def ref_matches(expected,actual):
        return any(r.get('source_id')==expected['source_id'] and any(option in r.get('quote','') for option in expected.get('quote_options',[expected['quote']])) for r in actual)
    def claim_checks(fact,claim):
        value=value_text(claim.get('value'))
        checks=[]
        for i,group in enumerate(fact.get('value_groups',[])):
            checks.append(('content_%d'%i,any(fragment in value for fragment in group)))
        for i,pattern in enumerate(fact.get('forbidden_value_patterns',[])):
            checks.append(('forbidden_value_%d'%i,re.search(pattern,value) is None))
        refs=all_refs(claim.get('evidence',[]))
        if fact.get('evidence'):
            checks.append(('verbatim_evidence',refs_valid(refs)))
            for i,expected in enumerate(fact['evidence']):
                checks.append(('evidence_fact_%d'%i,ref_matches(expected,refs)))
        if state=='known':
            fragments=value_fragments(claim.get('value'))
            checks.append(('value_grounded',bool(fragments) and all(fragment and any(fragment in r.get('quote','') for r in refs) for fragment in fragments)))
        if fact.get('precision'):
            checks.append(('precision',claim.get('precision') in fact['precision']))
        scope=claim.get('scope') or {}
        for key,allowed in fact.get('scope',{}).items():
            checks.append(('scope_'+key,scope.get(key) in allowed))
        for key in ('relation_evidence','object_evidence'):
            if fact.get(key):
                actual=all_refs(scope.get(key,claim.get(key,[])))
                checks.append((key+'_valid',refs_valid(actual)))
                for i,expected in enumerate(fact[key]):
                    checks.append((key+'_%d'%i,ref_matches(expected,actual)))
        if fact.get('period_evidence_any'):
            period_refs=refs+all_refs(scope.get('relation_evidence',claim.get('relation_evidence',[])))
            checks.append(('period_source_anchor',any(ref_matches(expected,period_refs) for expected in fact['period_evidence_any'])))
        for index,expected_link in enumerate(fact.get('links',[])):
            checks.append(('link_%d'%index,any(link.get('field_id')==expected_link['field_id'] and any(fragment in value_text(link.get('value')) for fragment in expected_link['value_options']) for link in claim.get('links',[]))))
        return checks

    # Each fact must be witnessed by one coherent claim. Do not borrow a value
    # from one person's statement and the relationship from another statement.
    # Engine-validated compatible statements participate; history never does.
    claims=[{'value':got.get('value'),'evidence':got.get('evidence',[]),'scope':got.get('scope'),
             'precision':got.get('precision'),'relation_evidence':got.get('relation_evidence',[]),
             'object_evidence':got.get('object_evidence',[]),'links':got.get('links',[]),'origin':'primary'}]
    if state=='known':
        for index,item in enumerate(got.get('statements',[])):
            if isinstance(item,dict) and isinstance(item.get('text'),str):
                claims.append({**item,'value':item['text'],'origin':'statement_%d'%index})
    facts=effective_gold.get('facts') or [effective_gold]
    checks=[('state',state in gold.get('states',[gold.get('state')]))]
    if state=='missing':checks.append(('missing_has_no_claim',got.get('value') in (None,'') and not got.get('evidence')))
    witnesses=[]
    for index,fact in enumerate(facts):
        candidates=[(claim,claim_checks(variant,claim),variant_index) for variant_index,variant in enumerate(fact_variants(fact)) for claim in claims]
        passing=next(((claim,detail,variant_index) for claim,detail,variant_index in candidates if all(ok for _,ok in detail)),None)
        best=passing or max(candidates,key=lambda pair:sum(ok for _,ok in pair[1]))
        witnesses.append({'fact':index,'claim_origin':best[0]['origin'],'variant':best[2],'passed':passing is not None})
        prefix=('fact_%d_'%index) if len(facts)>1 else ''
        checks.extend((prefix+name,ok) for name,ok in best[1])
    allowed_states=gold.get('states',[gold.get('state')])
    return {'field_id':fid,'inactive_unscored':gold.get('inactive_unscored',False),
            'positive':'known' in allowed_states and 'missing' not in allowed_states,
            'substantive':bool(all_refs(gold)) and 'missing' not in allowed_states,
            'missed':state=='missing' and not set(allowed_states)<={'missing'},
            'false_accept':state not in ('missing','ambiguous') and set(allowed_states)<={'missing'},
            'passed':all(ok for _,ok in checks),'checks':[{'dimension':name,'passed':ok} for name,ok in checks],
            'claim_witnesses':witnesses,'expected':gold,'actual':got}


def score_followup(gold,result,expected_fields):
    checks=[]
    decision,target=result.get('decision'),result.get('target')
    checks.append(('decision',decision in gold['decisions']))
    if 'targets' in gold:
        checks.append(('target',target in gold['targets']))
    closed={fid for fid,g in expected_fields.items() if set(g.get('states',[g.get('state')]))<=TERMINAL_STATES}
    checks.append(('no_reask_closed',not (decision in ('ask','ask_defer') and target in closed)))
    if decision in ('ask','ask_defer'):
        question=result.get('question') or ''
        checks.append(('question_present',bool(question)))
        # One target is the executable contract; multiple questions are separately visible.
        checks.append(('single_target',isinstance(target,str)))
        if gold.get('question_patterns'):
            checks.append(('question_intent',any(re.search(pattern,question) for pattern in gold['question_patterns'])))
    return {'passed':all(ok for _,ok in checks),'checks':[{'dimension':k,'passed':v} for k,v in checks], 'actual_decision':decision,'actual_target':target,'expected':gold}


def ratio(passed,total):
    return round(passed/total,6) if total else None


def latency_summary(values):
    values=sorted(v for v in values if isinstance(v,(int,float)) and math.isfinite(v))
    return {'count':len(values),'median_seconds':round(statistics.median(values),3) if values else None,
            'p95_seconds':round(values[max(0,math.ceil(.95*len(values))-1)],3) if values else None}


def summarize(rows):
    executed=[r for r in rows if r['execution']=='evaluated']
    field_rows=[f for r in executed for f in r['fields'] if not f.get('optional_unscored') and not f.get('inactive_unscored')]
    positive=[f for f in field_rows if f['positive']]
    negative=[f for f in field_rows if not f['positive']]
    substantive=[f for f in field_rows if f['substantive']]
    by_case=defaultdict(list)
    for row in rows:by_case[row['case_id']].append(row)
    case_passes=sum(all(r.get('passed',False) for r in case_rows) for case_rows in by_case.values())
    return {'planned_checkpoints':len(rows),'evaluated_checkpoints':len(executed),
            'transport_errors':sum(r['execution']=='call_error' for r in rows),'unexecuted':sum(r['execution']=='unexecuted' for r in rows),
            'protocol_invalid':sum(r.get('decision')=='invalid' for r in executed),
            'cases':len(by_case),'whole_case_passes':case_passes,'whole_case_accuracy':ratio(case_passes,len(by_case)),
            'missed_substantive_fields':sum(f['missed'] for f in field_rows),
            'false_accepted_fields':sum(f['false_accept'] for f in field_rows),
            'repeated_or_unnecessary_followups':sum(not next(c['passed'] for c in r['followup']['checks'] if c['dimension']=='no_reask_closed') for r in executed),
            'substantive_field_checks':len(substantive),'substantive_field_passes':sum(f['passed'] for f in substantive),
            'substantive_field_accuracy':ratio(sum(f['passed'] for f in substantive),len(substantive)),
            'field_checks':len(field_rows),'field_passes':sum(f['passed'] for f in field_rows),
            'field_accuracy':ratio(sum(f['passed'] for f in field_rows),len(field_rows)),
            'positive_field_checks':len(positive),'positive_field_passes':sum(f['passed'] for f in positive),
            'positive_field_accuracy':ratio(sum(f['passed'] for f in positive),len(positive)),
            'nonpositive_field_checks':len(negative),'nonpositive_field_accuracy':ratio(sum(f['passed'] for f in negative),len(negative)),
            'followup_checks':len(executed),'followup_passes':sum(r['followup']['passed'] for r in executed),
            'followup_accuracy':ratio(sum(r['followup']['passed'] for r in executed),len(executed)),
            'all_critical_checkpoint_passes':sum(r['passed'] for r in executed),
            'all_critical_checkpoint_accuracy':ratio(sum(r['passed'] for r in executed),len(executed)),
            'planned_completion_adjusted_accuracy':ratio(sum(r['passed'] for r in executed),len(rows))}


def score_session(session):
    data=load(session/'dataset.json')
    narrators={n['id']:n for n in data['narrators']}
    rows=[]
    for case in data['cases']:
        sources={}
        for index,turn in enumerate(case['turns']):
            source=turn['source'];sources[source['id']]=source['text']
            row={'case_id':case['id'],'narrator_id':case['narrator_id'],'question_id':case['question_id'],
                 'split':narrators[case['narrator_id']]['split'],'turn':index}
            path=session/'cases'/case['id']/('turn-%03d'%index)/'result.json'
            if not path.exists():
                row.update(execution='unexecuted',passed=False)
            else:
                record=load(path)
                if record['kind']!='evaluated':
                    row.update(execution='call_error',passed=False,error={k:v for k,v in record.items() if k!='input'})
                else:
                    result=record['result'];expected=turn['expected']
                    fields=[score_field(fid,g,result.get('fields',{}).get(fid,{}),sources) for fid,g in expected['fields'].items()]
                    followup=score_followup(expected['followup'],result,expected['fields'])
                    row.update(execution='evaluated',decision=result.get('decision'),fields=fields,followup=followup,
                               passed=result.get('decision')!='invalid' and all(f['passed'] for f in fields) and followup['passed'],
                               internal_repairs=record.get('internal_repairs',0))
            rows.append(row)
    report={'schema':SCHEMA,'scored_at':now(),'model':MODEL,'source_kind':'published_transcript',
            'attempt_errors':[],
            'narrators':len(narrators),'cases':len(data['cases']),'question_coverage':len({c['question_id'] for c in data['cases']}),
            'overall':summarize(rows),'by_split':{},'by_question':{},'by_narrator':{},'by_case':{},'rows':rows}
    for response_path in sorted((session/'cases').glob('*/turn-*/response-*.json')):
        response=load(response_path)
        if response.get('kind')=='call_error':
            report['attempt_errors'].append({'path':str(response_path.relative_to(session)),**{k:v for k,v in response.items() if k not in ('input','raw_content','output')}})
    report['total_transport_error_attempts']=len(report['attempt_errors'])
    performance={'field_model_calls':0,'control_model_calls':0,'model_calls':0,'successful_responses':0,'failed_attempts':0,'repair_calls':0,'semantic_review_calls':0,'seconds_sum':0.0,'usage':{}}
    for response_path in sorted((session/'cases').glob('*/turn-*/response-*.json')):
        response=load(response_path)
        if response.get('kind')=='model_call' or response.get('http_status') is not None:performance['model_calls']+=1
        performance['successful_responses']+=response.get('kind')=='model_call'
        performance['failed_attempts']+=response.get('kind')!='model_call'
        performance['repair_calls']+='repair1' in response_path.name
        performance['semantic_review_calls']+='-review' in response_path.name
        performance['field_model_calls']+='-field-' in response_path.name
        performance['control_model_calls']+='-control' in response_path.name
        performance['seconds_sum']+=response.get('seconds',0) or 0
        for key,value in (response.get('usage') or {}).items():
            if isinstance(value,(int,float)):performance['usage'][key]=performance['usage'].get(key,0)+value
    performance['seconds_sum']=round(performance['seconds_sum'],3)
    raw_first=[load(path) for path in sorted((session/'cases').glob('*/turn-*/response-000.json')) if load(path).get('kind')=='model_call']
    performance['first_response_raw_json_legal']=sum(not response.get('parse_error') and isinstance(response.get('output'),dict) for response in raw_first)
    performance['first_response_raw_json_total']=len(raw_first)
    performance['first_response_raw_json_legal_rate']=ratio(performance['first_response_raw_json_legal'],len(raw_first))
    actual_responses=[load(path) for path in sorted((session/'cases').glob('*/turn-*/response-*.json')) if load(path).get('kind')=='model_call']
    performance['actual_response_raw_json_legal']=sum(not r.get('parse_error') and isinstance(r.get('output'),dict) for r in actual_responses)
    performance['actual_response_raw_json_total']=len(actual_responses)
    performance['latency_actual_model_http']=latency_summary([r.get('seconds') for r in actual_responses])
    performance['raw_json_parse_failures_all_calls']=sum(bool(load(path).get('parse_error')) for path in sorted((session/'cases').glob('*/turn-*/response-*.json')))
    decisions=[load(path) for path in sorted((session/'cases').glob('*/turn-*/decision-*.json'))]
    performance['code_parse_recoveries']=sum(bool((decision.get('transport_parse_audit') or {}).get('ok')) and bool((decision.get('transport_parse_audit') or {}).get('original_parse_error')) for decision in decisions)
    performance['protocol_normalization_events']=sum(len(decision.get('protocol_normalizations',[])) for decision in decisions)
    performance['explicit_relation_alias_expansions']=sum(sum(event.get('rule')=='expand_explicit_same_field_evidence_alias' for event in decision.get('protocol_normalizations',[])) for decision in decisions)
    performance['optional_rejections']=sum(len(decision.get('optional_errors',[])) for decision in decisions)
    performance['inactive_conditional_rejections']=sum(len(decision.get('inactive_conditional_errors',[])) for decision in decisions)
    performance['latency_first_model_http']=latency_summary([response.get('seconds') for response in raw_first])
    cumulative=[]
    for turn_dir in sorted((session/'cases').glob('*/turn-*')):
        seconds=[load(path).get('seconds') for path in turn_dir.glob('response-*.json')]
        seconds=[value for value in seconds if isinstance(value,(int,float))]
        if seconds:cumulative.append(sum(seconds))
    performance['latency_checkpoint_model_http_including_repairs']=latency_summary(cumulative)
    executions=[load(path) for path in sorted((session/'run-executions').glob('*.json'))]
    performance['run_wall_seconds']=round(sum(item['wall_seconds'] for item in executions),3) if executions else None
    performance['run_executions']=executions
    performance['latency_note']='HTTP model-response durations; checkpoint sum includes actual repair/retry calls. Run wall time separately includes orchestration/SSH/lock wait. Old snapshots without wall instrumentation remain unavailable, never inferred from summed parallel calls.'
    report['performance']=performance
    first_rows=[]
    for row in rows:
        first=copy.deepcopy(row)
        tdir=session/'cases'/row['case_id']/('turn-%03d'%row['turn'])
        call_path=tdir/'response-000.json';decision_path=tdir/'decision-000.json'
        step_calls=sorted(tdir.glob('response-000-*.json'))
        legacy_success=call_path.exists() and load(call_path).get('kind')=='model_call'
        # Field steps have several real calls and one deterministic assembly.
        # Never fabricate a response-000.json to make the legacy reader happy.
        step_complete=bool(step_calls) and decision_path.exists() and (tdir/'assembled-initial-000.json').exists()
        if not decision_path.exists() and step_calls:
            control_decision=tdir/'control-decision-000.json'
            if control_decision.exists() and load(control_decision).get('decision') in ('paused','skipped','deferred'):
                decision_path=control_decision
                step_complete=True
        if (legacy_success or step_complete) and decision_path.exists():
            result=load(decision_path)
            case=next(c for c in data['cases'] if c['id']==row['case_id'])
            expected=case['turns'][row['turn']]['expected']
            first_sources={t['source']['id']:t['source']['text'] for t in case['turns'][:row['turn']+1]}
            fields=[score_field(fid,g,result.get('fields',{}).get(fid,{}),first_sources) for fid,g in expected['fields'].items()]
            followup=score_followup(expected['followup'],result,expected['fields'])
            first.update(execution='evaluated',decision=result.get('decision'),fields=fields,followup=followup,passed=result.get('decision')!='invalid' and all(f['passed'] for f in fields) and followup['passed'])
        else:
            failed=call_path.exists() or any(load(p).get('kind')=='call_error' for p in step_calls)
            first.update(execution='call_error' if failed else 'unexecuted',passed=False)
        first_rows.append(first)
    first_summary={'overall':summarize(first_rows),'by_split':{split:summarize([r for r in first_rows if r['split']==split]) for split in sorted({r['split'] for r in rows})},
                   'scope':'First attempt code decision before final protocol repair, after any fixed semantic stages. Field-step assembly is not a provider response. Initial network failures remain failures even when later retries succeed.'}
    report['first_code_decision']=first_summary
    report['first_response']={**first_summary,'compatibility_note':'Legacy key; use first_code_decision. Not a claim that a multi-call workflow is one model response.'}
    report['executed_question_count']=len({r['question_id'] for r in rows if r['execution']=='evaluated'})
    report['internal_protocol_repairs']=sum(r.get('internal_repairs',0) for r in rows)
    for key,groupby in [('by_split','split'),('by_question','question_id'),('by_narrator','narrator_id'),('by_case','case_id')]:
        for value in sorted({r[groupby] for r in rows}):
            report[key][value]=summarize([r for r in rows if r[groupby]==value])
    macro_keys=('substantive_field_accuracy','positive_field_accuracy','field_accuracy','followup_accuracy','all_critical_checkpoint_accuracy')
    report['question_macro']={key:ratio(sum(v[key] for v in report['by_question'].values() if v[key] is not None),sum(v[key] is not None for v in report['by_question'].values())) for key in macro_keys}
    report['narrator_macro']={key:ratio(sum(v[key] for v in report['by_narrator'].values() if v[key] is not None),sum(v[key] is not None for v in report['by_narrator'].values())) for key in macro_keys}
    report['positive_question_coverage']=sum(v['positive_field_checks']>0 for v in report['by_question'].values())
    # Threshold is strict >95%; it is never inferred from missing-only or unexecuted cases.
    report['executed_narrators']=len({r['narrator_id'] for r in rows if r['execution']=='evaluated'})
    report['executed_narrators_by_split']={split:len({r['narrator_id'] for r in rows if r['execution']=='evaluated' and r['split']==split}) for split in sorted({r['split'] for r in rows})}
    holdout=report['by_split'].get('holdout',{})
    report['acceptance']={'threshold':'>0.95','met': bool(report['question_coverage']==62 and report['executed_narrators']>=50 and report['executed_narrators_by_split'].get('holdout',0)>=10 and
        report['overall']['unexecuted']==0 and report['overall']['transport_errors']==0 and
        report['positive_question_coverage']==62 and holdout.get('substantive_field_accuracy') is not None and holdout.get('substantive_field_accuracy',0)>.95 and
        holdout.get('all_critical_checkpoint_accuracy',0)>.95 and report['question_macro']['substantive_field_accuracy'] is not None and
        report['question_macro']['substantive_field_accuracy']>.95 and report['question_macro']['all_critical_checkpoint_accuracy']>.95),
        'limitations':'Only this frozen corpus. Held-out people must not have been used for tuning this run; reuse makes them known regression data.'}
    save(session/'scores.json',report)
    def pct(value): return '—' if value is None else '%.2f%%'%(value*100)
    lines=['# 全题真实访谈冻结评测','',f'模型：{MODEL}；来源：published_transcript；逐题独立，同题保留多轮。',
           f'已执行人物 {report["executed_narrators"]}/{len(narrators)}；题例 {len(data["cases"])}；实际题覆盖 {report["executed_question_count"]}/62；正信息输入覆盖 {report["positive_question_coverage"]}/62。','',
           f'真实模型调用 {performance["model_calls"]}；协议修复调用 {performance["repair_calls"]}；响应累计 {performance["seconds_sum"]} 秒；token 用量 {performance["usage"]}。',
           f'首轮代码判定（固定字段步骤完成后、协议修复前）：有原话关键要素通过率 {pct(report["first_code_decision"]["overall"]["substantive_field_accuracy"])}；全关键点通过率 {pct(report["first_code_decision"]["overall"]["all_critical_checkpoint_accuracy"])}。',
           f'实际成功响应原始JSON合法 {performance["actual_response_raw_json_legal"]}/{performance["actual_response_raw_json_total"]}；全部调用原始解析失败 {performance["raw_json_parse_failures_all_calls"]}；代码无损解析恢复 {performance["code_parse_recoveries"]}；字段协议归一事件 {performance["protocol_normalization_events"]}；实际模型修复调用 {performance["repair_calls"]}。',
           '每个字段必须同时通过状态、内容、逐字证据和预先声明的精度／关系检查。缺失项单列，不能稀释正要素失败。无响应及未执行不计通过。','',
           '| 分组 | 执行/计划 | 有原话关键要素通过率 | 全字段通过率 | 追问通过率 | 全关键点通过率 |',
           '| --- | --- | --- | --- | --- | --- |']
    for label,summary in [('全部',report['overall']),*report['by_split'].items()]:
        lines.append('| %s | %s/%s | %s (%s/%s) | %s | %s | %s |'%(label,summary['evaluated_checkpoints'],summary['planned_checkpoints'],pct(summary['substantive_field_accuracy']),summary['substantive_field_passes'],summary['substantive_field_checks'],pct(summary['field_accuracy']),pct(summary['followup_accuracy']),pct(summary['all_critical_checkpoint_accuracy'])))
    lines+=['',f'题目等权平均：有原话关键要素 {pct(report["question_macro"]["substantive_field_accuracy"])}；全关键点 {pct(report["question_macro"]["all_critical_checkpoint_accuracy"])}。',
            '',f'漏提 {report["overall"]["missed_substantive_fields"]}；误收 {report["overall"]["false_accepted_fields"]}；已关闭目标重复追问 {report["overall"]["repeated_or_unnecessary_followups"]}；整例通过率 {pct(report["overall"]["whole_case_accuracy"])}。',
            f'人物等权平均：有原话关键要素 {pct(report["narrator_macro"]["substantive_field_accuracy"])}；包含正要素且实际执行的题覆盖 {report["positive_question_coverage"]}/62。',
            '','验收：'+('达到冻结语料门槛' if report['acceptance']['met'] else '尚未达到 >95% 门槛')+'。',
            '', '| 题号 | 执行/计划 | 有原话关键要素通过率 | 全字段通过率 | 追问通过率 | 全关键点通过率 |','| --- | --- | --- | --- | --- | --- |']
    for qid,summary in report['by_question'].items():
        lines.append('| %s | %s/%s | %s (%s/%s) | %s | %s | %s |'%(qid,summary['evaluated_checkpoints'],summary['planned_checkpoints'],pct(summary['substantive_field_accuracy']),summary['substantive_field_passes'],summary['substantive_field_checks'],pct(summary['field_accuracy']),pct(summary['followup_accuracy']),pct(summary['all_critical_checkpoint_accuracy'])))
    failures=[r for r in rows if r['execution']=='evaluated' and not r['passed']]
    lines+=['','## 失败明细','']
    for row in failures:
        failed_fields=[f['field_id']+':'+','.join(c['dimension'] for c in f['checks'] if not c['passed']) for f in row['fields'] if not f['passed']]
        if not row['followup']['passed']:failed_fields.append('followup:'+','.join(c['dimension'] for c in row['followup']['checks'] if not c['passed']))
        lines.append('- '+row['case_id']+' / turn '+str(row['turn'])+' / '+'；'.join(failed_fields))
    lines+=['','详细金标准、原始模型输出和逐项结果见 dataset.json、cases/、scores.json。保留集一旦用于调参，后续只可称已知回归；泛化结论需要新的独立人物。']
    (session/'report.md').write_text('\n'.join(lines)+'\n')
    return report


def main():
    global ROOT, MODEL
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,help='project root when running the frozen runner snapshot')
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('prepare');p.add_argument('--runtime',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--require-full',action='store_true')
    p=subs.add_parser('run');p.add_argument('--session',type=Path,required=True);p.add_argument('--split',choices=['all','development','holdout','new_holdout'],default='all');p.add_argument('--concurrency',type=int,choices=[1,2,3,4],default=4);p.add_argument('--max-cases',type=int);p.add_argument('--retry-errors',action='store_true',help='explicitly retry network errors, retaining all earlier attempts')
    p.add_argument('--token-budget',type=int,help='Observed-token soft limit; at most one already-dispatched batch can exceed it')
    p.add_argument('--call-budget',type=int,help='Hard cap on scheduled model requests, checked before every dispatch')
    p.add_argument('--critical-failure-limit',type=int,help='Development-only early stop after this many failed evaluated checkpoints')
    p.add_argument('--stop-when-impossible',action='store_true',help='Stop if remaining checkpoints cannot yield strict >95%%')
    p=subs.add_parser('score');p.add_argument('--session',type=Path,required=True)
    p=subs.add_parser('validate');p.add_argument('--runtime',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--require-full',action='store_true')
    args=parser.parse_args()
    if args.command == 'run' and any(getattr(args, key) is not None and getattr(args, key) <= 0
                                   for key in ('token_budget', 'call_budget', 'critical_failure_limit')):
        parser.error('budgets must be positive')
    if args.root:ROOT=args.root.resolve()
    if args.command in ('prepare','validate'):
        config=args.runtime/'provider-settings.json'
        MODEL=load(config).get('model','deepseek-flash') if config.exists() else 'deepseek-flash'
    elif args.command in ('run','score'):
        MODEL=load(args.session/'freeze.json')['model']
    if MODEL not in ALLOWED_DS_MODELS | ALLOWED_OPENAI_MODELS:
        raise ValueError('only explicitly frozen DS/OpenAI models are allowed')
    if args.command=='prepare':prepare(args)
    elif args.command=='run':return run(args)
    elif args.command=='score':print(json.dumps(score_session(args.session.resolve())['overall'],ensure_ascii=False))
    elif args.command=='validate':print(json.dumps(validate_dataset(load(args.dataset),contracts(args.runtime.resolve()),args.require_full),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (OSError,ValueError,RuntimeError) as exc:
        print('evaluation stopped: '+str(exc),file=sys.stderr)
        sys.exit(2)
