#!/usr/bin/env python3
"""Blind Haiku rubric (prompts/rubric-v1.txt, queue memoir) per chapter + code metrics per book.

  python3 tools/memoir_eval/score.py --run mb1-r1 --variants v1-on,v1-off [--books K1,K2] [--wait 7200] [--label it]

Each request shows one chapter (added sentences marked) and the elder's own words for that chapter; it
carries no variant, round or person-group information. Answers are cached by content (HAIKU_CACHE/memoir),
so an unchanged chapter is never scored twice.
"""
from __future__ import annotations

import argparse
import json
import time
from statistics import mean

import mb
import book_queue  # noqa: F401  (patches queue_worker for the memoir queue)
from book_queue import qw, DIMS

OUTPUT_NOTE = ('只输出一个 JSON 对象：{"faithful": 1-5, "lyrical": 1-5, "coherent": 1-5, "voice": 1-5, "structure": 1-5, '
               '"fabrication": [{"quote": "…", "why": "…"}], "note": "…"}，分数为整数，没有编造就给 "fabrication": []。')


def chapter_text(c):
    lines = ['章名：%s（%s）' % (c['title'], ' · '.join(mb.MODULE_NAME[m] for m in c['modules'])), '']
    for s in c['sections']:
        if len(c['sections']) > 1 and s['title']:
            lines.append('【节】' + s['title'])
        for p in s['paragraphs']:
            lines.append(''.join('【加写·%s】%s【/加写】' % (x['add'], x['t']) if x['add'] else x['t'] for x in p['sentences']))
        lines.append('')
    return '\n'.join(lines).strip()


def sources_text(book, plan_ch):
    ids = [u for s in plan_ch['sections'] for u in s['units']] + plan_ch['closing_units']
    lines = []
    for u in ids:
        x = book['units'][u]
        lines.append('[%s] 问：%s\n答：%s' % (u, x['asked'], x['text']))
    return '\n\n'.join(lines)


def request_input(book, plan_ch, c):
    n = sum(mb.han_len(x['t']) for s in c['sections'] for p in s['paragraphs'] for x in p['sentences'])
    m = sum(mb.han_len(book['units'][u]['text']) for s in plan_ch['sections'] for u in s['units'])
    return ('===== 这一章（%d 字；老人这部分原话约 %d 字）=====\n%s\n\n===== 老人原话 =====\n%s'
            % (n, m, chapter_text(c), sources_text(book, plan_ch)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--variants', required=True)
    ap.add_argument('--books', default='')
    ap.add_argument('--wait', type=float, default=10800)
    ap.add_argument('--label', default='')
    ap.add_argument('--rubric', default='rubric-v1.txt')
    a = ap.parse_args()
    run_dir = mb.RUNS / a.run
    q = qw.HaikuQueue('memoir')
    instructions = mb.prompt(a.rubric)
    pending, results = {}, {}
    for v in a.variants.split(','):
        for path in sorted((run_dir / v / 'books').glob('*.json')):
            k = path.stem
            if a.books and k not in a.books.split(','):
                continue
            book = mb.load(path)
            plan = mb.load(run_dir / 'plans' / (k + '.json'))
            for ci, c in enumerate(book['chapters']):
                if not c['sections']:
                    continue
                rid, hit = q.submit(instructions, request_input(book, plan['chapters'][ci], c), OUTPUT_NOTE, {'type': 'memoir'},
                                    meta={'run': a.run})
                key = (v, k, ci)
                if hit:
                    results[key] = hit['output']
                else:
                    pending[key] = rid
    print(json.dumps({'submitted': len(pending), 'cached': len(results)}), flush=True)
    deadline = time.time() + a.wait
    while pending and time.time() < deadline:
        for key, rid in list(pending.items()):
            r = q.poll(rid)
            if r:
                results[key] = r['output']
                del pending[key]
        if pending:
            time.sleep(10)
    summary, rows = {}, []
    for v in a.variants.split(','):
        books = {}
        for path in sorted((run_dir / v / 'books').glob('*.json')):
            k = path.stem
            if a.books and k not in a.books.split(','):
                continue
            book = mb.load(path)
            sc = [results[(v, k, ci)] for ci in range(len(book['chapters'])) if (v, k, ci) in results]
            mtr = book['metrics']
            if mtr.get('copy_ratio') is None:  # books built before the metric existed
                mtr['copy_ratio'] = mb.copy_ratio([x['t'] for c in book['chapters'] for s in c['sections'] for p in s['paragraphs']
                                                   for x in p['sentences'] if not x['add']],
                                                  '\n'.join(u['text'] for u in book['units'].values()))
            books[k] = {'name': book['person']['name'], 'chapters_scored': len(sc), 'chapters': len(book['chapters']),
                        **{d: round(mean(s[d] for s in sc), 2) if sc else None for d in DIMS},
                        'fabrication': sum(len(s['fabrication']) for s in sc),
                        'chars': mtr['chars'], 'elder_chars': mtr['elder_chars'], 'ratio_to_elder': mtr['ratio_to_elder'], 'copy_ratio': mtr['copy_ratio'],
                        'added_ratio': mtr['added_ratio'], 'unsupported_tokens': mtr['unsupported_tokens'],
                        'unit_use': mtr['unit_use'], 'mean_abs_deviation': mtr['mean_abs_deviation'],
                        'fallback_paragraphs': mtr['fallback_paragraphs'],
                        'notes': [s.get('note') for s in sc], 'fabrication_list': [f for s in sc for f in s['fabrication']]}
        allc = [results[key] for key in results if key[0] == v]
        summary[v] = {'books': books, 'chapters_scored': len(allc),
                      **{d: round(mean(s[d] for s in allc), 2) if allc else None for d in DIMS},
                      **{d + '_ge4': round(sum(1 for s in allc if s[d] >= 4) / len(allc), 2) if allc else None for d in DIMS},
                      'fabrication_per_chapter': round(sum(len(s['fabrication']) for s in allc) / len(allc), 2) if allc else None,
                      'code': {x: round(mean(b[x] for b in books.values() if b[x] is not None), 3) if books else None
                               for x in ('ratio_to_elder', 'copy_ratio', 'added_ratio', 'unsupported_tokens', 'unit_use', 'mean_abs_deviation',
                                         'fallback_paragraphs')}}
    out = {'run': a.run, 'rubric': a.rubric, 'pending': len(pending), 'summary': summary}
    mb.save(run_dir / ('scores%s.json' % ('-' + a.label if a.label else '')), out)
    lines = ['| 版本 | 章数 | 忠实 | 细腻抒情 | 连贯 | 口吻 | 结构篇幅 | 编造/章 | 成书/原话 | 照搬率 | 加写句占比 | 无来源数字地名人名 | 单元利用率 | 预算偏差 | 退回段 |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for v, s in summary.items():
        c = s['code']
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            v, s['chapters_scored'], s['faithful'], s['lyrical'], s['coherent'], s['voice'], s['structure'],
            s['fabrication_per_chapter'], c['ratio_to_elder'], c['copy_ratio'], c['added_ratio'], c['unsupported_tokens'], c['unit_use'],
            c['mean_abs_deviation'], c['fallback_paragraphs']))
    (run_dir / ('scores%s.md' % ('-' + a.label if a.label else ''))).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    print(json.dumps({'pending': len(pending), 'haiku_sent': q.sent, 'haiku_cached': q.cached}))


if __name__ == '__main__':
    main()
