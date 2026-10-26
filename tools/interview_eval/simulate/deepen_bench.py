#!/usr/bin/env python3
"""Deepen bench: the deepen decision points of an earlier v5 run, re-asked with another deepen prompt / policy.

  python3 deepen_bench.py --from st5-b5a-it --name st5-db-v5b --policy docs/prototypes/full-interview-v5/history/speaker-config.v5b.json

Points: every place in the source run where the deepen step called the speaking layer (asked, invalid, or the
model chose not to ask), with the dialogue exactly as it stood there. Only deepen calls are sent (~1k tokens per
point). The source run's deepen question and the new one are scored blind by the Haiku scorer queue with the
unchanged rubric as the last interviewer turn (persona material shown as in score.scorer_call). A point where a
version does not ask is listed but not scored. Output: RUNS/<name>/bench.json, report.md.
"""
import argparse
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
import interview as iv  # noqa: E402
import queue_worker as qw  # noqa: E402
import score as scoring  # noqa: E402


def points(src):
    out = []
    for f in sorted((common.RUNS / src / 'sessions').glob('*.json')):
        s = common.load(f)
        for ep in s['episodes']:
            dz = ep.get('deepen')
            if not dz:
                continue
            for e in dz['log']:
                if e['decision'] != 'asked' and e['reason'] not in ('invalid', 'model_skip'):
                    continue
                # dialogue up to the elder answer number e['k'] (scripted "continue" taps are not shown)
                dialogue, n, dims, old = [], 0, [], None
                for m in ep['messages']:
                    if m.get('scripted'):
                        continue
                    if n >= e['k'] and m['role'] == 'system':
                        old = m if m.get('kind') == 'deepen' else None
                        break
                    if m.get('kind') == 'deepen':
                        dims.append(m.get('dimension'))
                    dialogue.append((m['role'], m['text']))
                    n += m['role'] == 'elder'
                out.append({'session': s['session'], 'nid': s['narrator_id'], 'name': s.get('name'), 'qid': ep['qid'], 'k': e['k'],
                            'dims': dims, 'dialogue': dialogue, 'old': {'reply': old['text'] if old else '', 'dimension': e.get('dimension'),
                                                                         'reason': e['reason'], 'errors': e.get('errors')}})
    return out


def scorer_input(S, pt, reply):
    lines = ['老人资料：', S.personas.render(S.personas.material(pt['nid'], pt['qid'])), '', f'话题入口：{S.Q[pt["qid"]]["main_question"]}', '对话：']
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
    ap.add_argument('--from', dest='src', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--policy', required=True)
    ap.add_argument('--offline', action='store_true')
    a = ap.parse_args()
    S = iv.Setup(None, a.policy)
    run_dir = common.RUNS / a.name
    run_dir.mkdir(parents=True, exist_ok=False)
    pts = points(a.src)
    print(json.dumps({'points': len(pts)}), flush=True)
    calls = []
    for j, pt in enumerate(pts):
        dz = {'dims': pt['dims']}
        pt['call_id'] = f'db{j:03d}'
        calls.append({'id': pt['call_id'], 'system': S.deepen_prompt, 'params': S.deepen['model'],
                      'user': iv.deepen_user(S, pt['qid'], pt['dialogue'], dz)})
    relay = common.Relay(run_dir, offline=a.offline, wait_seconds=900)
    t0 = time.time()
    resp = relay.run_batch(a.name, calls) if calls else {}
    prompt = (iv.V4 / 'scorer-prompt.txt').read_text(encoding='utf-8')
    q = qw.HaikuQueue('scorer')
    pending = []
    for pt in pts:
        r = resp[pt['call_id']]
        dim, ack, question = iv.parse_deepen(r)
        elder_words = ''.join(t for role, t in pt['dialogue'] if role == 'elder')
        ack, fix = iv.clean_ack(ack, elder_words)
        if S.deepen.get('drop_echo_ack'):
            ack, echo = iv.deepen_ack(ack, question)
            fix += echo
        if S.deepen.get('extra_guards') and iv.DEEPEN_ACK_EVAL.search(ack):
            ack, fix = '', fix + ['ack_eval']
        prior = [t for role, t in pt['dialogue'] if role == 'system']
        dz = {'dims': pt['dims']}
        if not r.get('ok') or not isinstance(r.get('output'), dict):
            errs = ['call_failed']
        elif not question and not dim:
            errs = ['model_skip']
        else:
            errs = iv.check_deepen(dim, ack, question, prior, dz)
            if errs and ack and not iv.check_deepen(dim, '', question, prior, dz):
                fix.append('ack_dropped:' + ','.join(errs))
                ack, errs = '', []
        pt['new'] = {'reply': '' if errs else iv.join(ack, question), 'dimension': dim, 'errors': errs, 'repairs': fix, 'raw': r.get('content'),
                     'usage': r.get('usage')}
        for variant in ('old', 'new'):
            if not pt[variant]['reply']:
                continue
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
    lines = [f'# {a.name}（深挖对照：{a.src} 的深挖决策点，策略 {a.policy}）', '']
    summ = {}
    for variant in ('old', 'new'):
        sc = [pt[variant]['score'] for pt in pts if pt[variant].get('score')]
        row = {d: round(statistics.mean(s[d] for s in sc if d in s), 3) for d in scoring.DIMS} if sc else {}
        row['ge4'] = {d: round(sum(s.get(d, 0) >= 4 for s in sc) / len(sc), 3) for d in scoring.DIMS} if sc else {}
        row['violation_points'] = sum(1 for s in sc if s.get('violations'))
        row['violations'] = dict(Counter(v for s in sc for v in s.get('violations') or []))
        row['n'] = len(sc)
        row['not_asked'] = sum(1 for pt in pts if not pt[variant]['reply'])
        row['dimensions'] = dict(Counter(pt[variant].get('dimension') for pt in pts if pt[variant]['reply']))
        summ[variant] = row
        lines.append(f"- {variant}：n={row['n']}（不问 {row['not_asked']}）；" + '，'.join(f"{scoring.DIM_ZH[d]} {row.get(d)}" for d in scoring.DIMS)
                     + f"；≥4 {row['ge4']}；违规点 {row['violation_points']} {row['violations']}；维度 {row['dimensions']}")
    usage = relay.usage
    lines.append(f"- DS 新发 {relay.calls_sent} / 缓存 {relay.calls_cached}，token {usage.get('total_tokens', 0)}；用时 {round(time.time() - t0)}s")
    lines.append('')
    for pt in pts:
        lines.append(f"## {pt['name']} {pt['qid']} k={pt['k']}（已深挖 {pt['dims'] or '无'}）")
        for role, t in pt['dialogue'][-2:]:
            lines.append(('> 问：' if role == 'system' else '> 答：') + t.replace('\n', ' ')[:300])
        for variant in ('old', 'new'):
            s = pt[variant].get('score') or {}
            lines.append(f"- {variant}：{pt[variant]['reply'] or '（不问：' + str(pt[variant].get('errors') or pt[variant].get('reason')) + '）'}"
                         + (f"　[{pt[variant].get('dimension')}]〔" + ' '.join(f"{d[:3]}{s.get(d)}" for d in scoring.DIMS)
                            + (f" 违规{s.get('violations')}" if s.get('violations') else '') + '〕' if s else ''))
        lines.append('')
    (run_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    common.save(run_dir / 'bench.json', {'summary': summ, 'usage': usage, 'points': pts})
    print('\n'.join(lines[:5]), flush=True)
    S.ctx.engine.close()


if __name__ == '__main__':
    main()
