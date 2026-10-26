#!/usr/bin/env python3
"""Session plans for the story-question deepening test (v5).

  python3 tools/interview_eval/simulate/plan_story.py   # writes docs/prototypes/full-interview-v5/story-plan.json

Per group of split.json (iteration / holdout), people whose material is question-specific (more than
SMALL_PERSON characters; smaller people remember everything for every question) are eligible when at least
WINDOW story questions have material: questions the test set maps an excerpt to, then questions whose best
related excerpt reaches LEXICAL_MIN on the simulator's own retrieval score (persona.Personas.material). A person's
plan is those WINDOW questions in frozen bank order. Eligible people are sorted by amount of material and a
stratified Random(SEED) subset is taken (token budget). Each group also gets one small-material person whose plan
is reused from an earlier v4d-era run, so the A side is mostly served from cache and the case "the deepen question
asks for something the material does not have" is covered on purpose.
"""
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from persona import Personas, ROOT, SMALL_PERSON, STOP, bigrams  # noqa: E402

SEED = 20261026
WINDOW = 3
LEXICAL_MIN = 4.0
TAKE = {'iteration': 4, 'holdout': 1}
# small-material people with an earlier session on these story questions (iteration: sim-hv4d; holdout: sim-hb-ho1)
SMALL = {'iteration': ('N-3b7bd23f91', ['FM02', 'FM03', 'FM04', 'FM04b']),
         'holdout': ('N-f522cea657', ['FM02', 'FM03', 'FM04', 'FM04b'])}
V5 = ROOT / 'docs/prototypes/full-interview-v5'


def lexical(P, nid, qid):
    terms = P.query_terms(qid)
    best = 0.0
    for e in P.excerpts[nid]:
        qb, tb = bigrams(e['question']) - STOP, bigrams(e['text'][:600]) - STOP
        best = max(best, 2.0 * len(terms & qb) + len(terms & tb) / math.sqrt(max(1, len(tb)) / 20))
    return best


def build():
    P = Personas()
    split = json.loads((ROOT / 'docs/prototypes/full-interview-v4/split.json').read_text(encoding='utf-8'))
    bank = json.loads((V5 / 'story-questions.json').read_text(encoding='utf-8'))
    story = [q['id'] for q in bank['questions'] if q['depth'] == 'story']
    order = P.contracts['default_order']
    out = {'seed': SEED, 'rule': __doc__.strip().splitlines()[2:12]}
    for group in ('iteration', 'holdout'):
        eligible = []
        for nid in split[group]:
            if P.total_chars(nid) <= SMALL_PERSON:
                continue
            mapped = [q for q in story if P.mapped[nid].get(q)]
            lex = sorted(((lexical(P, nid, q), q) for q in story if q not in mapped), key=lambda x: (-x[0], order.index(x[1])))
            picks = (mapped + [q for s, q in lex if s >= LEXICAL_MIN])[:WINDOW]
            if len(picks) >= WINDOW:
                eligible.append({'nid': nid, 'name': P.names[nid], 'chars': P.total_chars(nid),
                                 'questions': sorted(picks, key=order.index),
                                 'mapped': [q for q in picks if q in mapped],
                                 'lexical': {q: round(s, 2) for s, q in lex if q in picks}})
        eligible.sort(key=lambda e: (e['chars'], e['nid']))
        k = TAKE[group]
        r = random.Random(SEED + len(eligible))
        chosen = []
        for j in range(k):
            lo, hi = j * len(eligible) // k, (j + 1) * len(eligible) // k
            chosen.append(eligible[lo + r.randrange(hi - lo)])
        small_nid, small_plan = SMALL[group]
        people = [e['nid'] for e in chosen] + [small_nid]
        plans = {e['nid']: e['questions'] for e in chosen}
        plans[small_nid] = small_plan
        out[group] = {'people': people, 'plans': plans,
                      'story_questions': sum(q in story for nid in people for q in plans[nid]),
                      'eligible': eligible,
                      'small_material': {'nid': small_nid, 'name': P.names[small_nid], 'chars': P.total_chars(small_nid)}}
    (V5 / 'story-plan.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return out


if __name__ == '__main__':
    s = build()
    for g in ('iteration', 'holdout'):
        print(g, s[g]['story_questions'], 'story questions;', len(s[g]['eligible']), 'eligible')
        for nid in s[g]['people']:
            print(' ', nid, s[g]['plans'][nid])
