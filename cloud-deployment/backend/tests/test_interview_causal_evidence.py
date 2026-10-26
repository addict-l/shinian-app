"""S01: literal cause selection through the real v3j assembly and Node engine.

The judge payload follows the saved cloud reproduction (both fields cite S1.1).
It is an explicit fixture, not a fresh model call.  The original v5f/v4d bundles
remain unchanged; the new assembly behavior is gated by the listening config.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.ai.contract_interview_v3j import V3jPipeline, V3jRuntime  # noqa: E402


def runtime(enabled=True):
    name = 'interview_runtime_v3j_v5f_listening' if enabled else 'interview_runtime_v3j_v5f'
    directory = BACKEND / 'app/ai' / name
    rt = V3jRuntime(directory, sha256((directory / 'manifest.json').read_bytes()).hexdigest(), 'v3j_v5f')
    assert bool(rt.speaker_config.get('literal_cause_span')) == enabled
    return rt


class CausalEvidenceTests(unittest.TestCase):
    def run_case(self, text, *, enabled=True, subject='self', word='粮站搬货', kind='content', concept='same'):
        rt = runtime(enabled)
        pipeline = V3jPipeline(rt, None)
        targets = {fid: {'best': 'S1.1', 'core': ['S1.1'], 'units': ['S1.1'],
                         'kind': kind, 'concept': concept, 'subject': subject}
                   for fid in ('WK01-E1', 'WK01-E2')}
        targets['WK01-E2']['link_word'] = word
        output = {'control': {'action': 'continue', 'units': []}, 'targets': targets}

        def call(system, user, params, timeout):
            if system == rt.verify_prompt:
                return {'ok': True, 'output': {'checks': {}}}
            self.assertEqual(system, rt.judge_prompt)
            return {'ok': True, 'output': deepcopy(output)}

        pipeline._call = call
        sources = [{'id': 'synthetic-cause', 'text': text, 'speaker': 'narrator', 'question_id': 'WK01',
                    'question': '您最初做的是什么工作？'}]
        return pipeline.run('WK01', sources, {'previous_fields': {}, 'ask_counts': {}})

    def test_explicit_cause_in_shared_sentence_survives_real_engine(self):
        examples = [
            ('因家穷才去粮站搬货。', '家穷'),
            ('因为家里穷，所以我去粮站搬货。', '家里穷'),
            ('我当时因为家里穷才去粮站搬货。', '家里穷'),
            ('当时我因为家穷才去粮站搬货。', '家穷'),
            ('因为家里穷，所以我去了粮站搬货。', '家里穷'),
            ('由于家里穷，我只好去粮站搬货。', '家里穷'),
            ('我去粮站搬货，是因为家里穷。', '家里穷'),
            ('我最初去粮站搬货是因为家穷。', '家穷'),
            ('因父亲生病才去粮站搬货。', '父亲生病'),
            ('因家里没钱才去粮站搬货。', '家里没钱'),
            ('因家窮才去糧站搬貨。', '家窮'),
        ]
        for text, expected in examples:
            with self.subTest(text=text):
                result = self.run_case(text, word='糧站搬貨' if '糧' in text else '粮站搬货')
                fields = result['result']['fields']
                self.assertEqual(result['result']['effective']['WK01-E2'], 'known')
                self.assertNotEqual(result['result']['decision'], 'ask')
                self.assertEqual(fields['WK01-E2']['value'], expected)
                self.assertEqual(fields['WK01-E1']['value'], text)
                self.assertEqual(fields['WK01-E2']['evidence'], [{'source_id': 'synthetic-cause', 'quote': text}])
                self.assertIn(expected, text)
                self.assertEqual(fields['WK01-E2']['links'][0]['field_id'], 'WK01-E1')

    def test_repetition_and_unproven_cause_remain_missing(self):
        for text in ('我去粮站搬货。', '家里穷，我去粮站搬货。',
                     '后来因厂里倒闭才去粮站搬货。', '不是因为家穷才去粮站搬货。',
                     '因家穷才没去粮站搬货。', '因家穷才去纺织厂。',
                     '因为家里穷，所以他去粮站搬货。', '我后来去粮站搬货，是因为家里穷。',
                     '我没有去粮站搬货，是因为家里穷。', '因家穷才想去粮站搬货。',
                     '因为不是家穷才去粮站搬货。', '因什么原因才去粮站搬货。',
                     '因家里穷才让弟弟去粮站搬货。', '因为家里穷，所以老李去粮站搬货。',
                     '因家里穷才我让弟弟去粮站搬货。', '因家里穷才去看弟弟在粮站搬货。',
                     '老李去粮站搬货是因为家里穷。'):
            with self.subTest(text=text):
                result = self.run_case(text)
                self.assertEqual(result['result']['effective']['WK01-E2'], 'missing')

    def test_other_person_and_noncontent_judgments_do_not_gain_cause(self):
        for text, kwargs in (
            ('他因家穷才去粮站搬货。', {'subject': 'self'}),
            ('因家穷才去粮站搬货。', {'subject': 'father'}),
            ('因家穷才去粮站搬货。', {'concept': 'different'}),
        ):
            with self.subTest(text=text, kwargs=kwargs):
                result = self.run_case(text, **kwargs)
                self.assertNotEqual(result['result']['effective']['WK01-E2'], 'known')

    def test_historical_runtime_keeps_original_behavior_without_opt_in(self):
        result = self.run_case('因家穷才去粮站搬货。', enabled=False)
        self.assertEqual(result['result']['effective']['WK01-E2'], 'missing')
        errors = [error for attempt in result['trace']['attempts'] for error in attempt['errors']]
        self.assertIn('WK01-E2:repetition_is_not_explanation', errors)


if __name__ == '__main__':
    unittest.main()
