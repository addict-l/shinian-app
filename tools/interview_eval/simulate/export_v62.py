#!/usr/bin/env python3
"""HTML side by side of two run_full.py runs (BRIEF12: V6.1 vs V6.2) for the user to read.

  python3 tools/interview_eval/simulate/export_v62.py --out 采访V6.2_对照_V6.1.html --title ... \
      --left V6.1=st8-b61-it+st8-b61-ho --right V6.2=st8-b62-it+st8-b62-ho [--summary FRAGMENT.md] [--intro TEXT]

Per person and question: every interviewer turn and every elder answer, verbatim. Marked: detail questions (深挖)
with their kind, redirect questions of a fact question (转向问), detail questions written with the told-story memory
("已讲过" — the sentences the interviewer was told the elder had already told, and where), the elder's sentences that
retell an earlier question (v62_metrics definition), turns the metrics count as a judgement of the elder or as a
question beyond his experience. The simulated elder is a Claude Haiku persona playing a person from published
interviews; it is not a real person.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import v62_metrics as vm  # noqa: E402
import v6flow  # noqa: E402

CSS = """
:root{--bg:#faf8f4;--fg:#222;--muted:#6b665e;--card:#fff;--line:#e4dfd6;--sys:#eef3f8;--eld:#fbf3e6;--deep:#2f6f4f;--told:#8a4b0f;--bad:#a1262b}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#e8e4dc;--muted:#a39d92;--card:#22201d;--line:#3a3631;--sys:#1f2a35;--eld:#2e2619;--deep:#7fc8a0;--told:#e0a868;--bad:#f08a8f}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 -apple-system,"PingFang SC","Noto Sans SC",sans-serif}
main{max-width:1180px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.4em 0} h2{font-size:1.25rem;margin:1.6em 0 .4em;border-bottom:1px solid var(--line)} h3{font-size:1.02rem;margin:1em 0 .3em}
.intro,.note{color:var(--muted);font-size:.92rem}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:760px){.grid{grid-template-columns:1fr}}
.col{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}
.col h4{margin:0 0 6px;font-size:.9rem;color:var(--muted)}
.m{border-radius:8px;padding:6px 9px;margin:6px 0;word-break:break-word}
.s{background:var(--sys)} .e{background:var(--eld)}
.who{font-size:.75rem;color:var(--muted);margin-right:6px}
.chip{display:inline-block;font-size:.72rem;border-radius:9px;padding:0 7px;margin-left:4px;border:1px solid currentColor}
.deep{color:var(--deep)} .told{color:var(--told)} .bad{color:var(--bad)}
.retell{text-decoration:underline dotted var(--told);text-underline-offset:3px}
.toldlist{font-size:.82rem;color:var(--told);margin:2px 0 0 10px}
table{border-collapse:collapse;font-size:.88rem;width:100%;overflow-x:auto;display:block}
td,th{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
"""


def esc(t):
    return html.escape(t or '')


def run_records(name):
    out = {}
    for s in vm.load_run(name):
        out[s['narrator_id']] = s
    return out


def retold_marks(text, seen_q):
    """Elder text with the sentences that retell an earlier question underlined."""
    parts = []
    for sent in vm.SENT.findall(text) or [text]:
        g = vm.grams(sent)
        best = max((len(g & og) / len(g), q) for q, og in seen_q) if g and seen_q else (0, None)
        if len(vm.han(sent)) >= 8 and best[0] >= 0.5:
            parts.append(f'<span class="retell" title="前面讲过（{esc(best[1])}）">{esc(sent)}</span>')
        else:
            parts.append(esc(sent))
    return ''.join(parts)


def question_html(rec, seen_q, words):
    sp = vm.backend().speaker
    st = vm.backend().story
    out = []
    logs = [e for e in ((rec.get('deepen') or {}).get('log') or []) if e.get('decision') == 'asked']
    redirect = bool((rec.get('deepen') or {}).get('redirect'))
    di = 0
    elder_so_far = ''
    for m in rec['messages']:
        if m['role'] == 'elder':
            if m.get('scripted'):
                out.append(f'<div class="m e"><span class="who">老人</span>（点了“继续”）</div>')
                continue
            elder_so_far += m['text']
            out.append(f'<div class="m e"><span class="who">老人</span>{retold_marks(m["text"], seen_q)}</div>')
            continue
        kind = m.get('kind')
        chips = ''
        extra = ''
        if kind == 'deepen':
            log = logs[di] if di < len(logs) else {}
            di += 1
            chips += f'<span class="chip deep">{"转向问" if redirect else "深挖"}·{esc(m.get("dimension") or log.get("dimension") or "")}</span>'
            if log.get('told_items'):
                chips += '<span class="chip told">知道已讲过</span>'
                extra = '<div class="toldlist">告诉采访者已讲过：' + '；'.join(
                    f'「{esc(s[:30])}」（{esc(q)}）' for q, s in log['told_items'][:3]) + '</div>'
        elif kind == 'followup':
            chips += '<span class="chip">追问</span>'
        elif kind in ('draft', 'supplement', 'transition', 'review'):
            chips += f'<span class="chip">{ {"draft": "草稿入口", "supplement": "补充", "transition": "转题", "review": "核对"}[kind] }</span>'
        if kind in ('followup', 'deepen', 'draft', 'supplement', 'transition', 'review'):
            ack = vm.turn_ack(m)
            bad = [w for w in words if ack and w in ack and w not in sp._simp(elder_so_far)]
            if bad:
                chips += f'<span class="chip bad">替老人评价：{esc("、".join(bad))}</span>'
            if kind in ('followup', 'deepen') and st.third_party(m.get('question_part') or m['text']):
                chips += '<span class="chip bad">超出亲历</span>'
        out.append(f'<div class="m s"><span class="who">采访者</span>{esc(m["text"])}{chips}{extra}</div>')
    return ''.join(out)


def chain_seen(sess, module):
    seen_q = []
    for qid, text in vm.seed_text(sess['_plan'], sess['narrator_id'], module):
        seen_q.append((qid, vm.grams(text)))
    return seen_q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', required=True)
    ap.add_argument('--left', required=True)
    ap.add_argument('--right', required=True)
    ap.add_argument('--summary')
    ap.add_argument('--intro', default='')
    a = ap.parse_args()
    (ll, ln), (rl, rn) = a.left.split('=', 1), a.right.split('=', 1)
    left, right = run_records(ln), run_records(rn)
    S = vm.setup()
    words = vm.eval_words()
    body = [f'<h1>{esc(a.title)}</h1>', f'<p class="intro">{esc(a.intro)}</p>',
            '<p class="note">标记：<span class="chip deep">深挖</span>故事题深挖；<span class="chip deep">转向问</span>事实题老人重讲时的转向问；'
            '<span class="chip told">知道已讲过</span>这句深挖/转向问写的时候，采访者被告知了老人前面已讲过的句子；'
            '<span class="retell">下划虚线</span>老人这句话大半是前面某题讲过的；<span class="chip bad">替老人评价</span>'
            '<span class="chip bad">超出亲历</span>按代码规则标出。老人由 Claude Haiku 扮演（素材来自公开访谈改编），不是真人。</p>']
    if a.summary:
        body.append('<h2>对比表</h2>' + md_table_html(Path(a.summary).read_text(encoding='utf-8')))
    for nid in [n for n in left if n in right] + [n for n in right if n not in left]:
        ls, rs = left.get(nid), right.get(nid)
        name = (ls or rs)['name']
        body.append(f'<h2>{esc(name)}（{esc(nid)}）</h2>')
        lrec = {r['qid']: r for r in (ls or {}).get('questions', [])}
        rrec = {r['qid']: r for r in (rs or {}).get('questions', [])}
        order = list(dict.fromkeys([*lrec, *rrec]))
        seen = {}
        for qid in order:
            module = S.module_of(qid)
            for side, sess, recs in (('l', ls, lrec), ('r', rs, rrec)):
                if sess is not None and (side, module) not in seen:
                    seen[(side, module)] = chain_seen(sess, module)
            entry = (lrec.get(qid) or rrec.get(qid))['entry']
            depth = {'story': '故事题', 'fact': '事实题', 'reflection': '感悟题'}.get(S.depth.get(qid), '')
            cols = []
            for side, label, recs in (('l', ll, lrec), ('r', rl, rrec)):
                rec = recs.get(qid)
                cols.append(f'<div class="col"><h4>{esc(label)}</h4>' + (question_html(rec, seen[(side, module)], words) if rec else '（无）') + '</div>')
                if rec:
                    seen[(side, module)].append((qid, set().union(*[vm.grams(t) for _, t in vm.elder_answers(rec)] or [set()])))
            body.append(f'<h3>{esc(qid)} · {esc(depth)} · {esc(entry)}</h3><div class="grid">{"".join(cols)}</div>')
    page = (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>采访 V6.2 对照</title><style>{CSS}</style></head><body><main>{"".join(body)}</main></body></html>')
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page, encoding='utf-8')
    print('wrote', a.out, len(page))


def md_table_html(md):
    out, rows = [], []
    for line in md.splitlines():
        if line.startswith('|'):
            cells = [c.strip() for c in line.strip('|').split('|')]
            if set(''.join(cells)) <= set('-'):
                continue
            rows.append(cells)
            continue
        if rows:
            out.append('<table>' + ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in r) + '</tr>' for r in rows) + '</table>')
            rows = []
        if line.strip():
            out.append(f'<p>{esc(line)}</p>')
    if rows:
        out.append('<table>' + ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in r) + '</tr>' for r in rows) + '</table>')
    return ''.join(out)


if __name__ == '__main__':
    main()
