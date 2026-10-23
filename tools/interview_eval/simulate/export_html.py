#!/usr/bin/env python3
"""Export complete simulated interviews as a readable HTML page (for the user to read).

  python3 export_html.py --out 模拟访谈_v4a_迭代组.html --title ... \
      --run 改前（固定话术）=sim-b0 --run 改后（v4a）=sim-v4a [--people NID,NID] [--intro TEXT]

Each person gets one section; the runs are shown side by side (stacked on a phone).
"""
import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
from persona import Personas  # noqa: E402
from score import label_messages, DIMS  # noqa: E402

C = json.loads((common.ROOT / 'docs/prototypes/full-interview-v3j/contracts.json').read_text(encoding='utf-8'))
F = {f['id']: f for q in C['questions'] for f in q['elements']}
ST = {'known': '已回答', 'none': '明确没有', 'unknown': '记不清', 'declined': '不愿讲', 'deferred': '以后再讲', 'ambiguous': '说有但没说清', 'conflict': '前后矛盾'}
KIND = {'entry': '入口问题', 'followup': '追问', 'supplement': '补充邀请', 'close': '收尾/转题', 'pause': '休息', 'resume': '继续'}
BEH = {'normal': '', 'short': '短答', 'drift': '跑题', 'reluctant': '不想多说', 'rest': '想歇会儿'}
REASON = {'done': '本题完成', 'limited': '信息有限', 'unknown': '老人记不清', 'declined': '老人不想讲', 'declined_partial': '已答，老人不想展开',
          'deferred': '以后再讲', 'cap': '追问已达上限',
          'asked_once': '同一点问过一次', 'max_turns': '轮数上限', 'rest': '老人要休息', 'error': '系统错误'}
DZ = {'natural': '自然', 'grounded': '贴合', 'timing': '时机', 'single': '单一', 'tone': '语气'}
VZ = {'multi_question': '一次多问', 'presupposition': '预设/编造', 'repeat_ask': '重复问', 'should_have_stopped': '该停不停'}
esc = lambda x: html.escape(str(x if x is not None else ''))

CSS = """
:root{--bg:#fbfaf7;--fg:#22211e;--muted:#6d6a62;--card:#ffffff;--line:#e4e1d8;--sys:#eef2f7;--eld:#f6f1e4;--good:#1f6b45;--bad:#a8321f;--chip:#efede6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#1a1a18;--fg:#e8e6df;--muted:#a19d92;--card:#222220;--line:#3a3934;--sys:#232a33;--eld:#2d2a22;--good:#6fc597;--bad:#f08d7a;--chip:#2c2b27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:4px 0 8px}h2{font-size:18px;margin:34px 0 6px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:15px;margin:0 0 8px}.intro{color:var(--muted);max-width:820px}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px;margin-top:10px}
.col{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.topic{margin:14px 0 4px;font-weight:600;font-size:14px;color:var(--muted)}
.msg{margin:6px 0;display:flex}.msg .b{padding:7px 11px;border-radius:12px;max-width:92%;white-space:pre-wrap}.s .b{background:var(--sys)}.e{justify-content:flex-end}.e .b{background:var(--eld)}
.meta{font-size:12px;color:var(--muted);margin-top:2px}.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:0 6px;margin:2px 4px 0 0;font-size:12px}
.lo{color:var(--bad);font-weight:600}.vio{color:var(--bad);font-weight:600;font-size:12px}.ok{color:var(--good)}details{margin:4px 0;font-size:13px;color:var(--muted)}summary{cursor:pointer}
table{border-collapse:collapse;font-size:13px;margin:8px 0;display:block;overflow-x:auto}td,th{border:1px solid var(--line);padding:4px 8px;text-align:left;white-space:nowrap}
.rec{font-size:13px;margin:4px 0 0;padding-left:18px}.mat{white-space:pre-wrap;font-size:12px;background:var(--chip);padding:8px;border-radius:8px}
"""


def scores_for(run):
    p = common.RUNS / run / 'scores.json'
    return common.load(p) if p.exists() else {}


def session_for(run, nid):
    for f in sorted((common.RUNS / run / 'sessions').glob('*.json')):
        s = common.load(f)
        if s.get('narrator_id') == nid:
            return s
    return None


def chips(t):
    if not t:
        return ''
    out = ''.join(f"<span class='chip{' lo' if (t.get(d) or 5) <= 3 else ''}'>{DZ[d]} {t.get(d)}</span>" for d in DIMS if t.get(d) is not None)
    if t.get('violations'):
        out += "<span class='vio'>违规：" + '、'.join(VZ.get(v, v) for v in t['violations']) + '</span>'
    return out


