"""Diagnostic only: v2 extractor A alone (no reviewer B / repair). Replays paid A calls from cache."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_baseline as base  # noqa: E402

NAME = 'v2-first-pass'
CallFailed = base.CallFailed
setup = base.setup


def run_checkpoint(payload, ctx):
    tag = 't%d' % len(payload['sources'])
    mi = ctx.engine.op('model_input', payload=payload)
    [r1] = yield [base.call(tag + '-extract', ctx.extractor, mi)]
    base.ok(r1)
    first = ctx.engine.op('analyze', payload=payload, proposal=r1.get('output'), raw=base.raw(r1))
    return first, {'extract': r1, 'first': first}
