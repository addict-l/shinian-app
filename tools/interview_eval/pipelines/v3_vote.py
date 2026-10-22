"""v3 + self-consistency: 3 judge samples per checkpoint, per-target majority on the code-derived state.

Sample 0 is the deterministic judge (temperature 0, identical to v3_judge, so it is cache-shared);
samples 1-2 use temperature 0.7. For each target the state chosen by most samples wins (ties keep
sample 0); its units/core/subject come from the first sample that voted for the winning state.
Assembly, engine validation and follow-up decision are exactly v3_judge's.
"""
import collections
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v3_judge', HERE / 'v3_judge.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

NAME = 'v3-vote'
CallFailed = base.CallFailed
setup = base.setup
DRY_RESPONSE = base.DRY_RESPONSE
K = int(os.environ.get('V3_VOTES', '3'))
HOT = {**base.PARAMS, 'temperature': 0.7}


def vote(outputs, fids):
    merged = {'control': (outputs[0] or {}).get('control') or {'action': 'continue', 'units': []}, 'targets': {}}
    detail = {}
    for fid in fids:
        answers = [((o or {}).get('targets') or {}).get(fid) for o in outputs]
        answers = [a if isinstance(a, dict) else {} for a in answers]
        verdicts = [base.verdict_of(a) or 'not_answered' for a in answers]
        counts = collections.Counter(verdicts)
        top = max(counts.values())
        winners = [v for v in counts if counts[v] == top]
        winner = verdicts[0] if verdicts[0] in winners else winners[0]
        chosen = next(a for a, v in zip(answers, verdicts) if v == winner)
        merged['targets'][fid] = chosen
        detail[fid] = verdicts
    return merged, detail


def run_checkpoint(payload, ctx):
    fids = base.judged_fields(payload, ctx)
    if not fids:
        return (yield from base.run_checkpoint(payload, ctx))
    tag = 't%d' % len(payload['sources'])
    message = base.user_message(payload, ctx, fids)
    calls = [{'id': tag + '-judge', 'system': ctx.prompt, 'user': message, 'params': base.PARAMS}]
    calls += [{'id': '%s-judge-s%d' % (tag, k), 'system': ctx.prompt, 'user': message, 'params': HOT, 'sample': k}
              for k in range(1, K)]
    responses = yield calls
    if not responses[0].get('ok'):
        raise CallFailed(json.dumps({k: responses[0].get(k) for k in ('error', 'http_status', 'error_detail')}, ensure_ascii=False))
    outputs = [r.get('output') if r.get('ok') and isinstance(r.get('output'), dict) else None for r in responses]
    merged, detail = vote([o for o in outputs if o is not None], fids)
    fake = {'ok': True, 'output': merged, 'content': json.dumps(merged, ensure_ascii=False)}
    gen = base.run_checkpoint(payload, ctx)
    gen.send(None)
    try:
        gen.send([fake])
    except StopIteration as stop:
        result, trace = stop.value
    trace['votes'] = detail
    trace['samples'] = [r.get('content') for r in responses]
    return result, trace
