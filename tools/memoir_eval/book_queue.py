#!/usr/bin/env python3
"""Haiku file queue for the memoir rubric (queue name: memoir), built on interview_eval's queue_worker.

Worker side (see tools/memoir_eval/WORKER.md):
  python3 tools/memoir_eval/book_queue.py next memoir 90
  python3 tools/memoir_eval/book_queue.py answer memoir <id> <<'JSON' ... JSON
  python3 tools/memoir_eval/book_queue.py status | stop | start      # operator

Same claim/answer/cache mechanics as the persona/scorer queues; only the queue name, claim TTL and
answer validation differ. Queue files live in RUNS/memoir-queue, cached answers in HAIKU_CACHE/memoir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mb  # sets SHINIAN_EVAL_HOME for a worktree before queue_worker reads it

sys.path.insert(0, str(mb.ROOT / 'tools/interview_eval/simulate'))
import queue_worker as qw  # noqa: E402

DIMS = ('faithful', 'lyrical', 'coherent', 'voice', 'structure')
qw.QUEUES = ('memoir',)
qw.CLAIM_TTL = {**qw.CLAIM_TTL, 'memoir': 900}
qw.SCRIPT = str(Path(__file__).resolve())
_base_validate = qw.validate


def validate(req, out):
    spec = req.get('validate') or {}
    if spec.get('type') != 'memoir':
        return _base_validate(req, out)
    if not isinstance(out, dict):
        return ['答案必须是一个 JSON 对象（花括号）']
    errs = []
    for d in DIMS:
        v = out.get(d)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            errs.append(f'"{d}" 必须是 1 到 5 的整数')
    fab = out.get('fabrication')
    if not isinstance(fab, list) or any(not isinstance(x, dict) or 'quote' not in x or 'why' not in x for x in fab):
        errs.append('"fabrication" 必须是列表，每项是含 "quote"、"why" 的对象（没有就给 []）')
    if not isinstance(out.get('note', ''), str):
        errs.append('"note" 必须是字符串')
    extra = set(out) - set(DIMS) - {'fabrication', 'note'}
    if extra:
        errs.append('多了字段：' + '、'.join(sorted(extra)))
    return errs


qw.validate = validate

if __name__ == '__main__':
    argv = list(sys.argv)
    # the base CLI checks queue names against its own tuple: map memoir commands onto it
    if len(argv) > 2 and argv[1] == 'next' and argv[2] not in ('memoir', 'all'):
        print('ERROR：队列名只能是 memoir')
        sys.exit(2)
    if len(argv) > 1 and argv[1] == 'answer' and (len(argv) < 4 or argv[2] != 'memoir'):
        print('用法：answer memoir <id> < answer.json')
        sys.exit(2)
    sys.exit(qw.main(argv))
