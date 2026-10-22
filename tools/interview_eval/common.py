"""Shared plumbing for relay-based interview evaluation.

- Engine: persistent bridge to a runtime's engine.js (validation + follow-up decision).
- Relay: ships model calls to the DeepSeek relay running on the user's computer
  (D:\\shinian_evl) via staged job files, with a content-addressed response cache.
- Dataset sampling restricted to the user's 55-person test set (development people
  that have frozen gold), scoring through the frozen runner's scoring functions.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import random
import secrets
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / 'docs/prototypes/full-interview-evaluation/single-question-v2-gold.json'
# Local working data lives under .runtime/ (git-ignored); every location can be overridden by environment variable.
WORK = Path(os.environ.get('SHINIAN_EVAL_HOME', ROOT / '.runtime/interview-eval'))
TESTSET_DIR = Path(os.environ.get('SHINIAN_TESTSET_DIR', WORK / 'testset'))  # unpacked 55-person test set (not in Git)
TESTSET_CSV = Path(os.environ.get('SHINIAN_TESTSET_CSV', TESTSET_DIR / '55人目录.csv'))
CACHE = Path(os.environ.get('SHINIAN_EVAL_CACHE', WORK / 'cache'))
RUNS = Path(os.environ.get('SHINIAN_EVAL_RUNS', WORK / 'runs'))
OUT_JOBS = Path(os.environ.get('SHINIAN_RELAY_OUT', WORK / 'relay/jobs'))
IN_ROOT = Path(os.environ.get('SHINIAN_RELAY_IN', WORK / 'relay/in'))
DEVICE_JOBS = os.environ.get('SHINIAN_DEVICE_JOBS', 'D:\\shinian_evl\\jobs')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def frozen_runner():
    spec = importlib.util.spec_from_file_location('frozen_runner', ROOT / 'tools/run_full_interview_eval.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = frozen_runner()


# --------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, runtime: Path):
        self.runtime = Path(runtime).resolve()
        self.proc = subprocess.Popen(['node', str(Path(__file__).with_name('engine_bridge.js')), str(self.runtime)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        self.lock = threading.Lock()
        self.n = 0
        self.defs = self.op('contracts')

    def op(self, name, **args):
        with self.lock:
            self.n += 1
            self.proc.stdin.write(json.dumps({'id': self.n, 'op': name, 'args': args}, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
            reply = json.loads(self.proc.stdout.readline())
        if 'error' in reply:
            raise RuntimeError('engine %s failed: %s' % (name, reply['error']))
        return reply['result']

    def payload_for(self, case, turn_index, previous, ask_counts):
        """Same construction as the frozen runner's payload_for (independent question)."""
        import copy
        defs = self.defs
        qid = case['question_id']
        turn = case['turns'][turn_index]
        sources = []
        for t in case['turns'][:turn_index + 1]:
            source = copy.deepcopy(t['source'])
            source.update(question_id=qid, speaker='narrator')
            source.setdefault('question', None)
            if t.get('focus'):
                source['target_field_id'] = t['focus']['field_id']
            if defs.get('model_source_fields'):
                source = {k: source[k] for k in defs['model_source_fields'] if k in source}
            sources.append(source)
        payload = {'question_id': qid, 'main_question': defs['questions'][qid], 'question_context_mode': 'independent',
                   'current_question': sources[-1]['question'] or '', 'source_kind': 'published_transcript',
                   'historical_question_verified': bool(sources[-1]['question']), 'focus': turn.get('focus'),
                   'field_contract': {k: v for k, v in defs['fields'].items() if v['question_id'] == qid},
                   'question_contract': defs.get('question_contracts', {}).get(qid, {}),
                   'sources': sources, 'previous_fields': copy.deepcopy(previous), 'ask_counts': copy.deepcopy(ask_counts)}
        if defs.get('model_field_contract_keys'):
            payload['field_contract'] = {fid: {k: v for k, v in f.items() if k in defs['model_field_contract_keys']}
                                         for fid, f in payload['field_contract'].items()}
        if defs.get('evidence_unit_protocol'):
            payload['evidence_units'] = self.op('evidence_units', question_id=qid, sources=sources)
        return payload

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


# --------------------------------------------------------------------------- relay
class RelayError(RuntimeError):
    pass


