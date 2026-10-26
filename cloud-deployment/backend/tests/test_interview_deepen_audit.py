"""Deepen call audit retention through real API/SQLite paths; provider output is synthetic.

The first-answer fallbacks previously discarded the deepen entry when clearing
pending, unlike detail-answer turns. Keep both failed calls and successful calls
whose output is rejected or chooses not to ask, including saved-call retries.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_interview_v5f as v5  # noqa: E402

from app.ai.contract_interview_v3j import V3jPipeline  # noqa: E402
from app.ai.llm_client import LLMServiceError  # noqa: E402
from app.services import contract_v3j_interview as flow  # noqa: E402


class AuditProvider(v5.Provider):
    """Add synthetic provider metadata; never represent it as an actual model call."""

    def __call__(self, system, user, params, timeout):
        response = super().__call__(system, user, params, timeout)
        response.update(response_id='fixture-' + self.seen[-1][0], response_model=params['model'],
                        params=deepcopy(params))
        return response


FALLBACKS = {
    'call_failed': LLMServiceError('synthetic provider failure'),
    'invalid': {'dimension': '人物', 'ack': '', 'question': '后来她也调过去了吗？'},
    'model_skip': {'dimension': '', 'ack': '', 'question': ''},
}
CLOSE = {'reply': '噢，原来如此。那您和伴侣平时是怎样相伴生活的？'}


class AuditAssertions:
    def assert_deepen_call(self, record, why, expected_stages):
        self.assertEqual(set(record['calls']), set(expected_stages))
        entry = record['calls']['deepen']
        self.assertEqual(len(entry['request_sha256']), 64)
        self.assertEqual(entry['runtime_manifest_sha256'], v5.v5f_runtime().manifest_sha256)
        self.assertEqual(entry['params'], v5.v5f_runtime().deepen_params)
        self.assertNotIn('reasoning_effort', entry['params'])
        self.assertIn('任务：deepen', entry['payload'])
        request = {'runtime': entry['runtime_manifest_sha256'], 'stage': 'deepen', 'params': entry['params'],
                   'system': v5.v5f_runtime().deepen_prompt, 'user': entry['payload']}
        digest = sha256(json.dumps(request, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()).hexdigest()
        self.assertEqual(entry['request_sha256'], digest)
        response = entry['response']
        if why == 'call_failed':
            self.assertFalse(response['ok'])
            self.assertEqual(response['error'], 'provider_request_failed')
            self.assertNotIn('response_id', response)
        else:
            self.assertTrue(response['ok'])
            self.assertEqual(response['response_id'], 'fixture-deepen')
            self.assertEqual(response['params']['thinking'], 'disabled')
            self.assertNotIn('reasoning_effort', response['params'])


class GuidedAuditTests(AuditAssertions, unittest.TestCase):
    setUp, tearDown = v5.GuidedTests.setUp, v5.GuidedTests.tearDown
    post_life, enter_module = v5.GuidedTests.post_life, v5.GuidedTests.enter_module
    url = v5.GuidedTests.url
    say, guide, move_to = v5.GuidedTests.say, v5.GuidedTests.guide, v5.GuidedTests.move_to
    turn, last = v5.GuidedTests.turn, v5.GuidedTests.last

    def run_first_fallback(self, why):
        self.enter_module('family')
        provider = AuditProvider(judge=[v5.FM01_READY], deepen=[FALLBACKS[why]], speaker=[CLOSE])
        reply = self.turn(v5.FM01_TEXT, provider)
        local = self.guide().contract_state
        self.assertEqual(self.guide().phase, 'supplement')
        self.assertTrue(self.last(reply).endswith(v5.DRAFT))
        self.assertEqual(local['deepen']['log'][-1]['reason'], why)
        self.assertIsNone(local['pending'])
        self.assertEqual(len(local['audit']), 1)
        self.assert_deepen_call(local['audit'][-1], why, ('judge', 'deepen', 'speaker'))

    def test_first_answer_provider_failure_keeps_complete_call(self):
        self.run_first_fallback('call_failed')

    def test_first_answer_invalid_question_keeps_provider_response(self):
        self.run_first_fallback('invalid')

    def test_first_answer_model_skip_keeps_provider_response(self):
        self.run_first_fallback('model_skip')

    def test_first_answer_crash_retry_and_duplicate_preserve_calls_once(self):
        self.enter_module('family')
        rid = uuid4()
        provider = AuditProvider(judge=[v5.FM01_READY], deepen=[FALLBACKS['call_failed']], speaker=[CLOSE])
        with patch.object(flow, 'finish', side_effect=LLMServiceError('synthetic crash after saved calls')):
            self.turn(v5.FM01_TEXT, provider, rid=rid, status=502)
        pending = deepcopy(self.guide().contract_state['pending']['calls'])
        self.assertEqual(set(pending), {'judge', 'deepen', 'speaker'})
        self.assertEqual([item[0] for item in provider.seen], ['judge', 'deepen', 'speaker'])
        empty = AuditProvider()
        first = self.turn(v5.FM01_TEXT, empty, rid=rid)
        local = self.guide().contract_state
        self.assertEqual(local['audit'][-1]['calls'], pending)
        self.assert_deepen_call(local['audit'][-1], 'call_failed', ('judge', 'deepen', 'speaker'))
        duplicate = self.turn(v5.FM01_TEXT, empty, rid=rid)
        self.assertEqual(self.last(first), self.last(duplicate))
        self.assertEqual(self.guide().contract_state['audit'], local['audit'])
        self.assertEqual(empty.seen, [])

    def test_detail_answer_failure_still_retains_call_and_no_new_judgment(self):
        self.enter_module('family')
        self.turn(v5.FM01_TEXT, AuditProvider(judge=[v5.FM01_READY], deepen=[v5.DEEPEN_1]))
        original_fields = deepcopy(self.guide().contract_state['fields'])
        provider = AuditProvider(deepen=[FALLBACKS['call_failed']], speaker=[CLOSE])
        self.turn(v5.ANSWER_1, provider)
        local = self.guide().contract_state
        self.assertEqual(local['fields'], original_fields)
        self.assertEqual(local['audit'][-1]['kind'], 'deepen_answer')
        self.assert_deepen_call(local['audit'][-1], 'call_failed', ('deepen', 'speaker'))
        self.assertEqual(provider.count('judge'), 0)


class SkeletonAuditTests(AuditAssertions, unittest.TestCase):
    setUp, tearDown = v5.SkeletonTests.setUp, v5.SkeletonTests.tearDown
    act, data, move_to, last = (v5.SkeletonTests.act, v5.SkeletonTests.data,
                                v5.SkeletonTests.move_to, v5.SkeletonTests.last)

    def test_first_skeleton_answer_failure_keeps_call_when_moving_on(self):
        self.move_to('SK01c')
        text = '家乡在徐州乡下，村口有一条小河，河边全是柳树，我们小时候天天在那儿摸鱼。'
        provider = AuditProvider(judge=[v5.judged(**{'SK01-E4': v5.content('S1.1'),
                                                    'SK01-E3.place': v5.content('S1.1'),
                                                    'SK01-E3.period': v5.content('S1.1')})],
                                 deepen=[FALLBACKS['call_failed']],
                                 speaker=[{'reply': '小时候常去河边啊。那咱们再聊聊，' + v5.MAIN('SK02')}])
        with patch.dict(os.environ, v5.V5F), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act(text)
        self.assertEqual(life['question_id'], 'SK02')
        local = self.data()['questions']['SK01c']
        self.assertEqual(local['status'], 'known')
        self.assertEqual(local['deepen']['log'][-1]['reason'], 'call_failed')
        self.assert_deepen_call(local['audit'][-1], 'call_failed', ('judge', 'deepen', 'speaker'))


if __name__ == '__main__':
    unittest.main()
