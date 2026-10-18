"""Guard source ownership and failure isolation at the answer-gate seam."""
import json
import tempfile
import unittest
from pathlib import Path

import run


class AnswerGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freeze = run.ROOT / 'docs/prototypes/full-interview-evaluation/run-single-question-v2-round001'
        data = json.loads((cls.freeze / 'dataset.json').read_text())
        case = next(row for row in data['cases'] if row['question_id'] == 'RV06b')
        turn = next((cls.freeze / 'cases' / case['id']).glob('turn-*'))
        cls.payload = json.loads((turn / 'request-000.json').read_text())['payload']

    def test_unanswered_target_remains_open(self):
        proposal = run.compile_verdict(self.payload, {'fields': {'RV06-E2': {'state': 'missing'}}})
        with tempfile.TemporaryDirectory() as temp:
            result = run.baseline.analyze(self.freeze, self.payload, proposal, Path(temp) / 'input.json')
        self.assertEqual(result['fields']['RV06-E2']['state'], 'missing')
        self.assertEqual(result['decision'], 'ask')

    def test_fabricated_source_pointer_cannot_become_answer(self):
        with self.assertRaisesRegex(ValueError, 'invalid evidence unit IDs'):
            run.compile_verdict(self.payload, {'fields': {'RV06-E2': {
                'state': 'known', 'value_unit_ids': ['MADE_UP.1'],
                'proof_unit_ids': ['MADE_UP.1'], 'subject': 'self', 'period': 'lifelong'}}})

    def test_another_question_field_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid field or state'):
            run.compile_verdict(self.payload, {'fields': {'RV06-E1': {'state': 'missing'}}})

    def test_processing_fault_cannot_be_compiled_as_missing(self):
        with self.assertRaisesRegex(ValueError, 'invalid verdict root'):
            run.compile_verdict(self.payload, None)

    def test_null_optional_metadata_does_not_invalidate_supported_answer(self):
        data = json.loads((self.freeze / 'dataset.json').read_text())
        case = next(row for row in data['cases'] if row['question_id'] == 'CH02b')
        turn = next((self.freeze / 'cases' / case['id']).glob('turn-*'))
        payload = json.loads((turn / 'request-000.json').read_text())['payload']
        verdict = {'fields': {'CH02-E2': {'state': 'known', 'value_unit_ids': ['S1.6'],
                   'proof_unit_ids': ['S1.1', 'S1.6'], 'subject': 'self', 'period': 'childhood',
                   'links': None, 'precision': None, 'stance': None}}}
        proposal = run.compile_verdict(payload, verdict)
        field = proposal['fields']['CH02-E2']
        self.assertNotIn('links', field)
        self.assertNotIn('precision', field)
        self.assertNotIn('stance', field)
        with tempfile.TemporaryDirectory() as temp:
            result = run.baseline.analyze(self.freeze, payload, proposal, Path(temp) / 'input.json')
        self.assertNotEqual(result['decision'], 'invalid')


if __name__ == '__main__':
    unittest.main()
