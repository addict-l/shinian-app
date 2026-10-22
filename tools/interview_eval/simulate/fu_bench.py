#!/usr/bin/env python3
"""Follow-up bench on real interview transcripts: fixed contract question vs. speaking layer, same decision points.

  python3 fu_bench.py --group iteration --name rp4-fu-v4c [--speaker-prompt P] [--policy P] [--offline] [--sample N]

Decision points: the full45 multi-turn transcript cases of the chosen split group (split.json 'iteration' = 30
people / 'holdout' = 15), at every checkpoint where the cached v3j result (offline replay run, --from) itself
decided 'ask' for a target not asked before, and the elder's words carry no stop signal (the v4 rules would ask
there too). Gold is never read: only the published source texts, their original questions and v3j's own output.
For each point the baseline reply is the engine's contract question; the v4 reply is one speaking-layer call
(DeepSeek). Both are scored blind by the Haiku scorer queue with the unchanged rubric, as the last interviewer
turn of the dialogue so far. Output: RUNS/<name>/bench.json, report.md.
"""
import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import interview as iv  # noqa: E402
import queue_worker as qw  # noqa: E402
import score as scoring  # noqa: E402
from persona import bigrams  # noqa: E402


def points(S, src_run, people):
    data = common.load(common.RUNS / 'datasets/full45.json') if (common.RUNS / 'datasets/full45.json').exists() else None
    case_person = {c['id']: c['narrator_id'] for c in data['cases']}
    out = []
    for cdir in sorted((common.RUNS / src_run / 'cases').iterdir()):
        nid = case_person.get(cdir.name)
        if nid not in people:
            continue
        for f in sorted(cdir.glob('turn-*.json')):
            d = common.load(f)
            res = (d.get('record') or {}).get('result') or {}
            p = d['payload']
            target = res.get('target')
            if res.get('decision') != 'ask' or not target or (p.get('ask_counts') or {}).get(target):
                continue
            text = p['sources'][-1]['text']
            if iv.elder_signal(text):
                continue
            qid = p['question_id']
            dialogue = []
            for s in p['sources']:
                dialogue += [('system', (s.get('question') or '').strip() or p['main_question']), ('elder', s['text'])]
            out.append({'case': cdir.name, 'turn': f.stem, 'nid': nid, 'qid': qid, 'target': target, 'engine_question': res.get('question'),
                        'dialogue': dialogue, 'fields': iv.judge_summary(S, res, qid)['fields'], 'main': p['main_question']})
    return out


