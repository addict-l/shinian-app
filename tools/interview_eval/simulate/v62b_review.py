#!/usr/bin/env python3
"""BRIEF14 (interview V6.2b, the humane interviewer) -- review material for the user: code metrics (0 token,
recomputable), the Haiku rubric with the added "humane" item, and the full question-and-answer text of V6.1 and
V6.2b side by side.

  python3 tools/interview_eval/simulate/v62b_review.py metrics V61=RUN+RUN V62b=RUN+RUN [--json OUT]
  python3 tools/interview_eval/simulate/v62b_review.py score RUN [RUN ...] [--offline]
        Haiku scorer queue, one request per question, prompt docs/prototypes/full-interview-v5/v6.2/humane-scorer-prompt.txt
        (the unchanged v4 rubric plus "humane": like a real interviewer -- gentle, respectful, guiding)
        -> RUNS/<RUN>/humane-scores.json
  python3 tools/interview_eval/simulate/v62b_review.py export --pair NAME=RUN61+RUN61:RUN62b+RUN62b [--pair ...]
        --metrics METRICS.json --html OUT.html --txt OUT.txt

Metric definitions (the same code for every version):
- fragment echo (碎片复述): an interviewer turn whose acknowledgement only repeats a few of the elder's words
  (interview_story.fragment_echo, as in v62_metrics.wording); rate over all interviewer turns.
- transition template (过渡套路): over consecutive closes of one chain, the share of pairs with the same pattern
  (acknowledgement kind + move-on phrase family) and with the same move-on phrase family.
- judgement of the elder (替老人评价): acknowledgement words of the backend's EVAL / EVAL_V62 lists the elder's words
  in this question lack (v62_metrics.wording_summary).
- third-party question (第三方追问): a follow-up, detail or handle question that interview_story.third_party(wide=True)
  flags -- how others talked to someone, courted or got on, discussed among themselves, felt, or private matters.
- empty answer offered a draft (空回答给草稿入口): a question that showed the draft offer while every elder answer
  before it was an empty one (at most 40 characters, saying he cannot remember / has nothing to say:
  interview_speaker.elder_signal 'unknown' or NOTHING_SAY).
- handle (引导抓手): an interviewer turn of the guide step; its answers' characters.
- deepening: detail questions asked and the characters of their answers.
- elder words / new material: v62_metrics.chain_metrics (new = sentences whose 4-grams are less than half covered by
  what he said earlier in this interview).
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import v6flow  # noqa: E402
import v62_metrics as vm  # noqa: E402

PROMPT = common.ROOT / 'docs/prototypes/full-interview-v5/v6.2/humane-scorer-prompt.txt'
DIMS = ('natural', 'grounded', 'timing', 'single', 'tone', 'humane')
KIND_LABEL = {'intro': '开场', 'entry': '入口题', 'followup': '追问', 'deepen': '深挖', 'guide': '引导抓手',
              'transition': '转题', 'draft': '草稿入口', 'supplement': '补充', 'review': '核对', 'pause': '休息',
              'resume': '继续'}


def runs_of(spec):
    return [r for r in spec.split('+') if r]


def sessions(spec):
    out = []
    for name in runs_of(spec):
        out += vm.load_run(name)
    return out


def empty_answer(text):
    sp = vm.backend().speaker
    words = sp._norm(text)
    return len(words) <= 40 and (sp.elder_signal(text) == 'unknown' or bool(sp.NOTHING_SAY.search(words)))


def turns_of(spec):
    """wording_summary turns of the runs, the handle turns counted like follow-ups."""
    turns = []
    S = vm.setup()
    for s in sessions(spec):
        for rec in s['questions']:
            key = f"{s['_run']}:{s['narrator_id']}:{S.module_of(rec['qid'])}"
            elder = ''
            for m in rec['messages']:
                if m['role'] == 'elder':
                    if not m.get('scripted'):
                        elder += m['text']
                    continue
                k = m.get('kind')
                if k in ('draft', 'supplement', 'transition') or (k == 'review' and m['text'] not in (
                        v6flow.REVIEW_TEXT, v6flow.LIFE_REVIEW_TEXT) and not m['text'].endswith(v6flow.LIFE_REVIEW_TEXT[-12:])):
                    turns.append((key, 'close', m['text'], elder))
                elif k in ('followup', 'deepen', 'guide'):
                    turns.append((key, 'followup' if k == 'guide' else k, m['text'], elder))
    return turns


def extra_counts(spec):
    st = vm.backend().story
    c = Counter()
    examples = defaultdict(list)
    for s in sessions(spec):
        for rec in s['questions']:
            msgs = rec['messages']
            elders_before_draft, drafted = [], False
            after = None
            for m in msgs:
                if m['role'] == 'elder':
                    if m.get('scripted'):
                        continue
                    c['elder_answers'] += 1
                    if empty_answer(m['text']):
                        c['empty_answers'] += 1
                    if after == 'guide':
                        c['guide_answer_chars'] += len(vm.han(m['text']))
                        c['guide_answers_with_content'] += not empty_answer(m['text'])
                    if not drafted:
                        elders_before_draft.append(m['text'])
                    after = None
                    continue
                k = m.get('kind')
                after = k
                if k == 'guide':
                    c['guides'] += 1
                    examples['guide'].append(f"{rec['qid']}：{m['text']}")
                if k in ('followup', 'deepen', 'guide') and st.third_party(m.get('question_part') or m['text'], wide=True):
                    c['third_party_wide'] += 1
                    examples['third_party'].append(f"{rec['qid']}：{m['text']}")
                if k == 'draft' and not drafted:
                    drafted = True
                    if elders_before_draft and all(empty_answer(t) for t in elders_before_draft):
                        c['empty_draft'] += 1
                        examples['empty_draft'].append(f"{rec['qid']}：{' / '.join(elders_before_draft)} → {m['text']}")
                if k == 'transition' and rec.get('close_reason') == 'unknown_empty':
                    c['empty_moved_on'] += 1
    return c, examples


def metrics(args):
    out_json = None
    if '--json' in args:
        i = args.index('--json')
        out_json = args[i + 1]
        args = args[:i] + args[i + 2:]
    table = {}
    for arg in args:
        label, spec = arg.split('=', 1)
        pooled = Counter()
        for name in runs_of(spec):
            _, res, _, _ = vm.run_table(name)
            pooled.update({k: v for k, v in res.items() if isinstance(v, (int, float))})
        w = vm.wording_row(vm.wording_summary(turns_of(spec)))
        extra, ex = extra_counts(spec)
        hum = humane_summary(spec)
        table[label] = {'runs': runs_of(spec), 'pooled': dict(pooled), 'wording': w, 'extra': dict(extra),
                        'humane': hum, 'examples': {k: v[:6] for k, v in ex.items()}}
    rows = metric_rows(table)
    labels = list(table)
    print('| 指标 | ' + ' | '.join(labels) + ' |')
    print('|---|' + '---|' * len(labels))
    for name, vals in rows:
        print(f'| {name} | ' + ' | '.join(str(v) for v in vals) + ' |')
    if out_json:
        common.save(Path(out_json), {'table': table, 'rows': rows, 'at': time.strftime('%Y-%m-%d %H:%M')})


def pct(x):
    return '—' if x is None else f'{x * 100:.0f}%'


def metric_rows(table):
    rows = []

    def row(name, f):
        rows.append((name, [f(v) for v in table.values()]))
    row('问答题数', lambda v: v['pooled'].get('questions', 0))
    row('采访者发言数', lambda v: v['wording']['turns'])
    row('碎片复述率', lambda v: pct(v['wording']['fragment_echo_rate']))
    row('收尾用过渡短语的比例', lambda v: pct(v['wording']['phrase_share_of_closes']))
    row('相邻收尾同一句式', lambda v: pct(v['wording']['same_pattern_rate']))
    row('相邻收尾同一短语族', lambda v: pct(v['wording']['same_family_rate']))
    row('替老人评价（次）', lambda v: v['wording']['subjective'])
    row('第三方追问（次，扩大口径）', lambda v: v['extra'].get('third_party_wide', 0))
    row('空回答（老人只说记不清/没什么）', lambda v: v['extra'].get('empty_answers', 0))
    row('空回答给草稿入口（题）', lambda v: v['extra'].get('empty_draft', 0))
    row('空回答后温和转题（题）', lambda v: v['extra'].get('empty_moved_on', 0))
    row('引导抓手（次）', lambda v: v['extra'].get('guides', 0))
    row('抓手后老人讲出内容（次）/字数', lambda v: f"{v['extra'].get('guide_answers_with_content', 0)} / {v['extra'].get('guide_answer_chars', 0)}")
    row('深挖（次）', lambda v: v['pooled'].get('deepen_turns', 0))
    row('深挖回答字数', lambda v: v['pooled'].get('deepen_answer_chars', 0))
    row('老人原话字数', lambda v: v['pooled'].get('elder_chars', 0))
    row('不重复新素材字数', lambda v: v['pooled'].get('novel_chars', 0))
    row('新素材比例', lambda v: pct(vm.ratio(v['pooled'].get('novel_chars', 0), v['pooled'].get('elder_chars', 0))))
    row('DeepSeek 调用次数', lambda v: v['pooled'].get('ds_calls', 0))
    row('DeepSeek token（本运行新发）', lambda v: v['pooled'].get('ds_tokens_new', 0))
    for d, name in (('humane', 'Haiku 像真人采访者（温柔尊敬有引导）'), ('natural', 'Haiku 自然'), ('grounded', 'Haiku 贴合'),
                    ('timing', 'Haiku 时机'), ('tone', 'Haiku 语气')):
        row(name + ' 均分 / ≥4 比例', lambda v, d=d: '—' if not v['humane'].get('n') else
            f"{v['humane']['mean'][d]:.2f} / {pct(v['humane']['ge4'][d])}")
    row('Haiku 硬性违规（次）', lambda v: v['humane'].get('violations', '—'))
    return rows


# --------------------------------------------------------------------------- Haiku rubric with the humane item
def v4_session(s, S):
    sess = vm.to_v4(s, S)
    for ep in sess['episodes']:  # the opening is shown with the first question (S0, not scored)
        msgs = ep['messages']
        if len(msgs) > 1 and msgs[0].get('kind') == 'intro' and msgs[1].get('kind') == 'entry':
            msgs[1] = {**msgs[1], 'text': msgs[0]['text'] + ' ' + msgs[1]['text']}
            del msgs[0]
    return sess


def score(args):
    import queue_worker as qw
    import score as scoring
    from persona import Personas
    offline = '--offline' in args
    names = [a for a in args if not a.startswith('--')]
    S = vm.setup()
    prompt = PROMPT.read_text(encoding='utf-8')
    SS = SimpleNamespace(personas=Personas(), F=S.rt.F)
    q = qw.HaikuQueue('scorer')
    items = []
    for name in names:
        for s in vm.load_run(name):
            sess = v4_session(s, S)
            for i, _ in enumerate(sess['episodes']):
                call, scored = scoring.scorer_call(SS, sess, i, prompt)
                if not scored:
                    continue
                note = call['output_note'].replace('natural/grounded/timing/single/tone 五个', 'natural/grounded/timing/single/tone/humane 六个')
                rid, row = q.submit(call['system'], call['user'], note, {**call['validate'], 'extra_dims': ['humane']},
                                    {'session': sess['session'], 'episode': i, 'humane': True})
                if row is None and offline:
                    row = {'ok': False, 'error': 'offline_haiku_cache_miss'}
                items.append([name, sess['session'], sess['episodes'][i]['qid'], scored, rid, row])
    t0, last = time.time(), 0
    while True:
        missing = 0
        for it in items:
            if it[5] is None:
                it[5] = q.poll(it[4])
                missing += it[5] is None
        if not missing:
            break
        if time.time() - last >= 120:
            last = time.time()
            print(json.dumps({'scorer_waiting': missing, 't': round(time.time() - t0)}), flush=True)
        time.sleep(5)
    by_run = defaultdict(dict)
    for name, sid, qid, scored, rid, row in items:
        out = row.get('output') if isinstance(row.get('output'), dict) else {}
        turns = out.get('turns') if isinstance(out.get('turns'), dict) else {}
        by_run[name][qid] = {'labels': scored, 'turns': {k: turns.get(k) for k in scored}, 'note': out.get('note'),
                             'fabrication': out.get('fabrication'), 'ok': bool(turns), 'cached': row.get('cached')}
    for name, qs in by_run.items():
        common.save(common.RUNS / name / 'humane-scores.json', {'run': name, 'prompt': str(PROMPT.relative_to(common.ROOT)),
                                                                'questions': qs, 'haiku': {'answered': q.sent, 'cached': q.cached}})
        print(name, json.dumps(humane_summary(name), ensure_ascii=False))


def humane_summary(spec):
    vals, vio, n = defaultdict(list), 0, 0
    for name in runs_of(spec):
        path = common.RUNS / name / 'humane-scores.json'
        if not path.exists():
            continue
        for qid, q in common.load(path)['questions'].items():
            for label, t in (q.get('turns') or {}).items():
                if not isinstance(t, dict):
                    continue
                n += 1
                vio += len(t.get('violations') or [])
                for d in DIMS:
                    if isinstance(t.get(d), int):
                        vals[d].append(t[d])
    if not n:
        return {}
    return {'n': n, 'mean': {d: sum(v) / len(v) for d, v in vals.items()},
            'ge4': {d: sum(1 for x in v if x >= 4) / len(v) for d, v in vals.items()}, 'violations': vio}


def humane_turns(spec):
    """{(qid, label): scores} of the runs, for the export."""
    out = {}
    for name in runs_of(spec):
        path = common.RUNS / name / 'humane-scores.json'
        if path.exists():
            for qid, q in common.load(path)['questions'].items():
                for label, t in (q.get('turns') or {}).items():
                    out[(qid, label)] = t
    return out


# --------------------------------------------------------------------------- export (full Q&A text)
def labelled(rec):
    """Messages of a question as the user reads them: (speaker, kind label, text, S-label for the rubric)."""
    out, s = [], 0
    msgs = rec['messages']
    for i, m in enumerate(msgs):
        if m['role'] == 'elder':
            out.append(('老人', '继续（点按）' if m.get('scripted') else '', m['text'], None))
            continue
        k = m.get('kind')
        if k == 'intro':
            out.append(('采访者', KIND_LABEL['intro'], m['text'], None))
            continue
        label = f'S{s}'
        s += 1
        out.append(('采访者', KIND_LABEL.get(k, k or ''), m['text'], label if label != 'S0' else None))
    return out


def by_qid(spec):
    recs = {}
    for s in sessions(spec):
        for rec in s['questions']:
            recs[rec['qid']] = (s, rec)
    return recs


def export(args):
    pairs, html_out, txt_out, mpath = [], None, None, None
    i = 0
    while i < len(args):
        if args[i] == '--pair':
            name, rest = args[i + 1].split('=', 1)
            left, right = rest.split(':')
            pairs.append((name, left, right))
            i += 2
        elif args[i] == '--html':
            html_out, i = args[i + 1], i + 2
        elif args[i] == '--txt':
            txt_out, i = args[i + 1], i + 2
        elif args[i] == '--metrics':
            mpath, i = args[i + 1], i + 2
        else:
            raise SystemExit('unknown argument ' + args[i])
    S = vm.setup()
    mt = common.load(Path(mpath)) if mpath else None
    esc = html.escape
    css = """
