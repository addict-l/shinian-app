#!/usr/bin/env python3
"""0-token checks of the v3 book layer (BRIEF11): story plan resolution, guards on added sentences, metrics.

  python3 tools/memoir_eval/test_story.py
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book  # noqa: E402
import mb  # noqa: E402
import story  # noqa: E402


def unit(uid, qid, module, text):
    return {'id': uid, 'qid': qid, 'module': module, 'depth': 'story', 'asked': '问', 'text': text, 'raw': text,
            'status': 'saved', 'clues': []}


def sent(t, add=None, src=()):
    return {'t': t, 'add': add, 'src': list(src)}


def chapter(sents, units=('U1',)):
    return {'title': 't', 'modules': ['childhood'], 'units': list(units),
            'sections': [{'title': 's', 'paragraphs': [{'sentences': sents}]}]}


class Plan(unittest.TestCase):
    def setUp(self):
        cat = mb.catalog()
        q = {}
        for qid, x in cat.items():
            q.setdefault(x['module'], qid)
        self.units = {
            'U1': unit('U1', q['childhood'], 'childhood', '我爸借了田种双季稻。那一年卖了一万斤。后来粮价跌了。'),
            'U2': unit('U2', q['work'], 'work', '我在学校排课。我爸种田的事前面讲过，他借田种稻，粮价跌了以后盖了新房。'),
            'U3': unit('U3', q['reflection'], 'reflection', '我觉得人要踏实。我爸借亲戚的田种双季稻，粮价跌了那几年很辛苦。'),
        }
        self.groups = [['childhood'], ['work'], ['reflection']]

    def test_parse_sents(self):
        self.assertEqual(story.parse_sents('all', 3), [1, 2, 3])
        self.assertEqual(story.parse_sents('1-2,5', 4), [1, 2])
        self.assertEqual(story.parse_sents([3, '1'], 3), [1, 3])
        self.assertEqual(story.parse_sents('2–3', 3), [2, 3])

    def test_story_written_once_and_echoed(self):
        out = {'stories': [{'id': 'S1', 'title': '借田种稻', 'gist': '', 'kind': 'story',
                            'parts': [{'unit': 'U1', 'sents': 'all'}, {'unit': 'U2', 'sents': '2'}, {'unit': 'U3', 'sents': '2'}]},
                           {'id': 'S2', 'title': '排课', 'kind': 'story', 'parts': [{'unit': 'U2', 'sents': '1'}]},
                           {'id': 'S3', 'title': '踏实', 'kind': 'reflection', 'parts': [{'unit': 'U3', 'sents': '1'}]}],
               'chapters': [{'module': 'childhood', 'title': '借田', 'title_quote': '借', 'title_source': 'U1',
                             'sections': [{'title': '借田种稻', 'stories': ['S1']}]},
                            {'module': 'work', 'sections': [{'title': '排课', 'stories': ['S2', 'S1']}]},
                            {'module': 'reflection', 'closing': ['S3'], 'echoes': [{'story': 'S1'}]}]}
        plan = story.resolve({}, self.units, {'ok': True, 'output': out}, self.groups, book.module_id)
        where = Counter(sid for c in plan['chapters'] for s in c['sections'] for sid in s['stories'])
        self.assertEqual(where['S1'], 1)  # placed once although listed twice
        ch1 = plan['chapters'][0]
        tell = {t['id'] for x in ch1['sections'][0]['story_meta'] for t in x['tellings']}
        self.assertEqual(tell, {'U1', 'U2', 'U3'})  # every telling of the story reaches its one section
        rv = plan['chapters'][2]
        self.assertEqual([e['story'] for e in rv['echoes']], ['S1'])
        self.assertEqual(rv['sections'][-1].get('role'), 'closing')
        self.assertIn('story_placed_twice:S1', plan['log'])

    def test_remark_of_a_later_module_goes_back_to_its_chapter_end(self):
        # v3 it1: a whole reflection answer was put into the childhood story; its remark that does not retell the
        # story ("人在一起，日子就有个盼头") belongs at the end of the reflection chapter
        self.units['U3'] = unit('U3', self.units['U3']['qid'], 'reflection', '人在一起，日子就有个盼头。我爸借了田种双季稻，后来粮价跌了。')
        out = {'stories': [{'id': 'S1', 'title': '借田种稻', 'kind': 'story',
                            'parts': [{'unit': 'U1', 'sents': 'all'}, {'unit': 'U3', 'sents': 'all'}]},
                           {'id': 'S2', 'title': '排课', 'kind': 'story', 'parts': [{'unit': 'U2', 'sents': 'all'}]}],
               'chapters': [{'module': 'childhood', 'sections': [{'title': '借田种稻', 'stories': ['S1']}]},
                            {'module': 'work', 'sections': [{'title': '排课', 'stories': ['S2']}]}]}
        plan = story.resolve({}, self.units, {'ok': True, 'output': out}, self.groups, book.module_id)
        rv = [c for c in plan['chapters'] if c['modules'] == ['reflection']][0]
        texts = [t['text'] for s in rv['sections'] for x in s['story_meta'] for t in x['tellings']]
        self.assertEqual(texts, ['人在一起，日子就有个盼头。'])
        self.assertIn('remark_moved:reflection(1 sentences)', plan['log'])

    def test_unplanned_sentence_joins_its_neighbour(self):
        out = {'stories': [{'id': 'S1', 'title': 'x', 'parts': [{'unit': 'U1', 'sents': '1-2'}, {'unit': 'U2', 'sents': 'all'},
                                                                {'unit': 'U3', 'sents': 'all'}]}],
               'chapters': [{'module': 'childhood', 'sections': [{'title': 'x', 'stories': ['S1']}]}]}
        plan = story.resolve({}, self.units, {'ok': True, 'output': out}, self.groups, book.module_id)
        keys = plan['stories']['S1']['keys']
        self.assertIn(['U1', 3], keys)
        self.assertIn('sentences_not_planned:1', plan['log'])
        # the work and reflection modules keep a chapter although the planner moved all their words away
        self.assertEqual([c['modules'][0] for c in plan['chapters']], ['childhood', 'work', 'reflection'])


class Guards(unittest.TestCase):
    def setUp(self):
        self.units = {'U1': unit('U1', 'CH01', 'childhood', '我爸借田种双季稻，卖了一万斤谷子。我那时候在田里割稻，热得很。')}

    def run_guard(self, sents):
        ch = chapter(sents)
        stats = {}
        story.guard([ch], self.units, stats)
        return [x['t'] for s in ch['sections'] for p in s['paragraphs'] for x in p['sentences']], stats

    def test_invented_noun_dropped(self):
        kept, st = self.run_guard([sent('我爸借田种稻。', src=['U1']), sent('他挑着扁担去了粮站。', '画面')])
        self.assertEqual(kept, ['我爸借田种稻。'])
        self.assertEqual(st['guard'], {'noun_lexicon': 1})

    def test_check_nouns(self):
        x = sent('稻田边的老槐树沙沙地响。', '画面')
        x['nouns'] = ['稻田', '老槐树']
        kept, st = self.run_guard([x])
        self.assertEqual(kept, [])
        self.assertEqual(st['guard'], {'noun_check': 1})

    def test_other_person_routine_and_gesture(self):
        kept, st = self.run_guard([sent('他天不亮就下地，天黑透了才回来。', '画面'), sent('校长没说什么，只是拍了拍我的肩膀。', '画面'),
                                   sent('太阳晒得我背上发烫。', '画面'), sent('人家把田交给我爸，是信得过他。', '感受')])
        self.assertEqual(kept, ['太阳晒得我背上发烫。'])
        self.assertEqual(st['guard'].get('other_person', 0) + st['guard'].get('noun_lexicon', 0), 3)

    def test_stock_closings_and_openings(self):
        kept, _ = self.run_guard([sent('这份情，我记到现在。', '收束'), sent('那一万斤谷子，我一直记着。', '收束'),
                                  sent('田里热得很，汗往下淌。', '画面'), sent('田里的稻子一片金黄。', '画面')])
        self.assertEqual(kept, ['这份情，我记到现在。', '田里热得很，汗往下淌。'])

    def test_facts_untouched(self):
        kept, _ = self.run_guard([sent('他天不亮就下地。', None, ['U1'])])
        self.assertEqual(kept, ['他天不亮就下地。'])


class Metrics(unittest.TestCase):
    def test_detail_use(self):
        units = {'U1': {'qid': 'CH01', 'asked': '问', 'text': '我爸借田种双季稻，卖了一万斤谷子。粮站在镇上，挑过去要半天。'}}
        b = {'units': units, 'chapters': [chapter([sent('我爸借田种了双季稻，卖了一万斤谷子。')])], 'not_written': {}}
        self.assertEqual(story.detail_use(b), 0.5)


if __name__ == '__main__':
    unittest.main(verbosity=1)
