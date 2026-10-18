"""Compare the production adapter with saved actual DS evidence, without calls.

Set TEST_INTERVIEW_FROZEN_RUN to a complete whole-question frozen run, and
optionally TEST_INTERVIEW_MULTITURN_RUN to the historical full development run.
These original records stay external to the application repository. A missing
fixture is explicitly skipped, never treated as a successful DS test.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai.contract_interview import ContractInterviewRuntime


def load(path):
    return json.loads(path.read_text())


class FrozenParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = os.getenv('TEST_INTERVIEW_FROZEN_RUN')
        if not location:
            raise unittest.SkipTest('External frozen real-DS records were not configured')
        cls.frozen_run = Path(location)
        spec = importlib.util.spec_from_file_location('frozen_parity_runner', cls.frozen_run / 'runner.snapshot.py')
        cls.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runner)
        cls.defs = load(cls.frozen_run / 'contracts.snapshot.json')
        cls.runtime = ContractInterviewRuntime(cls.frozen_run / 'runtime',
            sha256((cls.frozen_run / 'runtime/manifest.json').read_bytes()).hexdigest())

    def assert_model_parity(self, payload):
        context = {key: deepcopy(payload.get(key)) for key in ('current_question', 'focus', 'previous_fields', 'ask_counts')}
        actual = self.runtime.build(payload['question_id'], payload['sources'], context)
        expected = self.runner.model_input(payload, self.defs, self.frozen_run / 'runtime')
        expected['source_kind'] = 'live_interview'
        self.assertEqual(actual['model_input'], expected)
        self.assertEqual(actual['payload']['current_question'], payload['current_question'])
        self.assertEqual(actual['payload']['focus'], payload['focus'])
        self.assertEqual(actual['payload']['previous_fields'], payload['previous_fields'])

    def test_real_frozen_payloads_match_runner_payload_for_and_model_input(self):
        checkpoints = 0
        for case in load(self.frozen_run / 'dataset.json')['cases']:
            previous, counts = {}, {}
            for index, turn in enumerate(case['turns']):
                payload = self.runner.payload_for(case, index, self.defs, previous, counts, self.frozen_run / 'runtime')
                self.assert_model_parity(payload)
                record = load(self.frozen_run / 'cases' / case['id'] / f'turn-{index:03d}' / 'result.json')
                self.assertEqual(record['kind'], 'evaluated')
                previous = record['result']['fields']
                target = record['result'].get('target')
                if target:
                    counts[target] = counts.get(target, 0) + 1
                checkpoints += 1
        self.assertGreater(checkpoints, 0)

    def test_real_saved_a_and_b_results_match_frozen_decisions(self):
        checked, stages = 0, set()
        for path in self.frozen_run.glob('cases/*/turn-*/engine-input-*.json'):
            decision_path = path.with_name(path.name.replace('engine-input-', 'decision-'))
            if not decision_path.exists():
                continue
            item = load(path)
            call = {**(item.get('raw_model_response') or {}), 'output': item['proposal']}
            actual = self.runtime.analyze(item['payload'], call)
            self.assertEqual(actual, load(decision_path))
            stages.add('reviewer' if '-review.' in path.name else 'extractor')
            checked += 1
        self.assertGreater(checked, 0)
        self.assertEqual(stages, {'extractor', 'reviewer'})

    def test_review_feedback_matches_each_saved_frozen_a_to_b_input(self):
        checked = 0
        for request in self.frozen_run.glob('cases/*/turn-*/request-*-review.json'):
            stem = request.name.removeprefix('request-').removesuffix('-review.json')
            folder = request.parent
            a_request = load(folder / ('request-' + stem + '.json'))
            call = load(folder / ('response-' + stem + '.json'))
            decision = load(folder / ('decision-' + stem + '.json'))
            model_input = deepcopy(a_request['payload'])
            model_input['source_kind'] = 'live_interview'
            actual = self.runtime.review_input(model_input, call.get('output'), decision)
            expected = load(request)['payload']
            expected['source_kind'] = 'live_interview'
            self.assertEqual(actual, expected)
            checked += 1
        self.assertGreater(checked, 0)

    def test_real_multi_turn_previous_fields_and_explicit_focus_forwarding(self):
        location = os.getenv('TEST_INTERVIEW_MULTITURN_RUN')
        if not location:
            self.skipTest('External historical real multi-turn records were not configured')
        old = Path(location)
        cases = {case['id']: case for case in load(old / 'dataset.json')['cases']}
        paths = sorted(old.glob('cases/*/turn-001/engine-input-*.json'))
        self.assertTrue(paths)
        checked = 0
        for path in paths:
            recorded = load(path)['payload']
            if not recorded.get('previous_fields'):
                continue
            case = cases[path.parents[1].name]
            payload = self.runner.payload_for(case, 1, self.defs, recorded['previous_fields'],
                                               recorded['ask_counts'], self.frozen_run / 'runtime')
            self.assert_model_parity(payload)
            # No current published-transcript gold checkpoint has a focus. This
            # separate wiring probe is explicitly synthetic controller context,
            # not represented as an additional real model interaction.
            focused = deepcopy(case)
            field = next(iter(payload['field_contract']))
            focused['turns'][1]['focus'] = {'field_id': field}
            probe = self.runner.payload_for(focused, 1, self.defs, recorded['previous_fields'],
                                              recorded['ask_counts'], self.frozen_run / 'runtime')
            self.assert_model_parity(probe)
            self.assertEqual(probe['sources'][-1]['target_field_id'], field)
            checked += 1
        self.assertGreater(checked, 0)


if __name__ == '__main__':
    unittest.main()