def scorer_input(S, pt, reply):
    lines = ['老人资料：', '\n'.join('【你讲的】' + t for r, t in pt['dialogue'] if r == 'elder'), '', f'话题入口：{pt["main"]}', '对话：']
    s = e = 0
    for role, text in pt['dialogue']:
        if role == 'system':
            lines.append(f'S{s}：{text}')
            s += 1
        else:
            e += 1
            lines.append(f'E{e}：{text}')
    label = f'S{s}'
    lines.append(f'{label}：{reply}')
    lines += ['系统记下的内容：', '（本项不评）', '需要打分的采访者发言：' + label]
    return '\n'.join(lines), label


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--group', choices=('iteration', 'holdout'), required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--from', dest='src', default='off-v4-f45-check1')
    ap.add_argument('--speaker-prompt')
    ap.add_argument('--policy')
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--sample', type=int)
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--rescore', help='re-score the replies of an earlier bench (no DeepSeek call) with a tagged input, to measure scorer noise')
    a = ap.parse_args()
    S = iv.Setup(a.speaker_prompt, a.policy)
    split = common.load(iv.V4 / 'split.json')
    run_dir = common.RUNS / a.name
    run_dir.mkdir(parents=True, exist_ok=False)
    if a.rescore:
        pts = common.load(common.RUNS / a.rescore / 'bench.json')['points']
    else:
        pts = points(S, a.src, set(split[a.group]))
    if a.sample and a.sample < len(pts):
        keep = set(random.Random(a.seed).sample(range(len(pts)), a.sample))
        pts = [x for k, x in enumerate(pts) if k in keep]
    print(json.dumps({'points': len(pts), 'people': len({p['nid'] for p in pts})}), flush=True)
    calls = []
    for k, pt in enumerate(pts):
        pt['call_id'] = f'fu{k:03d}'
        calls.append({'id': pt['call_id'], 'system': S.speaker_prompt, 'params': S.policy['model'],
                      'user': iv.speaker_user(S, pt['qid'], pt['dialogue'], pt['fields'], 'ask', pt['target'], pt['engine_question'])})
    relay = common.Relay(run_dir, offline=a.offline, wait_seconds=900)
    t0 = time.time()
    resp = relay.run_batch(a.name, calls) if calls and not a.rescore else {}
    prompt = (iv.V4 / 'scorer-prompt.txt').read_text(encoding='utf-8')
    q = qw.HaikuQueue('scorer')
    pending = []
    for pt in pts:
        if a.rescore:
            for variant in ('base', 'v4'):
                text, label = scorer_input(S, pt, pt[variant]['reply'])
                text = text.replace('需要打分的采访者发言：', f'（复评 {a.name}）\n需要打分的采访者发言：')
                note = f'只输出一个 JSON 对象，格式见指令末尾的“输出格式”。turns 里必须正好包含：{label}；fabrication、record_errors 没有就给 []。'
                rid, row = q.submit(prompt, text, note, {'type': 'scorer', 'labels': [label]}, {'bench': a.name, 'variant': variant})
                pending.append([pt, variant, label, rid, row])
            continue
        r = resp[pt['call_id']]
        ack, question = iv.parse_speaker(r)
        ack, _ = iv.clean_ack(ack, ''.join(x for r, x in pt['dialogue'] if r == 'elder'))
        prior = [t for role, t in pt['dialogue'] if role == 'system']
        errs = iv.check_ask(ack, question, prior) + (['inference_in_question'] if iv.INFER.search(question) else [])
        if errs:
            question = pt['engine_question']
            ack = '' if iv.check_close(ack) else ack
        pt['v4'] = {'reply': iv.join(ack, question), 'question': question, 'errors': errs, 'usage': r.get('usage'), 'raw': r.get('content')}
        pt['base'] = {'reply': pt['engine_question'], 'question': pt['engine_question']}
        for variant in ('base', 'v4'):
            text, label = scorer_input(S, pt, pt[variant]['reply'])
            note = f'只输出一个 JSON 对象，格式见指令末尾的“输出格式”。turns 里必须正好包含：{label}；fabrication、record_errors 没有就给 []。'
            rid, row = q.submit(prompt, text, note, {'type': 'scorer', 'labels': [label]}, {'bench': a.name, 'variant': variant})
            pending.append([pt, variant, label, rid, row])
    last = 0
    while any(x[4] is None for x in pending):
        for x in pending:
            if x[4] is None:
                x[4] = q.poll(x[3])
        if time.time() - last > 60:
            last = time.time()
            print(json.dumps({'scorer_waiting': sum(x[4] is None for x in pending)}), flush=True)
        time.sleep(1)
    for pt, variant, label, rid, row in pending:
        sc = scoring.parse_scores(row, [label])
        pt[variant]['score'] = (sc.get('turns') or {}).get(label) or {}
        pt[variant]['note'] = sc.get('note')
    # summary
    lines = [f'# {a.name}（追问对照：真实访谈稿上 v3j 决定追问的点；来源 {a.src}，{a.group} 组）', '']
    summ = {}
    for variant, zh in (('base', '改前：合同固定问句'), ('v4', '改后：说话层')):
        sc = [pt[variant]['score'] for pt in pts if pt[variant].get('score')]
        row = {d: round(statistics.mean(s[d] for s in sc if d in s), 3) for d in scoring.DIMS} if sc else {}
        row['ge4'] = {d: round(sum(s.get(d, 0) >= 4 for s in sc) / len(sc), 3) for d in ('natural', 'grounded', 'timing')} if sc else {}
        row['violation_points'] = sum(1 for s in sc if s.get('violations'))
        row['violations'] = dict(Counter(v for s in sc for v in s.get('violations') or []))
        row['n'] = len(sc)
        g = []
        for pt in pts:
            elder = ''.join(t for r, t in pt['dialogue'] if r == 'elder')
            words = bigrams(pt[variant]['question']) & bigrams(elder)
            words -= bigrams(pt['main'] + (pt['engine_question'] or '')) | scoring.GENERIC
            g.append(bool(words))
        row['grounded_proxy'] = round(sum(g) / len(g), 3) if g else None
        row['verbatim'] = round(sum(pt[variant]['question'].strip() == (pt['engine_question'] or '').strip() for pt in pts) / len(pts), 3) if pts else None
        summ[variant] = row
        lines.append(f"- {zh}：n={row['n']}；" + '，'.join(f"{scoring.DIM_ZH[d]} {row.get(d)}" for d in scoring.DIMS)
                     + f"；≥4 占比 {row['ge4']}；违规点 {row['violation_points']} {row['violations']}；引用老人原话 {row['grounded_proxy']}；照念固定句 {row['verbatim']}")
    fb = sum(1 for pt in pts if pt['v4']['errors'])
    usage = relay.usage
    lines.append(f"- 说话层校验回退 {fb}/{len(pts)}；DS 新发 {relay.calls_sent} / 缓存 {relay.calls_cached}，token {usage.get('total_tokens', 0)}；用时 {round(time.time() - t0)}s")
    lines.append('')
    for pt in pts:
        lines.append(f"## {S.personas.names.get(pt['nid'], pt['nid'])} {pt['qid']} {pt['turn']} → {S.F[pt['target']]['label']}")
        for role, t in pt['dialogue'][-2:]:
            lines.append(('> 问：' if role == 'system' else '> 答：') + t.replace('\n', ' ')[:300])
        for variant in ('base', 'v4'):
            s = pt[variant].get('score') or {}
            lines.append(f"- {'改前' if variant == 'base' else '改后'}：{pt[variant]['reply']}　〔" + ' '.join(f"{d[:3]}{s.get(d)}" for d in scoring.DIMS)
                         + (f" 违规{s.get('violations')}" if s.get('violations') else '') + '〕' + (f"（回退 {pt['v4']['errors']}）" if variant == 'v4' and pt['v4']['errors'] else ''))
        lines.append('')
    (run_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    common.save(run_dir / 'bench.json', {'summary': summ, 'usage': usage, 'points': pts})
    print('\n'.join(lines[:6]), flush=True)
    S.ctx.engine.close()


if __name__ == '__main__':
    main()