:root{--bg:#faf8f4;--fg:#222;--muted:#6b6b6b;--card:#fff;--line:#e4dfd6;--v61:#5b6b8c;--v62:#2f7d5b;--tag:#f1ece2;
--deepen:#b5651d;--guide:#2f7d5b;--trans:#5b6b8c;--draft:#9b3b3b;--elder:#f6f2ea}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1b1b1d;--fg:#e8e6e1;--muted:#a3a19c;--card:#242427;
--line:#3a3a3f;--tag:#33322f;--elder:#2b2a27;--v61:#9fb0d6;--v62:#7cc9a3;--deepen:#e0a060;--guide:#7cc9a3;--trans:#9fb0d6;--draft:#e08a8a}}
:root[data-theme="dark"]{--bg:#1b1b1d;--fg:#e8e6e1;--muted:#a3a19c;--card:#242427;--line:#3a3a3f;--tag:#33322f;--elder:#2b2a27;
--v61:#9fb0d6;--v62:#7cc9a3;--deepen:#e0a060;--guide:#7cc9a3;--trans:#9fb0d6;--draft:#e08a8a}
body{background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;margin:0}
main{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:19px;margin:36px 0 8px;border-bottom:2px solid var(--line);padding-bottom:4px}
h3{font-size:16px;margin:26px 0 8px}.muted{color:var(--muted);font-size:13px}
table.m{border-collapse:collapse;width:100%;background:var(--card);font-size:14px;margin:10px 0}
table.m th,table.m td{border:1px solid var(--line);padding:5px 8px;text-align:left}table.m th{background:var(--tag)}
.wrap{overflow-x:auto}
.q{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:760px){.q{grid-template-columns:1fr}}
.col{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.col h4{margin:0 0 6px;font-size:14px}.col.v61 h4{color:var(--v61)}.col.v62 h4{color:var(--v62)}
.t{margin:6px 0;padding:6px 8px;border-radius:6px}.t.elder{background:var(--elder)}
.who{font-weight:600;font-size:13px;margin-right:6px}.tag{display:inline-block;font-size:12px;padding:0 6px;border-radius:4px;background:var(--tag);margin-right:6px}
.tag.深挖{color:var(--deepen)}.tag.引导抓手{color:var(--guide);font-weight:600}.tag.转题{color:var(--trans)}.tag.草稿入口{color:var(--draft)}
.sc{font-size:12px;color:var(--muted);margin-left:4px}.end{font-size:12px;color:var(--muted);margin-top:6px}
"""
    parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>采访V6.2b问答对照</title><style>{css}</style></head><body><main>']
    txt = []
    parts.append('<h1>采访 V6.2b 问答原文（对照 V6.1）——审核用</h1>')
    parts.append('<p class="muted">模拟老人（Claude Haiku 按真实口述资料扮演，素材按题分配的“rich”设定），非真人。采访 DeepSeek v4-pro，thinking disabled。'
                 '同一人物、同一行为种子分别跑 V6.1 与 V6.2b；题库 83 题、题序、判定层 v3j 均未改。第一句老人回答两边相同（只看到入口题），之后随采访者的话分开。'
                 '标签：入口题 / 追问 / 深挖 / 引导抓手 / 转题 / 草稿入口 / 补充 / 核对；每句采访者发言后的小字是 Haiku 量表“像真人采访者”分（1–5）。</p>')
    txt.append('采访 V6.2b 问答原文（对照 V6.1）——审核用\n模拟老人（Claude Haiku 按真实口述资料扮演），非真人；采访 DeepSeek v4-pro，thinking disabled。\n')
    if mt:
        labels = list(mt['table'])
        parts.append('<h2>指标</h2><div class="wrap"><table class="m"><tr><th>指标</th>' + ''.join(f'<th>{esc(l)}</th>' for l in labels) + '</tr>')
        txt.append('【指标】  ' + ' | '.join(labels))
        for name, vals in mt['rows']:
            parts.append(f'<tr><td>{esc(name)}</td>' + ''.join(f'<td>{esc(str(v))}</td>' for v in vals) + '</tr>')
            txt.append(f'{name}：' + ' | '.join(str(v) for v in vals))
        parts.append('</table></div><p class="muted">定义见 tools/interview_eval/simulate/v62b_review.py 文件头；代码指标 0 token 可复算。</p>')
        txt.append('')
    for name, left, right in pairs:
        L, R = by_qid(left), by_qid(right)
        hl, hr = humane_turns(left), humane_turns(right)
        qids = [q for q in S.plan() if q in L or q in R]
        parts.append(f'<h2>{esc(name)}</h2>')
        txt.append('=' * 30 + f'\n{name}\n' + '=' * 30)
        for qid in qids:
            entry = S.rt.questions[qid]['main_question']
            depth = S.depth.get(qid, '')
            dz = {'story': '故事题', 'fact': '事实题', 'reflection': '感悟题'}.get(depth, depth)
            parts.append(f'<h3>{esc(qid)} · {esc(dz)} · {esc(entry)}</h3><div class="q">')
            txt.append(f'\n—— {qid}（{dz}）{entry} ——')
            for tag, recs, hs, cls in (('V6.1', L, hl, 'v61'), ('V6.2b', R, hr, 'v62')):
                parts.append(f'<div class="col {cls}"><h4>{tag}</h4>')
                txt.append(f'【{tag}】')
                if qid not in recs:
                    parts.append('<p class="muted">（未跑）</p></div>')
                    continue
                _, rec = recs[qid]
                for who, kind, text, label in labelled(rec):
                    sc = hs.get((qid, label)) if label else None
                    score_txt = f'<span class="sc">像真人 {sc.get("humane")}</span>' if isinstance(sc, dict) and sc.get('humane') else ''
                    tag_html = f'<span class="tag {esc(kind)}">{esc(kind)}</span>' if kind else ''
                    parts.append(f'<div class="t {"elder" if who == "老人" else "sys"}"><span class="who">{who}</span>{tag_html}{esc(text)}{score_txt}</div>')
                    txt.append(f'{who}{"（" + kind + "）" if kind else ""}：{text}')
                parts.append(f'<div class="end">结束：{esc(str(rec.get("status")))} / {esc(str(rec.get("close_reason")))}</div></div>')
            parts.append('</div>')
    parts.append('</main></body></html>')
    if html_out:
        Path(html_out).write_text('\n'.join(parts), encoding='utf-8')
    if txt_out:
        Path(txt_out).write_text('\n'.join(txt) + '\n', encoding='utf-8')
    print(json.dumps({'html': html_out, 'txt': txt_out, 'pairs': len(pairs)}, ensure_ascii=False))


if __name__ == '__main__':
    cmd, rest = sys.argv[1], sys.argv[2:]
    {'metrics': metrics, 'score': score, 'export': export}[cmd](rest)
