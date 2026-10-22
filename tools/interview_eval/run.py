#!/usr/bin/env python3
"""Random 5-10 person interview evaluation through the local DeepSeek relay.

  python tools/interview_eval/run.py --pipeline tools/interview_eval/pipelines/v2_baseline.py [--people N] [--seed S]
  python tools/interview_eval/run.py --pipeline ... --dataset RUN/dataset.json   # re-run a fixed sample
  python tools/interview_eval/run.py --pipeline ... --offline                    # replay from cache only

Every case is an independent question; turns inside a case are sequential and
carry only that question's validated fields. All checkpoints advance together,
so each pipeline stage becomes ONE relay job.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def load_pipeline(path):
    spec = importlib.util.spec_from_file_location('pipeline_' + Path(path).stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_runner(case, ctx, pipeline, run_dir):
    previous, counts, records = {}, {}, {}
    for index in range(len(case['turns'])):
        payload = ctx.engine.payload_for(case, index, previous, counts)
        try:
            result, trace = yield from pipeline.run_checkpoint(payload, ctx)
            record = {'kind': 'evaluated', 'result': result}
        except pipeline.CallFailed as exc:  # transport failure: retained as failure
            record, trace = {'kind': 'call_error', 'error': str(exc)}, {'error': str(exc)}
        records[index] = record
        common.save(run_dir / 'cases' / case['id'] / ('turn-%03d.json' % index),
                    {'payload': payload, 'record': record, 'trace': trace})
        if record['kind'] != 'evaluated' or record['result'].get('decision') == 'invalid':
            break
        previous = record['result'].get('fields', {})
        target = record['result'].get('target')
        if record['result'].get('decision') == 'ask' and target:
            counts[target] = counts.get(target, 0) + 1
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pipeline', required=True, type=Path)
    p.add_argument('--people', type=int)
    p.add_argument('--seed', type=int)
    p.add_argument('--dataset', type=Path, help='reuse a previously drawn sample (dataset.json of an earlier run)')
    p.add_argument('--name', default=None)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--fresh', action='store_true', help='ignore the response cache: re-call DeepSeek for every request')
    p.add_argument('--dry', action='store_true', help='plumbing test: every call returns the pipeline DRY_RESPONSE (or {}); nothing sent or cached')
    p.add_argument('--exclude', default='', help='comma separated narrator ids to exclude from sampling')
    a = p.parse_args()

    pipeline = load_pipeline(a.pipeline)
    data = common.load(a.dataset) if a.dataset else common.sample_dataset(a.people, a.seed, [x for x in a.exclude.split(',') if x])
    stamp = time.strftime('%Y%m%d-%H%M%S')
    name = a.name or f'{stamp}-{pipeline.NAME}'
    run_dir = common.RUNS / name
    run_dir.mkdir(parents=True, exist_ok=False)
    common.save(run_dir / 'dataset.json', data)
    print(json.dumps({'run': str(run_dir), 'pipeline': pipeline.NAME, **data.get('selection', {})}, ensure_ascii=False), flush=True)

    ctx = pipeline.setup()
    relay = common.Relay(run_dir, offline=a.offline, fresh=a.fresh,
                         dry=(getattr(pipeline, 'DRY_RESPONSE', None) or (lambda call: '{}')) if a.dry else None)
    gens, pending, results = {}, {}, {}
    for case in data['cases']:
        gen = case_runner(case, ctx, pipeline, run_dir)
        try:
            pending[case['id']] = gen.send(None)
            gens[case['id']] = gen
        except StopIteration as stop:
            for index, rec in (stop.value or {}).items():
                results[(case['id'], index)] = rec
    phase = 0
    t0 = time.time()
    while gens:
        phase += 1
        batch, owners = [], {}
        for cid, calls in pending.items():
            for call in calls:
                uid = f'{cid}::{call["id"]}'
                owners[uid] = (cid, call['id'])
                batch.append({**call, 'id': uid})
        responses = relay.run_batch(f'{name}-p{phase:02d}', batch)
        print(json.dumps({'phase': phase, 'calls': len(batch), 'sent': relay.calls_sent, 'cached': relay.calls_cached,
                          'elapsed': round(time.time() - t0, 1)}), flush=True)
        for cid in list(gens):
            mine = [responses[f'{cid}::{call["id"]}'] for call in pending[cid]]
            try:
                pending[cid] = gens[cid].send(mine)
            except StopIteration as stop:
                for index, rec in (stop.value or {}).items():
                    results[(cid, index)] = rec
                del gens[cid], pending[cid]
            except Exception:
                traceback.print_exc()
                results[(cid, 0)] = {'kind': 'harness_error', 'error': traceback.format_exc()[-1500:]}
                del gens[cid], pending[cid]
    rows, summary = common.score_rows(data, results)
    report = {'run': name, 'pipeline': pipeline.NAME, 'selection': data.get('selection'), 'overall': summary,
              'relay': {'sent': relay.calls_sent, 'cached': relay.calls_cached, 'phases': phase, 'usage': relay.usage},
              'wall_seconds': round(time.time() - t0, 1), 'rows': rows}
    common.save(run_dir / 'scores.json', report)
    lines = [f"# {name}", '',
             f"人物 {len(data['narrators'])}：{'、'.join(n['name'] for n in data['narrators'])}",
             f"关键点通过 {summary['all_critical_checkpoint_passes']}/{summary['planned_checkpoints']} = "
             f"{100 * summary['all_critical_checkpoint_passes'] / max(1, summary['planned_checkpoints']):.2f}%",
             f"有原话要素 {summary['substantive_field_passes']}/{summary['substantive_field_checks']}；"
             f"追问 {summary['followup_passes']}/{summary['followup_checks']}；漏提 {summary['missed_substantive_fields']}；"
             f"误收 {summary['false_accepted_fields']}；协议无效 {summary['protocol_invalid']}；调用错误 {summary['transport_errors']}",
             f"模型调用 新发 {relay.calls_sent} / 缓存 {relay.calls_cached}；阶段 {phase}",
             f"DS token（仅新发）：总 {relay.usage.get('total_tokens', 0)}，输入 {relay.usage.get('prompt_tokens', 0)}"
             f"（缓存命中 {relay.usage.get('prompt_cache_hit_tokens', 0)}），输出 {relay.usage.get('completion_tokens', 0)}", '', '## 失败', *common.failure_lines(rows)]
    (run_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines), flush=True)
    passed = summary['all_critical_checkpoint_passes'] * 100 > 95 * summary['planned_checkpoints']
    print(json.dumps({'gate_strictly_above_95': passed}), flush=True)
    ctx.engine.close()
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
