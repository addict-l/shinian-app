"""v3m (experiment): several judge prompts per checkpoint, per-target majority vote on the answer kind, then v3h assembly.

Offline experiment to test whether independent judge prompts disagree in a way a vote can fix.
V3M_JUDGES = comma list of judge prompt paths; a path suffixed with '@old' is sent with the older
child-field wording (to replay caches made before that wording changed). The first judge in the list wins ties
and supplies the sentence ids when it is in the majority.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v3h  # noqa: E402

NAME = 'v3m'
CallFailed = v3h.CallFailed
DRY_RESPONSE = v3h.DRY_RESPONSE
RUNTIME = v3h.RUNTIME


def setup():
    ctx = v3h.setup()
    spec = os.environ.get('V3M_JUDGES') or str(RUNTIME / 'judge-prompt.txt')
    ctx.judges = []
    for item in spec.split(','):
        path, _, flag = item.partition('@')
        ctx.judges.append({'prompt': Path(path).read_text(encoding='utf-8'), 'old': flag == 'old', 'name': Path(path).stem})
    return ctx


def category(j):
    if not isinstance(j, dict):
        return 'absent'
    v = v3h.verdict_of(j)
    return {'answered': 'content', 'none': 'negation', 'unspecified': 'unspecified', 'unknown': 'unknown',
            'declined': 'declined', 'deferred': 'deferred'}.get(v, 'absent')


def merge(outputs, fids):
    merged = {'control': (outputs[0].get('control') or {'action': 'continue', 'units': []}), 'targets': {}}
    votes = {}
    for fid in fids:
        cats = [category((o.get('targets') or {}).get(fid)) for o in outputs]
        count = Counter(cats)
        top = max(count.values())
        winners = [c for c in cats if count[c] == top]
        win = winners[0]  # first judge's category wins ties
        votes[fid] = cats
        src = next(o for o, c in zip(outputs, cats) if c == win)
        j = (src.get('targets') or {}).get(fid)
        if isinstance(j, dict):
            merged['targets'][fid] = j
    return merged, votes


def run_checkpoint(payload, ctx):
    fids = v3h.judged_fields(payload, ctx)
    tag = 't%d' % len(payload['sources'])
    if not fids:
        result = ctx.engine.op('analyze', payload=payload, proposal={'control': {'action': 'continue', 'evidence_unit_ids': []}, 'fields': {}}, raw=None)
        return result, {'note': 'no judged fields'}
    calls = []
    for k, jd in enumerate(ctx.judges):
        saved = set(v3h.EXP)
        if jd['old']:
            v3h.EXP.add('old_child_note')
        else:
            v3h.EXP.discard('old_child_note')
        msg = v3h.user_message(payload, ctx, fids)
        v3h.EXP.clear(); v3h.EXP.update(saved)
        calls.append({'id': '%s-judge%d' % (tag, k), 'system': jd['prompt'], 'user': msg, 'params': v3h.PARAMS})
    rs = yield calls
    outputs = []
    for r in rs:
        if not r.get('ok'):
            raise CallFailed(json.dumps({k: r.get(k) for k in ('error', 'http_status', 'error_detail')}, ensure_ascii=False))
        o = r.get('output') if isinstance(r.get('output'), dict) else {}
        if not isinstance(o.get('targets'), dict):
            o = {**o, 'targets': {}}
        outputs.append(o)
    output, votes = merge(outputs, fids)
    result, proposal, info = v3h.settle(payload, output, ctx, fids)
    trace = {'judges': [r.get('content') for r in rs], 'votes': votes, 'attempts': info['attempts'],
             'guard_probe': info.get('guard_probe'), 'stage_fallback': info['stage_fallback']}
    return result, trace
