#!/usr/bin/env python3
"""Story-question metrics of simulated runs (v5 deepening test), side by side as markdown (+ JSON with --json).

  python3 tools/interview_eval/simulate/story_metrics.py A=st5-a-it B=st5-b5a-it [--json out.json] [--html fragment.html]
  (a run may be RUN1+RUN2 to pool runs)

Per story question (story-questions.json): the elder's own words (characters without punctuation, summed over
the question), deepen questions asked, why deepening stopped or was skipped, the kind asked (scene / people /
detail / feeling), how the elder answered the deepen questions (and whether a "can't remember" came from the
material limit or from the sampled reluctance), and the blind rubric on all interviewer turns of story questions.
"""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
from interview import elder_signal  # noqa: E402
from score import DIMS, label_messages  # noqa: E402

BANK = common.load(common.ROOT / 'docs/prototypes/full-interview-v5/story-questions.json')
STORY = {q['id']: q for q in BANK['questions'] if q['depth'] == 'story'}


def chars(text):
    return len(re.sub(r'[\s，。！？、,.!?；;：:“”"‘’…~—（）()《》]', '', text or ''))


def mean(xs):
    return round(statistics.mean(xs), 2) if xs else None


def median(xs):
    return round(statistics.median(xs), 1) if xs else None


def ge4(xs):
    return round(sum(x >= 4 for x in xs) / len(xs), 3) if xs else None


def run_metrics(run):
    sessions, scores = [], {}
    for part in run.split('+'):  # "RUN1+RUN2" joins runs (e.g. iteration + holdout)
        rd = common.RUNS / part
        sessions += [common.load(f) for f in sorted((rd / 'sessions').glob('*.json'))]
        scores.update((common.load(rd / 'scores.json').get('scores') or {}) if (rd / 'scores.json').exists() else {})
    words, deepens, reasons, first_reason, dims, ans = [], [], Counter(), Counter(), Counter(), Counter()
    deepen_words, before_words = [], []
    turns = {'all': [], 'deepen': [], 'close': [], 'followup': []}
    vio, vio_deepen = Counter(), Counter()
    per_q = []
    for s in sessions:
        for i, ep in enumerate(s['episodes']):
            if ep['qid'] not in STORY:
                continue
            elder = [m for m in ep['messages'] if m['role'] == 'elder' and not m.get('scripted')]
            w = sum(chars(m['text']) for m in elder)
            dw = sum(chars(m['text']) for m in elder if m.get('deepen_answer'))
            words.append(w)
            deepen_words.append(dw)
            before_words.append(w - dw)
            dz = ep.get('deepen') or {}
            n = sum(1 for m in ep['messages'] if m.get('kind') == 'deepen')
            deepens.append(n)
            for e in dz.get('log') or []:
                reasons[e['reason']] += 1
            if dz.get('log'):
                first_reason[dz['log'][0]['reason']] += 1
            for m in ep['messages']:
                if m.get('kind') == 'deepen':
                    dims[m.get('dimension')] += 1
            # how the elder answered each deepen question
            msgs = ep['messages']
            for j, m in enumerate(msgs):
                if m['role'] != 'elder' or not m.get('deepen_answer'):
                    continue
                sig = elder_signal(m['text'])
                beh = m.get('behavior')
                if sig == 'unknown':
                    key = 'unknown_sampled_reluctant' if beh == 'reluctant' else 'unknown_material'
                elif sig == 'declined':
                    key = 'declined_sampled' if beh == 'reluctant' else 'declined_other'
                elif sig == 'rest' or beh == 'rest':
                    key = 'rest'
                elif chars(m['text']) <= 20:
                    key = 'short'
                else:
                    key = 'answered'
                ans[key] += 1
            sc = (scores.get(s['session']) or {}).get(str(i)) or {}
            for label, m in label_messages(ep):
                t = (sc.get('turns') or {}).get(label)
                if m['role'] != 'system' or not t:
                    continue
                turns['all'].append(t)
                if m.get('kind') in turns:
                    turns[m['kind']].append(t)
                for v in t.get('violations') or []:
                    vio[v] += 1
                    if m.get('kind') == 'deepen':
                        vio_deepen[v] += 1
            per_q.append({'session': s['session'], 'name': s.get('name'), 'qid': ep['qid'], 'words': w, 'deepen_words': dw, 'deepens': n,
                          'close': ep['close_reason'], 'first_reason': (dz.get('log') or [{}])[0].get('reason')})
    out = {'run': run, 'story_questions': len(words), 'words_mean': mean(words), 'words_median': median(words),
           'words_before_deepen_mean': mean(before_words), 'deepen_words_mean': mean(deepen_words),
           'ge150': round(sum(w >= 150 for w in words) / len(words), 3) if words else None,
           'deepens_mean': mean(deepens), 'deepens_dist': dict(sorted(Counter(deepens).items())),
           'deepens_total': sum(deepens), 'reasons': dict(reasons), 'first_reason': dict(first_reason), 'dimensions': dict(dims),
           'deepen_answers': dict(ans), 'deepen_answers_total': sum(ans.values()),
           'turns_scored': len(turns['all']), 'violations': dict(vio), 'violations_deepen': dict(vio_deepen),
           'violation_turns': sum(1 for t in turns['all'] if t.get('violations')),
           'per_question': per_q}
    for d in DIMS:
        xs = [t[d] for t in turns['all'] if t.get(d) is not None]
        out['mean_' + d], out['ge4_' + d] = mean(xs), ge4(xs)
        xd = [t[d] for t in turns['deepen'] if t.get(d) is not None]
        out['deepen_mean_' + d], out['deepen_ge4_' + d] = mean(xd), ge4(xd)
        xc = [t[d] for t in turns['close'] if t.get(d) is not None]
        out['close_mean_' + d] = mean(xc)
    out['deepen_turns_scored'] = len(turns['deepen'])
    out['violation_rate'] = round(out['violation_turns'] / len(turns['all']), 3) if turns['all'] else None
    return out


