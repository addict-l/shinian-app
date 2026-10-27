"""Render a book JSON (book.py) to Markdown and a review HTML page.

Markdown: added sentences in italics with a 〔加写·类型〕 tag; paragraphs that fell back to the confirmed
grounded draft carry 〔如实草稿〕; each chapter ends with its list of added sentences to confirm.
HTML: the same text; added sentences highlighted with their type, fallback paragraphs tinted, and every
paragraph expandable to show the elder's own words it cites (question asked + full answer).
"""
from __future__ import annotations

import html
from pathlib import Path

import mb

NOTE = {'rich': '测试样书，素材来自公开访谈（模拟“老人确认过的回忆”）', 'thin': '测试样书，素材来自模拟访谈里模拟老人说的话'}


def chapter_label(i, c, has_prologue):
    if c['modules'][0] == 'skeleton':
        return '序章'
    n = i if has_prologue else i + 1
    return '第%s章' % '一二三四五六七八九十'[n - 1] if n <= 10 else '第%d章' % n


def to_markdown(book):
    lines = ['# %s的回忆录' % book['person']['name'], '', '> %s。版本：%s（%s）。' % (NOTE[book['material']['kind']], book['variant'], book['edition']),
             '> 斜体加〔加写〕的句子是写作者加的（感受、回望、过渡、意象、呼应、收束），需老人确认；〔如实草稿〕段落是核对未通过后退回的如实草稿。', '']
    has_pro = book['chapters'] and book['chapters'][0]['modules'][0] == 'skeleton'
    for i, c in enumerate(book['chapters']):
        lines += ['## %s　%s' % (chapter_label(i, c, has_pro), c['title']), '*%s*' % ' · '.join(mb.MODULE_NAME[m] for m in c['modules']), '']
        adds = []
        for s in c['sections']:
            if len(c['sections']) > 1 and s['title']:
                lines += ['### %s' % s['title'], '']
            for p in s['paragraphs']:
                out = []
                for x in p['sentences']:
                    if x['add']:
                        out.append('*%s*〔加写·%s〕' % (x['t'], x['add']))
                        adds.append('（%s）%s' % (x['add'], x['t']))
                    else:
                        out.append(x['t'])
                lines += [('〔如实草稿〕' if p.get('fallback') else '') + ''.join(out), '']
        if adds:
            lines += ['> 本章加写句（待老人确认）：', ''] + ['> - %s' % a for a in adds] + ['']
    nw = book['not_written']
    if nw['private'] or nw['declined']:
        lines += ['## 没有写进书的内容（待老人决定）', '']
        for p in nw['private']:
            lines.append('- 私事（%s）：%s' % (p.get('kind'), p['quote']))
        for d in nw['declined']:
            lines.append('- 老人说不想讲：%s' % d.get('quote'))
        lines.append('')
    return '\n'.join(lines)


CSS = '''
:root{--bg:#faf7f1;--ink:#2b2622;--muted:#7a6f64;--add:#fbe7c6;--addline:#d9963a;--fb:#e6eef7;--card:#fff;--line:#e4dccf}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1d1b19;--ink:#ece6dd;--muted:#a89c8f;--add:#4a3a20;--addline:#e0a24a;--fb:#24303d;--card:#262320;--line:#3a352f}}
:root[data-theme="dark"]{--bg:#1d1b19;--ink:#ece6dd;--muted:#a89c8f;--add:#4a3a20;--addline:#e0a24a;--fb:#24303d;--card:#262320;--line:#3a352f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.95 "Songti SC","Noto Serif SC","Source Han Serif SC",serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 80px}h1{font-size:30px;margin:8px 0 4px;letter-spacing:.06em}
.note{color:var(--muted);font-size:14px;border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:var(--card)}
h2{font-size:23px;margin:56px 0 0;letter-spacing:.05em}.mod{color:var(--muted);font-size:14px;margin:2px 0 18px}
h3{font-size:18px;margin:30px 0 8px;color:var(--muted);font-weight:600}
.p{margin:0 0 6px;text-indent:2em}.add{background:var(--add);border-bottom:2px solid var(--addline);border-radius:3px;padding:0 2px}
.tag{font-size:11px;color:var(--addline);margin-left:2px;vertical-align:super;text-indent:0}
.fb{background:var(--fb);border-radius:6px;padding:4px 8px}.fbt{font-size:12px;color:var(--muted)}
details{margin:0 0 14px 2em;font-size:13px;color:var(--muted)}summary{cursor:pointer}
.src{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:6px 0;line-height:1.7}
.src b{color:var(--ink)}.legend span{display:inline-block;margin-right:12px}
.toc a{color:inherit}.adds{font-size:14px;color:var(--muted);border-left:3px solid var(--addline);padding-left:10px;margin:18px 0}
.metrics{font:13px/1.6 ui-monospace,Menlo,monospace;color:var(--muted);white-space:pre-wrap}
'''


