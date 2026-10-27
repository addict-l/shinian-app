#!/usr/bin/env python3
"""File queues served by Claude Haiku sub-agents (simulated elder = persona, rubric scorer = scorer).

Worker side (see WORKER.md):
  python3 queue_worker.py next  <persona|scorer|all> [wait_seconds]   # claim one request and print it, or IDLE / DONE
  python3 queue_worker.py answer <persona|scorer> <id> [--no-next] [--wait S] < answer.json
        # validate and store the answer; on success it immediately claims and prints the next request
  python3 queue_worker.py status                                     # counts per queue (for the operator)

Runner side: HaikuQueue(name).submit(...) writes <dir>/<id>.request.json (self-contained: full instructions +
input + output spec) unless the content-addressed Haiku cache already holds the answer; poll(id) returns the
response once a worker has answered. Claims are taken under an flock on <dir>/.lock, so two workers never get
the same request; a claim older than its TTL (worker died) can be claimed again. The first valid answer wins.
Haiku answers are cached by request content in HAIKU_CACHE/<queue>/ (separate from the DeepSeek cache), so
pipelines that send the same request (e.g. the first answer of a question) share the same elder answer.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

WORK = Path(os.environ.get('SHINIAN_EVAL_HOME', Path(__file__).resolve().parents[3] / '.runtime/interview-eval'))
RUNS = Path(os.environ.get('SHINIAN_EVAL_RUNS', WORK / 'runs'))
HAIKU_CACHE = Path(os.environ.get('SHINIAN_HAIKU_CACHE', WORK / 'cache-haiku'))
QUEUES = ('persona', 'scorer')
CLAIM_TTL = {'persona': 300, 'scorer': 600}
MODEL_TAG = 'claude-haiku-subagent'
SCRIPT = str(Path(__file__).resolve())
DIMS = ('natural', 'grounded', 'timing', 'single', 'tone')
VIOLATIONS = ('multi_question', 'presupposition', 'repeat_ask', 'should_have_stopped')


def qdir(name):
    d = RUNS / f'{name}-queue'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'done').mkdir(exist_ok=True)
    return d


def _write_atomic(path, obj):
    tmp = path.with_name(path.name + f'.tmp{os.getpid()}')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@contextmanager
def locked(name):
    fd = os.open(qdir(name) / '.lock', os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def request_key(queue, instructions, input_text, output_spec):
    body = {'queue': queue, 'model': MODEL_TAG, 'instructions': instructions, 'input': input_text, 'output': output_spec}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


# --------------------------------------------------------------------------- validation
def validate(req, out):
    """Return a list of problems (empty = valid)."""
    if not isinstance(out, dict):
        return ['答案必须是一个 JSON 对象（花括号）']
    spec = req.get('validate') or {}
    errs = []
    if spec.get('type') == 'persona':
        r = out.get('reply')
        if not isinstance(r, str) or not r.strip():
            errs.append('缺少非空字符串字段 "reply"')
        elif len(r) > spec.get('max_chars', 400):
            errs.append(f'"reply" 太长（{len(r)} 字，上限 {spec.get("max_chars", 400)}）')
        extra = set(out) - {'reply'}
        if extra:
            errs.append('只允许字段 "reply"，多了：' + '、'.join(sorted(extra)))
    elif spec.get('type') == 'scorer':
        turns = out.get('turns')
        if not isinstance(turns, dict):
            errs.append('缺少对象字段 "turns"')
            turns = {}
        for label in spec.get('labels') or []:
            t = turns.get(label)
            if not isinstance(t, dict):
                errs.append(f'"turns" 里缺少 "{label}"')
                continue
            for d in DIMS:
                v = t.get(d)
                if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
                    errs.append(f'{label}.{d} 必须是 1 到 5 的整数')
            vio = t.get('violations')
            if not isinstance(vio, list) or any(v not in VIOLATIONS for v in vio):
                errs.append(f'{label}.violations 必须是列表，元素只能是 ' + '/'.join(VIOLATIONS))
        unknown = set(turns) - set(spec.get('labels') or [])
        if unknown:
            errs.append('"turns" 里多了不需要打分的发言：' + '、'.join(sorted(unknown)))
        for key, need in (('fabrication', ('turn', 'claim')), ('record_errors', ('item', 'why'))):
            v = out.get(key)
            if not isinstance(v, list) or any(not isinstance(x, dict) or any(k not in x for k in need) for x in v):
                errs.append(f'"{key}" 必须是列表，每项是含 ' + '、'.join(f'"{k}"' for k in need) + ' 的对象（没有就给 []）')
        if not isinstance(out.get('note', ''), str):
            errs.append('"note" 必须是字符串')
    elif spec.get('type') == 'material':  # v5d memoir-material rubric (material.py)
        items = out.get('items')
        kinds = spec.get('kinds') or []
        if not isinstance(items, list):
            errs.append('缺少列表字段 "items"（没有素材就给 []）')
            items = []
        for k, it in enumerate(items):
            if not isinstance(it, dict) or not isinstance(it.get('text'), str) or not it.get('text').strip():
                errs.append(f'items[{k}] 必须是含非空 "text" 的对象')
            elif it.get('kind') not in kinds:
                errs.append(f'items[{k}].kind 只能是 ' + '/'.join(kinds))
        v = out.get('usable')
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            errs.append('"usable" 必须是 1 到 5 的整数')
        extra = set(out) - {'items', 'usable', 'note'}
        if extra:
            errs.append('只允许字段 items、usable、note，多了：' + '、'.join(sorted(extra)))
        if not isinstance(out.get('note', ''), str):
            errs.append('"note" 必须是字符串')
    return errs


# --------------------------------------------------------------------------- worker commands
def _pending(name):
    d = qdir(name)
    out = []
    for req in d.glob('*.request.json'):
        rid = req.name[:-len('.request.json')]
        if (d / f'{rid}.response.json').exists():
            continue
        out.append((req.stat().st_mtime, rid))
    return [rid for _, rid in sorted(out)]


def _try_claim(name):
    d = qdir(name)
    with locked(name):
        for rid in _pending(name):
            claim = d / f'{rid}.claim'
            if claim.exists():
                try:
                    info = _read(claim)
                except (ValueError, OSError):
                    info = {'claimed_at': 0}
                if time.time() - info.get('claimed_at', 0) < CLAIM_TTL[name]:
                    continue
                attempt = info.get('attempt', 1) + 1
            else:
                attempt = 1
            _write_atomic(claim, {'claimed_at': time.time(), 'attempt': attempt, 'pid': os.getpid()})
            return rid
    return None


def _stopped(name):
    return (qdir(name) / 'STOP').exists()


def render(name, rid):
    req = _read(qdir(name) / f'{rid}.request.json')
    lines = [f'CLAIMED {name} {rid}',
             '',
             '===== 指令（你这次要扮演的角色和规则，只照它做）=====',
             req['instructions'].rstrip(),
             '',
             '===== 输入 =====',
             req['input'].rstrip(),
             '',
             '===== 输出要求 =====',
             req.get('output_note') or '只输出一个 JSON 对象。',
             '',
             '===== 提交方法（把 JSON 放在两行 JSON 之间，原样提交）=====',
             f"python3 {SCRIPT} answer {name} {rid} <<'JSON'",
             '{ ...你的 JSON... }',
             'JSON']
    return '\n'.join(lines)


def cmd_next(which, wait):
    names = QUEUES if which == 'all' else (which,)
    deadline = time.time() + max(0, wait)
    while True:
        for name in names:
            rid = _try_claim(name)
            if rid:
                left = len(_pending(name)) - 1
                print(render(name, rid))
                print(f'\n（{name} 队列里另有 {max(0, left)} 个请求在等或正被处理）')
                return 0
        if all(_stopped(n) for n in names) and not any(_pending(n) for n in names):
            print('DONE（不再需要 worker：请结束循环，回复“worker 结束”）')
            return 0
        if time.time() >= deadline:
            print('IDLE（暂时没有请求：请再次运行同一条 next 命令继续等待）')
            return 0
        time.sleep(1.0)


def cmd_answer(name, rid, raw, auto_next=True, wait=90):
    d = qdir(name)
    req_path = d / f'{rid}.request.json'
    if not req_path.exists():
        if (d / 'done' / f'{rid}.response.json').exists() or (d / f'{rid}.response.json').exists():
            print(f'IGNORED：{rid} 已有答案（可能别的 worker 先交了），不用再交。')
        else:
            print(f'ERROR：找不到请求 {rid}，请检查队列名和编号。')
            return 1
    else:
        text = raw.strip()
        if text.startswith('```'):
            text = text.strip('`')
            text = text[text.find('{'):] if '{' in text else text
        try:
            out = json.loads(text)
        except ValueError as exc:
            print(f'ERROR：不是合法 JSON（{exc}）。请只提交一个 JSON 对象，修正后重交同一编号。')
            return 1
        req = _read(req_path)
        errs = validate(req, out)
        if errs:
            print('ERROR：答案没通过检查：' + '；'.join(errs) + '。修正后重交同一编号。')
            return 1
        resp = d / f'{rid}.response.json'
        with locked(name):
            if resp.exists():
                print(f'IGNORED：{rid} 已有答案（别的 worker 先交了）。')
            else:
                # a non-Haiku worker (e.g. Codex / GPT, PERSONA_WORKER.md) names itself; the cache key stays the same
                _write_atomic(resp, {'id': rid, 'output': out, 'answered_at': time.time(),
                                     'model': os.environ.get('SHINIAN_WORKER_MODEL', '').strip() or MODEL_TAG})
                print(f'OK：{name} {rid} 已提交。')
    if auto_next:
        print('\n—— 自动领取下一个 ——\n')
        return cmd_next('all', wait)
    return 0


def cmd_status():
    for name in QUEUES:
        d = qdir(name)
        pend = _pending(name)
        claimed = [r for r in pend if (d / f'{r}.claim').exists()]
        answered = len(list(d.glob('*.response.json')))
        print(json.dumps({'queue': name, 'pending': len(pend), 'claimed': len(claimed), 'answered_not_collected': answered,
                          'done': len(list((d / 'done').glob('*.response.json'))), 'stop': _stopped(name)}, ensure_ascii=False))


# --------------------------------------------------------------------------- runner side
class HaikuQueue:
    """Runner-side client: content-addressed cache + request files + polling."""

    def __init__(self, name):
        assert name in QUEUES
        self.name = name
        self.dir = qdir(name)
        self.cache = HAIKU_CACHE / name
        self.cache.mkdir(parents=True, exist_ok=True)
        self.sent = 0
        self.cached = 0
        self.t_submit = {}

    def submit(self, instructions, input_text, output_note, validate_spec, meta=None):
        """Returns (rid, cached_response_or_None)."""
        key = request_key(self.name, instructions, input_text, {'note': output_note, 'validate': validate_spec})
        rid = self.name[0] + '-' + key[:16]
        hit = self.cache / f'{key}.json'
        if hit.exists():
            self.cached += 1
            return rid, {**_read(hit), 'cached': True}
        path = self.dir / f'{rid}.request.json'
        if not path.exists() and not (self.dir / f'{rid}.response.json').exists():
            _write_atomic(path, {'id': rid, 'key': key, 'queue': self.name, 'created': time.time(), 'instructions': instructions,
                                 'input': input_text, 'output_note': output_note, 'validate': validate_spec, 'meta': meta or {}})
        self.t_submit[rid] = (time.time(), key)
        return rid, None

    def poll(self, rid):
        resp = self.dir / f'{rid}.response.json'
        if not resp.exists():
            # the same request may have been submitted twice and already collected by the first poll
            key = self.t_submit.get(rid, (None, None))[1]
            if key and (self.cache / f'{key}.json').exists():
                return {**_read(self.cache / f'{key}.json'), 'cached': True}
            return None
        try:
            row = _read(resp)
        except ValueError:
            return None
        t0, key = self.t_submit.get(rid, (None, None))
        req_path = self.dir / f'{rid}.request.json'
        if key is None and req_path.exists():
            key = _read(req_path)['key']
        out = {'id': rid, 'ok': True, 'output': row['output'], 'content': json.dumps(row['output'], ensure_ascii=False),
               'model_requested': row.get('model') or MODEL_TAG, 'answered_at': row.get('answered_at'),
               'seconds': round(row['answered_at'] - t0, 1) if t0 and row.get('answered_at') else None, 'usage': {}}
        if key:
            _write_atomic(self.cache / f'{key}.json', {k: v for k, v in out.items() if k != 'seconds'})
        with locked(self.name):
            for suffix in ('.request.json', '.claim', '.response.json'):
                p = self.dir / f'{rid}{suffix}'
                if p.exists():
                    os.replace(p, self.dir / 'done' / p.name)
        self.sent += 1
        return out

    def waiting(self):
        return len(_pending(self.name))


def set_stop(on=True, names=QUEUES):
    for n in names:
        p = qdir(n) / 'STOP'
        if on:
            p.write_text(str(time.time()), encoding='utf-8')
        elif p.exists():
            p.unlink()


def main(argv):
    if len(argv) < 2 or argv[1] not in ('next', 'answer', 'status', 'stop', 'start'):
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == 'next':
        which = argv[2] if len(argv) > 2 else 'all'
        if which not in QUEUES + ('all',):
            print('ERROR：队列名只能是 persona / scorer / all')
            return 2
        return cmd_next(which, float(argv[3]) if len(argv) > 3 else 90)
    if cmd == 'answer':
        if len(argv) < 4 or argv[2] not in QUEUES:
            print('用法：answer <persona|scorer> <id> < answer.json')
            return 2
        wait = 90
        if '--wait' in argv:
            wait = float(argv[argv.index('--wait') + 1])
        return cmd_answer(argv[2], argv[3], sys.stdin.read(), auto_next='--no-next' not in argv, wait=wait)
    if cmd == 'status':
        cmd_status()
        return 0
    if cmd in ('stop', 'start'):  # operator only
        set_stop(cmd == 'stop')
        cmd_status()
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