class Relay:
    """Batches calls into one job file; waits for the staged response; caches by content."""

    def __init__(self, run_dir: Path, offline=False, wait_seconds=7200, dry=None, fresh=False):
        self.run_dir = Path(run_dir)
        self.offline = offline
        self.fresh = fresh  # ignore cached answers: every call goes to DeepSeek again
        self.dry = dry  # callable(call) -> content string, for plumbing tests only (never cached)
        self.wait_seconds = wait_seconds
        CACHE.mkdir(parents=True, exist_ok=True)
        OUT_JOBS.mkdir(parents=True, exist_ok=True)
        self.calls_sent = 0
        self.calls_cached = 0
        self.usage = {}  # summed DeepSeek usage of calls actually sent in this run (cached calls cost nothing)

    @staticmethod
    def key(call):
        body = {k: call.get(k) for k in ('system', 'user', 'params', 'sample')}
        return sha(json.dumps(body, ensure_ascii=False, sort_keys=True))

    def _find_staged(self, name):
        for path in IN_ROOT.rglob(name):
            return path
        return None

    def run_batch(self, job_name, calls):
        """calls: [{'id','system','user'(str),'params'{...},'sample'?}] -> {id: response}"""
        out, todo = {}, []
        if self.dry:
            for call in calls:
                content = self.dry(call)
                try:
                    parsed, err = json.loads(content), None
                except ValueError:
                    parsed, err = None, 'JSONDecodeError'
                out[call['id']] = {'id': call['id'], 'ok': True, 'content': content, 'output': parsed, 'parse_error': err, 'dry': True}
            return out
        for call in calls:
            path = CACHE / (self.key(call) + '.json')
            if path.exists() and not self.fresh:
                out[call['id']] = {**load(path), 'cached': True}
                self.calls_cached += 1
            else:
                todo.append(call)
        if not todo:
            return out
        if not self.offline and len(todo) > 4:
            # warm DeepSeek's prefix cache with one call per new system prompt, then send the rest
            warm_file = CACHE / 'warmed-prompts.json'
            warmed = load(warm_file) if warm_file.exists() else {}
            first = {}
            for call in todo:
                h = sha(call['system'])[:16]
                if time.time() - warmed.get(h, 0) > 1800 and h not in first:
                    first[h] = call
            if first:
                out.update(self.run_batch(job_name + '-w', list(first.values())))
                warmed.update({h: time.time() for h in first})
                save(warm_file, warmed)
                todo = [c for c in todo if c['id'] not in out]
                if not todo:
                    return out
        if self.offline:
            for call in todo:
                out[call['id']] = {'id': call['id'], 'ok': False, 'error': 'offline_cache_miss'}
            return out
        prompts, index = {}, {}
        for call in todo:
            h = sha(call['system'])[:16]
            prompts.setdefault(h, call['system'])
        job = {'job': job_name, 'concurrency': 24,
               'defaults': {}, 'prompts': prompts,
               'calls': [{'id': c['id'], 'system_ref': sha(c['system'])[:16], 'user': c['user'], 'params': c['params']}
                         for c in todo]}
        request_path = OUT_JOBS / (job_name + '.request.json')
        if request_path.exists():
            raise RelayError('job name reused: ' + job_name)
        save(request_path, job)
        save(self.run_dir / 'relay-awaiting.json', {'job': job_name, 'calls': len(todo), 'since': time.time(),
                                                    'device_path': DEVICE_JOBS + '\\' + job_name + '.request.json'})
        print(json.dumps({'relay_job_written': job_name, 'calls': len(todo)}), flush=True)
        deadline = time.time() + self.wait_seconds
        response_path = done_path = None
        while time.time() < deadline:
            done_path = self._find_staged(job_name + '.done.json')
            response_path = self._find_staged(job_name + '.response.jsonl')
            if done_path and response_path:
                break
            time.sleep(3)
        else:
            raise RelayError('timed out waiting for relay job ' + job_name)
        time.sleep(1)
        rows = {}
        for line in response_path.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('id') is not None:
                rows[row['id']] = row
        for call in todo:
            row = rows.get(call['id']) or {'id': call['id'], 'ok': False, 'error': 'missing_from_relay_response'}
            if row.get('ok'):
                content = row.get('content') or ''
                try:
                    row['output'], row['parse_error'] = json.loads(content), None
                except ValueError:
                    row['output'], row['parse_error'] = None, 'JSONDecodeError'
                if self.fresh:  # keep fresh answers separate; never overwrite the shared cache
                    save(self.run_dir / 'fresh-responses' / (self.key(call) + '.json'), row)
                else:
                    save(CACHE / (self.key(call) + '.json'), row)
            for k, v in (row.get('usage') or {}).items():
                if isinstance(v, (int, float)):
                    self.usage[k] = self.usage.get(k, 0) + v
            out[call['id']] = row
            self.calls_sent += 1
        (self.run_dir / 'relay-awaiting.json').unlink(missing_ok=True)
        return out


