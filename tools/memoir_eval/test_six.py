#!/usr/bin/env python3
"""0-token checks of the v2 six-chapter book (user decision 2026-11-03 06:42: prologue + one chapter per module).

  python3 tools/memoir_eval/test_six.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book  # noqa: E402
import mb  # noqa: E402


def unit(uid, qid, module, text):
    return {'id': uid, 'qid': qid, 'module': module, 'depth': 'story', 'asked': '问', 'text': text, 'raw': text,
            'status': 'saved', 'clues': []}


class SixChapters(unittest.TestCase):
    def setUp(self):
        cat = mb.catalog()
        by_mod = {}
        for qid, q in cat.items():
            by_mod.setdefault(q['module'], qid)
        self.q = by_mod
        # one short unit per module: the v1 rules would merge all of these (each far below 1500 chars)
        self.units = {('U%02d' % i): unit('U%02d' % i, by_mod[m], m, '我小时候家里种田，' * 3)
                      for i, (m, _, _) in enumerate(mb.MODULES, 1)}
        self.handoff = {'person': {'name': '测试'}, 'questions': []}

    def test_groups_one_per_module(self):
        groups = book.six_groups(self.units)
        self.assertEqual(groups, [[m] for m, _, _ in mb.MODULES])

    def test_no_merge_and_restore(self):
        groups = book.six_groups(self.units)
        ids = list(self.units)
        # planner puts the later_life unit into the family chapter (a move): later_life would vanish
        plan = {'chapters': [{'module': m, 'title': None, 'sections': [{'title': 's', 'units': [u]}], 'closing_units': []}
                             for (m, _, _), u in zip(mb.MODULES, ids) if m != 'later_life']}
        fam = next(c for c in plan['chapters'] if c['module'] == 'family')
        fam['sections'][0]['units'].append(ids[[m for m, _, _ in mb.MODULES].index('later_life')])
        row = {'ok': True, 'output': plan}
        out = book.resolve_plan(self.handoff, dict(self.units), row, 'standard', groups)
        self.assertEqual([c['modules'] for c in out['chapters']], [[m] for m, _, _ in mb.MODULES])
        self.assertTrue(any(x.startswith('module_restored:later_life') for x in out['log']))
        self.assertFalse(any(x.startswith('merged:') for x in out['log']))


if __name__ == '__main__':
    unittest.main()
