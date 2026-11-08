"""Markdown + review HTML of the v4 sample chapters (BRIEF13).

HTML: sentences that describe someone else's thoughts or feelings are highlighted (for the elder to confirm); every
section can be expanded to the elder's own words it was written from; each chapter ends with the new-event check
(what was flagged, how it was rewritten or deleted) and the length / copy-rate numbers.
"""
from __future__ import annotations

import html
import json

import mb
import v4

CH_NO = {'skeleton': '序章', 'childhood': '第一章', 'growth': '第二章', 'work': '第三章', 'family': '第四章',
         'later_life': '第五章', 'reflection': '第六章'}
DIM_CN = {'literary': '细腻与文学性', 'human': '像真人写的自传', 'rewritten': '不照搬原话', 'coherent': '连贯与节奏'}

CSS = """
:root{--bg:#faf7f2;--fg:#2b2622;--muted:#7a6f66;--card:#fffdf9;--line:#e6ddd2;--mind:#fde7b0;--mind-fg:#5a3d00;--accent:#8a4b2a;--del:#b3412e;--ok:#3d7a4a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1d1a17;--fg:#ebe4dc;--muted:#a59a8f;--card:#26221e;--line:#3a332d;--mind:#5b4513;--mind-fg:#ffe7b0;--accent:#e0a37f;--del:#ef8a77;--ok:#8fcf9c}}
:root[data-theme="dark"]{--bg:#1d1a17;--fg:#ebe4dc;--muted:#a59a8f;--card:#26221e;--line:#3a332d;--mind:#5b4513;--mind-fg:#ffe7b0;--accent:#e0a37f;--del:#ef8a77;--ok:#8fcf9c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"Noto Serif SC","Songti SC","SimSun",serif;line-height:1.95;font-size:17px}
main{max-width:760px;margin:0 auto;padding:32px 16px 80px}
h1{font-size:28px;margin:0 0 6px;letter-spacing:.06em}
h2{font-size:23px;margin:56px 0 4px;letter-spacing:.05em;color:var(--accent)}
h3{font-size:18px;margin:34px 0 8px}
.sub{color:var(--muted);font-size:14px;margin:0 0 18px}
p.t{text-indent:2em;margin:0 0 14px}
mark.mind{background:var(--mind);color:var(--mind-fg);padding:0 2px;border-radius:3px}
.legend{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;font-size:14px;color:var(--muted);line-height:1.7;font-family:system-ui,sans-serif}
details{margin:6px 0 10px;font-family:system-ui,sans-serif;font-size:14px}
details summary{cursor:pointer;color:var(--muted)}
details .src{background:var(--card);border-left:3px solid var(--line);padding:8px 12px;margin:8px 0;line-height:1.75}
details .q{color:var(--muted);font-size:13px}
.report{margin-top:28px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;font-family:system-ui,sans-serif;font-size:14px;line-height:1.7}
.report h4{margin:6px 0 8px;font-size:15px}
.report table{border-collapse:collapse;width:100%;margin:6px 0 12px;display:block;overflow-x:auto}
.report td,.report th{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
.report th{color:var(--muted);font-weight:600;white-space:nowrap}
.old{color:var(--del);text-decoration:line-through}
.new{color:var(--ok)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:0 5px;font-size:12px;color:var(--muted);white-space:nowrap}
"""


def esc(s):
    return html.escape(s or '')


def section_sources(plan, ch, s):
    pch = plan['chapters'][v4.chapter_index(plan, ch['module'])]
    ids = s['stories'] or []
    rows = [(m, t) for m in v4.stories_of(pch) if m['id'] in ids for t in m['tellings']]
    return rows


def issue_rows(ch):
    rows = []
    for s in ch['sections']:
        for p in s['paragraphs']:
            for x in p:
                for h in x.get('history') or []:
                    rows.append((x['n'], h))
    return sorted(rows, key=lambda r: (r[1]['round'], r[0]))