def episode_html(ep, sc, show_entry):
    parts = [f"<div class='topic'>{esc(ep['qid'])}　{esc(ep['entry'])}</div>"]
    for label, m in label_messages(ep):
        if m['role'] == 'system':
            if m.get('kind') == 'entry' and (m.get('shown_in_previous') or not show_entry):
                continue
            t = (sc.get('turns') or {}).get(label)
            meta = KIND.get(m.get('kind'), m.get('kind') or '')
            if m.get('target'):
                meta += '：' + F.get(m['target'], {}).get('label', m['target'])
            if m.get('kind') == 'close':
                meta += '（' + REASON.get(m.get('reason'), m.get('reason') or '') + '）'
            if (m.get('speaker') or {}).get('fallback'):
                meta += ' · 说话层校验未过，用固定句'
            parts.append(f"<div class='msg s'><div class='b'>{esc(m['text'])}<div class='meta'>{esc(meta)}</div><div>{chips(t)}</div></div></div>")
        else:
            tag = '（点了“继续”）' if m.get('scripted') else ' · '.join(x for x in [BEH.get(m.get('behavior'), ''), '语音错字' if m.get('asr') else ''] if x)
            judge = m.get('judge')
            inner = ''
            if judge:
                rec = '；'.join(f"{F[f]['label']}={ST.get(v['state'], v['state'])}" for f, v in judge.get('fields', {}).items()) or '无'
                inner = f"<details><summary>判定层</summary>决定：{esc(judge.get('decision'))}" + (
                    f"　目标：{esc(F.get(judge.get('target'), {}).get('label', ''))}" if judge.get('target') else '') + f"<br>已记：{esc(rec)}</details>"
            parts.append(f"<div class='msg e'><div class='b'>{esc(m['text'])}" + (f"<div class='meta'>{esc(tag)}</div>" if tag else '') + inner + '</div></div>')
    fin = (ep.get('final') or {}).get('fields') or {}
    if fin:
        parts.append("<details><summary>本题记下的内容</summary><ul class='rec'>" + ''.join(
            f"<li>{esc(F[f]['label'])}：{esc(ST.get(v['state'], v['state']))}" + (f"「{esc(v.get('value'))}」" if v.get('value') else '') + '</li>'
            for f, v in fin.items()) + '</ul></details>')
    flags = [f"老人说了资料里没有的：{esc(x.get('claim'))}（{esc(x.get('turn'))}）" for x in sc.get('fabrication') or []]
    flags += [f"记录可能有误：{esc(x.get('item'))}，{esc(x.get('why'))}" for x in sc.get('record_errors') or []]
    if flags:
        parts.append('<div class="vio">' + '<br>'.join(flags) + '</div>')
    return ''.join(parts)


def summary_table(runs):
    rows = [('每题老人回答轮数', 'elder_turns'), ('每题追问次数', 'followups'), ('每题补充邀请', 'supplements'), ('重复追问/题', 'repeat_target'),
            ('追问照念固定问句', 'verbatim'), ('追问引用老人原话词', 'grounded_proxy'), ('题目完成率', 'complete'), ('发言平均字数', 'reply_len_mean'),
            ('自然不生硬', 'score_natural'), ('贴合当前事件', 'score_grounded'), ('时机（结束自然）', 'score_timing'), ('单一不预设', 'score_single'),
            ('语气', 'score_tone'), ('硬性违规率（轮）', 'violation_rate'), ('每轮延迟（秒）', 'latency_mean_s'), ('每轮 token', 'tokens_per_model_turn')]
    out = ['<table><tr><th>指标</th>' + ''.join(f'<th>{esc(lbl)}</th>' for lbl, _ in runs) + '</tr>']
    ms = [scores_for(r).get('metrics') or {} for _, r in runs]
    for name, key in rows:
        out.append(f'<tr><td>{esc(name)}</td>' + ''.join(f"<td>{esc(m.get(key))}</td>" for m in ms) + '</tr>')
    return ''.join(out) + '</table>'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--intro', default='')
    p.add_argument('--run', action='append', required=True, help='label=run_name')
    p.add_argument('--people', default='')
    a = p.parse_args()
    runs = [tuple(x.split('=', 1)) for x in a.run]
    P = Personas()
    first = common.load(common.RUNS / runs[0][1] / 'plan.json')
    people = [x for x in a.people.split(',') if x] or first['people']
    parts = [f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{esc(a.title)}</title><style>{CSS}</style></head><body><main><h1>{esc(a.title)}</h1><p class='intro'>{a.intro}</p>",
             '<h3>本页所选运行的整体指标（全部会话）</h3>', summary_table(runs)]
    for nid in people:
        sess = [(lbl, session_for(r, nid), (scores_for(r).get('scores') or {})) for lbl, r in runs]
        if not any(s for _, s, _ in sess):
            continue
        parts.append(f"<h2>{esc(P.names[nid])}</h2>")
        mats = []
        any_s = next(s for _, s, _ in sess if s)
        for q in any_s['questions']:
            mats.append(f"【{q}】\n" + P.render(P.material(nid, q)))
        parts.append("<details><summary>模拟老人可用的真实资料（只能讲这些）</summary><div class='mat'>" + esc('\n\n'.join(mats)) + '</div></details>')
        parts.append("<div class='cols'>")
        for lbl, s, sc in sess:
            parts.append(f"<div class='col'><h3>{esc(lbl)}</h3>")
            if not s:
                parts.append('（无）</div>')
                continue
            for i, ep in enumerate(s['episodes']):
                parts.append(episode_html(ep, (sc.get(s['session']) or {}).get(str(i)) or {}, show_entry=True))
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</main></body></html>')
    Path(a.out).write_text('\n'.join(parts), encoding='utf-8')
    print(a.out)


if __name__ == '__main__':
    main()
