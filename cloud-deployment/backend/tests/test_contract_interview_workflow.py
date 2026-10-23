"""Existing App API + SQLite persistence, with provider calls replaced by fixtures."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNTIME = Path(os.environ.get('TEST_INTERVIEW_RUNTIME', ROOT / 'app/ai/interview_runtime'))
os.environ['INTERVIEW_RUNTIME_DIR'] = str(RUNTIME)
os.environ['INTERVIEW_RUNTIME_MANIFEST_SHA256'] = sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest()
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['LLM_MODEL'] = 'test-only'
os.environ.pop('LLM_TURN_MODEL', None)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import database
database.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
database.SessionLocal = sessionmaker(bind=database.engine, expire_on_commit=False)
from app.db.base import Base
import app.models
from app.models.family import FamilyModel
from app.models.family_member import FamilyMemberModel
from app.models.chat_session import ChatSessionModel
from app.models.chat_message import ChatMessageModel
from app.schemas.guided_interview import GuidedInterviewState
from app.schemas.story_information import StoryInformation
from app.services import life_overview, guided_interview
from app.services.contract_interview_state import runtime, questions
from app.ai.contract_interview import ContractInterviewPipeline
from app.ai.llm_client import LLMServiceError
from app.api.authentication import current_session
from app.main import app
from fastapi.testclient import TestClient


EMPTY = {'control': {'action': 'continue', 'evidence_unit_ids': []}, 'fields': {}}


def response(proposal):
    if isinstance(proposal, str):
        return {'kind': 'model_call', 'output': None, 'raw_content': proposal, 'parse_error': True, 'finish_reason': 'stop'}
    return {'kind': 'model_call', 'output': deepcopy(proposal), 'raw_content': json.dumps(proposal), 'parse_error': False, 'finish_reason': 'stop'}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        self.family, self.person, self.session = uuid4(), uuid4(), uuid4()
        with database.SessionLocal.begin() as db:
            db.add(FamilyModel(id=str(self.family), name='隔离测试家庭'))
            db.add(FamilyMemberModel(id=str(self.person), family_id=str(self.family), name='测试受访者', relationship='本人',
                created_at=datetime.now(timezone.utc), life_interview=life_overview.new_data()))
            db.add(ChatSessionModel(id=str(self.session), family_id=str(self.family), primary_person_id=str(self.person),
                title='测试采访', session_type='guided_interview', status='active', llm_model='test-only',
                information=StoryInformation(guided_interview=GuidedInterviewState(module_selected=False)).model_dump(mode='json'),
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        app.dependency_overrides[current_session] = lambda: SimpleNamespace(family_id=str(self.family))
        self.web = TestClient(app)
        self.mock_client = patch('app.services.chat_service.ChatService._get_llm_client', return_value=SimpleNamespace())
        self.mock_client.start()

    def tearDown(self):
        self.mock_client.stop()
        app.dependency_overrides.clear()

    def post_life(self, action='answer', text='跳过', rid=None, expected=None):
        overview = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()
        return self.web.post(f'/api/v1/chat/sessions/{self.session}/life-overview/actions', json={
            'action': action, 'text': text, 'client_request_id': str(rid or uuid4()),
            'expected_version': overview['version'] if expected is None else expected})

    def enter_module(self, module):
        for _ in questions('skeleton'):
            self.assertEqual(self.post_life().status_code, 200)
        self.assertEqual(self.post_life('confirm', '').status_code, 200)
        state = self.web.get(f'/api/v1/chat/sessions/{self.session}/state').json()
        result = self.web.post(f'/api/v1/chat/sessions/{self.session}/interview', json={
            'module': module, 'expected_version': state['session']['version']})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_catalog_routes_contain_all_six_modules_and_72_questions(self):
        data = self.web.get('/api/v1/chat/interview-modules').json()
        self.assertEqual([len(row['baseline_questions']) for row in data], [10, 10, 15, 9, 8, 20])
        self.assertEqual(sum(len(row['baseline_questions']) for row in data), 72)
        self.assertEqual(next(q['text'] for q in data[3]['baseline_questions'] if q['id']=='FM03'), runtime().questions['FM03']['main_question'])

    def test_eleven_skeleton_questions_complete_through_existing_api(self):
        seen = []
        for _ in questions('skeleton'):
            before = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()
            self.assertEqual(before['total_questions'], 11)
            seen.append(before['question_id'])
            self.assertEqual(self.post_life().status_code, 200)
        self.assertEqual(seen, [q['id'] for q in questions('skeleton')])
        result = self.post_life('confirm', '').json()['life_overview']
        self.assertEqual(result['status'], 'confirmed')
        self.assertTrue(all(field['status'] == 'skipped' for field in result['fields']))

    def test_skeleton_catalog_order_survives_mysql_json_reordering(self):
        from app.services import contract_life_overview as contract
        for version in ('full-interview-v2.0.0', 'full-interview-v1.29.1'):
            with self.subTest(version=version):
                catalog = questions('skeleton', version)
                with patch.object(contract, 'runtime', return_value=runtime(version)), patch.object(
                        contract, 'questions', return_value=catalog):
                    data = contract.new_data()
                expected = [q['id'] for q in catalog]
                with database.SessionLocal.begin() as db:
                    db.get(FamilyMemberModel, str(self.person)).life_interview = data
                for number, qid in enumerate(expected, 1):
                    # MySQL JSON objects return keys by length, then binary order.
                    with database.SessionLocal.begin() as db:
                        person = db.get(FamilyMemberModel, str(self.person))
                        data = deepcopy(person.life_interview)
                        data['questions'] = dict(sorted(data['questions'].items(), key=lambda row: (len(row[0]), row[0])))
                        person.life_interview = data
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(person, 'life_interview')
                    before = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()
                    self.assertEqual(before['question_id'], qid)
                    self.assertEqual(before['question_number'], number)
                    self.assertEqual(before['total_questions'], len(expected))
                    self.assertEqual([field['topic_id'] for field in before['fields']], expected)
                    self.assertEqual(self.post_life().status_code, 200)
                done = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()
                self.assertEqual(done['status'], 'review')
                self.assertIsNone(done['question_id'])
                self.assertEqual(done['question_number'], len(expected))

    def test_existing_skeleton_progress_and_correction_keep_catalog_order(self):
        from app.services import contract_life_overview as contract
        data = contract.new_data()
        data['questions']['SK01']['status'] = 'known'
        data['questions']['SK03']['status'] = 'known'
        data['questions']['SK01']['pipeline'] = 'v3j_v4d'
        data['questions'] = dict(sorted(data['questions'].items(), key=lambda row: (len(row[0]), row[0])))
        original = deepcopy(data)
        self.assertEqual(contract.view(data).question_id, 'SK01b')
        self.assertEqual(contract.view(data).question_number, 2)
        self.assertEqual(data, original)
        from app.services.contract_v3j_life_overview import next_question
        self.assertEqual(next_question(data, 'SK01'), runtime().questions['SK01b']['main_question'])
        data['pending'] = {'request_id': str(uuid4()), 'request': {'action': 'answer'}, 'question_id': 'SK02', 'asked_question': '此前已问的名字问题', 'calls': {'judge': {'cached': True}}}
        pending = deepcopy(data['pending'])
        self.assertEqual(contract.view(data).question_id, 'SK02')
        self.assertEqual(data['pending'], pending)
        data['pending'] = None
        data['editing_question_id'] = 'SK03d'
        self.assertEqual(contract.view(data).question_id, 'SK03d')
        self.assertEqual(contract.view(data).question_number, 8)
        data['editing_question_id'] = None
        self.assertEqual(contract.view(data).question_id, 'SK01b')

    def test_skeleton_failure_preserves_raw_answer_and_reuses_a_on_retry(self):
        rid = uuid4()
        initial = self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').json()['version']
        with patch.object(ContractInterviewPipeline, '_call', side_effect=[response(EMPTY), LLMServiceError('down')]) as model:
            first = self.post_life(text='村里有很多树。', rid=rid, expected=initial)
            self.assertEqual(first.status_code, 502)
            self.assertEqual(model.call_count, 2)
        with database.SessionLocal() as db:
            data = db.get(FamilyMemberModel, str(self.person)).life_interview
            self.assertEqual(len([turn for turn in data['turns'] if turn['role'] == 'user']), 1)
            self.assertEqual(set(data['pending']['calls']), {'extractor'})
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)) as model:
            retry = self.post_life(text='村里有很多树。', rid=rid, expected=initial)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(retry.json()['life_overview']['question'], '您大概是哪一年出生的？')
            self.assertEqual(self.post_life(text='村里有很多树。', rid=rid, expected=initial).status_code, 200)
            self.assertEqual(model.call_count, 1)

    def test_guided_messages_use_frozen_question_and_retain_pending_calls(self):
        state = self.enter_module('family')
        self.assertIn(runtime().questions['FM01']['main_question'], state['messages'][-1]['content'])
        rid = uuid4()
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        body = {'client_request_id': str(rid), 'content': '我记得那段日子。'}
        with patch.object(ContractInterviewPipeline, '_call', side_effect=[response(EMPTY), LLMServiceError('down')]):
            self.assertEqual(self.web.post(url, json=body).status_code, 502)
        with database.SessionLocal() as db:
            data = db.get(ChatSessionModel, str(self.session)).information['guided_interview']['contract_state']
            self.assertEqual(data['question_id'], 'FM01')
            self.assertEqual(len(data['sources']), 1)
            self.assertEqual(set(data['pending']['calls']), {'extractor'})
            self.assertIn(runtime().questions['FM01']['main_question'], data['sources'][0]['question'])
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)) as model:
            reply = self.web.post(url, json=body)
            self.assertEqual(reply.status_code, 201)
            self.assertEqual(model.call_count, 1)
            replay = self.web.post(url, json=body)
            self.assertEqual(replay.status_code, 201)
            self.assertEqual(model.call_count, 1)

    def test_invalid_protocol_is_saved_and_never_sent_as_repeat_question(self):
        self.enter_module('family')
        rid = uuid4()
        body = {'client_request_id': str(rid), 'content': '我们是同学。'}
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        with patch.object(ContractInterviewPipeline, '_call', return_value=response('{bad')) as model:
            self.assertEqual(self.web.post(url, json=body).status_code, 502)
            self.assertEqual(model.call_count, 3)
            # Only an explicit request retries; each request has at most A/B/repair.
            self.assertEqual(self.web.post(url, json=body).status_code, 502)
            self.assertEqual(model.call_count, 6)
        state = self.web.get(f'/api/v1/chat/sessions/{self.session}/state').json()
        self.assertEqual(state['messages'][-1]['role'], 'user')
        self.assertTrue(state['readiness']['needs_analysis'])
        pending = state['session']['information']['guided_interview']['contract_state']['pending']
        self.assertEqual(len(pending['failed_attempts']), 2)
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)):
            final = self.web.post(url, json=body)
            self.assertEqual(final.status_code, 201)
        audit = final.json()['session']['information']['guided_interview']['contract_state']['audit']
        self.assertEqual([record['result']['decision'] for record in audit], ['invalid', 'invalid', 'ask'])

    def test_new_answer_cannot_strand_an_unfinished_provider_request(self):
        self.enter_module('family')
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        rid = uuid4()
        answer = {'client_request_id': str(rid), 'content': '我记得那段日子。'}
        with patch.object(ContractInterviewPipeline, '_call', side_effect=[response(EMPTY), LLMServiceError('down')]):
            self.assertEqual(self.web.post(url, json=answer).status_code, 502)
        newer = {'client_request_id': str(uuid4()), 'content': '那时候我们还住在老房子。'}
        with patch.object(ContractInterviewPipeline, '_call') as model:
            rejected = self.web.post(url, json=newer)
            self.assertEqual(rejected.status_code, 409)
            model.assert_not_called()
        with database.SessionLocal() as db:
            self.assertIsNone(db.get(ChatMessageModel, newer['client_request_id']))
            pending = db.get(ChatSessionModel, str(self.session)).information['guided_interview']['contract_state']['pending']
            self.assertEqual(pending['request_id'], str(rid))
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)) as model:
            resumed = self.web.post(url, json=answer)
            self.assertEqual(resumed.status_code, 201, resumed.text)
            self.assertEqual(model.call_count, 1)
            # Once B completes, the previously rejected text can be sent normally.
            self.assertEqual(self.web.post(url, json=newer).status_code, 201)
            self.assertEqual(model.call_count, 3)

    def test_same_module_control_keeps_the_pending_subquestion(self):
        self.enter_module('family')
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)) as model:
            answer = self.web.post(url, json={'content': '我记得那段日子。', 'client_request_id': str(uuid4())})
            self.assertEqual(answer.status_code, 201)
            pending = answer.json()['session']['information']['guided_interview']['pending_question']['text']
            repeated = self.web.post(url, json={'content': '聊家庭生活', 'client_request_id': str(uuid4())})
            self.assertEqual(repeated.status_code, 201)
            self.assertEqual(repeated.json()['messages'][-1]['content'], pending)
            self.assertEqual(model.call_count, 2)

    def test_pause_control_is_not_narrative_or_model_input(self):
        self.enter_module('family')
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        with patch.object(ContractInterviewPipeline, '_call') as model:
            paused = self.web.post(url, json={'content': '暂停', 'client_request_id': str(uuid4())})
            self.assertEqual(paused.status_code, 201)
            info = paused.json()['session']['information']
            self.assertEqual(info['guided_interview']['phase'], 'paused')
            self.assertEqual(info['narrative_sources'], [])
            self.assertEqual(info['guided_interview']['contract_state'], {})
            model.assert_not_called()

    def test_following_question_does_not_reuse_other_question_facts(self):
        index = next(i for i,q in enumerate(questions('work')) if q['id']=='WK12')
        state = GuidedInterviewState(module='work', topic_index=index)
        state.contract_state = {'question_id': 'WK12', 'fields': {'WK12-E1': {'state': 'known'}}, 'sources': []}
        following = guided_interview.following(state)
        self.assertEqual(following.topic_index, index+1)
        self.assertEqual(following.contract_state, {})
        self.assertIn('WK12', following.contract_history)
        self.assertEqual(guided_interview.opening_text(following), runtime().questions['WK13']['main_question'])

    def test_legacy_questions_are_not_reinterpreted_under_new_ids(self):
        legacy = GuidedInterviewState(version=2, module='family', topic_index=2)
        self.assertIn('家人一起做过', guided_interview.opening_text(legacy))
        following = guided_interview.following(legacy)
        self.assertEqual(following.version, 3)
        self.assertEqual(following.topic_index, 0)
        self.assertEqual(following.legacy_checkpoint['topic_index'], 2)
        self.assertEqual(following.contract_state, {})

    def test_another_family_cannot_read_or_write_interview(self):
        app.dependency_overrides[current_session] = lambda: SimpleNamespace(family_id=str(uuid4()))
        self.assertEqual(self.web.get(f'/api/v1/chat/sessions/{self.session}/life-overview').status_code, 404)
        self.assertEqual(self.web.post(f'/api/v1/chat/sessions/{self.session}/messages', json={'content': '测试'}).status_code, 404)

    def test_new_session_gate_keeps_existing_v3_and_originals_readable(self):
        with patch.dict(os.environ, {'INTERVIEW_NEW_SESSIONS_ENABLED': '0'}):
            self.assertEqual(GuidedInterviewState().version, 2)
            self.assertNotIn('schema_version', life_overview.new_data())
            legacy = GuidedInterviewState(version=2, module='family', topic_index=2)
            self.assertEqual(guided_interview.following(legacy).version, 2)
            # Stored schema 2 and guided v3 remain operable despite the gate.
            result = self.post_life('answer', '跳过').json()['life_overview']
            self.assertEqual(result['question_id'], 'SK01b')
            for _ in range(10):
                self.assertEqual(self.post_life().status_code, 200)
            self.assertEqual(self.post_life('confirm', '').status_code, 200)
            state = self.web.get(f'/api/v1/chat/sessions/{self.session}/state').json()
            switched = self.web.post(f'/api/v1/chat/sessions/{self.session}/interview', json={
                'module': 'work', 'expected_version': state['session']['version']})
            self.assertEqual(switched.status_code, 200)
            guide = switched.json()['session']['information']['guided_interview']
            self.assertEqual(guide['version'], 3)
            self.assertIn(runtime().questions['WK01']['main_question'], switched.json()['messages'][-1]['content'])
            last = GuidedInterviewState(version=3, module='work', topic_index=11)
            self.assertIn(runtime('full-interview-v1.29.1').questions['WK13']['main_question'], guided_interview.opening_text(guided_interview.following(last)))

    def test_explicit_refusal_moves_next_and_never_offers_generation(self):
        self.enter_module('family')
        url = f'/api/v1/chat/sessions/{self.session}/conversation/messages'
        # A prior answer, including an already exposed offer, must not cause a
        # refusal to ask the user to save it first.
        with patch.object(ContractInterviewPipeline, '_call', return_value=response(EMPTY)):
            self.assertEqual(self.web.post(url,json={'content':'我们在学校认识。','client_request_id':str(uuid4())}).status_code,201)
        rid=str(uuid4());body={'content':'我不想回答这个问题','client_request_id':rid}
        with patch.object(ContractInterviewPipeline, '_call') as model:
            r=self.web.post(url,json=body);self.assertEqual(r.status_code,201,r.text)
            out=r.json();self.assertIn('那我们聊聊下一个话题吧。',out['messages'][-1]['content'])
            self.assertIn(runtime().questions['FM01b']['main_question'],out['messages'][-1]['content'])
            self.assertFalse(out['can_generate']);self.assertIsNone(out['generation_offer'])
            self.assertEqual(out['session']['information']['guided_interview']['processed_topics']['FM01'],'skipped')
            self.assertEqual(out['session']['information']['guided_interview']['contract_state'],{})
            self.assertIn('FM01',out['session']['information']['guided_interview']['contract_history'])
            again=self.web.post(url,json=body);self.assertEqual(again.json()['messages'][-1]['id'],out['messages'][-1]['id'])
            model.assert_not_called()

    def test_skeleton_refusal_skips_without_calling_model(self):
        with patch.object(ContractInterviewPipeline, '_call') as model:
            out=self.post_life(text='不想回答').json()['life_overview']
            self.assertEqual(out['question_id'],'SK01b')
            self.assertEqual(out['fields'][0]['status'],'skipped')
            self.assertIn('那我们聊聊下一个话题吧。',out['turns'][-1]['content'])
            model.assert_not_called()

    def test_last_question_skip_offers_one_module_question_without_save(self):
        self.enter_module('family')
        with database.SessionLocal.begin() as db:
            row=db.get(ChatSessionModel,str(self.session));info=StoryInformation.model_validate(row.information)
            info.guided_interview.topic_index=len(questions('family'))-1
            row.information=info.model_dump(mode='json')
        with patch.object(ContractInterviewPipeline,'_call') as model:
            out=self.web.post(f'/api/v1/chat/sessions/{self.session}/conversation/messages',json={'content':'不想回答','client_request_id':str(uuid4())}).json()
            self.assertEqual(out['messages'][-1]['content'].count('？'),1)
            self.assertIn('接下来您想聊哪个部分',out['messages'][-1]['content'])
            self.assertFalse(out['can_generate']);self.assertIsNone(out['generation_offer']);model.assert_not_called()

    def test_skip_after_provider_failure_retains_original_and_failure_trace(self):
        with patch.object(ContractInterviewPipeline, '_call', side_effect=LLMServiceError('down')):
            self.assertEqual(self.post_life(text='我的原始回答要保留。').status_code,502)
        with patch.object(ContractInterviewPipeline, '_call') as model:
            skipped=self.post_life(text='跳过');self.assertEqual(skipped.status_code,200,skipped.text)
            self.assertEqual(skipped.json()['life_overview']['question_id'],'SK01b');model.assert_not_called()
        with database.SessionLocal() as db:
            data=db.get(FamilyMemberModel,str(self.person)).life_interview
            self.assertEqual(len(data['abandoned_pending_requests']),1)
            self.assertTrue(any(t['content']=='我的原始回答要保留。' for t in data['turns']))

    def test_saved_v1_catalog_keeps_six_question_positions(self):
        from app.services.contract_life_overview import new_data
        with patch('app.services.contract_life_overview.runtime',return_value=runtime('full-interview-v1.29.1')), patch('app.services.contract_life_overview.questions',return_value=questions('skeleton','full-interview-v1.29.1')):
            old=new_data()
        with database.SessionLocal.begin() as db:db.get(FamilyMemberModel,str(self.person)).life_interview=old
        result=self.post_life(text='不想回答').json()['life_overview']
        self.assertEqual(result['total_questions'],6);self.assertEqual(result['question_id'],'SK02')

    def test_refusal_patterns_do_not_match_unknown_or_third_person(self):
        from app.services.interview_controls import skips_question
        for text in ['我不想回答这个问题','不想说了','这个问题我不想回答','跳过','这题不适用']:
            self.assertTrue(skips_question(text),text)
        for text in ['不知道','记不清了','我不想放弃这份工作','父亲不想回答这个问题','我不想回答这个问题的原因是当时很忙']:
            self.assertFalse(skips_question(text),text)


if __name__ == '__main__':
    unittest.main()
