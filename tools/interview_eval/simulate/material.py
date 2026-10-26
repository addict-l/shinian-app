#!/usr/bin/env python3
"""Memoir-material value of story questions (v5d): how much of what the elder said on each story question could go
straight into the memoir.

  python3 tools/interview_eval/simulate/material.py A=st5-a-it+st5-a-ho B=st6-b5d-it [--offline] [--json OUT]

Two measures per story question (story-questions.json), both blind to the interviewer:
- rubric (Claude Haiku via the scorer file queue, fixed prompt docs/prototypes/full-interview-v5/material-prompt.txt):
  the elder's own words of the question only (each answer as a numbered paragraph, the entry question as the
  topic; no interviewer turn, so the wording of a version cannot be seen) -> concrete items (人物 地点 时间 经过 原话
  物件 感受) and an overall 1-5 "usable" score. Items per question is the main number. Answers are cached by content,
  so the same words get the same answer in every run.
- code (reproducible, no model): content bigrams of the elder's words that also occur in the persona material of the
  question (persona.bigrams minus a generic list) -- "material told" -- and that count over the material's own content
  bigrams -- "coverage". The simulated elder can only tell what his material holds, so this is the ceiling-aware view.
Results per run part: RUNS/<part>/material.json.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter

from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import queue_worker as qw  # noqa: E402
from persona import Personas, bigrams  # noqa: E402

PROMPT = (common.ROOT / 'docs/prototypes/full-interview-v5/material-prompt.txt').read_text(encoding='utf-8')
KINDS = ['人物', '地点', '时间', '经过', '原话', '物件', '感受']
NOTE = '只输出一个 JSON 对象：{"items": [{"kind": "...", "text": "..."}], "usable": 1-5 的整数, "note": "一句话"}（不加解释，不加代码块）。'
BANK = common.load(common.ROOT / 'docs/prototypes/full-interview-v5/story-questions.json')
STORY = {q['id'] for q in BANK['questions'] if q['depth'] == 'story'}
GENERIC = bigrams('时候以后后来那时当时现在事情经历印象记得觉得一下一点一件这件那件这段那段日子生活家里好像大概反正就是这样'
                  '具体详细情形情况样子清楚知道真的实在其实不太没有什么')


def elder_words(ep):
    return [m['text'] for m in ep['messages'] if m['role'] == 'elder' and not m.get('scripted')]


def request_input(ep):
    lines = [f'话题：{ep["entry"]}', '老人的原话：']
    lines += [f'（{k}）{t}' for k, t in enumerate(elder_words(ep), 1)]
    return '\n'.join(lines)


def code_measure(P, nid, ep):
    told = bigrams(''.join(elder_words(ep))) - GENERIC
    mat = bigrams(P.render(P.material(nid, ep['qid'])).replace('【当时被问】', '').replace('【你讲的】', '')) - GENERIC
    hit = told & mat
    return {'told_bigrams': len(told), 'material_told': len(hit), 'material_bigrams': len(mat),
            'coverage': round(len(hit) / len(mat), 3) if mat else None}


def collect(part, P, q, offline):
    rd = common.RUNS / part
    items = []
    for f in sorted((rd / 'sessions').glob('*.json')):
        s = common.load(f)
        for i, ep in enumerate(s['episodes']):
            if ep['qid'] not in STORY:
                continue
            rid, row = q.submit(PROMPT, request_input(ep), NOTE, {'type': 'material', 'kinds': KINDS},
                                {'material': part, 'session': s['session'], 'episode': i})
            if row is None and offline:
                row = {'ok': False, 'error': 'offline_haiku_cache_miss'}
            items.append([s, i, ep, rid, row, code_measure(P, s['narrator_id'], ep)])
    return items


def wait(q, items):
    t0, last = time.time(), 0
    while True:
        missing = 0
        for it in items:
            if it[4] is None:
                it[4] = q.poll(it[3])
                missing += it[4] is None
        if not missing:
            return
        if time.time() - last >= 60:
            last = time.time()
            print(json.dumps({'material_waiting': missing, 't': round(time.time() - t0)}), flush=True)
        time.sleep(1)


def parse(row):
    out = row.get('output') if isinstance(row, dict) and isinstance(row.get('output'), dict) else None
    if not out:
        return None
    its = [x for x in out.get('items') or [] if isinstance(x, dict) and x.get('kind') in KINDS]
    return {'items': its, 'n': len(its), 'by_kind': dict(Counter(x['kind'] for x in its)), 'usable': out.get('usable'), 'note': out.get('note')}


def summarise(rows):
    ok = [r for r in rows if r['rubric']]
    n = [r['rubric']['n'] for r in ok]
    u = [r['rubric']['usable'] for r in ok]
    kinds = Counter()
    for r in ok:
        kinds.update(r['rubric']['by_kind'])
    mt = [r['code']['material_told'] for r in rows]
    cov = [r['code']['coverage'] for r in rows if r['code']['coverage'] is not None]
    mean = lambda xs: round(statistics.mean(xs), 2) if xs else None
    return {'story_questions': len(rows), 'rubric_scored': len(ok), 'items_mean': mean(n), 'items_median': statistics.median(n) if n else None,
            'items_total': sum(n), 'by_kind_per_q': {k: round(kinds[k] / len(ok), 2) for k in KINDS} if ok else {},
            'usable_mean': mean(u), 'usable_ge4': round(sum(x >= 4 for x in u) / len(u), 3) if u else None,
            'material_told_mean': mean(mt), 'coverage_mean': mean(cov)}


def main(argv):
    offline = '--offline' in argv
    out_json = argv[argv.index('--json') + 1] if '--json' in argv else None
    runs = [a for a in argv if not a.startswith('--') and a != out_json]
    runs = [tuple(x.split('=', 1)) if '=' in x else (x, x) for x in runs]
    P = Personas()
    q = qw.HaikuQueue('scorer')
    allitems = {}
    for _, name in runs:
        for part in name.split('+'):
            if part not in allitems:
                allitems[part] = collect(part, P, q, offline)
    wait(q, [it for its in allitems.values() for it in its])
    per_part = {}
    for part, its in allitems.items():
        rows = []
        for s, i, ep, rid, row, code in its:
            rows.append({'session': s['session'], 'name': s.get('name'), 'qid': ep['qid'], 'episode': i,
                         'chars': sum(len(t) for t in elder_words(ep)), 'rubric': parse(row), 'code': code})
        per_part[part] = rows
        common.save(common.RUNS / part / 'material.json', {'prompt_sha': common.sha(PROMPT), 'rows': rows})
    summary = {}
    for lbl, name in runs:
        rows = [r for part in name.split('+') for r in per_part[part]]
        summary[lbl] = summarise(rows)
    keys = [('故事题数', 'story_questions'), ('素材条数/题 均值（Haiku）', 'items_mean'), ('　中位数', 'items_median'),
            ('　各类/题', 'by_kind_per_q'), ('可写性 均值', 'usable_mean'), ('可写性 ≥4 占比', 'usable_ge4'),
            ('讲出的资料实词数/题（代码）', 'material_told_mean'), ('资料覆盖率（代码）', 'coverage_mean')]
    print('| 素材价值（故事题） | ' + ' | '.join(lbl for lbl, _ in runs) + ' |')
    print('|---|' + '---|' * len(runs))
    for zh, k in keys:
        print(f'| {zh} | ' + ' | '.join(json.dumps(summary[l][k], ensure_ascii=False) if isinstance(summary[l][k], dict) else str(summary[l][k])
                                       for l, _ in runs) + ' |')
    if out_json:
        Path(out_json).write_text(json.dumps({'summary': summary, 'per_part': per_part}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1:])
