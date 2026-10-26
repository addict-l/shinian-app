"""Listening candidate guards: real composition, fixed provider replies, no network."""
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from tests import test_interview_v5f as base
from app.ai.contract_interview_v3j import V3jRuntime
from app.ai import interview_speaker as speaker, interview_story as story

RUNTIME = Path(__file__).resolve().parents[1] / 'app/ai/interview_runtime_v3j_v5f_listening'


def runtime():
    return V3jRuntime(RUNTIME, sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest(), 'v3j_v5f')


class ListeningTests(unittest.TestCase):
    def setUp(self):
        self.rt = runtime()
        self.elder = '师傅每天收工以后还留我认机器，我那时候总记错，他一遍一遍教。'
        self.question = '师傅后来怎么教您的？'
        self.dz = {'asked': 0, 'dims': []}

    def deepen(self, ack):
        row = {'ok': True, 'output': {'dimension': '人物', 'ack': ack, 'question': self.question}}
        return story.compose_deepen(self.rt, row, self.dz, [], self.elder)

    def test_short_grounded_ack_is_not_removed_as_repetition(self):
        ack = '师傅收工后还陪着您呢。'
        _, actual, q, errors, _ = self.deepen(ack)
        self.assertEqual(actual, ack)
        self.assertEqual(q, self.question)
        self.assertEqual(errors, [])

    def test_empty_ack_never_yields_bare_deepen_and_is_disclosed(self):
        _, ack, q, errors, fixes = self.deepen('')
        self.assertTrue(ack)
        self.assertEqual(q, self.question)
        self.assertEqual(errors, [])
        self.assertIn('ack_fallback', fixes)

    def test_ungrounded_praise_is_not_used_to_satisfy_ack(self):
        for text in ('真贴心。', '您真细心。', '这个名字有深意。', '您一定很感动。'):
            with self.subTest(text=text):
                _, ack, _, _, fixes = self.deepen(text)
                self.assertNotEqual(ack, text)
                self.assertTrue(ack)
                self.assertIn('ack_fallback', fixes)

    def test_followup_keeps_target_and_adds_ack(self):
        result = {'question': '您为什么去做这份工作？'}
        row = {'ok': True, 'output': {'ack': '', 'question': result['question']}}
        text, q, spoken = speaker.compose_ask(self.rt, row, result, 'WK01-E2', [], '我去粮站搬货。')
        self.assertEqual(q, result['question'])
        self.assertTrue(spoken['ack'])
        self.assertTrue(text.startswith(spoken['ack']))
        self.assertIn('ack_fallback', spoken['repairs'])
        self.assertTrue(spoken['fallback'])

    def test_module_menu_fallback_is_disclosed(self):
        from app.services import contract_v3j_interview as service
        state = SimpleNamespace(speaker_last_close=None, contract_history={}, contract_state={})
        with patch.object(service, 'upcoming', return_value=('接下来想聊哪个话题？', True)), \
             patch.object(service, '_speak', return_value=({'ok': False}, {})):
            text, spoken = service._transition(self.rt, None, state, 'FM01',
                [('elder', self.elder)], {}, 'done', {'calls': {}}, None)
        self.assertTrue(text.startswith(speaker.LISTENING_FALLBACK))
        self.assertIn('ack_fallback', spoken['notes'])
        self.assertTrue(spoken['fallback'])

    def test_transition_and_draft_have_ack_before_next_question(self):
        entry = self.rt.questions['SK02']['main_question']
        for reply in (entry, '嗯。'+entry, '真仔细。'+entry):
            text, ack, notes, ok = story.close_reply(self.rt, reply, entry, self.elder)
            self.assertTrue(ok)
            self.assertTrue(ack)
            self.assertTrue(text.startswith(ack))
            self.assertTrue(text.endswith(entry))
            self.assertIn('ack_fallback', notes)
            self.assertTrue(story.draft_ack(self.rt, reply, entry, self.elder))

    def test_comma_joined_ack_is_kept_instead_of_generic_fallback(self):
        entry = self.rt.questions['SK01b']['main_question']
        text, ack, notes, ok = story.close_reply(self.rt, '一九五二年，那'+entry, entry, '我是一九五二年出生的。')
        self.assertTrue(ok)
        self.assertEqual(ack, '一九五二年。')
        self.assertNotIn('ack_fallback', notes)
        entry = self.rt.questions['SK01c']['main_question']
        text, ack, notes, ok = story.close_reply(self.rt, '苏州的小村庄，那咱们再聊聊，'+entry, entry, '我出生在苏州的小村庄。')
        self.assertEqual(ack, '苏州的小村庄。')
        self.assertNotIn('ack_fallback', notes)

    def test_common_evaluations_do_not_survive_close_cleaning(self):
        entry = self.rt.questions['SK04']['main_question']
        for praise in ('真好。', '这个挺重要。', '这习惯真好。', '挺有意思。', '这个画面真温暖。', '这两个词听着就实在。'):
            text, ack, _, _ = story.close_reply(self.rt, '家里有事会一起商量。'+praise+entry, entry, '家里有事会一起商量。')
            self.assertNotIn(praise, text)
            self.assertEqual(ack, '家里有事会一起商量。')

    def test_comma_lead_cannot_smuggle_a_second_question_without_question_mark(self):
        entry = self.rt.questions['SK01b']['main_question']
        for extra in ('您当时多大', '后来怎么样了', '那后来呢'):
            text, ack, notes, ok = story.close_reply(self.rt, extra+'，那'+entry, entry, '我是一九五二年出生的。')
            self.assertNotIn(extra, text)
            self.assertTrue(text.endswith(entry))
            self.assertIn('ack_fallback', notes)

    def test_ack_repetition_in_question_is_allowed(self):
        ack = '原来是师傅牵的线。'
        row = {'ok': True, 'output': {'dimension': '人物', 'ack': ack, 'question': '师傅牵线时怎么说的？'}}
        _, got, _, errs, _ = story.compose_deepen(self.rt, row, self.dz, [], '后来是师傅给我们牵的线。')
        self.assertEqual(got, ack)
        self.assertFalse(errs)

    def test_skip_or_failed_deepen_does_not_turn_into_fixed_question(self):
        for row, reason in (({'ok': False}, 'call_failed'), ({'ok': True, 'output': {}}, 'model_skip')):
            self.assertIn(reason, story.compose_deepen(self.rt, row, self.dz, [], self.elder)[3])

    def test_old_v4d_and_v5f_keep_empty_ack_behavior(self):
        row = {'ok': True, 'output': {'ack': '', 'question': self.question}}
        for rt in (base.v3j_runtime(), base.v5f_runtime()):
            text, _, spoken = speaker.compose_ask(rt, row, {'question': self.question}, 'WK01-E2', [], self.elder)
            self.assertEqual(text, self.question)
            self.assertEqual(spoken['ack'], '')

    def test_prompt_and_config_require_listening_and_thinking_off(self):
        self.assertTrue(self.rt.speaker_config['listen_first'])
        for prompt in (self.rt.speaker_prompt, self.rt.deepen_prompt):
            self.assertNotIn('多数时候留空', prompt)
            self.assertNotIn('ack 通常留空', prompt)
        for params in (self.rt.judge_params, self.rt.verify_params, self.rt.speaker_params, self.rt.deepen_params):
            self.assertEqual(params['thinking'], 'disabled')
            self.assertNotIn('reasoning_effort', params)
