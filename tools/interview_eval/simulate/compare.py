#!/usr/bin/env python3
"""Side-by-side metrics of simulated runs as a markdown table:  python3 compare.py RUN [RUN ...]"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402

ROWS = [('话题数', 'episodes'), ('打分发言数', 'scored_turns'), ('每题老人回答轮数', 'elder_turns'), ('每题追问', 'followups'),
        ('每题补充邀请', 'supplements'), ('重复追问（同目标）/题', 'repeat_target'), ('题目完成率（ready）', 'complete'),
        ('追问照念固定问句', 'verbatim'), ('追问引用老人原话词', 'grounded_proxy'), ('发言平均字数', 'reply_len_mean'),
        ('自然不生硬', 'score_natural'), ('　≥4 占比', 'ge4_natural'), ('贴合当前事件', 'score_grounded'), ('　≥4 占比', 'ge4_grounded'),
        ('时机（结束自然）', 'score_timing'), ('　≥4 占比', 'ge4_timing'), ('单一不预设', 'score_single'), ('语气', 'score_tone'),
        ('硬性违规率（轮）', 'violation_rate'), ('违规明细', 'violations'), ('模拟老人编造（处）', 'fabrication_total'),
        ('记录错误（处）', 'record_errors_total'), ('转题引子同会话内重复', 'transition_repeat'), ('收尾原因', 'close_reasons'), ('说话层回退', 'speaker_fallback'),
        ('每轮延迟均值 s', 'latency_mean_s'), ('每轮 token', 'tokens_per_model_turn')]


def main(runs):
    data = [common.load(common.RUNS / r / 'scores.json') for r in runs]
    print('| 指标 | ' + ' | '.join(runs) + ' |')
    print('|---|' + '---|' * len(runs))
    for name, key in ROWS:
        vals = []
        for d in data:
            v = (d.get('metrics') or {}).get(key)
            vals.append('' if v is None else str(v).replace('|', '/'))
        print(f'| {name} | ' + ' | '.join(vals) + ' |')
    print('| DS 新发 token | ' + ' | '.join(str(((d.get('relay') or {}).get('usage') or {}).get('total_tokens', 0)) for d in data) + ' |')


if __name__ == '__main__':
    main(sys.argv[1:])
