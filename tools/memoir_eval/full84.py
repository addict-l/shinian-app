#!/usr/bin/env python3
"""v1.1 full-interview test: statistics of a complete simulated interview (simulate/run_full.py) and the interview
record page (question asked, the elder's own words, follow-up / detail-question marks) for reading the book
against what was said.

  python3 tools/memoir_eval/full84.py stats  mb2-full84 N-6733a23cd1 [--handoff PATH] [--book PATH]
  python3 tools/memoir_eval/full84.py html   mb2-full84 N-6733a23cd1 OUT.html
  python3 tools/memoir_eval/full84.py report mb2-full84 N-6733a23cd1 OUT.md [--handoff PATH] [--book PATH] [--json OUT.json]
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter, defaultdict

import mb

DEPTH = {'story': '故事题', 'fact': '事实题', 'reflection': '感悟题'}
KIND = {'entry': '问', 'followup': '追问', 'deepen': '深挖', 'draft': '草稿', 'supplement': '补充', 'review': '核对',
        'transition': '转题', 'pause': '暂停', 'resume': '继续'}


def load(run, pid):
    return mb.load(mb.RUNS / run / 'sessions' / ('%s.json' % pid))


def outcome(rec):
    """answered / unknown (记不清) / declined (不愿讲 or skipped)."""
    if rec['status'] == 'skipped' or rec.get('close_reason') in ('declined', 'deferred', 'skip_control'):
        return 'declined'
    eff = ((rec.get('final') or {}).get('effective') or {})
    known = any(v in ('known', 'none') for v in eff.values())
    if not known and (rec.get('close_reason') == 'unknown' or any(v == 'unknown' for v in eff.values())):
        return 'unknown'
    if not rec['sources']:
        return 'unknown'
    return 'answered' if known or rec.get('deepen_sources') else 'unknown' if rec.get('close_reason') == 'unknown' else 'answered'


def stats(run, pid, handoff=None, book=None):
    sess = load(run, pid)
    cat = mb.catalog()
    recs = [r for r in sess['questions'] if not r.get('error')]
    out = {'run': run, 'person': sess['name'], 'questions': len(sess['questions']), 'errors': len(sess['questions']) - len(recs)}
    oc = Counter(outcome(r) for r in recs)
    out['outcome'] = dict(oc)
    by_mod, by_depth, by_kind = Counter(), Counter(), Counter()
    q_mod, q_depth = Counter(), Counter()
    all_elder = 0
    deepen = followups = 0
    behaviours, models = Counter(), Counter()
    by_model = defaultdict(lambda: defaultdict(list))  # model -> behaviour -> answer lengths (comparability)
    for r in recs:
        q = cat[r['qid']]
        mod, depth = q['module'], q['depth']
        q_mod[mod] += 1
        q_depth[depth] += 1
        for s in r['sources']:
            n = mb.han_len(s['text'])
            by_mod[mod] += n
            by_depth[depth] += n
            by_kind['deepen_answer' if s.get('deepen_answer') else 'judged'] += n
        for m in r['messages']:
            if m['role'] == 'elder' and not m.get('scripted'):
                all_elder += mb.han_len(m['text'])
                behaviours[m.get('behavior')] += 1
                model = ((m.get('calls') or [{}])[0]).get('model') or '?'
                models[model] += 1
                by_model[model][m.get('behavior')].append(mb.han_len(m['text']))
        deepen += (r.get('deepen') or {}).get('asked', 0)
        followups += r.get('followups') or 0
    total = sum(by_mod.values())
    out.update({'source_chars': total, 'all_elder_chars': all_elder, 'followups': followups, 'deepen_questions': deepen,
                'elder_answers': sum(behaviours.values()), 'behaviours': dict(behaviours), 'persona_models': dict(models),
                'persona_mean_chars': {mo: {b: [len(v), round(sum(v) / len(v), 1)] for b, v in sorted(bs.items(), key=str)}
                                       for mo, bs in by_model.items()},
                'by_module': {mb.MODULE_NAME[m]: {'questions': q_mod[m], 'chars': by_mod[m], 'per_question': round(by_mod[m] / max(1, q_mod[m]), 1)}
                              for m, _, _ in mb.MODULES},
                'by_depth': {DEPTH[d]: {'questions': q_depth[d], 'chars': by_depth[d], 'per_question': round(by_depth[d] / max(1, q_depth[d]), 1)}
                             for d in DEPTH},
                'by_kind': dict(by_kind),
                'story_deepen': {'story_questions': q_depth['story'],
                                 'deepened': sum(1 for r in recs if (r.get('deepen') or {}).get('asked'))}})
    if handoff:
        h = mb.load(handoff)
        drafts = [q.get('draft') for q in h['questions'] if q.get('draft')]
        out['draft_chars'] = sum(mb.han_len(p['text']) for d in drafts for p in d['paragraphs'])
        out['drafts'] = len(drafts)
        out['drafts_fallback'] = sum(1 for d in drafts if d.get('generated_by') == 'verbatim_fallback')
    # projection at the v3b book ratio (standard edition 0.7 x elder chars; v3b books came out at 0.82-0.86 x)
    out['projection'] = {'standard_0.7': int(total * 0.7), 'v3b_observed_0.82-0.86': [int(total * 0.82), int(total * 0.86)],
                         'full_1.0': total, 'target_40000_needs_elder_chars': [int(40000 / 0.86), int(40000 / 0.7)],
                         'target_50000_needs_elder_chars': [int(50000 / 0.86), int(50000 / 0.7)]}
    # gap to the standard edition target (4-5 万字) at the planned 0.7 ratio and at the v3b observed 0.86
    out['gap'] = {'%d' % t: {'at_0.7': t - int(total * 0.7), 'at_0.86': t - int(total * 0.86),
                             'elder_chars_missing_at_0.7': max(0, int(t / 0.7) - total)} for t in (40000, 50000)}
    if book:
        b = mb.load(book)
        out['book'] = {k: b['metrics'].get(k) for k in ('chars', 'elder_chars', 'ratio_to_elder', 'added_ratio', 'copy_ratio')}
        out['book']['chapters'] = [(c['title'], '/'.join(c['modules']), c['chars']) for c in b['metrics'].get('chapters') or []]
        out['book']['pictures'] = (b['metrics'].get('pipeline') or {}).get('pictures')
        ratio = b['metrics'].get('ratio_to_elder') or 0
        out['gap']['book'] = {'%d' % t: t - (b['metrics'].get('chars') or 0) for t in (40000, 50000)}
        out['gap']['elder_chars_needed_at_book_ratio'] = {'%d' % t: int(t / ratio) if ratio else None for t in (40000, 50000)}
    return out


def report(st):
    """Markdown statistics page (Chinese) of stats()."""
    oc = st['outcome']
    lines = ['# 完整采访统计：%s（%s）' % (st['person'], st['run']), '',
             '- 题数 %d（出错 %d）：作答 %d、记不清 %d、不愿讲/跳过 %d' % (
                 st['questions'], st['errors'], oc.get('answered', 0), oc.get('unknown', 0), oc.get('declined', 0)),
             '- 老人回答 %d 次（行为抽样 %s）；扮演老人的模型：%s' % (
                 st['elder_answers'], '、'.join('%s %d' % kv for kv in sorted(st['behaviours'].items(), key=str)),
                 '、'.join('%s %d' % kv for kv in st['persona_models'].items())),
             '- 追问 %d 次；深挖 %d 次（%d 道故事题里 %d 道有深挖）' % (
                 st['followups'], st['deepen_questions'], st['story_deepen']['story_questions'], st['story_deepen']['deepened']),
             '- 记入回忆的老人原话 **%d 字**（其中深挖回答 %d 字）；老人所有发言 %d 字' % (
                 st['source_chars'], st['by_kind'].get('deepen_answer', 0), st['all_elder_chars']),
             '- 每次回答平均字数（按扮演模型、行为；[次数, 平均字]）：' + '；'.join(
                 '%s：%s' % (mo, '、'.join('%s %s' % (b, v) for b, v in bs.items())) for mo, bs in st['persona_mean_chars'].items()), '']
    if 'draft_chars' in st:
        lines += ['- 如实草稿 %d 篇 %d 字（逐字兜底 %d 篇）' % (st['drafts'], st['draft_chars'], st['drafts_fallback']), '']
    lines += ['## 按模块', '', '| 模块 | 题数 | 原话字数 | 每题 |', '|---|---|---|---|']
    lines += ['| %s | %d | %d | %.0f |' % (k, v['questions'], v['chars'], v['per_question']) for k, v in st['by_module'].items()]
    lines += ['', '## 按题型', '', '| 题型 | 题数 | 原话字数 | 每题 |', '|---|---|---|---|']
    lines += ['| %s | %d | %d | %.0f |' % (k, v['questions'], v['chars'], v['per_question']) for k, v in st['by_depth'].items()]
    pj, gap = st['projection'], st['gap']
    lines += ['', '## 能写多长、离标准本 4–5 万字差多少', '',
              '- 按标准本比例 0.7：约 %d 字；按 v3b 实际成书比例 0.82–0.86：约 %d–%d 字' % (
                  pj['standard_0.7'], pj['v3b_observed_0.82-0.86'][0], pj['v3b_observed_0.82-0.86'][1]),
              '- 离 4 万字：差 %d 字（0.7）/ %d 字（0.86）；离 5 万字：差 %d / %d 字' % (
                  gap['40000']['at_0.7'], gap['40000']['at_0.86'], gap['50000']['at_0.7'], gap['50000']['at_0.86']),
              '- 要写到 4 万 / 5 万字，按 0.7 需要老人原话约 %d / %d 字（还缺 %d / %d 字）' % (
                  int(40000 / 0.7), int(50000 / 0.7), gap['40000']['elder_chars_missing_at_0.7'], gap['50000']['elder_chars_missing_at_0.7'])]
    if 'book' in st:
        b = st['book']
        lines += ['- 实际成书 **%d 字**（成书/原话 %.2f，加写占比 %s，照搬率 %s，标“画面”的加写句 %s 处）；离 4 万字差 %d，离 5 万字差 %d' % (
            b['chars'] or 0, b['ratio_to_elder'] or 0, b.get('added_ratio'), b.get('copy_ratio'), b.get('pictures'),
            gap['book']['40000'], gap['book']['50000']), '', '| 章 | 模块 | 字数 |', '|---|---|---|']
        lines += ['| %s | %s | %d |' % c for c in b['chapters']]
    lines += ['', '注：原话字数按汉字计；模拟老人每次回答的长短由行为抽样决定（normal 约 80–250 字，long 变体放宽），'
              '所以总字数受模拟器设定的天花板限制，真实老人可能更长也可能更短。', '']
    return '\n'.join(lines)


def players(st):
    names = {'claude-haiku-subagent': 'Claude Haiku'}
    m = st.get('persona_models') or {}
    if len(m) <= 1:
        return ''.join(names.get(k, k) for k in m) or 'Claude Haiku'
    return '、'.join('%s %d 次' % (names.get(k, k), v) for k, v in m.items()) + '回答，'


def to_html(run, pid):
    sess = load(run, pid)
    cat = mb.catalog()
    e = html.escape
    st = stats(run, pid)
    css = '''
:root{--bg:#f7f5f0;--ink:#26221e;--muted:#786d62;--card:#fff;--line:#e2dacd;--sys:#eef1f5;--eld:#fff8ec;--deep:#c0602b;--fu:#3f6fa8;--warn:#a33}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1c1a18;--ink:#ebe5dc;--muted:#a4998d;--card:#25221f;--line:#3a352f;--sys:#252b33;--eld:#2e281f;--deep:#e08a55;--fu:#7aa3d6;--warn:#e07070}}
:root[data-theme="dark"]{--bg:#1c1a18;--ink:#ebe5dc;--muted:#a4998d;--card:#25221f;--line:#3a352f;--sys:#252b33;--eld:#2e281f;--deep:#e08a55;--fu:#7aa3d6;--warn:#e07070}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 "PingFang SC","Noto Sans SC",sans-serif}
main{max-width:820px;margin:0 auto;padding:28px 16px 80px}h1{font-size:26px;margin:4px 0}h2{font-size:20px;margin:44px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.note{color:var(--muted);font-size:14px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.q{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:14px 0}
.qh{font-size:13px;color:var(--muted);margin-bottom:6px}.qh b{color:var(--ink);font-size:15px}
.badge{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 8px;margin-left:6px}
.m{border-radius:8px;padding:6px 10px;margin:6px 0;overflow-wrap:anywhere}.sys{background:var(--sys)}.eld{background:var(--eld)}
.k{font-size:12px;color:var(--muted);margin-right:6px}.k.deepen{color:var(--deep);font-weight:600}.k.followup{color:var(--fu);font-weight:600}
.tag{font-size:12px;color:var(--deep);margin-left:6px}.n{font-size:12px;color:var(--muted);margin-left:6px}.dim{opacity:.6}
table{border-collapse:collapse;font-size:14px;margin:8px 0}td,th{border:1px solid var(--line);padding:3px 8px;text-align:right}th:first-child,td:first-child{text-align:left}
.toc{font-size:14px}.toc a{color:inherit;margin-right:10px}
'''
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>完整采访记录</title><style>%s</style></head><body><main>' % css,
           '<h1>完整采访记录：%s</h1>' % e(sess['name']),
           '<p class="note">测试记录：模拟老人（%s按公开访谈改编的资料扮演）接受完整采访，采访方是生产版 V6 流程（开篇骨架 11 题 + 六个模块 72 题，共 %d 题；'
           'DeepSeek v4-pro，关思考）。<b>老人原话</b>浅黄底，<span style="color:var(--fu)">追问</span>、<span style="color:var(--deep)">深挖</span>在问句前标出；'
           '“深挖回答”是回答深挖问题的原话（进草稿，不再判定）；灰色的“没有了”类回答只用于结束补充，不进回忆。'
           '每题末尾的数字是这一题记入回忆的原话字数。运行 %s。</p>' % (e(players(st)), len(sess['questions']), e(run))]
    out.append('<table><tr><th>模块</th><th>题数</th><th>原话字数</th><th>每题</th></tr>' + ''.join(
        '<tr><td>%s</td><td>%d</td><td>%d</td><td>%.0f</td></tr>' % (e(k), v['questions'], v['chars'], v['per_question'])
        for k, v in st['by_module'].items()) + '<tr><td>合计</td><td>%d</td><td>%d</td><td>%.0f</td></tr></table>' % (
        len(sess['questions']), st['source_chars'], st['source_chars'] / max(1, len(sess['questions']))))
    out.append('<p class="note">作答 %d 题、记不清 %d 题、不愿讲/跳过 %d 题；追问 %d 次，深挖 %d 次（%d 道故事题里 %d 道有深挖）。</p>' % (
        st['outcome'].get('answered', 0), st['outcome'].get('unknown', 0), st['outcome'].get('declined', 0), st['followups'],
        st['deepen_questions'], st['story_deepen']['story_questions'], st['story_deepen']['deepened']))
    mods = defaultdict(list)
    for r in sess['questions']:
        mods[cat[r['qid']]['module']].append(r)
    out.append('<p class="toc">' + ''.join('<a href="#%s">%s</a>' % (m, e(mb.MODULE_NAME[m])) for m, _, _ in mb.MODULES if mods[m]) + '</p>')
    status_name = {'answered': '作答', 'unknown': '记不清', 'declined': '不愿讲/跳过'}
    for m, _, _ in mb.MODULES:
        if not mods[m]:
            continue
        out.append('<h2 id="%s">%s</h2>' % (m, e(mb.MODULE_NAME[m])))
        for r in mods[m]:
            q = cat[r['qid']]
            src_ids = {s['id'] for s in r['sources']}
            deep_ids = {s['id'] for s in r['sources'] if s.get('deepen_answer')}
            chars = sum(mb.han_len(s['text']) for s in r['sources'])
            out.append('<div class="q"><div class="qh"><b>%s</b> %s<span class="badge">%s</span><span class="badge">%s</span><span class="n">原话 %d 字</span></div>' % (
                e(r['qid']), e(q['title']), DEPTH[q['depth']], status_name[outcome(r)], chars))
            prev_kind = None
            for msg in r['messages']:
                if msg['role'] == 'system':
                    kind = msg.get('kind')
                    prev_kind = kind
                    cls = kind if kind in ('deepen', 'followup') else ''
                    out.append('<div class="m sys"><span class="k %s">%s</span>%s</div>' % (cls, KIND.get(kind, kind), e(msg['text'])))
                else:
                    if msg.get('scripted'):
                        out.append('<div class="m eld dim"><span class="k">（点“继续”）</span>%s</div>' % e(msg['text']))
                        continue
                    tag = '深挖回答' if msg['id'] in deep_ids else ('补充' if prev_kind in ('draft', 'supplement') and msg['id'] in src_ids else '')
                    dim = '' if msg['id'] in src_ids else ' dim'
                    out.append('<div class="m eld%s"><span class="k">老人</span>%s%s</div>' % (
                        dim, e(msg['text']), '<span class="tag">%s</span>' % tag if tag else ''))
            out.append('</div>')
    out.append('</main></body></html>')
    return '\n'.join(out)


if __name__ == '__main__':
    cmd, run, pid = sys.argv[1:4]
    if cmd == 'stats':
        args = sys.argv[4:]
        kw = {}
        for flag in ('--handoff', '--book'):
            if flag in args:
                kw[flag[2:]] = args[args.index(flag) + 1]
        print(json.dumps(stats(run, pid, **kw), ensure_ascii=False, indent=1))
    elif cmd == 'html':
        open(sys.argv[4], 'w', encoding='utf-8').write(to_html(run, pid))
    elif cmd == 'report':
        args = sys.argv[5:]
        kw = {}
        for flag in ('--handoff', '--book'):
            if flag in args:
                kw[flag[2:]] = args[args.index(flag) + 1]
        st = stats(run, pid, **kw)
        open(sys.argv[4], 'w', encoding='utf-8').write(report(st))
        if '--json' in args:
            mb.save(args[args.index('--json') + 1], st)
