#!/usr/bin/env python3
"""Iteration / holdout split of the 45 development people and per-person session plans.

  python3 tools/interview_eval/simulate/plan.py      # writes docs/prototypes/full-interview-v4/split.json

Split: people sorted by amount of material, cut into consecutive triples; Random(SEED) puts one of each
triple into the holdout group (15) and two into the iteration group (30). Session plan per person: the
4 consecutive questions of the frozen default order that contain the most questions the test set maps
material to (ties: the earliest window). Full simulated runs use a seeded subset of each group.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from persona import Personas, ROOT  # noqa: E402

SEED = 20261022
WINDOW = 4
OUT = ROOT / 'docs/prototypes/full-interview-v4/split.json'


def window_for(P, nid, size=WINDOW):
    order = P.contracts['default_order']
    mapped = set(P.mapped_questions(nid))
    best = None
    for i in range(len(order) - size + 1):
        w = order[i:i + size]
        n = sum(q in mapped for q in w)
        if best is None or n > best[0]:
            best = (n, w)
    return best[1], best[0]


def build():
    P = Personas()
    people = sorted(P.people(), key=lambda n: (P.total_chars(n), n))
    rng = random.Random(SEED)
    holdout, iteration = [], []
    for i in range(0, len(people), 3):
        triple = people[i:i + 3]
        pick = rng.randrange(len(triple))
        for k, nid in enumerate(triple):
            (holdout if k == pick else iteration).append(nid)
    plans = {}
    for nid in people:
        w, n = window_for(P, nid)
        plans[nid] = {'name': P.names[nid], 'chars': P.total_chars(nid), 'questions': w, 'mapped_in_window': n}
    # full-run subsets (token budget): 8 iteration people, 8 holdout people, stratified by material size
    def subset(group, k):
        g = sorted(group, key=lambda n: (P.total_chars(n), n))
        r = random.Random(SEED + len(group))
        out = []
        for j in range(k):
            lo, hi = j * len(g) // k, (j + 1) * len(g) // k
            out.append(g[lo + r.randrange(hi - lo)])
        return out
    split = {'seed': SEED, 'rule': __doc__.strip().splitlines()[3:7], 'iteration': iteration, 'holdout': holdout,
             'iteration_run': subset(iteration, 8), 'holdout_run': subset(holdout, 8), 'plans': plans}
    OUT.write_text(json.dumps(split, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return split


if __name__ == '__main__':
    s = build()
    P = Personas()
    for g in ('iteration_run', 'holdout_run'):
        print(g)
        for nid in s[g]:
            p = s['plans'][nid]
            print(' ', nid, p['name'], p['chars'], p['questions'], p['mapped_in_window'])
    print(len(s['iteration']), len(s['holdout']))
