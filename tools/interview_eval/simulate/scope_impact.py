#!/usr/bin/env python3
"""0-token impact check of the v5d signal scope ("记不清但接着讲"), on every stored elder answer.

  python3 tools/interview_eval/simulate/scope_impact.py [--cloud <dir of 原始记录/*.json>] > scope-impact.txt

Old reading = the shared C01 rules as the backend has them (interview.elder_signal / v4_decide, v5c1 deepen_close and
deepen gate). New reading = the same with policy signal_scope on (interview.signal_scope). Listed:

1. signal: every distinct answer whose literal signal is 'unknown' (or the v5c1 "想不出 / 说不出 / 没什么特别"
   wordings), read in its context (the question just asked, the elder's earlier words in that question): whole or
   partial, with the clauses taken as signal and as new content;
2. decide: every judged answer of the v4 simulated runs where v4_decide (v4d caps, the record's own follow-up counts)
   gives another result;
3. deepen: every deepen answer of the v5 runs where deepen_close gives another result, and every deepen-gate step
   that the old reading stopped at a "can't remember" signal and the new one lets through.

Answers are those of <runs>/*/sessions (simulated runs), datasets/full45.json and, with --cloud, the cloud QA raw
records. Distinct = same text, same question just asked, same earlier words. No model call; deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import interview as iv  # noqa: E402

V4D = common.load(iv.V4 / 'speaker-config.json')
MIN = 15


class Cfg:
    def __init__(self, policy):
        self.policy = policy


def contexts(runs):
    """(source, where, text, question, before, message, episode, index, session) for every elder answer."""
    for run in sorted(p for p in runs.iterdir() if (p / 'sessions').is_dir()):
        for path in sorted((run / 'sessions').glob('*.json')):
            s = common.load(path)
            for ep in s.get('episodes') or []:
                msgs = ep['messages']
                for j, m in enumerate(msgs):
                    if m['role'] != 'elder' or m.get('scripted'):
                        continue
                    q = next((x.get('question_part') or x['text'] for x in reversed(msgs[:j]) if x['role'] == 'system'), '')
                    before = ''.join(x['text'] for x in msgs[:j] if x['role'] == 'elder' and not x.get('scripted'))
                    yield ('sim', f'{run.name}/{s.get("name")}/{ep["qid"]}', m['text'], q, before, m, ep, j, s)


def other_answers(runs, cloud):
    full45 = runs / 'datasets/full45.json'
    if full45.exists():
        for case in common.load(full45)['cases']:
            before = ''
            for t in case['turns']:
                yield ('full45', case['id'], t['source']['text'], t['source'].get('question') or '', before)
                before += t['source']['text']
    if cloud:
        for path in sorted(Path(cloud).glob('*.json')):
            rec = common.load(path)
            prev, before, qid = '', '', None
            for e in rec['events']:
                if e.get('question_id') != qid:
                    qid, before = e.get('question_id'), ''
                if e['role'] == 'respondent':
                    yield ('cloud', f'{path.stem}/{e.get("question_id")}', e['text'], prev, before)
                    before += e['text']
                elif e['role'] == 'interviewer':
                    prev = e['text']


def decide_pair(m, ep, j):
    """v4_decide old / new for a judged answer, with the record's own follow-up state."""
    judge = m['judge']
    st = {'followups': 0, 'ask_counts': {}, 'prev_eff': {}}
    last_target = None
    for x in ep['messages'][:j]:
        if x['role'] == 'system' and x.get('kind') == 'followup':
            st['followups'] += 1
            st['ask_counts'][x['target']] = st['ask_counts'].get(x['target'], 0) + 1
            last_target = x['target']
        if x['role'] == 'elder' and x.get('judge'):
            st['prev_eff'] = dict(x['judge'].get('effective') or {})
    result = {'decision': judge['decision'], 'target': judge['target'], 'effective': judge['effective'], 'active': judge['active']}
    q = next((x.get('question_part') or x['text'] for x in reversed(ep['messages'][:j]) if x['role'] == 'system'), '')
    before = ''.join(x['text'] for x in ep['messages'][:j] if x['role'] == 'elder' and not x.get('scripted'))
    old = iv.v4_decide(Cfg(V4D), result, dict(st), m['text'])
    st2 = dict(st, asked=q, before=before, last_target=last_target)
    new = iv.v4_decide(Cfg({**V4D, 'signal_scope': True, 'scope_min_chars': MIN}), result, st2, m['text'])
    return old, new


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--runs', default=str(common.RUNS))
    ap.add_argument('--cloud')
    a = ap.parse_args()
    runs = Path(a.runs)
    seen, rows = {}, []
    dec, deep, gate = [], [], []
    n_all = n_judged = n_deepen = 0
    for src, where, text, q, before, m, ep, j, s in contexts(runs):
        n_all += 1
        key = (src, text, q, before)
        if key not in seen:
            seen[key] = [where]
        else:
            seen[key].append(where)
        if m.get('judge') and s.get('mode') == 'v4':
            n_judged += 1
            old, new = decide_pair(m, ep, j)
            if old != new:
                dec.append((where, text, m['judge']['decision'], old, new))
        if m.get('deepen_answer'):
            n_deepen += 1
            old = iv.deepen_close(text, None, True)
            new = iv.deepen_close(text, None, True, (q, before, MIN))
            if old != new:
                deep.append((where, text, old, new))
        for e in (ep.get('deepen') or {}).get('log') or []:
            if e.get('k') == sum(1 for x in ep['messages'][:j + 1] if x['role'] == 'elder' and not x.get('scripted')) \
                    and e.get('reason') in ('signal_unknown', 'signal_unknown_extra'):
                sc = iv.signal_scope(text, q, before, MIN, extra=True)
                if sc[0] == 'partial':
                    gate.append((where, text, e['reason'], sc))
    for src, where, text, q, before in other_answers(runs, a.cloud):
        n_all += 1
        seen.setdefault((src, text, q, before), []).append(where)
    for (src, text, q, before), wh in seen.items():
        sig = iv.elder_signal(text)
        extra = bool(iv.DEEPEN_UNKNOWN.search(text or ''))
        if sig == 'unknown' or (extra and sig is None):
            sc = iv.signal_scope(text, q, before, MIN, extra=True)
            rows.append((src, sig or 'extra', sc, text, wh))
    distinct = Counter(k[0] for k in seen)
    print(f'answers {n_all}; distinct (text + question + earlier words) per source {dict(sorted(distinct.items()))}; '
          f'judged v4 answers {n_judged}; deepen answers {n_deepen}; min_chars {MIN}')
    part = [r for r in rows if r[2][0] == 'partial']
    print(f'\n== 1. answers with a "can\'t remember" signal: {len(rows)} distinct, partial {len(part)} ==')
    for src, sig, sc, text, wh in sorted(rows, key=lambda r: (r[2][0] != 'partial', r[0], r[4][0])):
        print(f'[{src}] {sig} -> {sc[0]}  x{len(wh)}  {wh[0]}\n    {text}' +
              (f'\n    signal: {sc[2]}\n    new:    {sc[1]}' if sc[0] == 'partial' else ''))
    print(f'\n== 2. v4_decide changes on judged answers (v4d caps, record state): {len(dec)} of {n_judged} ==')
    for where, text, d, old, new in dec:
        print(f'engine {d}: {old} -> {new}  {where}\n    {text}')
    print(f'\n== 3a. deepen_close changes on deepen answers: {len(deep)} of {n_deepen} ==')
    for where, text, old, new in deep:
        print(f'{old} -> {new}  {where}\n    {text}')
    print(f'\n== 3b. deepen-gate steps stopped by a signal that the new reading lets through: {len(gate)} ==')
    for where, text, reason, sc in gate:
        print(f'{reason} -> partial  {where}\n    {text}\n    new: {sc[1]}')
    summary = {'signal_answers': len(rows), 'partial': len(part), 'partial_by_source': dict(Counter(r[0] for r in part)),
               'decide_changes': len(dec), 'decide_change_kinds': dict(Counter(f'{o[1]}->{n[0]}:{n[1]}' for _, _, _, o, n in dec)),
               'deepen_close_changes': len(deep), 'deepen_gate_changes': len(gate)}
    print('\nsummary ' + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
