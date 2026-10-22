#!/usr/bin/env python3
"""Turn-level replay of the speaking layer on decision points harvested from earlier simulated runs.

  python3 replay_speaker.py --from sim-b0 --name rp-v4a [--speaker-prompt P] [--policy P] [--offline] [--max N]

For every elder answer that received a judgment in the source run, the v4 ending rules decide ask/close given
the dialogue so far, and the speaking layer writes the reply. Only speaker calls are sent (elder answers and
judgments are reused), so a speaker-prompt change costs ~1k tokens per decision point. Output: replies.md.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import interview as iv  # noqa: E402
from score import grounded_words  # noqa: E402


def contexts(S, run, max_per_episode=2):
    out = []
    for f in sorted((common.RUNS / run / 'sessions').glob('*.json')):
        s = common.load(f)
        questions = s['questions']
        for ei, ep in enumerate(s['episodes']):
            next_entry = S.Q[questions[ei + 1]]['main_question'] if ei + 1 < len(questions) else None
            st = {'followups': 0, 'ask_counts': {}, 'prev_eff': {}, 'supplements': 0}
            n = 0
            for j, m in enumerate(ep['messages']):
                if m['role'] == 'system' and m.get('kind') == 'followup':
                    st['followups'] += 1
                    st['ask_counts'][m['target']] = st['ask_counts'].get(m['target'], 0) + 1
                if m['role'] != 'elder' or not m.get('judge'):
                    continue
                if any(x.get('kind') == 'supplement' for x in ep['messages'][:j]):
                    break  # baseline-only supplement loop: not a v4 situation
                judge = m['judge']
                result = {'decision': judge['decision'], 'target': judge['target'], 'question': judge['question'],
                          'effective': judge['effective'], 'active': judge['active']}
                action, arg = iv.v4_decide(S, result, st, m['text'])
                st['prev_eff'] = dict(judge['effective'] or {})
                dialogue = [(x['role'], x['text']) for x in ep['messages'][:j + 1] if not x.get('scripted')]
                out.append({'session': s['session'], 'name': s['name'], 'qid': ep['qid'], 'msg': j, 'action': action, 'arg': arg,
                            'dialogue': dialogue, 'fields': judge['fields'], 'engine_question': judge['question'],
                            'next_entry': next_entry, 'prior': [x.get('question_part') for x in ep['messages'][:j] if x['role'] == 'system'],
                            'episode': ep})
                n += 1
                if n >= max_per_episode or action != 'ask':
                    break
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--from', dest='src', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--speaker-prompt')
    p.add_argument('--policy')
    p.add_argument('--offline', action='store_true')
    p.add_argument('--max', type=int)
    p.add_argument('--sample', type=int, help='seeded random sample of N decision points across all sessions')
    p.add_argument('--seed', type=int, default=7)
    a = p.parse_args()
    S = iv.Setup(a.speaker_prompt, a.policy)
    run_dir = common.RUNS / a.name
    run_dir.mkdir(parents=True, exist_ok=False)
    ctxs = contexts(S, a.src)[:a.max or None]
    if a.sample and a.sample < len(ctxs):
        import random
        keep = set(random.Random(a.seed).sample(range(len(ctxs)), a.sample))
        ctxs = [c for k, c in enumerate(ctxs) if k in keep]
    calls = []
    for k, c in enumerate(ctxs):
        if c['action'] == 'ask':
            user = iv.speaker_user(S, c['qid'], c['dialogue'], c['fields'], 'ask', c['arg'], c['engine_question'])
        elif c['action'] == 'close':
            user = iv.speaker_user(S, c['qid'], c['dialogue'], c['fields'], 'close', reason=c['arg'], next_entry=c['next_entry'])
        else:
            continue
        calls.append({'id': f'rp{k:03d}', 'system': S.speaker_prompt, 'user': user, 'params': S.policy['model']})
        c['call_id'] = f'rp{k:03d}'
    relay = common.Relay(run_dir, offline=a.offline, wait_seconds=900)  # 15 min without relay progress -> stop
    t0 = time.time()
    resp = relay.run_batch(a.name, calls) if calls else {}
    lines = [f'# {a.name}（说话层回放，来源 {a.src}）', '']
    stats = {'ask': 0, 'close': 0, 'fallback': 0, 'verbatim': 0, 'grounded': 0}
    rows = []
    for c in ctxs:
        if 'call_id' not in c:
            continue
        r = resp[c['call_id']]
        ack, q = iv.parse_speaker(r)
        if c['action'] == 'ask':
            ack, _ = iv.clean_ack(ack, ''.join(x for r, x in c['dialogue'] if r == 'elder'))
            errs = iv.check_ask(ack, q, c['prior']) + (['inference_in_question'] if iv.INFER.search(q) else [])
            stats['ask'] += 1
            final_q = q if not errs else (c['engine_question'] or '')
            stats['verbatim'] += final_q.strip() == (c['engine_question'] or '').strip()
            ep = dict(c['episode'])
            ep['messages'] = c['episode']['messages'][:c['msg'] + 1] + [{'role': 'system', 'engine_question': c['engine_question']}]
            g = grounded_words(final_q, ep, c['msg'] + 1)
            stats['grounded'] += bool(g)
            out = iv.join(ack, final_q)
        else:
            text, ack_part, notes, ok = iv.compose_close(ack, c['next_entry'], ''.join(x for r, x in c['dialogue'] if r == 'elder'))
            errs = [] if ok else notes
            stats['close'] += 1
            stats['repaired'] = stats.get('repaired', 0) + (1 if ok and notes else 0)
            out = text if ok else '（回退）' + iv.join(iv.FALLBACK_CLOSE.get(c['arg'], '好的。'), c['next_entry'] or '')
            if ok and notes:
                out += f'　〔修复 {notes}〕'
            g = []
        stats['fallback'] += bool(errs)
        rows.append({**{k: v for k, v in c.items() if k != 'episode'}, 'ack': ack, 'question': q, 'errors': errs, 'reply': out,
                     'usage': r.get('usage'), 'seconds': r.get('seconds')})
        lines.append(f"## {c['name']} {c['qid']} #{c['msg']} {c['action']}:{c['arg']}")
        for role, text in c['dialogue'][-3:]:
            lines.append(('> 问：' if role == 'system' else '> 答：') + text.replace('\n', ' '))
        if c['action'] == 'ask':
            lines.append(f"> 参考问法：{c['engine_question']}")
        lines.append(f"**回复**：{out}" + (f"　〔校验未过 {errs}〕" if errs else '') + (f"　〔贴合词 {g}〕" if g else ''))
        lines.append('')
    usage = relay.usage
    head = [f"决策点 {len(rows)}（追问 {stats['ask']}，收尾 {stats['close']}）；校验未过 {stats['fallback']}；"
            f"追问与固定句相同 {stats['verbatim']}/{stats['ask']}；追问含老人原话词 {stats['grounded']}/{stats['ask']}",
            f"新发 {relay.calls_sent} / 缓存 {relay.calls_cached}；DS token（仅新发）总 {usage.get('total_tokens', 0)}；用时 {round(time.time() - t0, 1)}s", '']
    (run_dir / 'replies.md').write_text('\n'.join(lines[:2] + head + lines[2:]) + '\n', encoding='utf-8')
    common.save(run_dir / 'replies.json', {'stats': stats, 'usage': usage, 'rows': rows})
    print('\n'.join(head))
    S.ctx.engine.close()


if __name__ == '__main__':
    main()
