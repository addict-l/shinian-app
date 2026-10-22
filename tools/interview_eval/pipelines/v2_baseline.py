"""Current production flow (full-interview-v2.0.0): extractor A -> reviewer B -> at most one repair.

Mirrors cloud-deployment/backend/app/ai/contract_interview.py ContractInterviewPipeline.run
and the frozen runner's non-workflow path. Provider: deepseek-v4-pro, thinking disabled,
max_tokens 16384, no temperature (as provider-settings.json).
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

NAME = 'v2-baseline'
RUNTIME = common.ROOT / 'docs/prototypes/full-interview-v2/single-question-v2'
PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 16384, 'temperature': None, 'json_mode': True}


class CallFailed(RuntimeError):
    pass


class Ctx:
    pass


def setup():
    ctx = Ctx()
    ctx.engine = common.Engine(RUNTIME)
    ctx.extractor = (RUNTIME / 'extractor-prompt.txt').read_text(encoding='utf-8')
    ctx.reviewer = (RUNTIME / 'reviewer-prompt.txt').read_text(encoding='utf-8')
    return ctx


def call(cid, system, payload):
    return {'id': cid, 'system': system, 'user': json.dumps(payload, ensure_ascii=False), 'params': PARAMS}


def ok(response):
    if not response.get('ok'):
        raise CallFailed(json.dumps({k: response.get(k) for k in ('error', 'http_status', 'error_detail')}, ensure_ascii=False))
    return response


def raw(response):
    return {'raw_content': response.get('content'), 'parse_error': response.get('parse_error'),
            'finish_reason': response.get('finish_reason')}


def run_checkpoint(payload, ctx):
    tag = 't%d' % len([s for s in payload['sources']])
    mi = ctx.engine.op('model_input', payload=payload)
    [r1] = yield [call(tag + '-extract', ctx.extractor, mi)]
    ok(r1)
    first = ctx.engine.op('analyze', payload=payload, proposal=r1.get('output'), raw=raw(r1))
    review = ctx.engine.op('review_input', payload=mi, candidate=r1.get('output'), checked=first)
    [r2] = yield [call(tag + '-review', ctx.reviewer, review)]
    ok(r2)
    result = ctx.engine.op('analyze', payload=payload, proposal=r2.get('output'), raw=raw(r2))
    trace = {'extract': r1, 'first': first, 'review': r2, 'reviewed': result}
    if result.get('decision') == 'invalid':
        repair = copy.deepcopy(mi)
        repair['extraction_retry'] = {'attempt': 1, 'validation_errors': result.get('errors', []),
                                      'previous_proposal': r2.get('output')}
        [r3] = yield [call(tag + '-repair1', ctx.reviewer, repair)]
        ok(r3)
        result = ctx.engine.op('analyze', payload=payload, proposal=r3.get('output'), raw=raw(r3))
        trace.update(repair=r3, repaired=result)
    return result, trace