# --------------------------------------------------------------------------- dataset
def testset_dev_ids():
    with TESTSET_CSV.open(encoding='utf-8-sig') as f:
        return {r['人物ID'] for r in csv.DictReader(f) if r['数据划分'] == 'development'}


def sample_dataset(people=None, seed=None, exclude=()):
    gold = load(GOLD)
    allowed = testset_dev_ids()
    ids = sorted(n['id'] for n in gold['narrators'] if n['id'] in allowed and n['id'] not in set(exclude))
    seed = secrets.randbits(63) if seed is None else seed
    rng = random.Random(seed)
    count = people if people is not None else rng.randint(5, 10)
    if not 5 <= count <= 10:
        raise ValueError('select 5-10 people')
    chosen = set(rng.sample(ids, count))
    data = {k: v for k, v in gold.items() if k not in ('narrators', 'cases')}
    data['narrators'] = [n for n in gold['narrators'] if n['id'] in chosen]
    data['cases'] = [c for c in gold['cases'] if c['narrator_id'] in chosen]
    data['selection'] = {'seed': seed, 'people': count, 'pool': len(ids), 'narrator_ids': sorted(chosen),
                         'names': [n['name'] for n in data['narrators']],
                         'cases': len(data['cases']), 'checkpoints': sum(len(c['turns']) for c in data['cases']),
                         'algorithm': 'sorted test-set development IDs with frozen gold; Random(seed): count=randint(5,10) unless fixed, then sample'}
    return data


# --------------------------------------------------------------------------- scoring
def score_rows(data, results):
    """results: {(case_id, turn): record}; record = {'kind':'evaluated','result':{...}} or call_error."""
    narrators = {n['id']: n for n in data['narrators']}
    rows = []
    for case in data['cases']:
        sources = {}
        for index, turn in enumerate(case['turns']):
            sources[turn['source']['id']] = turn['source']['text']
            row = {'case_id': case['id'], 'narrator_id': case['narrator_id'], 'question_id': case['question_id'],
                   'split': narrators[case['narrator_id']]['split'], 'turn': index}
            record = results.get((case['id'], index))
            if record is None:
                row.update(execution='unexecuted', passed=False)
            elif record.get('kind') != 'evaluated':
                row.update(execution='call_error', passed=False, error=record)
            else:
                result, expected = record['result'], turn['expected']
                fields = [RUNNER.score_field(fid, g, result.get('fields', {}).get(fid, {}), sources)
                          for fid, g in expected['fields'].items()]
                followup = RUNNER.score_followup(expected['followup'], result, expected['fields'])
                row.update(execution='evaluated', decision=result.get('decision'), fields=fields, followup=followup,
                           passed=result.get('decision') != 'invalid' and all(f['passed'] for f in fields) and followup['passed'])
            rows.append(row)
    return rows, RUNNER.summarize(rows)


def failure_lines(rows):
    lines = []
    for row in rows:
        if row['passed']:
            continue
        if row['execution'] != 'evaluated':
            lines.append(f"- {row['case_id']} / t{row['turn']}: {row['execution']}")
            continue
        bad = [f['field_id'] + ':' + ','.join(c['dimension'] for c in f['checks'] if not c['passed'])
               for f in row['fields'] if not f['passed']]
        if not row['followup']['passed']:
            fu = row['followup']
            bad.append('followup(%s/%s vs %s/%s):' % (fu['actual_decision'], fu['actual_target'],
                                                     fu['expected'].get('decisions'), fu['expected'].get('targets'))
                       + ','.join(c['dimension'] for c in fu['checks'] if not c['passed']))
        lines.append(f"- {row['case_id']} / t{row['turn']}: " + '; '.join(bad))
    return lines
