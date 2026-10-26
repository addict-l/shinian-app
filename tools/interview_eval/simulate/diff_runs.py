#!/usr/bin/env python3
"""Check that two simulated runs are the same interview: session records and per-question scores, ignoring only
call timing and cache flags (which differ between a live run and its offline replay).

  python3 tools/interview_eval/simulate/diff_runs.py RUN_A RUN_B      # exit 0 = identical, 1 = differences listed
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402

VOLATILE = {'seconds', 'cached'}


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def walk(a, b, path, out):
    if type(a) is not type(b):
        out.append(f'{path}: {str(a)[:80]!r} != {str(b)[:80]!r}')
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f'{path}.{k}: only in {"B" if k not in a else "A"}')
            else:
                walk(a[k], b[k], f'{path}.{k}', out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f'{path}: length {len(a)} != {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f'{path}[{i}]', out)
    elif a != b:
        out.append(f'{path}: {str(a)[:80]!r} != {str(b)[:80]!r}')


def main(ra, rb):
    out = []
    da, db = common.RUNS / ra / 'sessions', common.RUNS / rb / 'sessions'
    names = sorted({f.name for f in da.glob('*.json')} | {f.name for f in db.glob('*.json')})
    for n in names:
        if not (da / n).exists() or not (db / n).exists():
            out.append(f'{n}: missing in one run')
            continue
        walk(strip(common.load(da / n)), strip(common.load(db / n)), n, out)
    sa, sb = common.load(common.RUNS / ra / 'scores.json'), common.load(common.RUNS / rb / 'scores.json')
    walk(strip(sa.get('scores')), strip(sb.get('scores')), 'scores', out)
    walk(strip(sa.get('metrics')), strip(sb.get('metrics')), 'metrics', out)
    print(json.dumps({'sessions': len(names), 'differences': len(out)}))
    for line in out[:200]:
        print(' ', line)
    return 1 if out else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
