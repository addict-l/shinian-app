"""Warm move-on transitions keep the existing listening and question boundaries."""
import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai import interview_speaker as speaker, interview_story as story
from app.services import contract_v3j_interview as service
from app.services import contract_v3j_life_overview as life_service
from tests.test_interview_listening import runtime
import tests.test_interview_v3j_skeleton as skeleton
from tests.test_interview_v3j_v4d import V3J
from app.ai.contract_interview_v3j import V3jPipeline
from app.models.family_member import FamilyMemberModel


class WarmTransitionTests(unittest.TestCase):
    def setUp(self):
        self.old = runtime()
        self.rt = copy.copy(self.old)
        self.rt.speaker_config = dict(self.old.speaker_config, warm_transition=True)
        self.entry = '小时候家里主要靠什么维持生活？'
        self.elder = '我爸胆子大，还借田种双季稻。'
        self.ack = '您爸胆子大，还借田种双季稻。'

    def close(self, reply, seen=(), entry=None, rt=None):
        return story.close_reply(rt or self.rt, reply, self.entry if entry is None else entry, self.elder, seen)

    def test_example_retains_ack_transition_and_original_question(self):
        reply = self.ack + '那咱们再来聊聊，' + self.entry
        text, ack, notes, ok = self.close(reply)
        self.assertTrue(ok)
        self.assertEqual(text, reply)
        self.assertEqual(ack, self.ack)
        self.assertNotIn('transition_fallback', notes)
        self.assertEqual(text.count('？'), 1)

    def test_old_v6_output_remains_unchanged(self):
        reply = self.ack + '那咱们再聊聊，' + self.entry
        text, _, _, ok = self.close(reply, rt=self.old)
        self.assertTrue(ok)
        self.assertEqual(text, self.ack + self.entry)

    def test_safe_model_variants_and_recent_deduplication(self):
        reply = self.ack + '我还想听您讲讲，' + self.entry
        text, _, _, _ = self.close(reply)
        self.assertIn('我还想听您讲讲，', text)
        text, _, notes, _ = self.close(reply, seen=['此前。' + '我还想听您讲讲，' + self.entry])
        self.assertNotIn('我还想听您讲讲，', text)
        self.assertIn('transition_fallback', notes)
        self.assertTrue(text.endswith(self.entry))

    def test_missing_or_unsafe_lead_falls_back_without_invented_content(self):
        for lead in ('', '那您母亲那时很高兴吧，', '那为什么不多讲呢？'):
            with self.subTest(lead=lead):
                text, ack, notes, ok = self.close(self.ack + lead + self.entry)
                self.assertTrue(ok)
                self.assertTrue(ack)
                self.assertEqual(text.count('？'), 1)
                self.assertTrue(text.endswith(self.entry))
                self.assertNotIn('很高兴', text)
                self.assertNotIn('为什么不多讲', text)
                self.assertIn('transition_fallback', notes)

    def test_transition_alone_never_counts_as_listening(self):
        text, ack, notes, _ = self.close('那咱们再来聊聊，' + self.entry)
        self.assertEqual(ack, speaker.LISTENING_FALLBACK)
        self.assertIn('ack_fallback', notes)
        self.assertTrue(text.startswith(ack))
        self.assertTrue(text.endswith(self.entry))

    def test_draft_and_final_close_never_contain_move_on(self):
        reply = self.ack + '那咱们再来聊聊，' + self.entry
        draft = story.draft_ack(self.rt, reply, self.entry, self.elder)
        self.assertEqual(draft, self.ack)
        text, ack, _, ok = story.close_reply(self.rt, self.ack, None, self.elder)
        self.assertTrue(ok)
        self.assertEqual(text, ack)
        self.assertNotIn('聊聊', text)

    def test_skip_transition_uses_same_rules_but_menu_does_not_add_it(self):
        state = SimpleNamespace(speaker_last_close=None, contract_history={}, contract_state={})
        with patch.object(service, 'upcoming', return_value=(self.entry, False)), \
             patch.object(service, '_speak', return_value=({'output': {'reply': '不想多讲也没关系。' + self.entry}}, {})):
            text, audit = service._transition(self.rt, None, state, 'SK03',
                [('elder', '这题我不想说。')], {}, 'declined', {'calls': {}}, None)
        self.assertTrue(text.startswith('不想多讲也没关系。'))
        self.assertTrue(text.endswith(self.entry))
        self.assertEqual(text.count('？'), 1)
        self.assertEqual(audit['close_reason'], 'declined')
        with patch.object(service, 'upcoming', return_value=('接下来想聊哪个话题？', True)), \
             patch.object(service, '_speak', return_value=({'output': {'reply': '不想说也没关系。'}}, {})):
            text, _ = service._transition(self.rt, None, state, 'SK03',
                [('elder', '这题我不想说。')], {}, 'declined', {'calls': {}}, None)
        self.assertNotIn('再来聊聊', text)

    def test_decline_transition_is_not_ack_and_gets_respectful_fallback(self):
        text, ack, notes, ok = story.close_reply(self.rt, '接下来聊聊。' + self.entry,
                                                self.entry, '这题我不想说。', reason='declined')
        self.assertTrue(ok)
        self.assertEqual(ack, story.WARM_DECLINE_ACK)
        self.assertNotIn('接下来聊聊。', text)
        self.assertEqual(text.count('？'), 1)
        self.assertIn('ack_fallback', notes)
        self.assertTrue(text.endswith(self.entry))

    def test_partial_refusal_draft_respects_refusal_without_fake_transition(self):
        state = SimpleNamespace(speaker_last_close=None, contract_history={}, contract_state={})
        with patch.object(service, 'upcoming', return_value=(self.entry, False)), \
             patch.object(service, '_speak', return_value=({'output': {'reply': '接下来聊聊。' + self.entry}}, {})):
            ack, text, audit = service._draft_ack(self.rt, None, state, 'FM01',
                [('elder', '我们是在工厂认识的。'), ('elder', '这段我不想多讲。')], {},
                'declined_partial', {'calls': {}}, None)
        self.assertEqual(ack, story.WARM_DECLINE_ACK)
        self.assertNotIn('接下来聊聊', text)
        self.assertIn(service.DRAFT_TEXT, text)
        self.assertTrue(audit['fallback'])
        self.assertIn('ack_fallback', audit['notes'])

    def test_v61_drops_new_subjective_judgments_but_keeps_actual_facts(self):
        for evaluation in ('听着就亲切。', '真勤快。', '这习惯好。', '心里稳当。'):
            with self.subTest(evaluation=evaluation):
                text, ack, _, _ = self.close(self.ack + evaluation + self.entry)
                self.assertEqual(ack, self.ack)
                self.assertNotIn(evaluation, text)

    def test_seen_close_uses_last_displayed_instead_of_dictionary_order(self):
        last = '好。那咱们再来聊聊，旧问题？'
        older = [{'speaker': {'task': 'close', 'text': '好。那我们再来聊聊，旧问题？'}}]
        state = SimpleNamespace(speaker_last_close=last, contract_history={'a': {'audit': older}}, contract_state={})
        seen = story.seen_with_last(self.rt, service.seen_closes(state), state.speaker_last_close)
        self.assertEqual(seen[-1], last)
        self.assertNotIn(last, story.seen_with_last(self.old, service.seen_closes(state), state.speaker_last_close))
        data = {'speaker_last_close': last, 'questions': {'later': {'audit': older}, 'earlier': {'audit': older}}}
        self.assertEqual(story.seen_with_last(self.rt, life_service.seen_closes(data), data['speaker_last_close'])[-1], last)
        self.assertNotIn(last, story.seen_with_last(self.old, life_service.seen_closes(data), data['speaker_last_close']))


