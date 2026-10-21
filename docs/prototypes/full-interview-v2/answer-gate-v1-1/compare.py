#!/usr/bin/env python3
"""Paired comparison of two fully executed, frozen interview sessions."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text())


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def turn_seconds(session: Path, row: dict):
    directory = session / 'cases' / row['case_id'] / f"turn-{row['turn']:03d}"
    responses = [read(path) for path in directory.glob('response-*.json')]
    seconds = [record['seconds'] for record in responses if isinstance(record.get('seconds'), (int, float))]
    return round(sum(seconds), 3) if seconds else None


def pct(value):
    return f'{value * 100:.2f}%' if value is not None else '—'


def health(session: Path):
    freeze, score = read(session / 'freeze.json'), read(session / 'scores.json')
    if freeze['provider_settings'].get('thinking') != 'disabled' or 'reasoning_effort' in freeze['provider_settings']:
        raise ValueError('provider settings violate disabled-thinking requirement: ' + str(session))
    checked = 0
    for path in (session / 'batches').glob('*.raw.jsonl'):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get('kind') != 'model_call':
                continue
            settings = record.get('provider_settings') or {}
            if settings.get('thinking') != 'disabled' or 'reasoning_effort' in settings:
                raise ValueError('a real model response violated disabled-thinking requirement')
            checked += 1
    if checked != score['performance']['successful_responses']:
        raise ValueError('raw model response count disagrees with scored responses')
    overall = score['overall']
    if overall['evaluated_checkpoints'] != overall['planned_checkpoints'] or overall['transport_errors'] or overall['unexecuted']:
        raise ValueError('comparison requires every checkpoint executed without transport error')
    return freeze, score, checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('control', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    control, candidate = args.control.resolve(), args.candidate.resolve()
    c_freeze, c, c_calls = health(control)
    n_freeze, n, n_calls = health(candidate)
    for filename in ('dataset.json', 'contracts.snapshot.json', 'runtime/contracts.json', 'runtime/provider-settings.json'):
        if sha(control / filename) != sha(candidate / filename):
            raise ValueError('paired inputs differ: ' + filename)
    if c_freeze['model'] != n_freeze['model']:
        raise ValueError('model changed')
    ck = {(row['case_id'], row['turn']): row for row in c['rows']}
    nk = {(row['case_id'], row['turn']): row for row in n['rows']}
    if ck.keys() != nk.keys():
        raise ValueError('paired cases or turns differ')
    pairs = []
    for key in sorted(ck):
        old, new = ck[key], nk[key]
        pairs.append({'case_id': key[0], 'turn': key[1], 'question_id': old['question_id'],
                      'control_passed': old['passed'], 'candidate_passed': new['passed'],
                      'control_decision': old.get('decision'), 'candidate_decision': new.get('decision'),
                      'control_seconds': turn_seconds(control, old), 'candidate_seconds': turn_seconds(candidate, new),
                      'control_followup_passed': old.get('followup', {}).get('passed'),
                      'candidate_followup_passed': new.get('followup', {}).get('passed')})
    co, no = c['overall'], n['overall']
    old_times = [row['control_seconds'] for row in pairs if row['control_seconds'] is not None]
    new_times = [row['candidate_seconds'] for row in pairs if row['candidate_seconds'] is not None]
    old_median, new_median = statistics.median(old_times), statistics.median(new_times)
    # Declared before reading candidate scores: 4 additional successes of 33,
    # no additional repeated follow-up, and at least 15% lower checkpoint median.
    gates = {'accuracy_gain_at_least_4_of_33': no['all_critical_checkpoint_passes'] - co['all_critical_checkpoint_passes'] >= 4,
             'repeated_followups_not_increased': no['repeated_or_unnecessary_followups'] <= co['repeated_or_unnecessary_followups'],
             'median_checkpoint_at_least_15_percent_faster': new_median <= old_median * .85}
    result = {'scope': 'same frozen published-transcript development batch; paired fresh model calls; not live-interview acceptance',
              'control': str(control), 'candidate': str(candidate), 'same_dataset_sha256': sha(control / 'dataset.json'),
              'same_contracts_sha256': sha(control / 'runtime/contracts.json'), 'model': c_freeze['model'],
              'thinking_disabled_witness_calls': {'control': c_calls, 'candidate': n_calls},
              'metrics': {}, 'directional_improvement_gates': gates, 'all_directional_gates_met': all(gates.values()),
              'pairs': pairs}
    for label, score, times in [('control', c, old_times), ('candidate', n, new_times)]:
        overall, performance = score['overall'], score['performance']
        result['metrics'][label] = {
            'passed': overall['all_critical_checkpoint_passes'], 'checkpoints': overall['planned_checkpoints'],
            'pass_rate': overall['all_critical_checkpoint_accuracy'],
            'repeated_or_unnecessary_followups': overall['repeated_or_unnecessary_followups'],
            'followup_passes': overall['followup_passes'], 'false_accepted_fields': overall['false_accepted_fields'],
            'missed_substantive_fields': overall['missed_substantive_fields'], 'protocol_invalid': overall['protocol_invalid'],
            'model_calls': performance['model_calls'], 'run_wall_seconds': performance['run_wall_seconds'],
            'checkpoint_http_median_seconds': statistics.median(times),
            'checkpoint_http_p95_seconds': performance['latency_checkpoint_model_http_including_repairs']['p95_seconds']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    m = result['metrics']
    lines = ['# 采访答案门原型：同批真实材料配对测试', '',
             '范围：8 位公开访谈人物、33 个检查点、28 道题。两组材料、合同、模型和关闭思考设置完全相同；两组均重新实际调用模型。',
             '这是已用于开发的真实访谈回放，不代表老人实时回答新问法，也不是正式三轮验收。', '',
             '| 指标 | 现有链路 | 答案门原型 |', '| --- | ---: | ---: |']
    rows = [
        ('严格关键点通过', lambda v: f"{v['passed']}/{v['checkpoints']} ({pct(v['pass_rate'])})"),
        ('重复或不必要追问', lambda v: str(v['repeated_or_unnecessary_followups'])),
        ('追问判断通过', lambda v: f"{v['followup_passes']}/{v['checkpoints']}"),
        ('误收字段', lambda v: str(v['false_accepted_fields'])),
        ('漏提实质字段', lambda v: str(v['missed_substantive_fields'])),
        ('协议无效', lambda v: str(v['protocol_invalid'])),
        ('单检查点模型 HTTP 时间中位数', lambda v: f"{v['checkpoint_http_median_seconds']:.3f} 秒"),
        ('单检查点模型 HTTP 时间 P95', lambda v: f"{v['checkpoint_http_p95_seconds']:.3f} 秒"),
        ('模型调用次数', lambda v: str(v['model_calls'])),
        ('并发整批墙钟时间', lambda v: f"{v['run_wall_seconds']:.3f} 秒")]
    lines += [f'| {name} | {format_value(m["control"])} | {format_value(m["candidate"])} |'
              for name, format_value in rows]
    lines += ['', '预先设定的方向性标准：33 点至少多通过 4 点、重复追问不增加、单检查点耗时中位数至少下降 15%。本批结果：' + ('三项均达到。' if result['all_directional_gates_met'] else '未同时达到三项。'),
              '33 点样本过小，方向性改善不能当成统计显著性或 >95% 正式验收。', '',
              '## 判定变化', '']
    for row in pairs:
        if row['control_passed'] != row['candidate_passed']:
            direction = '改善' if row['candidate_passed'] else '退步'
            lines.append(f"- {direction}：{row['question_id']}，{row['case_id']} 第 {row['turn']+1} 轮；"
                         f"现有 {row['control_decision']}，原型 {row['candidate_decision']}。")
    lines += ['', '原始请求、模型响应、逐字段分数与失败均保存在各自会话目录；JSON 配对数据与本文同名。'
              ' 模型 HTTP 时间是每检查点实际请求耗时之和；并发批次墙钟时间包含调度与环境等待，不能当成用户单轮等待。']
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'report': str(args.out.with_suffix('.md')), 'gates': gates,
                      'control_passed': m['control']['passed'], 'candidate_passed': m['candidate']['passed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
