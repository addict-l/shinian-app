"""Skeleton questions (life overview) in the v3j_v4d flow: switch, markers, fallbacks and retries, offline.

Provider calls are replaced by fixtures; the real Node engine of the pinned
runtime bundle validates every proposal. Same isolated App API and SQLite setup
as test_contract_interview_workflow and test_interview_v3j_v4d.
"""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_contract_interview_workflow as base  # noqa: E402
from test_interview_v3j_v4d import V3J, Provider, content, judged  # noqa: E402  (sets the v3j bundle pin)

from app.ai.contract_interview import ContractInterviewPipeline  # noqa: E402
from app.ai.contract_interview_v3j import V3jPipeline  # noqa: E402
from app.ai.llm_client import LLMServiceError  # noqa: E402
from app.models.family_member import FamilyMemberModel  # noqa: E402
from app.schemas.life_overview import LifeOverview  # noqa: E402
from app.services import contract_life_overview as overview  # noqa: E402
from app.services import contract_v3j_interview as flow  # noqa: E402
from app.services.contract_interview_state import questions, runtime  # noqa: E402
from app.services.interview_controls import SKIP_ACK  # noqa: E402

MAIN = lambda qid: runtime().questions[qid]['main_question']  # noqa: E731
REVIEW = '这些是您提供的人生线索。请先核对，有需要更正的地方可以告诉我；确认后再选想聊的部分。'
PAUSE = '好，先休息。您的回答和采访位置都已保留。'


