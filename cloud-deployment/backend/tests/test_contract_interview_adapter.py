"""Offline integration guards; real DS acceptance lives in the frozen runs."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai.contract_interview import ContractInterviewPipeline, ContractInterviewRuntime
from app.ai.llm_client import LLMConfigurationError, LLMResponseFormatError, LLMServiceError


RUNTIME = Path(os.environ.get('TEST_INTERVIEW_RUNTIME',
    Path(__file__).resolve().parents[1] / 'app/ai/interview_runtime'))


def response(proposal):
    raw = proposal if isinstance(proposal, str) else json.dumps(proposal, ensure_ascii=False)
    try:
        output, error = json.loads(raw), None
    except ValueError:
        output, error = None, 'JSONDecodeError'
    return {'kind': 'model_call', 'output': output, 'raw_content': raw,
            'parse_error': error, 'finish_reason': 'stop'}


EMPTY = {'control': {'action': 'continue', 'evidence_unit_ids': []}, 'fields': {}}


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.digest = sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest()
        cls.runtime = ContractInterviewRuntime(RUNTIME, cls.digest)

    def sources(self, qid='SK01'):
        return [{'id': 'S1', 'question_id': qid, 'speaker': 'narrator',
                 'text': '我记得村里有很多树。', 'question': self.runtime.questions[qid]['main_question']}]

    def pipeline(self, answers):
        pipeline = ContractInterviewPipeline(self.runtime, None)
        pipeline._call = Mock(side_effect=answers)
        return pipeline

    def test_manifest_is_required_and_must_match(self):
        with self.assertRaises(LLMConfigurationError):
            ContractInterviewRuntime(RUNTIME, '0' * 64)

    def test_thinking_cannot_be_reenabled_even_with_valid_manifest(self):
        import shutil
        with TemporaryDirectory() as folder:
            copy = Path(folder) / 'runtime'
            shutil.copytree(RUNTIME, copy)
            settings = json.loads((copy / 'provider-settings.json').read_text())
            settings['thinking'] = 'enabled'
            (copy / 'provider-settings.json').write_text(json.dumps(settings))
            manifest = json.loads((copy / 'manifest.json').read_text())
            manifest['files']['provider-settings.json'] = sha256((copy / 'provider-settings.json').read_bytes()).hexdigest()
            (copy / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(LLMConfigurationError):
                ContractInterviewRuntime(copy, sha256((copy / 'manifest.json').read_bytes()).hexdigest())

    def test_bundle_has_all_questions_and_uses_original_engine(self):
        self.assertEqual(len(self.runtime.questions), 83)
        self.assertEqual(sum(len(q['elements']) for q in self.runtime.questions.values()), 216)
        built = self.runtime.build('SK01', self.sources())
        self.assertIn('evidence_units', built['model_input'])
        self.assertNotIn('ask_counts', built['model_input'])
        result = self.runtime.analyze(built['payload'], response(EMPTY))
        self.assertEqual(result['decision'], 'ask')
        self.assertEqual(result['target'], 'SK01-E1')

    def test_cross_question_state_and_sources_are_rejected(self):
        with self.assertRaises(LLMResponseFormatError):
            self.runtime.build('SK01', self.sources('SK02'))
        with self.assertRaises(LLMResponseFormatError):
            self.runtime.build('SK01', self.sources(), {'previous_fields': {'SK02-E2': {}}})

    def test_actual_question_is_preserved_and_never_fabricated(self):
        sources = self.sources()
        sources[0]['question'] = '您大概是哪一年出生的？'
        self.assertEqual(self.runtime.build('SK01', sources)['payload']['current_question'], sources[0]['question'])
        del sources[0]['question']
        built = self.runtime.build('SK01', sources)
        self.assertEqual(built['payload']['current_question'], '')
        self.assertFalse(built['model_input']['historical_question_verified'])

    def test_every_extraction_is_reviewed_and_saved_before_next_call(self):
        pipeline = self.pipeline([response(EMPTY), response(EMPTY)])
        stages = []
        result = pipeline.run('SK01', self.sources(), save_call=lambda stage, entry: stages.append(stage))
        self.assertEqual(stages, ['extractor', 'reviewer'])
        self.assertEqual(pipeline._call.call_count, 2)
        self.assertEqual(result['result']['decision'], 'ask')
        self.assertEqual(result['internal_repairs'], 0)
        review = pipeline._call.call_args_list[1].args[1]['semantic_review']
        self.assertEqual(review['unverified_candidate'], EMPTY)

    def test_only_one_protocol_repair_and_invalid_never_becomes_user_question(self):
        pipeline = self.pipeline([response('{bad'), response('{bad'), response('{bad')])
        result = pipeline.run('SK01', self.sources())
        self.assertEqual(pipeline._call.call_count, 3)
        self.assertEqual(result['internal_repairs'], 1)
        self.assertEqual(result['result']['decision'], 'invalid')
        self.assertIsNone(result['result']['question'])

    def test_transport_retry_reuses_durable_a_and_does_not_redo_it(self):
        saved = {}
        pipeline = self.pipeline([response(EMPTY), LLMServiceError('unavailable')])
        with self.assertRaises(LLMServiceError):
            pipeline.run('SK01', self.sources(), save_call=lambda stage, entry: saved.update({stage: entry}))
        self.assertEqual(set(saved), {'extractor'})
        retry = self.pipeline([response(EMPTY)])
        result = retry.run('SK01', self.sources(), saved_calls=saved)
        self.assertEqual(retry._call.call_count, 1)
        self.assertEqual(result['result']['decision'], 'ask')

    def test_pending_call_cannot_be_reused_for_changed_source(self):
        first = self.pipeline([response(EMPTY), response(EMPTY)]).run('SK01', self.sources())
        changed = self.sources()
        changed[0]['text'] = '我记得村里没有树。'
        retry = self.pipeline([])
        with self.assertRaises(LLMResponseFormatError):
            retry.run('SK01', changed, saved_calls=first['calls'])
        self.assertEqual(retry._call.call_count, 0)

    def test_saved_invalid_protocol_result_keeps_exact_three_calls(self):
        first = self.pipeline([response('{bad'), response('{bad'), response('{bad')]).run('SK01', self.sources())
        retry = self.pipeline([])
        replay = retry.run('SK01', self.sources(), saved_calls=first['calls'])
        self.assertEqual(retry._call.call_count, 0)
        self.assertEqual(replay['result'], first['result'])

    def test_provider_request_always_disables_thinking(self):
        sdk = Mock()
        sdk.client.with_options.return_value.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(EMPTY)), finish_reason='stop')],
            id='synthetic-response', model=self.runtime.settings['model'], usage=None)
        pipeline = ContractInterviewPipeline(self.runtime, sdk)
        pipeline._call('system', {'source': 'synthetic'})
        arguments = sdk.client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments['model'], self.runtime.settings['model'])
        self.assertEqual(arguments['extra_body']['thinking'], {'type': 'disabled'})
        self.assertNotIn('reasoning_effort', arguments['extra_body'])
        self.assertNotIn('temperature', arguments)


if __name__ == '__main__':
    unittest.main()
