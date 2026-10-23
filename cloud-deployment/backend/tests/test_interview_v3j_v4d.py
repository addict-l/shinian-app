"""v3j judgment + v4d speaking layer: switch, flow markers, fallbacks and retries, offline.

Provider calls are replaced by fixtures; the real Node engine of the pinned
runtime bundle validates every proposal. Uses the same isolated App API and
SQLite setup as test_contract_interview_workflow.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_contract_interview_workflow as base  # noqa: E402  (shared env, SQLite and App setup)

BACKEND = Path(__file__).resolve().parents[1]
V3J_RUNTIME = BACKEND / 'app/ai/interview_runtime_v3j_v4d'
os.environ['INTERVIEW_V3J_RUNTIME_DIR'] = str(V3J_RUNTIME)
os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'] = sha256((V3J_RUNTIME / 'manifest.json').read_bytes()).hexdigest()
os.environ.pop('INTERVIEW_PIPELINE', None)

from app.ai import interview_speaker as speaker  # noqa: E402
from app.ai.contract_interview import ContractInterviewPipeline  # noqa: E402
from app.ai.contract_interview_v3j import V3jPipeline, V3jRuntime  # noqa: E402
from app.ai.llm_client import LLMConfigurationError, LLMResponseFormatError, LLMServiceError  # noqa: E402
from app.models.chat_session import ChatSessionModel  # noqa: E402
from app.schemas.story_information import StoryInformation  # noqa: E402
from app.services import contract_v3j_interview as flow  # noqa: E402
from app.services.contract_interview_state import configured_pipeline, questions, runtime, v3j_runtime  # noqa: E402
from app.services.interview_controls import SKIP_ACK  # noqa: E402

V3J = {'INTERVIEW_PIPELINE': 'v3j_v4d'}
DRAFT = '这段可以先整理成草稿了。您还有什么想补充的吗？'


def out(value):
    return {'kind': 'model_call', 'ok': True, 'content': json.dumps(value, ensure_ascii=False), 'output': deepcopy(value),
            'parse_error': None, 'finish_reason': 'stop'}


def judged(**targets):
    return {'control': {'action': 'continue', 'units': []}, 'targets': targets}


def content(*units):
    return {'best': units[0], 'about': '测试', 'kind': 'content', 'concept': 'same', 'match': '测试',
            'units': list(units), 'core': list(units), 'subject': 'self'}


def stated(kind, unit='S1.1'):
    return {'best': unit, 'about': '测试', 'kind': kind, 'concept': 'same', 'match': '', 'units': [unit], 'core': [], 'subject': 'self'}


class Provider:
    """Fixture answers per stage, recognised by the system prompt of the pinned bundle."""

    def __init__(self, judge=(), verify=(), speaker=()):
        self.queues = {'judge': list(judge), 'verify': list(verify), 'speaker': list(speaker)}
        self.seen = []

    def __call__(self, system, user, params, timeout):
        rt = v3j_runtime()
        stage = {rt.judge_prompt: 'judge', rt.verify_prompt: 'verify', rt.speaker_prompt: 'speaker'}[system]
        self.seen.append((stage, user))
        item = self.queues[stage].pop(0)
        if isinstance(item, Exception):
            raise item
        return out(item)

    def count(self, stage):
        return sum(1 for s, _ in self.seen if s == stage)


class FlowTests(unittest.TestCase):
    """The workflow fixture (family, person, session, App client) without re-running its tests."""
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown
    post_life, enter_module = base.WorkflowTests.post_life, base.WorkflowTests.enter_module
    url = property(lambda self: f'/api/v1/chat/sessions/{self.session}/conversation/messages')

    def say(self, text, rid=None, status=201):
        response = self.web.post(self.url, json={'content': text, 'client_request_id': str(rid or uuid4())})
        self.assertEqual(response.status_code, status, response.text)
        return response.json() if status == 201 else response

    def guide(self):
        with base.database.SessionLocal() as db:
            return StoryInformation.model_validate(db.get(ChatSessionModel, str(self.session)).information).guided_interview

    def move_to(self, qid):
        with base.database.SessionLocal.begin() as db:
            row = db.get(ChatSessionModel, str(self.session))
            info = StoryInformation.model_validate(row.information)
            guide = info.guided_interview
            guide.topic_index = [q['id'] for q in questions(guide.module)].index(qid)
            guide.contract_state, guide.pending_question, guide.phase = {}, None, 'opening'
            row.information = info.model_dump(mode='json')

    # --- switch and markers -------------------------------------------------------------------
    def test_switch_defaults_to_v2_and_rejects_unknown_values(self):
        self.assertEqual(configured_pipeline(), 'v2')
        with patch.dict(os.environ, {'INTERVIEW_PIPELINE': 'v3x'}):
            with self.assertRaises(LLMConfigurationError):
                configured_pipeline()
        self.enter_module('family')
        with patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            self.say('我们是在工厂认识的。')
            self.assertEqual(old.call_count, 2)
            new.assert_not_called()
        self.assertNotIn('pipeline', self.guide().contract_state)

    def test_v2_question_in_progress_is_not_taken_over(self):
        self.enter_module('family')
        rid = uuid4()
        with patch.object(ContractInterviewPipeline, '_call', side_effect=[base.response(base.EMPTY), LLMServiceError('down')]):
            self.say('我们是在工厂认识的。', rid, status=502)
        with patch.dict(os.environ, V3J), \
                patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            self.say('我们是在工厂认识的。', rid)  # retry keeps v2 and reuses its saved extractor call
            self.assertEqual(old.call_count, 1)
            reply = self.say('跳过')  # still the v2 question: fixed wording, no speaking layer
            self.assertEqual(reply['messages'][-1]['content'], SKIP_ACK + '\n' + runtime().questions['FM01b']['main_question'])
            new.assert_not_called()
        self.assertNotIn('pipeline', self.guide().contract_history['FM01'])
        provider = Provider(judge=[judged()], speaker=[{'ack': '', 'question': '您们是怎么一起过日子的？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(ContractInterviewPipeline, '_call') as old:
            self.say('我们一起过了很多年。')  # the next question starts in the configured flow
            old.assert_not_called()
        state = self.guide().contract_state
        self.assertEqual((state['question_id'], state['pipeline']), ('FM01b', 'v3j_v4d'))
        self.assertEqual(state['pipeline_manifest_sha256'], os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])

    def test_v3j_question_keeps_its_flow_after_rollback(self):
        self.enter_module('family')
        provider = Provider(judge=[judged(), judged()], speaker=[{'ack': '', 'question': '您结过婚吗？'}] * 3)
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.say('我们是在工厂认识的。')
        with patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(ContractInterviewPipeline, '_call') as old:  # INTERVIEW_PIPELINE back to v2
            self.say('嗯，在工厂。')
            old.assert_not_called()
            self.assertEqual(provider.count('judge'), 2)
            self.say('跳过')
        with patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            self.say('我们一起过了很多年。')  # the question after the rollback is v2 again
            self.assertEqual(old.call_count, 2)
            new.assert_not_called()

    # --- follow-up --------------------------------------------------------------------------------
    def test_follow_up_is_written_by_the_speaker_and_target_stays_the_engines(self):
        self.enter_module('family')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})],
                            speaker=[{'ack': '在工厂认识的。', 'question': '后来在工厂里，您们是怎样慢慢熟悉起来的？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('我们是在工厂认识的。')
        self.assertEqual(reply['messages'][-1]['content'], '在工厂认识的。后来在工厂里，您们是怎样慢慢熟悉起来的？')
        self.assertIsNone(reply['generation_offer'])
        guide = self.guide()
        self.assertEqual(guide.pending_question.target, 'FM01-E2')  # engine's target
        self.assertEqual(guide.pending_question.text, '后来在工厂里，您们是怎样慢慢熟悉起来的？')
        speaker_input = next(u for s, u in provider.seen if s == 'speaker')
        self.assertIn('要问的一点：与伴侣相知的过程', speaker_input)
        self.assertIn('参考问法：后来，您们是怎样慢慢了解彼此的？', speaker_input)
        self.assertIn('答：我们是在工厂认识的。', speaker_input)
        self.assertEqual(guide.contract_state['ask_counts'], {'FM01-E2': 1})
        # The next answer is judged against the question part actually asked.
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S2.1')})],
                            speaker=[{'reply': '天天一起上下班。那您和伴侣平时是怎样相伴生活的？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.say('后来天天一起上下班，慢慢就熟了。')
        judge_input = next(u for s, u in provider.seen if s == 'judge')
        self.assertIn('第2段 原问：后来在工厂里，您们是怎样慢慢熟悉起来的？', judge_input)

    def test_speaker_failure_or_invalid_question_falls_back_to_engine_question(self):
        self.enter_module('family')
        cases = ((LLMServiceError('down'), ''), ({'ack': '', 'question': '那您保存好了吗？'}, ''),
                 ({'ack': '好。', 'question': '您结婚了吗？您爱人呢？'}, '好。'))
        for (answer, ack), qid in zip(cases, ('FM02', 'FM03', 'FM04')):
            self.move_to(qid)  # each case is a fresh question
            provider = Provider(judge=[judged()], speaker=[answer])
            with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
                reply = self.say('那时候日子很平常。')
            engine_question = self.guide().contract_state['last_result']['question']
            self.assertEqual(reply['messages'][-1]['content'], ack + engine_question)
            self.assertEqual(self.guide().pending_question.text, engine_question)
            self.assertTrue(self.guide().contract_state['audit'][-1]['speaker']['fallback'])

    # --- question finished: draft step kept -----------------------------------------------------------
    def test_finished_question_keeps_draft_sentence_and_offer_generation(self):
        self.enter_module('family')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S1.2')})],
                            speaker=[{'reply': '在工厂认识，后来天天一起上下班。那您和伴侣平时是怎样相伴生活的？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。')
        self.assertEqual(reply['messages'][-1]['content'], '在工厂认识，后来天天一起上下班。' + DRAFT)
        self.assertEqual(reply['generation_offer']['message_id'], reply['messages'][-1]['id'])
        self.assertTrue(reply['can_generate'])
        guide = self.guide()
        self.assertEqual(guide.phase, 'supplement')
        self.assertEqual(guide.speaker_last_close, '在工厂认识，后来天天一起上下班。')
        self.assertIn('收尾原因：这个话题已经聊完', next(u for s, u in provider.seen if s == 'speaker'))
        self.assertIn('下一题：' + runtime().questions['FM01b']['main_question'], next(u for s, u in provider.seen if s == 'speaker'))
        # The existing supplement / review step is unchanged.
        with patch.object(V3jPipeline, '_call') as model:
            review = self.say('没有了')
            model.assert_not_called()
        self.assertEqual(review['messages'][-1]['content'], '好，先核对这段草稿，您确认后再保存。')
        self.assertIsNotNone(review['generation_offer'])

    def test_draft_acknowledgement_never_mentions_saving_and_falls_back(self):
        self.enter_module('family')
        for answer in ({'reply': '好，这段我帮您整理成草稿。那您和伴侣平时是怎样相伴生活的？'}, LLMServiceError('down'), {'reply': ''}):
            self.move_to('FM01')  # a fresh question each time: a second answer would be a supplement (C03)
            provider = Provider(judge=[judged(**{'FM01-E1': stated('unknown')})], speaker=[answer])
            with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
                reply = self.say('记不清了。' + str(uuid4())[:4])
            self.assertEqual(reply['messages'][-1]['content'], DRAFT)
            self.assertIsNotNone(reply['generation_offer'])
        self.assertIn('收尾原因：老人说记不清了', next(u for s, u in provider.seen if s == 'speaker'))
        # a transition clause is not shown before the draft sentence
        self.move_to('FM01')
        provider = Provider(judge=[judged(**{'FM01-E1': stated('unknown')})],
                            speaker=[{'reply': '记不清也没关系。那咱们换个话题聊聊，您和伴侣平时是怎样相伴生活的？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('真记不清了。')
        self.assertEqual(reply['messages'][-1]['content'], '记不清也没关系。' + DRAFT)

    # --- refusal: speaker acknowledgement, then the next entry -------------------------------------------
    def test_refusal_is_acknowledged_by_speaker_and_moves_on_without_save(self):
        self.enter_module('family')
        nxt = runtime().questions['FM01b']['main_question']
        provider = Provider(speaker=[{'reply': '好，这个咱们就不多聊了。那' + nxt}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('我不想回答这个问题')
        self.assertEqual(reply['messages'][-1]['content'], '好，这个咱们就不多聊了。那' + nxt)
        self.assertEqual(provider.count('judge'), 0)
        self.assertFalse(reply['can_generate'])
        self.assertIsNone(reply['generation_offer'])
        guide = self.guide()
        self.assertEqual(guide.processed_topics['FM01'], 'skipped')
        self.assertTrue(guide.last_topic_skipped)
        self.assertEqual(guide.contract_state, {})
        self.assertEqual(guide.contract_history['FM01']['pipeline'], 'v3j_v4d')
        self.assertIn('答：我不想回答这个问题', provider.seen[0][1])
        self.assertIn('收尾原因：老人不想多说', provider.seen[0][1])
        # an engine refusal (declined field) takes the same path
        provider = Provider(judge=[judged(**{'FM01-E3': stated('declined')})], speaker=[{'reply': '好，我把这段记录下来。'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('这些事我不想多讲。')
        self.assertEqual(reply['messages'][-1]['content'], SKIP_ACK + '\n' + runtime().questions['FM02']['main_question'])
        self.assertEqual(self.guide().processed_topics['FM01b'], 'skipped')

    def test_refusal_falls_back_to_fixed_sentence_and_keeps_module_menu(self):
        self.enter_module('family')
        provider = Provider(speaker=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('跳过')
        self.assertEqual(reply['messages'][-1]['content'], SKIP_ACK + '\n' + runtime().questions['FM01b']['main_question'])
        self.move_to(questions('family')[-1]['id'])
        provider = Provider(speaker=[{'reply': '好，这个咱们就不多说了。接下来您想聊哪个部分？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('不想回答')
        from app.services.interview_modules import module_menu
        self.assertEqual(reply['messages'][-1]['content'], '好，这个咱们就不多说了。' + module_menu())
        self.assertIn('下一题：' + module_menu(), provider.seen[0][1])
        self.assertIsNone(reply['generation_offer'])
        self.assertEqual(self.guide().phase, 'module_review')

    # --- persistence and retry ---------------------------------------------------------------------------
    def test_retry_resumes_without_repeating_any_model_call(self):
        self.enter_module('family')
        self.move_to('FM07')
        rid, text = uuid4(), '对我来说家人就是一切。没有家人就没有我。'
        provider = Provider(judge=[judged(**{'FM07-E1': content('S1.1', 'S1.2')})], verify=[LLMServiceError('down')])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            self.say(text, rid, status=502)
        self.assertEqual(set(self.guide().contract_state['pending']['calls']), {'judge'})
        verified = {'checks': {'FM07-E1': {'says': '家人是一切', 'answer': '家人就是一切', 'added': '', 'direction': 'content', 'itself': 'yes'}}}
        provider = Provider(verify=[verified], speaker=[{'ack': '没有家人就没有您。', 'question': '有没有哪一刻，让您特别感到家人的意义？'}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(flow, 'finish', side_effect=RuntimeError('crash after the speaking-layer call')):
            with self.assertRaises(RuntimeError):
                self.say(text, rid)
        self.assertEqual((provider.count('judge'), provider.count('verify'), provider.count('speaker')), (0, 1, 1))
        self.assertEqual(set(self.guide().contract_state['pending']['calls']), {'judge', 'verify', 'speaker'})
        provider = Provider()
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say(text, rid)
            self.assertEqual(reply['messages'][-1]['content'], '没有家人就没有您。有没有哪一刻，让您特别感到家人的意义？')
            again = self.say(text, rid)
        self.assertEqual(provider.seen, [])
        self.assertEqual(again['messages'][-1]['id'], reply['messages'][-1]['id'])
        audit = self.guide().contract_state['audit'][-1]
        self.assertEqual(set(audit['calls']), {'judge', 'verify', 'speaker'})
        self.assertEqual(audit['runtime_manifest_sha256'], os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])

    def test_skip_speaker_call_is_persisted_for_retry(self):
        self.enter_module('family')
        rid = uuid4()
        from app.services import contract_guided_interview as guided
        original = guided.skip_topic

        def crash_after_speaker(*args, **kwargs):
            if 'text' in kwargs:  # the speaking layer has answered and been saved
                raise RuntimeError('crash')
            return original(*args, **kwargs)

        provider = Provider(speaker=[{'reply': '好。那' + runtime().questions['FM01b']['main_question']}])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider), \
                patch.object(guided, 'skip_topic', side_effect=crash_after_speaker):
            with self.assertRaises(RuntimeError):
                self.say('跳过', rid)
        self.assertEqual(provider.count('speaker'), 1)
        provider = Provider()
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('跳过', rid)
        self.assertEqual(provider.seen, [])
        self.assertEqual(reply['messages'][-1]['content'], '好。那' + runtime().questions['FM01b']['main_question'])

    def test_pause_signal_keeps_existing_pause(self):
        self.enter_module('family')
        provider = Provider(judge=[judged()])
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            reply = self.say('哎，我有点累了，想先歇一会儿。')
        self.assertEqual(reply['messages'][-1]['content'], '好，先休息。您的讲述和采访位置都已保留。')
        self.assertEqual(provider.count('speaker'), 0)
        self.assertEqual(self.guide().phase, 'paused')


class RuntimeAndSpeakerTests(unittest.TestCase):
    """Bundle integrity, request shape and the pure speaking-layer rules."""

    def setUp(self):
        self.rt = v3j_runtime()

    def copy(self, folder):
        target = Path(folder) / 'runtime'
        shutil.copytree(V3J_RUNTIME, target)
        return target

    def repin(self, target):
        manifest = json.loads((target / 'manifest.json').read_text())
        manifest['files'] = {name: sha256((target / name).read_bytes()).hexdigest() for name in manifest['files']}
        (target / 'manifest.json').write_text(json.dumps(manifest))
        return sha256((target / 'manifest.json').read_bytes()).hexdigest()

    def test_integrity_is_as_strict_as_the_main_runtime(self):
        with self.assertRaises(LLMConfigurationError):
            V3jRuntime(V3J_RUNTIME, '0' * 64)
        with patch.dict(os.environ, {'INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256': ''}), self.assertRaises(LLMConfigurationError):
            V3jRuntime(V3J_RUNTIME)  # no pin, no bundle
        with TemporaryDirectory() as folder:
            target = self.copy(folder)
            (target / 'evidence-units').write_text('module.exports = {}')  # would shadow evidence-units.js
            with self.assertRaises(LLMConfigurationError):
                V3jRuntime(target, os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])
        for change in ({'thinking': 'enabled'}, {'reasoning_effort': 'high'}):
            with TemporaryDirectory() as folder:
                target = self.copy(folder)
                settings = json.loads((target / 'provider-settings.json').read_text())
                settings['judge'].update(change)
                (target / 'provider-settings.json').write_text(json.dumps(settings))
                with self.assertRaises(LLMConfigurationError):
                    V3jRuntime(target, self.repin(target))
        with TemporaryDirectory() as folder:
            target = self.copy(folder)
            (target / 'judge-prompt.txt').write_text('changed')
            with self.assertRaises(LLMConfigurationError):
                V3jRuntime(target, os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])

    def test_bundle_is_the_tested_candidate_on_the_frozen_bank(self):
        for params in (self.rt.judge_params, self.rt.verify_params, self.rt.speaker_params):
            self.assertEqual((params['model'], params['thinking']), ('deepseek-v4-pro', 'disabled'))
        self.assertEqual((self.rt.judge_params['max_tokens'], self.rt.judge_params['temperature']), (1500, 0))
        self.assertEqual((self.rt.verify_params['max_tokens'], self.rt.verify_params['temperature']), (900, 0))
        self.assertEqual((self.rt.speaker_params['max_tokens'], self.rt.speaker_params['temperature']), (200, 0.3))
        self.assertEqual(self.rt.speaker_config['version'], 'v4d')
        self.assertEqual(self.rt.version, runtime().version)
        self.assertEqual([(q['id'], q['main_question']) for q in self.rt.contracts['questions']],
                         [(q['id'], q['main_question']) for q in runtime().contracts['questions']])
        root = BACKEND.parents[1]
        freeze = root / 'docs/question-bank-freeze-v2.json'
        if not (root / 'docs/prototypes/full-interview-v3j').is_dir() or not freeze.exists():
            self.skipTest('docs/prototypes is not part of this checkout')
        self.assertEqual([q['id'] for q in self.rt.contracts['questions']], json.loads(freeze.read_text())['question_ids'])
        check = subprocess.run([sys.executable, str(BACKEND / 'scripts/build_interview_v3j_runtime.py'), '--check'],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertEqual(check.stdout.strip(), os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'])

    def test_opting_in_validates_the_bundle_at_startup(self):
        env = {**os.environ, 'DATABASE_URL': 'sqlite://', 'LLM_MODEL': 'test-only', 'INTERVIEW_PIPELINE': 'v3j_v4d'}
        run = lambda extra: subprocess.run([sys.executable, '-c', 'import app.main'], cwd=BACKEND, env={**env, **extra},
                                           capture_output=True, text=True)
        self.assertEqual(run({}).returncode, 0, run({}).stderr[-500:])
        failed = run({'INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256': '0' * 64})
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('LLMConfigurationError', failed.stderr)
        self.assertNotEqual(run({'INTERVIEW_PIPELINE': 'v3'}).returncode, 0)
        self.assertEqual(run({'INTERVIEW_PIPELINE': '', 'INTERVIEW_V3J_RUNTIME_DIR': ''}).returncode, 0)  # default v2 needs no bundle

    def test_provider_request_has_thinking_disabled_and_no_reasoning_effort(self):
        sdk = Mock()
        sdk.client.with_options.return_value.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content='{}'), finish_reason='stop')], id='synthetic', model='m', usage=None)
        V3jPipeline(self.rt, sdk)._call('system', 'user', self.rt.judge_params, 110.0)
        arguments = sdk.client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(sdk.client.with_options.call_args.kwargs, {'timeout': 110.0, 'max_retries': 0})
        self.assertEqual(arguments['model'], 'deepseek-v4-pro')
        self.assertEqual(arguments['extra_body'], {'thinking': {'type': 'disabled'}})
        self.assertEqual(arguments['response_format'], {'type': 'json_object'})
        self.assertEqual((arguments['temperature'], arguments['max_tokens']), (0, 1500))
        self.assertNotIn('reasoning_effort', arguments)

    def test_saved_call_from_other_input_is_never_reused(self):
        sources = [{'id': 'S1', 'question_id': 'FM07', 'speaker': 'narrator', 'text': '家人就是一切。',
                    'question': self.rt.questions['FM07']['main_question']}]
        pipeline = V3jPipeline(self.rt, None)
        pipeline._call = Mock(return_value=out(judged()))
        first = pipeline.run('FM07', sources)
        changed = deepcopy(sources)
        changed[0]['text'] = '家人不算什么。'
        retry = V3jPipeline(self.rt, None)
        retry._call = Mock()
        with self.assertRaises(LLMResponseFormatError):
            retry.run('FM07', changed, saved_calls=first['calls'])
        retry._call.assert_not_called()
        # v2 stage records cannot satisfy a v3j stage
        v2_saved = {'extractor': {'request_sha256': 'x', 'response': out({})}}
        retry._call = Mock(return_value=out(judged()))
        retry.run('FM07', sources, saved_calls=v2_saved)
        self.assertEqual(retry._call.call_count, 1)
        with self.assertRaises(LLMResponseFormatError):
            pipeline.run('FM07', sources, {'previous_fields': {'FM01-E1': {}}})

    def test_ending_rules_and_acknowledgement_cleaning(self):
        cfg = self.rt.speaker_config
        ask = {'decision': 'ask', 'target': 'FM01-E1', 'effective': {}, 'active': ['FM01-E1']}
        st = lambda **k: {'followups': 0, 'ask_counts': {}, 'prev_eff': {}, **k}
        self.assertEqual(speaker.decide(cfg, ask, st(), '在工厂认识的'), ('ask', 'FM01-E1'))
        self.assertEqual(speaker.decide(cfg, ask, st(), '这个就不多讲了'), ('close', 'declined'))
        self.assertEqual(speaker.decide(cfg, ask, st(), '记不清了'), ('close', 'unknown'))
        self.assertEqual(speaker.decide(cfg, ask, st(), '我有点累了'), ('rest', None))
        self.assertEqual(speaker.decide(cfg, ask, st(followups=2), '嗯'), ('close', 'cap'))
        self.assertEqual(speaker.decide(cfg, ask, st(ask_counts={'FM01-E1': 1}), '嗯'), ('close', 'asked_once'))
        self.assertEqual(speaker.decide(cfg, {'decision': 'ready'}, st(), ''), ('close', 'done'))
        self.assertEqual(speaker.clean_ack(self.rt, '那家里一定很热闹，您是老二。', '我是老二')[0], '您是老二。')
        self.assertEqual(speaker.lead_ack(self.rt, '您说不上标准，那咱们换个话题聊聊。在您看来什么样的事不必计较？',
                                          '在您看来什么样的事不必计较？'), '您说不上标准。')
        self.assertEqual(speaker.lead_ack(self.rt, '好，我帮您保存。那下一题？', '下一题？'), '')


if __name__ == '__main__':
    unittest.main()