class SkeletonFlowTests(unittest.TestCase):
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown

    def act(self, text='跳过', rid=None, status=200, action='answer', topic=None, version=None):
        current = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()
        body = {'action': action, 'text': text, 'client_request_id': str(rid or uuid4()),
                'expected_version': current['version'] if version is None else version}
        if topic:
            body['topic_id'] = topic
        response = self.web.post(f'/api/v1/chat/sessions/{self.session}/life-overview/actions', json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()['life_overview'] if status == 200 else response

    def data(self):
        with base.database.SessionLocal() as db:
            return deepcopy(db.get(FamilyMemberModel, str(self.person)).life_interview)

    def move_to(self, qid):
        """Questions before ``qid`` were answered earlier (v2, no marker); ``qid`` is next."""
        with base.database.SessionLocal.begin() as db:
            person = db.get(FamilyMemberModel, str(self.person))
            data = deepcopy(person.life_interview)
            for key in data['questions']:
                if key == qid:
                    break
                data['questions'][key]['status'] = 'skipped'
            data['turns'].append({'id': str(uuid4()), 'role': 'assistant', 'content': MAIN(qid), 'created_at': overview.now()})
            person.life_interview = data

    def last(self, life):
        return life['turns'][-1]['content']

    # --- switch and markers -------------------------------------------------------------------
    def test_default_v2_skeleton_is_unchanged(self):
        with patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            life = self.act('村里有很多树。')
            self.assertEqual(old.call_count, 2)
            self.assertEqual(self.last(life), life['question'])  # v2 follow-up: the engine's question alone
            self.assertEqual(life['question'], self.data()['questions']['SK01']['last_result']['question'])
            life = self.act('不想回答')
            self.assertEqual(self.last(life), SKIP_ACK + '\n' + MAIN('SK01b'))
            new.assert_not_called()
        data = self.data()
        self.assertNotIn('speaker_last_close', data)
        self.assertFalse(any('pipeline' in q or 'asked_question' in q for q in data['questions'].values()))
        self.assertEqual(set(data['questions']['SK01']), {'question_id', 'sources', 'fields', 'ask_counts', 'last_result',
                                                          'pending', 'audit', 'status'})

    def test_started_v2_skeleton_question_is_not_taken_over(self):
        rid = uuid4()
        with patch.object(ContractInterviewPipeline, '_call', side_effect=[base.response(base.EMPTY), LLMServiceError('down')]):
            self.act('村里有很多树。', rid, status=502)
        with patch.dict(os.environ, V3J), \
                patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            life = self.act('村里有很多树。', rid)  # retry keeps v2 and reuses its saved extractor call
            self.assertEqual(old.call_count, 1)
            self.assertEqual(life['question_id'], 'SK01')
            self.act('那时候日子很平常。')  # still the v2 question
            self.assertEqual(old.call_count, 3)
            life = self.act('跳过')
            self.assertEqual(self.last(life), SKIP_ACK + '\n' + MAIN('SK01b'))
            new.assert_not_called()
        self.assertNotIn('pipeline', self.data()['questions']['SK01'])
        provider = Provider(judge=[judged()], speaker=[{'ack': '', 'question': '您是在哪儿出生的呀？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(ContractInterviewPipeline, '_call') as old:
            self.act('那地方离城不远。')  # the next skeleton question starts in the configured flow
            old.assert_not_called()
        local = self.data()['questions']['SK01b']
        self.assertEqual(local['pipeline'], 'v3j_v4d')
        self.assertEqual(local['pipeline_manifest_sha256'], os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])

    def test_v3j_skeleton_question_keeps_its_flow_after_rollback(self):
        provider = Provider(judge=[judged(), judged()], speaker=[{'ack': '', 'question': '您是哪一年出生的呀？'},
                                                                 {'reply': '好的。那' + MAIN('SK01b')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.act('我是小时候在村里长大的。')
        with patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(ContractInterviewPipeline, '_call') as old:  # INTERVIEW_PIPELINE back to v2
            life = self.act('嗯，那时候还小。')
            old.assert_not_called()
            self.assertEqual(provider.count('judge'), 2)
            self.assertEqual(self.last(life), '好的。那' + MAIN('SK01b'))  # same target asked once: close

    def test_saved_legacy_catalog_stays_on_v2(self):
        from app.services.contract_life_overview import new_data
        with patch('app.services.contract_life_overview.runtime', return_value=runtime('full-interview-v1.29.1')), \
                patch('app.services.contract_life_overview.questions', return_value=questions('skeleton', 'full-interview-v1.29.1')):
            old = new_data()
        with base.database.SessionLocal.begin() as db:
            db.get(FamilyMemberModel, str(self.person)).life_interview = old
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call') as new:
            life = self.act('不想回答')
            new.assert_not_called()
        self.assertEqual((life['total_questions'], life['question_id']), (6, 'SK02'))
        self.assertIn(SKIP_ACK, self.last(life))

    # --- follow-up --------------------------------------------------------------------------------
    def test_follow_up_is_written_by_the_speaker_and_falls_back_to_engine_question(self):
        provider = Provider(judge=[judged()], speaker=[{'ack': '在村里长大的。', 'question': '那您大概是哪一年出生的呀？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('我是在村里长大的。')
        self.assertEqual(self.last(life), '在村里长大的。那您大概是哪一年出生的呀？')
        self.assertEqual((life['question_id'], life['question']), ('SK01', '那您大概是哪一年出生的呀？'))
        speaker_input = next(u for s, u in provider.seen if s == 'speaker')
        self.assertIn('当前话题：' + MAIN('SK01'), speaker_input)
        self.assertIn('答：我是在村里长大的。', speaker_input)
        self.assertIn('要问的一点：出生时间', speaker_input)
        local = self.data()['questions']['SK01']
        self.assertEqual((local['status'], local['asked_target'], local['ask_counts'], local['followups']),
                         ('pending', 'SK01-E1', {'SK01-E1': 1}, 1))
        # The next answer is judged against the question part actually asked. The same target was asked once,
        # so the ending rules close (v4d same_target_cap); the speaker fails and the fixed close follows.
        provider = Provider(judge=[judged()], speaker=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('那时候家里很穷。')
        self.assertIn('第2段 原问：那您大概是哪一年出生的呀？', next(u for s, u in provider.seen if s == 'judge'))
        speaker_input = next(u for s, u in provider.seen if s == 'speaker')
        self.assertIn('问：在村里长大的。那您大概是哪一年出生的呀？\n答：那时候家里很穷。', speaker_input)
        self.assertIn('收尾原因：这一点刚才问过了', speaker_input)
        self.assertEqual(self.last(life), '我记下了。' + MAIN('SK01b'))
        local = self.data()['questions']['SK01']
        self.assertEqual((local['status'], local['asked_question']), ('unknown', None))
        self.assertTrue(local['audit'][-1]['speaker']['fallback'])
        # A follow-up whose speaker call fails is the engine question.
        provider = Provider(judge=[judged()], speaker=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('我是在外婆家生的。')
        engine_question = self.data()['questions']['SK01b']['last_result']['question']
        self.assertEqual(self.last(life), engine_question)
        self.assertEqual((life['question_id'], life['question']), ('SK01b', engine_question))
        self.assertTrue(self.data()['questions']['SK01b']['audit'][-1]['speaker']['fallback'])

    # --- question finished: close into the next skeleton question ----------------------------------------
    def test_finished_question_closes_into_next_skeleton_question(self):
        self.move_to('SK03c')
        provider = Provider(judge=[judged(**{'SK03-E3': content('S1.1')})],
                            speaker=[{'reply': '您有一个哥哥。那咱们再聊聊，' + MAIN('SK03d')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('我有一个哥哥。')
        text = '您有一个哥哥。那咱们再聊聊，' + MAIN('SK03d')
        self.assertEqual(self.last(life), text)
        self.assertEqual((life['question_id'], life['question']), ('SK03d', MAIN('SK03d')))
        speaker_input = provider.seen[-1][1]
        self.assertIn('收尾原因：这个话题已经聊完', speaker_input)
        self.assertIn('下一题：' + MAIN('SK03d'), speaker_input)
        self.assertNotIn('上次换话题时你说的', speaker_input)
        data = self.data()
        self.assertEqual(data['questions']['SK03c']['status'], 'known')
        self.assertEqual(data['speaker_last_close'], text)
        # The overview field is projected exactly as on the v2 path.
        field = next(f for f in life['fields'] if f['topic_id'] == 'SK03c')
        self.assertEqual(field['evidence'], [{'message_id': data['turns'][-2]['id'], 'quote': '我有一个哥哥。'}])
        # The next close is told what was said last time; a reply that fails the checks falls back.
        provider = Provider(judge=[judged(**{'SK03-E4': content('S1.1')})], speaker=[{'reply': '好，我帮您保存下来。'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('家里人相处得很和睦。')
        self.assertIn('上次换话题时你说的：' + text, provider.seen[-1][1])
        self.assertEqual(self.last(life), '我记下了。' + MAIN('SK04'))
        self.assertEqual(self.data()['speaker_last_close'], '我记下了。' + MAIN('SK04'))
        provider = Provider(judge=[judged(**{'SK04-E1': content('S1.1')})], speaker=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('家里人都教我做人要老实。')
        self.assertEqual(life['question_id'], 'SK04')  # SK04 asks the personality-effect follow-up
        self.assertEqual(self.last(life), self.data()['questions']['SK04']['last_result']['question'])

    def test_ending_rule_closes_an_engine_follow_up_with_v2_status(self):
        self.move_to('SK03d')
        provider = Provider(judge=[judged()], speaker=[{'reply': '记不清也没关系。那咱们换个话题聊聊，' + MAIN('SK04')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('这个我真记不太清了。')
        self.assertEqual(self.data()['questions']['SK03d']['last_result']['decision'], 'ask')
        self.assertEqual(self.last(life), '记不清也没关系。那咱们换个话题聊聊，' + MAIN('SK04'))
        self.assertEqual(self.data()['questions']['SK03d']['status'], 'unknown')
        self.assertIn('收尾原因：老人说记不清了', provider.seen[-1][1])
        self.assertEqual(life['question_id'], 'SK04')

    def test_last_skeleton_question_keeps_the_review_text(self):
        self.move_to('SK06')
        provider = Provider(judge=[judged(**{'SK06-E1': content('S1.1'), 'SK06-E2': content('S1.2')})], verify=[{'checks': {}}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('平平淡淡。因为一辈子没有大起大落。')
        self.assertEqual(self.data()['questions']['SK06']['status'], 'known')
        self.assertEqual(provider.count('speaker'), 0)
        self.assertEqual(self.last(life), REVIEW)
        self.assertEqual((life['status'], life['question_id']), ('review', None))
        self.assertEqual(self.act('', action='confirm')['status'], 'confirmed')

    # --- refusal ---------------------------------------------------------------------------------------
    def test_refusal_is_acknowledged_by_speaker_and_falls_back(self):
        provider = Provider(speaker=[{'reply': '好，这个咱们就不多聊了。那' + MAIN('SK01b')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('不想回答')
        self.assertEqual(self.last(life), '好，这个咱们就不多聊了。那' + MAIN('SK01b'))
        self.assertEqual(provider.count('judge'), 0)
        self.assertIn('收尾原因：老人不想多说', provider.seen[0][1])
        self.assertIn('答：不想回答', provider.seen[0][1])
        self.assertEqual(self.data()['questions']['SK01']['status'], 'skipped')
        self.assertEqual(self.data()['questions']['SK01']['sources'], [])
        provider = Provider(speaker=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('跳过')
        self.assertEqual(self.last(life), SKIP_ACK + '\n' + MAIN('SK01c'))
        # the elder saying he does not want to talk about it (engine still asking) takes the same path
        provider = Provider(judge=[judged()], speaker=[{'reply': '好，我把这段记录下来。'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('家乡的事我不想多讲。')
        self.assertEqual(self.last(life), SKIP_ACK + '\n' + MAIN('SK02'))
        self.assertEqual(self.data()['questions']['SK01c']['status'], 'declined')
        self.assertEqual(life['question_id'], 'SK02')

    # --- pause -----------------------------------------------------------------------------------------
    def test_pause_signal_keeps_existing_pause(self):
        provider = Provider(judge=[judged()])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('哎，我有点累了，想先歇一会儿。')
            self.assertEqual(self.last(life), PAUSE)
            self.assertTrue(life['paused'])
            self.assertEqual((life['question_id'], life['question']), ('SK01', MAIN('SK01')))
            life = self.act('继续')
        self.assertEqual(self.last(life), '好，我们接着聊。' + MAIN('SK01'))
        self.assertEqual(provider.count('speaker'), 0)

    # --- persistence and retry ---------------------------------------------------------------------------
    def test_retry_resumes_without_repeating_any_model_call(self):
        self.move_to('SK03c')
        rid, text, version = uuid4(), '我有一个哥哥。', self.data()['version']
        provider = Provider(judge=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.act(text, rid, status=502)
        self.assertEqual(self.data()['pending']['calls'], {})
        provider = Provider(judge=[judged(**{'SK03-E3': content('S1.1')})], speaker=[{'reply': '您有一个哥哥。那' + MAIN('SK03d')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch('app.services.contract_v3j_life_overview.finish', side_effect=RuntimeError('crash after the speaking-layer call')):
            with self.assertRaises(RuntimeError):
                self.act(text, rid)
        self.assertEqual((provider.count('judge'), provider.count('speaker')), (1, 1))
        self.assertEqual(set(self.data()['pending']['calls']), {'judge', 'speaker'})
        self.assertNotIn('speaker_last_close', self.data())
        provider = Provider()
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act(text, rid, version=version)
            again = self.act(text, rid, version=version)
        self.assertEqual(provider.seen, [])
        self.assertEqual(self.last(life), '您有一个哥哥。那' + MAIN('SK03d'))
        self.assertEqual(again['turns'], life['turns'])
        audit = self.data()['questions']['SK03c']['audit']
        self.assertEqual(set(audit[-1]['calls']), {'judge', 'speaker'})
        self.assertEqual(len([t for t in life['turns'] if t['role'] == 'user' and t['content'] == text]), 1)

    def test_skip_speaker_call_is_persisted_for_retry(self):
        rid = uuid4()
        provider = Provider(speaker=[{'reply': '好。那' + MAIN('SK01b')}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(overview, '_reply', side_effect=RuntimeError('crash after the speaking-layer call')):
            with self.assertRaises(RuntimeError):
                self.act('跳过', rid)
        self.assertEqual(provider.count('speaker'), 1)
        provider = Provider()
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('跳过', rid)
        self.assertEqual(provider.seen, [])
        self.assertEqual(self.last(life), '好。那' + MAIN('SK01b'))

    def test_v3j_overview_is_readable_and_confirmed_quotes_feed_background(self):
        self.move_to('SK06')
        provider = Provider(judge=[judged(**{'SK06-E1': content('S1.1'), 'SK06-E2': content('S1.2')})], verify=[{'checks': {}}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.act('平平淡淡。因为一辈子没有大起大落。')
        self.act('', action='confirm')
        from app.services.life_overview import background, read
        LifeOverview.model_validate(read(self.person).model_dump())
        stored = {ref['quote'] for f in self.data()['questions']['SK06']['fields'].values() for ref in f.get('evidence', [])}
        self.assertTrue(stored)
        self.assertEqual({q.quote for q in background(self.person)}, stored)


if __name__ == '__main__':
    unittest.main()
