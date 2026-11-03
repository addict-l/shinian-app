"""Cache hits answer under the request id; the 0-token replay ignores saved call ids.

Run: python3 -m unittest discover -s tools/interview_eval/tests
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'simulate'))


class RunBatchIdTest(unittest.TestCase):
    def test_cache_hit_takes_request_id(self):
        import common
        with tempfile.TemporaryDirectory() as tmp:
            old = common.CACHE
            common.CACHE = Path(tmp)
            try:
                relay = common.Relay.__new__(common.Relay)
                relay.dry = None
                relay.fresh = False
                relay.offline = True
                relay.calls_cached = 0
                call = {'id': 'N-6733a23cd1:WK05::WK05-a1-t1-judge', 'system': 's', 'user': 'u',
                        'params': {'model': 'deepseek-v4-pro', 'thinking': 'disabled'}}
                stored = {'id': 's03-N-63f4aa2206::WK05-a1-t1-judge', 'ok': True, 'content': '{}', 'output': {}}
                (Path(tmp) / (common.Relay.key(call) + '.json')).write_text(json.dumps(stored), encoding='utf-8')
                out = relay.run_batch('t', [call])
            finally:
                common.CACHE = old
        row = out[call['id']]
        self.assertEqual(row['id'], call['id'])
        self.assertTrue(row['cached'])
        self.assertEqual(row['content'], '{}')


class ReplayNormTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('SHINIAN_EVAL_HOME', tempfile.gettempdir())
        import v6_replay
        self.norm = v6_replay._norm

    def test_call_id_prefix_ignored(self):
        a = {'calls': [{'id': 's03-N-63f4aa2206::WK05-a1-t1-judge', 'content': 'x', 'cached': True}],
             'messages': [{'calls': [{'id': 'WK05-e0-sim'}]}]}
        b = {'calls': [{'id': 'N-6733a23cd1:WK05::WK05-a1-t1-judge', 'content': 'x'}],
             'messages': [{'calls': [{'id': 'WK05-e0-sim'}]}]}
        self.assertEqual(self.norm(a), self.norm(b))

    def test_content_and_question_part_still_compared(self):
        a = {'calls': [{'id': 'p::WK05-a1-t1-judge', 'content': 'x'}]}
        self.assertNotEqual(self.norm(a), self.norm({'calls': [{'id': 'p::WK05-a1-t1-judge', 'content': 'y'}]}))
        self.assertNotEqual(self.norm(a), self.norm({'calls': [{'id': 'p::WK05-a1-t1-judge', 'content': 'x'},
                                                                 {'id': 'p::WK05-a2-judge-1', 'content': 'x'}]}))

    def test_other_simulator_id_ignored(self):
        a = {'calls': [{'id': 's03-N-63f4aa2206::WK05-a1-t1-judge', 'content': 'x'}]}
        b = {'calls': [{'id': 'N-6733a23cd1:WK05::WK05-a2-judge-1', 'content': 'x'}]}
        self.assertEqual(self.norm(a), self.norm(b))

    def test_ids_outside_calls_kept(self):
        self.assertNotEqual(self.norm({'id': 'a::x'}), self.norm({'id': 'b::x'}))


if __name__ == '__main__':
    unittest.main()
