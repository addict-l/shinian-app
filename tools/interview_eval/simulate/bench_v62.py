#!/usr/bin/env python3
"""BRIEF12 single-step bench: the V6.2 deepen step at the points where a baseline run (V6.1) decided about deepening.

  python3 tools/interview_eval/simulate/bench_v62.py RUN [RUN ...] --name st8-bench1 [--offline] [--json OUT]

For every story question (and, with the V6.2 story memory, every fact question) of the baseline run, at the first
answer where its deepen gate ran (the elements were complete), the V6.2 bundle sees exactly the same dialogue and
the told-story memory of that point (the run's memory seed + the earlier questions of the chain as the baseline
told them). Gate, deepen input and -- when the gate asks -- one DeepSeek deepen call (relay job <name>-p001, cached
by content) give the V6.2 detail question, shown next to what V6.1 asked. Code checks per question: third party,
asks to retell what was told, yes/no frame. Only one turn is replayed; what the elder would answer is not
simulated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import v62_metrics as vm  # noqa: E402
import v6flow  # noqa: E402


def points(S, sess):
    """(record, dialogue up to the gate, reason, latest text, memory) per question, in plan order per chain."""
    st = S.story
    out = []
    chains = {}
    for rec in sess['questions']:
        chains.setdefault(S.module_of(rec['qid']), []).append(rec)
    for module, recs in chains.items():
        memory = []
        seed = vm.seed_text(sess['_plan'], sess['narrator_id'], module)
        if seed:
            path = common.RUNS / sess['_plan']['memory_seed'] / 'sessions' / f"{sess['narrator_id']}.json"
            import run_full
            memory = run_full.seed_items(S, common.load(path)['questions'], module)
        for rec in recs:
            steps = [s for s in rec.get('steps') or [] if s.get('answer')]
            gate = next((s for s in steps if s.get('rule', {}).get('action') == 'close' and not s.get('deepen_answer')
                         and s['rule'].get('reason') not in ('declined', 'deferred')), None)
            if gate is not None:
                ids = [m['id'] for m in rec['messages']]
                upto = ids.index(gate['answer'])
                msgs = rec['messages'][:upto + 1]
                dialogue = [('system', rec['entry'])]
                for m in msgs[1:]:
                    if m['role'] == 'elder' and not m.get('scripted'):
                        prev = [x for x in msgs[:msgs.index(m)] if x['role'] == 'system'][-1]['text']
                        if len(dialogue) > 1:
                            dialogue.append(('system', prev))
                        dialogue.append(('elder', m['text']))
                out.append((rec, dialogue, gate['rule']['reason'], msgs[-1]['text'], list(memory)))
            local = {'question_id': rec['qid'], 'sources': [x for x in rec.get('sources') or [] if not x.get('deepen_answer')],
                     'deepen': {'sources': [x for x in rec.get('sources') or [] if x.get('deepen_answer')]}}
            memory += st.memory_items([local])
    return out


def main(argv):
    name = argv[argv.index('--name') + 1]
    offline = '--offline' in argv
    out_json = argv[argv.index('--json') + 1] if '--json' in argv else None
    runs = [a for a in argv if not a.startswith('--') and a not in (name, out_json)]
    S = v6flow.Setup(version='v6.2')
    rt, st, cfg = S.rt, S.story, S.rt.speaker_config
    mem_cfg = cfg['story_memory']
    rows, calls = [], []
    for run in runs:
        for sess in vm.load_run(run):
            for rec, dialogue, reason, text, memory in points(S, sess):
                qid = rec['qid']
                redirect = qid not in rt.story and S.depth.get(qid) in mem_cfg['redirect_depths']
                if qid not in rt.story and not redirect:
                    continue
                elder_words = ''.join(t for role, t in dialogue if role == 'elder')
                view = st.memory_view(memory, elder_words, mem_cfg)
                dz = st.new_deepen(rt, qid) if qid in rt.story else st.new_redirect(rt, qid)
                dz['asked_text'], dz['before'], dz['last'] = dialogue[-2][1] if len(dialogue) > 2 else rec['entry'], \
                    ''.join(t for role, t in dialogue[:-1] if role == 'elder'), text
                k = sum(1 for role, _ in dialogue if role == 'elder')
                ok, why, info = st.memory_gate(cfg, reason, text, elder_words, dz, k, view)
                old = [e for e in (rec.get('deepen') or {}).get('log') or [] if e.get('decision') == 'asked']
                row = {'run': run, 'person': sess['name'], 'qid': qid, 'depth': S.depth.get(qid), 'reason': reason,
                       'gate': why, 'retold': view['retold'], 'total': view['total'], 'told_items': view['items'][:3],
                       'v61_question': old[0]['question'] if old else None, 'v61_ack': old[0].get('ack') if old else None}
                if ok:
                    dz['told'] = st.told_text(view)
                    user = st.deepen_user(rt, qid, dialogue, dz, view)
                    cid = f'{len(calls):03d}-{qid}'
                    calls.append({'id': cid, 'system': rt.deepen_prompt, 'user': user, 'params': rt.deepen_params})
                    row.update(call=cid, _dz=dz, _words=elder_words, _prior=[rec['entry']])
                rows.append(row)
    relay = common.Relay(common.RUNS / name, offline=offline)
    resp = relay.run_batch(f'{name}-p001', calls) if calls else {}
    for row in rows:
        if 'call' not in row:
            continue
        r = resp[row.pop('call')]
        dz, words, prior = row.pop('_dz'), row.pop('_words'), row.pop('_prior')
        dim, ack, q, errs, fixes = st.compose_deepen(rt, r, dz, prior, words)
        row.update(v62_dimension=dim, v62_ack=ack, v62_question=q, v62_errors=errs, v62_repairs=fixes, v62_raw=r.get('content'),
                   third_party_v61=bool(row['v61_question'] and st.third_party(row['v61_question'])))
    for row in rows:
        row.pop('_dz', None), row.pop('_words', None), row.pop('_prior', None)
        print(json.dumps({k: row.get(k) for k in ('person', 'qid', 'depth', 'gate', 'retold', 'total', 'v61_question',
                                                   'v62_ack', 'v62_question', 'v62_errors')}, ensure_ascii=False))
    print(json.dumps({'points': len(rows), 'calls': len(calls), 'sent': relay.calls_sent, 'cached': relay.calls_cached,
                      'tokens': relay.usage.get('total_tokens', 0)}))
    if out_json:
        common.save(Path(out_json), rows)


if __name__ == '__main__':
    main(sys.argv[1:])