def main(a=None):
    plan, book3 = v4.load_material()
    tag = (a.tag if a else '') or ''
    fin = mb.load(v4.RUN / ('book%s-final.json' % tag))
    scores = mb.load(v4.RUN / ('scores%s.json' % tag)) if (v4.RUN / ('scores%s.json' % tag)).exists() else {}
    md, hb = [], []
    md += ['# 黄小荣的回忆录（样章 · v4 整体文学重写）', '',
           '> 这是两章样章，供审读写法：第一章“家乡与童年”、第三章“工作与劳动”。素材是黄小荣公开访谈原话（约 1 万字）。',
           '> 写法：每个故事整体重写成第一人称的文学叙述，环境、心理、动作细节可以放开写；唯一的硬约束是不新增原话里没有的事件、经过、结局、人物，'
           '不改年份地点数字人名，不替别人编台词。标 〔他人心理·待确认〕 的句子写了别人心里怎么想，请老人确认。', '']
    hb += ['<h1>黄小荣的回忆录</h1><p class="sub">样章 · v4 整体文学重写 · 第一章、第三章</p>',
           '<div class="legend">这是两章样章，供审读写法。素材是黄小荣公开访谈原话（约 1 万字）。每个故事整体重写成第一人称的文学叙述，环境、心理、动作细节放开写；'
           '唯一的硬约束是<b>不新增原话里没有的事件、经过、结局、人物</b>，不改年份地点数字人名，不替别人编台词。<br>'
           '<mark class="mind">黄色高亮</mark> 的句子写了“我”以外的人心里怎么想，请老人确认。每节下面可以展开看这一节依据的原话；每章末尾是新增事件检查结果和字数、照搬率。</div>']
    for ch in fin['chapters']:
        m = ch['metrics']
        no = CH_NO[ch['module']]
        md += ['## %s　%s' % (no, ch['title']), '*%s*' % mb.MODULE_NAME[ch['module']], '']
        hb.append('<h2>%s　%s</h2><p class="sub">%s</p>' % (no, esc(ch['title']), mb.MODULE_NAME[ch['module']]))
        for s in ch['sections']:
            if s['title']:
                md += ['### ' + s['title'], '']
                hb.append('<h3>%s</h3>' % esc(s['title']))
            for p in s['paragraphs']:
                xs = [x for x in p if x['t']]
                if not xs:
                    continue
                md.append(''.join(x['t'] + ('〔他人心理·待确认〕' if x['mind'] else '') for x in xs))
                md.append('')
                hb.append('<p class="t">%s</p>' % ''.join(
                    '<mark class="mind" title="写了别人的心理，请老人确认">%s</mark>' % esc(x['t']) if x['mind'] else esc(x['t']) for x in xs))
            src = section_sources(plan, ch, s)
            if src:
                md += ['<details><summary>本节依据的原话（%s）</summary>' % '、'.join(t['id'] for _, t in src), '']
                md += ['> **%s 问：%s**  \n> %s' % (t['id'], t['asked'], v4.redact(t['text'])) for _, t in src]
                md += ['', '</details>', '']
                hb.append('<details><summary>本节依据的原话（%s）</summary>%s</details>' % (
                    '、'.join(t['id'] for _, t in src),
                    ''.join('<div class="src"><div class="q">%s · 问：%s</div>%s</div>' % (t['id'], esc(t['asked']), esc(v4.redact(t['text'])))
                            for _, t in src)))
        # ---- end-of-chapter report
        rows = issue_rows(ch)
        checks = ch.get('checks') or []
        sc = scores.get('v4-' + ch['module']) or {}
        sc3 = scores.get('v3-' + ch['module']) or {}
        md += ['### 本章检查与统计', '']
        md.append('- 字数：%d 字（汉字计；目标 %d，上限 %d）；这部分原话 %d 字，成书 / 原话 = %.2f' % (
            m['chars'], m['target'], m['max'], m['elder_chars'], m['ratio_to_elder']))
        md.append('- 照搬率（与原话重合的 8 字以上连续片段占全文）：%.0f%%（引语以外 %.0f%%；12 字以上 %.0f%%）%s' % (
            100 * m['copy8'], 100 * m['copy8_outside_quotes'], 100 * m['copy12'],
            '；v3 同章 %.0f%%' % (100 * sc3['copy8']) if sc3.get('copy8') is not None else ''))
        md.append('- 新增事件检查：%s 轮；各轮发现 %s 处；改写 %d 句、删除 %d 句；最后一轮剩余 %d 处' % (
            len(checks), ' / '.join(str(x) for x in m['new_events_by_round']), m['rewritten_sents'], m['deleted_sents'], m['new_events_left']))
        md.append('- 标出的“他人心理”句：%d 句' % m['others_mind'])
        if sc:
            md.append('- 量表（Haiku rubric-v4）：' + '，'.join('%s %s' % (DIM_CN[d], sc.get(d)) for d in v4.RUBRIC_DIMS)
                      + '；量表列出的新增事件 %d 处' % len(sc.get('new_events') or [])
                      + ('（v3 同章：' + '，'.join('%s %s' % (DIM_CN[d], sc3.get(d)) for d in v4.RUBRIC_DIMS) + '）' if sc3 else ''))
        md.append('')
        if rows:
            md += ['| 轮 | 句 | 类型 | 原句 | 处理 |', '|---|---|---|---|---|']
            for n, h in rows:
                md.append('| %d | %d | %s | %s | %s |' % (h['round'], n, h.get('type') or '', h['old'].replace('|', '｜'),
                                                         ('改写为：' + h['new'].replace('|', '｜')) if h['action'] == 'rewritten' else '删除'))
            md.append('')
        hb.append('<div class="report"><h4>本章检查与统计</h4>')
        hb.append('<p>字数 <b>%d</b>（汉字计；目标 %d，上限 %d）· 这部分原话 %d 字 · 成书/原话 %.2f<br>' % (
            m['chars'], m['target'], m['max'], m['elder_chars'], m['ratio_to_elder']))
        hb.append('照搬率（8 字以上与原话相同的连续片段占全文）<b>%.0f%%</b>（引语以外 %.0f%%，12 字以上 %.0f%%）%s<br>' % (
            100 * m['copy8'], 100 * m['copy8_outside_quotes'], 100 * m['copy12'],
            '；v3 同章 %.0f%%' % (100 * sc3['copy8']) if sc3.get('copy8') is not None else ''))
        hb.append('新增事件检查 %d 轮，各轮发现 %s 处；改写 %d 句、删除 %d 句；最后剩余 <b>%d</b> 处 · 标出的“他人心理”句 <b>%d</b> 句</p>' % (
            len(checks), ' / '.join(str(x) for x in m['new_events_by_round']), m['rewritten_sents'], m['deleted_sents'], m['new_events_left'], m['others_mind']))
        if sc:
            hb.append('<p>量表（Haiku rubric-v4，1–5）：%s；量表列出的新增事件 %d 处%s</p>' % (
                ' · '.join('%s <b>%s</b>' % (DIM_CN[d], sc.get(d)) for d in v4.RUBRIC_DIMS), len(sc.get('new_events') or []),
                ('<br>v3 同章：' + ' · '.join('%s %s' % (DIM_CN[d], sc3.get(d)) for d in v4.RUBRIC_DIMS)) if sc3 else ''))
            for e in sc.get('new_events') or []:
                hb.append('<p class="q">量表指出：“%s”——%s</p>' % (esc(e.get('quote')), esc(e.get('why'))))
        if rows:
            hb.append('<table><tr><th>轮</th><th>类型</th><th>原句与问题</th><th>处理</th></tr>')
            for n, h in rows:
                hb.append('<tr><td>%d</td><td><span class="tag">%s</span></td><td><span class="old">%s</span><br><span class="q">%s</span></td><td>%s</td></tr>' % (
                    h['round'], esc(h.get('type')), esc(h['old']), esc(h.get('why')),
                    '<span class="new">%s</span>' % esc(h['new']) if h['action'] == 'rewritten' else '删除'))
            hb.append('</table>')
        hb.append('</div>')
    priv = [p['quote'] for p in plan.get('private', [])] + v4.PRIVATE_EXTRA
    md += ['## 没有写进样章的内容（私事，待老人决定）', ''] + ['- ' + p for p in priv] + ['']
    hb.append('<h2>没有写进样章的内容</h2><p class="sub">私事，待老人决定</p><ul>%s</ul>' % ''.join('<li>%s</li>' % esc(p) for p in priv))
    v4.OUT.mkdir(parents=True, exist_ok=True)
    name = '回忆录样章_黄小荣_v4%s' % tag
    (v4.OUT / (name + '.md')).write_text('\n'.join(md), encoding='utf-8')
    page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>回忆录样章 v4</title><style>%s</style></head><body><main>%s</main></body></html>' % (CSS, '\n'.join(hb)))
    (v4.OUT / (name + '.html')).write_text(page, encoding='utf-8')
    print(json.dumps({'md': str(v4.OUT / (name + '.md')), 'html': str(v4.OUT / (name + '.html'))}, ensure_ascii=False))