class WarmSkeletonApiTests(unittest.TestCase):
    setUp, tearDown = skeleton.SkeletonFlowTests.setUp, skeleton.SkeletonFlowTests.tearDown
    act, data, move_to, last = (skeleton.SkeletonFlowTests.act, skeleton.SkeletonFlowTests.data,
                                skeleton.SkeletonFlowTests.move_to, skeleton.SkeletonFlowTests.last)

    def test_actual_skeleton_skip_uses_last_displayed_transition(self):
        rt = runtime()
        rt.speaker_config = dict(rt.speaker_config, warm_transition=True)
        self.move_to('SK03c')
        with skeleton.base.database.SessionLocal.begin() as db:
            member = db.get(FamilyMemberModel, str(self.person))
            data = copy.deepcopy(member.life_interview)
            data['speaker_last_close'] = '您家种田。那咱们再来聊聊，旧问题？'
            data['questions']['SK01']['audit'] = [{'speaker': {'task': 'close', 'text': data['speaker_last_close']}}]
            data['questions']['SK03']['audit'] = [{'speaker': {'task': 'close', 'text': '家中有几人。那我们再来聊聊，旧问题？'}}]
            member.life_interview = data
        row = {'ok': True, 'output': {'reply': '这段不多讲也没关系。那咱们再来聊聊，' + skeleton.MAIN('SK03d')}}
        with patch.dict(os.environ, V3J), patch.object(life_service, 'flow_runtime', return_value=rt), \
             patch.object(V3jPipeline, 'speak', return_value=(row, {})):
            result = self.act('跳过')
        text = self.last(result)
        self.assertEqual(result['question_id'], 'SK03d')
        self.assertNotIn('那咱们再来聊聊', text)
        self.assertEqual(text.count('？'), 1)
        self.assertTrue(text.endswith(skeleton.MAIN('SK03d')))


if __name__ == '__main__':
    unittest.main()