ROWS = [('故事题数', 'story_questions'), ('每题老人原话字数 均值', 'words_mean'), ('　中位数', 'words_median'),
        ('　其中深挖前', 'words_before_deepen_mean'), ('　其中深挖回答', 'deepen_words_mean'), ('≥150 字的题占比', 'ge150'),
        ('每题深挖次数', 'deepens_mean'), ('深挖次数分布', 'deepens_dist'), ('深挖维度', 'dimensions'),
        ('首个触发/跳过原因', 'first_reason'), ('全部触发/跳过/停止原因', 'reasons'), ('老人对深挖的回答', 'deepen_answers'),
        ('打分发言数（故事题）', 'turns_scored')] + \
       [(f'{z} 均分 / ≥4', d) for z, d in (('自然', 'natural'), ('贴合', 'grounded'), ('时机', 'timing'), ('单一', 'single'), ('语气', 'tone'))] + \
       [('硬性违规轮次 / 率', 'violation_turns'), ('违规明细', 'violations'), ('深挖发言打分数', 'deepen_turns_scored')] + \
       [(f'深挖发言 {z} 均分 / ≥4', 'deepen_' + d) for z, d in (('自然', 'natural'), ('贴合', 'grounded'), ('时机', 'timing'), ('单一', 'single'), ('语气', 'tone'))] + \
       [('深挖发言违规', 'violations_deepen')]


def cell(m, key):
    if key in DIMS:
        return f"{m.get('mean_' + key)} / {m.get('ge4_' + key)}"
    if key.startswith('deepen_') and key[7:] in DIMS:
        d = key[7:]
        return f"{m.get('deepen_mean_' + d)} / {m.get('deepen_ge4_' + d)}"
    if key == 'violation_turns':
        return f"{m.get('violation_turns')} / {m.get('violation_rate')}"
    v = m.get(key)
    return '' if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v))


def main(argv):
    out_json = out_html = None
    if '--html' in argv:
        k = argv.index('--html')
        out_html = argv[k + 1]
        argv = argv[:k] + argv[k + 2:]
    if '--json' in argv:
        k = argv.index('--json')
        out_json = argv[k + 1]
        argv = argv[:k] + argv[k + 2:]
    runs = [tuple(x.split('=', 1)) if '=' in x else (x, x) for x in argv]
    ms = [run_metrics(r) for _, r in runs]
    print('| 指标 | ' + ' | '.join(f'{lbl}（{r}）' for lbl, r in runs) + ' |')
    print('|---|' + '---|' * len(runs))
    for name, key in ROWS:
        print(f'| {name} | ' + ' | '.join(cell(m, key).replace('|', '/') for m in ms) + ' |')
    if out_html:  # fragment for export_html.py --summary
        import html as H
        rows = ['<table><tr><th>指标（故事题）</th>' + ''.join(f'<th>{H.escape(lbl)}</th>' for lbl, _ in runs) + '</tr>']
        for name, key in ROWS:
            rows.append(f'<tr><td>{H.escape(name)}</td>' + ''.join(f'<td>{H.escape(cell(m, key))}</td>' for m in ms) + '</tr>')
        Path(out_html).write_text('<h3>故事题指标（A = v4d 不深挖，B = 深挖）</h3>' + ''.join(rows) + '</table>', encoding='utf-8')
    if out_json:
        Path(out_json).write_text(json.dumps({lbl: m for (lbl, _), m in zip(runs, ms)}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1:])