def to_html(book):
    e = html.escape
    has_pro = book['chapters'] and book['chapters'][0]['modules'][0] == 'skeleton'
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>%s回忆录样书</title><style>%s</style></head><body><main>' % (e(book['person']['name']), CSS),
           '<h1>%s的回忆录</h1>' % e(book['person']['name']),
           '<p class="note">%s。版本 %s（%s）。<br><span class="legend"><span class="add">加写句</span>写作者加的感受、回望、过渡、意象、呼应、收束，需老人确认；'
           '<span class="fb">如实草稿</span>核对未通过、退回的如实草稿段落；每段下方可展开看老人原话。</span></p>'
           % (e(NOTE[book['material']['kind']]), e(book['variant']), e(book['edition']))]
    out.append('<nav class="toc"><p>' + '<br>'.join('<a href="#c%d">%s　%s</a>' % (i, chapter_label(i, c, has_pro), e(c['title']))
                                                   for i, c in enumerate(book['chapters'])) + '</p></nav>')
    for i, c in enumerate(book['chapters']):
        out.append('<h2 id="c%d">%s　%s</h2><p class="mod">%s</p>' % (i, chapter_label(i, c, has_pro), e(c['title']),
                                                                     e(' · '.join(mb.MODULE_NAME[m] for m in c['modules']))))
        adds = []
        for s in c['sections']:
            if len(c['sections']) > 1 and s['title']:
                out.append('<h3>%s</h3>' % e(s['title']))
            for p in s['paragraphs']:
                parts = []
                for x in p['sentences']:
                    if x['add']:
                        parts.append('<span class="add">%s</span><span class="tag">%s</span>' % (e(x['t']), e(x['add'])))
                        adds.append((x['add'], x['t']))
                    else:
                        parts.append(e(x['t']))
                cls = 'p fb' if p.get('fallback') else 'p'
                lead = '<span class="fbt">〔如实草稿〕</span>' if p.get('fallback') else ''
                out.append('<p class="%s">%s%s</p>' % (cls, lead, ''.join(parts)))
                src = list(dict.fromkeys(u for x in p['sentences'] for u in x['src']))
                if src:
                    out.append('<details><summary>原话来源 %s</summary>%s</details>' % (
                        e('、'.join(src)), ''.join('<div class="src"><b>%s · 问：</b>%s<br><b>答：</b>%s</div>' % (
                            e(u), e(book['units'][u]['asked']), e(book['units'][u]['text'])) for u in src if u in book['units'])))
        if adds:
            out.append('<div class="adds">本章加写句（待老人确认）：<br>' + '<br>'.join('（%s）%s' % (e(a), e(t)) for a, t in adds) + '</div>')
    nw = book['not_written']
    if nw['private'] or nw['declined']:
        out.append('<h2>没有写进书的内容（待老人决定）</h2><ul>')
        out += ['<li>私事（%s）：%s</li>' % (e(p.get('kind') or ''), e(p['quote'])) for p in nw['private']]
        out += ['<li>老人说不想讲：%s</li>' % e(d.get('quote') or '') for d in nw['declined']]
        out.append('</ul>')
    m = book.get('metrics') or {}
    out.append('<h2>代码指标</h2><div class="metrics">成书 %s 字 / 原话 %s 字（%.2f 倍）；加写句占比 %s；来源中找不到的数字/地名/人名 %s 处；原话单元利用率 %s；'
               '各章字数与预算平均偏差 %s；退回如实草稿 %s 段</div>' % (
                   m.get('chars'), m.get('elder_chars'), m.get('ratio_to_elder') or 0, m.get('added_ratio'), m.get('unsupported_tokens'),
                   m.get('unit_use'), m.get('mean_abs_deviation'), m.get('fallback_paragraphs')))
    out.append('</main></body></html>')
    return '\n'.join(out)


def write_all(book, base):
    base = Path(base)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix('.md').write_text(to_markdown(book), encoding='utf-8')
    base.with_suffix('.html').write_text(to_html(book), encoding='utf-8')
