"""v3j judgment + v5f speaking layer (story-question deepening, signal scope, warm wording guards), offline.

Model calls are FIXED FIXTURES (Provider), not real model output; the real Node engine of the pinned v3j_v5f bundle
validates every proposal. Same isolated App API and SQLite setup as test_contract_interview_workflow.

Covered: the bundle (pin, the 23 story-question labels checked against the catalog), the switch (default v2 and
v3j_v4d unchanged, questions started in v3j_v4d keep it), deepening on the guided interview (trigger after ready,
answers kept and not judged, the cap of 2 and of 1 on sensitive questions, short answers, failed or invalid deepen
calls fall back to the draft step, retries reuse saved calls, skip / tired while a detail question waits), the
partial "can't remember" reading, the skeleton story question SK01c, and the backend functions against the
simulator's own (same texts in, same results out).

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_v5f -v
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_contract_interview_workflow as base  # noqa: E402
import test_interview_v3j_skeleton as skeleton  # noqa: E402  (module: its tests are not run twice)
import test_interview_v3j_v4d as guided  # noqa: E402  (sets the v3j_v4d bundle pin)
from test_interview_v3j_v4d import DRAFT, V3J, content, judged, out  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
V5F_RUNTIME = BACKEND / 'app/ai/interview_runtime_v3j_v5f'
os.environ['INTERVIEW_V5F_RUNTIME_DIR'] = str(V5F_RUNTIME)
os.environ['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256'] = sha256((V5F_RUNTIME / 'manifest.json').read_bytes()).hexdigest()

from app.ai import interview_speaker as speaker  # noqa: E402
from app.ai import interview_story as story  # noqa: E402
from app.ai import interview_style as style  # noqa: E402
from app.ai.contract_interview import ContractInterviewPipeline  # noqa: E402
from app.ai.contract_interview_v3j import V3jPipeline, V3jRuntime  # noqa: E402
from app.ai.llm_client import LLMConfigurationError, LLMServiceError  # noqa: E402
from app.services.contract_interview_state import v3j_runtime, v5f_runtime  # noqa: E402

V5F = {'INTERVIEW_PIPELINE': 'v3j_v5f'}
MAIN = skeleton.MAIN
FM01_TEXT = '我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。'  # engine ready with FM01-E1 / E2
FM01_READY = judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S1.2')})
DEEPEN_1 = {'dimension': '人物', 'ack': '', 'question': '一起上下班那阵子，她后来怎么样了？'}
DEEPEN_2 = {'dimension': '场景', 'ack': '', 'question': '头一回见面以后，你们后来是怎么约着出去的？'}
ANSWER_1 = '她后来调到别的车间去了，可每天下班还在厂门口等我，一等就是大半年。'
ANSWER_2 = '后来我们就约着去看电影，看完再沿着河边走回厂里的宿舍，一走就是一个钟头。'


class Provider:
    """Fixture answers per stage, recognised by the system prompt of the bundle that sent the request."""

    def __init__(self, judge=(), verify=(), speaker=(), deepen=()):
        self.queues = {'judge': list(judge), 'verify': list(verify), 'speaker': list(speaker), 'deepen': list(deepen)}
        self.seen = []

    def __call__(self, system, user, params, timeout):
        prompts = {}
        for rt in (v3j_runtime(), v5f_runtime()):
            prompts.update({rt.judge_prompt: 'judge', rt.verify_prompt: 'verify', rt.speaker_prompt: 'speaker'})
        prompts[v5f_runtime().deepen_prompt] = 'deepen'
        stage = prompts[system]
        self.seen.append((stage, user, system))
        if not self.queues[stage]:
            raise AssertionError(f'no {stage} fixture left for: {user[-300:]}')
        item = self.queues[stage].pop(0)
        if isinstance(item, Exception):
            raise item
        return out(item)

    def count(self, stage):
        return sum(1 for s, _, _ in self.seen if s == stage)

    def inputs(self, stage):
        return [u for s, u, _ in self.seen if s == stage]


def load_simulator():
    """tools/interview_eval/simulate/interview.py and style.py, when this checkout has them."""
    sim = ROOT / 'tools/interview_eval/simulate'
    if not (sim / 'interview.py').exists():
        raise unittest.SkipTest('tools/interview_eval is not part of this checkout')
    for path in (str(sim.parent), str(sim)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import interview  # noqa: F401
    import style as sim_style  # noqa: F401
    return interview, sim_style


# --------------------------------------------------------------------------- bundle
class BundleTests(unittest.TestCase):
    def test_v5f_bundle_pins_and_labels(self):
        rt = v5f_runtime()
        self.assertEqual((rt.pipeline, rt.version), ('v3j_v5f', v3j_runtime().version))
        self.assertEqual(len(rt.story), 23)
        self.assertEqual({q for q, item in rt.story.items() if item.get('sensitive')}, {'WK09', 'FM03', 'RV02'})
        self.assertEqual(rt.deepen_params, {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 200,
                                            'temperature': 0.3, 'json_mode': True})
        self.assertEqual(rt.speaker_config['version'], 'v5f')
        # the judgment layer is the very same files as the v3j_v4d bundle
        for name in ('engine.js', 'contracts.json', 'judge-prompt.txt', 'verify-prompt.txt', 'opencc-ts-char-map.json'):
            self.assertEqual((V5F_RUNTIME / name).read_bytes(), (guided.V3J_RUNTIME / name).read_bytes(), name)
        # the v5 files are the simulator's tested originals
        for name, source in (('speaker-prompt.txt', 'speaker-prompt.txt'), ('speaker-config.json', 'speaker-config.json'),
                             ('deepen-prompt.txt', 'deepen-prompt.txt'), ('story-questions.json', 'story-questions.json')):
            original = ROOT / 'docs/prototypes/full-interview-v5' / source
            if original.exists():
                self.assertEqual((V5F_RUNTIME / name).read_bytes(), original.read_bytes(), name)

    def test_bundle_integrity_and_pipeline(self):
        digest = os.environ['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']
        with self.assertRaises(LLMConfigurationError):  # the v4d bundle is not a v5f bundle
            V3jRuntime(guided.V3J_RUNTIME, sha256((guided.V3J_RUNTIME / 'manifest.json').read_bytes()).hexdigest(), 'v3j_v5f')
        with self.assertRaises(LLMConfigurationError):  # nor the other way round
            V3jRuntime(V5F_RUNTIME, digest, 'v3j_v4d')
        with self.assertRaises(LLMConfigurationError):
            V3jRuntime(V5F_RUNTIME, '0' * 64, 'v3j_v5f')
        with TemporaryDirectory() as tmp:
            # labels that do not match the catalog are refused even with a consistent, re-pinned manifest
            target = Path(tmp) / 'bundle'
            shutil.copytree(V5F_RUNTIME, target)
            bank = json.loads((target / 'story-questions.json').read_text(encoding='utf-8'))
            bank['questions'][0]['main_question'] += '吗'
            (target / 'story-questions.json').write_text(json.dumps(bank, ensure_ascii=False), encoding='utf-8')
            manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
            manifest['files']['story-questions.json'] = sha256((target / 'story-questions.json').read_bytes()).hexdigest()
            (target / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaises(LLMConfigurationError):
                V3jRuntime(target, sha256((target / 'manifest.json').read_bytes()).hexdigest(), 'v3j_v5f')

    def test_build_script_checks_both_bundles(self):
        import subprocess
        if not (ROOT / 'docs/prototypes/full-interview-v5').exists():
            self.skipTest('docs/prototypes is not part of this checkout')
        for args, pin in (([], guided.V3J_RUNTIME), (['--bundle', 'v5f'], V5F_RUNTIME)):
            done = subprocess.run([sys.executable, str(BACKEND / 'scripts/build_interview_v3j_runtime.py'), '--check', *args],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(done.stdout.strip(), sha256((pin / 'manifest.json').read_bytes()).hexdigest())


# --------------------------------------------------------------------------- reading rules
class ReadingTests(unittest.TestCase):
    def test_partial_cant_remember_only_with_the_v5f_configuration(self):
        v4d, v5f = v3j_runtime().speaker_config, v5f_runtime().speaker_config
        ask = {'decision': 'ask', 'target': 'WK01-E2', 'effective': {'WK01-E1': 'known'}, 'active': ['WK01-E1', 'WK01-E2']}
        text = '那天的情形我记不太清了。就记得后来师傅把我留下了，让我先去扫地烧水，晚上还教我认机器。'
        st = lambda: {'followups': 0, 'ask_counts': {}, 'prev_eff': {}, 'asked': '报到那天是什么情形？', 'before': '',  # noqa: E731
                      'last_target': 'WK01-E2'}
        self.assertEqual(speaker.decide(v4d, ask, st(), text), ('close', 'unknown'))
        self.assertEqual(speaker.decide(v5f, ask, st(), text), ('close', 'unknown_partial'))
        self.assertEqual(speaker.decide(v5f, ask, st(), '记不清了。'), ('close', 'unknown'))
        # another open point the engine wants may still be asked
        other = {**ask, 'target': 'WK01-E3'}
        self.assertEqual(speaker.decide(v5f, other, st(), text), ('ask', 'WK01-E3'))
        self.assertIn('unknown_partial', speaker.CLOSE_REASON)
        self.assertEqual(speaker.signal_scope(text, '报到那天是什么情形？')[0], 'partial')

    def test_deepen_checks(self):
        dz = {'asked': 1, 'dims': ['人物'], 'last': '老先生就在学校的柴房里教。学生一早上去背书，他翻到哪本就叫你背哪本。',
              'before': '后来跟老先生在柴房读了一年私塾，五经四书都背。'}
        cfg = v5f_runtime().speaker_config['deepen']
        self.assertIn('yes_no', story.check_deepen('人物', '', '后来她们也录取了吗？', [], {**dz, 'asked': 0}, cfg))
        self.assertIn('repeat_last', story.check_deepen('细节', '', '在柴房里背书，当时是怎么个背法？', [], dz, cfg))
        self.assertEqual(story.check_deepen('场景', '', '背完书以后，老先生后来怎么样了？', [], dz, cfg), [])
        self.assertEqual(story.check_deepen('场景', '', '一起背书的同学里，都有谁？', [], dz, cfg), [])
        self.assertIn('multi_part', story.check_deepen('场景', '', '是在什么地方，周围是什么样子的？', [], dz, cfg))
        self.assertNotIn('yes_no', story.check_deepen('人物', '', '后来她们也录取了吗？', [], dz, {}))  # off without the key

    def test_close_guards(self):
        rt = v5f_runtime()
        elder = '我倒想起在马祖那两年，有一次蒋经国先生半夜坐渔船到北竿转，上不了岸。'
        entry = MAIN('CH06b')
        # naming a person he mentioned is not a restatement
        self.assertEqual(story.close_reply(rt, '噢，还见过蒋经国先生。' + entry, entry, elder)[0], '噢，还见过蒋经国先生。' + entry)
        # a natural move-on phrase is kept once, dropped when an earlier close of the interview used it
        reply = '那可真不容易。那咱们再聊聊，' + entry
        self.assertEqual(story.close_reply(rt, reply, entry, '那时候走夜路回家，苦啊。')[0], reply)
        self.assertEqual(story.close_reply(rt, reply, entry, '那时候走夜路回家，苦啊。', ['好。那咱们再聊聊，您的求学过程是怎样的？'])[0],
                         '那可真不容易。' + entry)
        # a restating acknowledgement is dropped; what is left as a bare interjection goes with it (or stays whole)
        text, _, notes, ok = story.close_reply(rt, '噢，上大夜班回来还得走路回家。' + entry, entry,
                                               '真要说辛苦，那就是上大夜班，回到家差不多一点钟，还得走路回家。')
        self.assertTrue(ok)
        self.assertNotEqual(story.lead_part(text, entry), '噢，')
        # the v4d configuration has no guards
        self.assertEqual(story.guarded(v3j_runtime(), reply, entry, '')[0], reply)


class SimulatorParityTests(unittest.TestCase):
    """The backend's v5 functions against the simulator's own, over the same texts (stored runs when present)."""

    @classmethod
    def setUpClass(cls):
        cls.sim, cls.sim_style = load_simulator()
        cls.texts = cls.corpus()

    @classmethod
    def corpus(cls):
        texts = {'elder': ['记不清了。', '那天的情形我记不太清了。就记得后来师傅把我留下了，让我先去扫地烧水。', ANSWER_1, ANSWER_2,
                           '这个我一时想不出哪一回特别的。', '就是把孩子盼大了嘛，这个不多讲了。', '哎，累了，歇会儿吧。'],
                 'close': [], 'deepen': []}
        runs = Path(os.getenv('SHINIAN_EVAL_RUNS', ROOT / '.runtime/interview-eval/runs'))
        for path in sorted(runs.glob('st[567]-*/sessions/*.json'))[:400]:
            session = json.loads(path.read_text(encoding='utf-8'))
            for episode in session['episodes']:
                messages = episode['messages']
                for j, m in enumerate(messages):
                    if m['role'] == 'elder' and not m.get('scripted'):
                        before = ''.join(x['text'] for x in messages[:j] if x['role'] == 'elder' and not x.get('scripted'))
                        asked = next((x.get('question_part') or x['text'] for x in reversed(messages[:j]) if x['role'] == 'system'), '')
                        texts['elder'].append((m['text'], asked, before))
                    sp = m.get('speaker') or {}
                    if m.get('kind') == 'close' and sp.get('raw') and m.get('entry_part'):
                        try:
                            raw = json.loads(sp['raw'])
                        except ValueError:
                            continue
                        words = ''.join(x['text'] for x in messages[:j] if x['role'] == 'elder' and not x.get('scripted'))
                        texts['close'].append(((raw.get('reply') or raw.get('ack') or '').strip(), m['entry_part'], words))
                    if m.get('kind') == 'deepen':
                        last = messages[j - 1]['text']
                        before = ''.join(x['text'] for x in messages[:j - 1] if x['role'] == 'elder' and not x.get('scripted'))
                        texts['deepen'].append((m['question_part'], last, before))
        texts['elder'] = [t if isinstance(t, tuple) else (t, '', '') for t in texts['elder']]
        return texts

    def test_reading_functions_match(self):
        sim = self.sim
        for text, asked, before in self.texts['elder']:
            self.assertEqual(speaker.elder_signal(text), sim.elder_signal(text), text)
            for extra in (False, True):
                self.assertEqual(speaker.signal_scope(text, asked, before, 15, extra), sim.signal_scope(text, asked, before, 15, extra), text)
                scope = (asked, before, 15)
                self.assertEqual(story.deepen_close(text, None, extra, scope), sim.deepen_close(text, None, extra, scope), text)
            self.assertEqual(story.story_dims(text), sim.story_dims(text), text)
            self.assertEqual(story.repeats_last(asked, text, before), sim.repeats_last(asked, text, before), text)
            self.assertEqual(story.mask_names(text), sim.mask_names(text), text)

    def test_wording_functions_match(self):
        sim, sim_style = self.sim, self.sim_style
        rt = v5f_runtime()
        for reply, entry, words in self.texts['close']:
            mine = speaker.compose_close(rt, reply, entry, words)
            theirs = sim.compose_close(reply, entry, words)
            self.assertEqual(mine, theirs, reply)
            if not mine[3]:
                continue
            text = mine[0]
            self.assertEqual(style.split_turn(text, entry), sim_style.split_turn(text, entry), text)
            self.assertEqual(style.is_restate(text, words), sim_style.is_restate(text, words), text)
            for names in (False, True):
                self.assertEqual(story.restates(mine[1], words, names), sim.restates(mine[1], words, names), text)
            for seen in ([], [text], ['好。那咱们再聊聊，' + entry]):
                for args in (('clause', True, 14, None), ('clause', 'repeat', 14, {'names': True, 'bare': True, 'seen': seen}),
                             (True, True, None, None)):
                    self.assertEqual(story.guard_close(text, entry, words, *args), sim.guard_close(text, entry, words, *args), text)
        for question, last, before in self.texts['deepen']:
            dz = {'asked': 1, 'dims': ['人物'], 'last': last, 'before': before}
            cfg = v5f_runtime().speaker_config['deepen']
            self.assertEqual(story.check_deepen('场景', '', question, [], dz, cfg), sim.check_deepen('场景', '', question, [], dz, cfg))


# --------------------------------------------------------------------------- guided interview
class GuidedTests(unittest.TestCase):
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown
    post_life, enter_module = base.WorkflowTests.post_life, base.WorkflowTests.enter_module
    url = guided.FlowTests.url
    say, guide, move_to = guided.FlowTests.say, guided.FlowTests.guide, guided.FlowTests.move_to

    def turn(self, text, provider, env=V5F, rid=None, status=201):
        with patch.dict(os.environ, env), patch.object(V3jPipeline, '_call', side_effect=provider):
            return self.say(text, rid, status)

    def last(self, reply):
        return reply['messages'][-1]['content']

    def test_default_and_v3j_v4d_do_not_deepen(self):
        self.enter_module('family')
        with patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            self.say('我们是在工厂认识的。')
            self.assertEqual(old.call_count, 2)
            new.assert_not_called()
        self.move_to('FM01')
        provider = Provider(judge=[FM01_READY], speaker=[{'reply': '天天一起上下班。那您和伴侣平时是怎样相伴生活的？'}])
        reply = self.turn(FM01_TEXT, provider, env=V3J)
        self.assertEqual(self.last(reply), '天天一起上下班。' + DRAFT)
        self.assertEqual(provider.count('deepen'), 0)
        state = self.guide().contract_state
        self.assertEqual(state['pipeline'], 'v3j_v4d')
        self.assertNotIn('deepen', state)

    def test_v3j_v4d_question_keeps_its_flow_when_v5f_is_switched_on(self):
        self.enter_module('family')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})],
                            speaker=[{'ack': '', 'question': '后来您们是怎样慢慢熟起来的？'}])
        self.turn('我们是在工厂认识的。', provider, env=V3J)
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S2.1')})],
                            speaker=[{'reply': '天天一起上下班。那您和伴侣平时是怎样相伴生活的？'}])
        reply = self.turn('后来天天一起上下班，慢慢就熟了，一年后就结婚了。', provider)  # now v3j_v5f
        self.assertEqual(self.last(reply), '天天一起上下班。' + DRAFT)
        self.assertEqual(provider.count('deepen'), 0)
        self.assertEqual(self.guide().contract_state['pipeline'], 'v3j_v4d')
        self.assertEqual(provider.seen[-1][2], v3j_runtime().speaker_prompt)  # the v4d prompt, not v5f
        self.move_to('FM01b')
        provider = Provider(judge=[judged()], speaker=[{'ack': '', 'question': '您们平时怎么一起过日子？'}])
        self.turn('我们一起过了很多年。', provider)
        state = self.guide().contract_state
        self.assertEqual((state['question_id'], state['pipeline']), ('FM01b', 'v3j_v5f'))
        self.assertEqual(state['pipeline_manifest_sha256'], os.environ['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256'])

    def test_story_question_deepens_twice_then_offers_the_draft(self):
        self.enter_module('family')
        provider = Provider(judge=[FM01_READY], deepen=[DEEPEN_1])
        reply = self.turn(FM01_TEXT, provider)
        self.assertEqual(self.last(reply), DEEPEN_1['question'])
        self.assertIsNone(reply['generation_offer'])
        guide = self.guide()
        self.assertEqual((guide.phase, guide.pending_question.key, guide.pending_question.text),
                         ('exploring', 'deepen', DEEPEN_1['question']))
        deepen_input = provider.inputs('deepen')[0]
        self.assertIn('当前话题：' + MAIN('FM01'), deepen_input)
        self.assertIn('深挖方向：' + v5f_runtime().story['FM01']['deepen_direction'], deepen_input)
        self.assertIn('答：' + FM01_TEXT, deepen_input)
        self.assertTrue(deepen_input.endswith('已经深挖过：（无）\n任务：deepen'))
        fields = deepcopy(guide.contract_state['fields'])
        # the answer to the detail question is kept, not judged
        provider = Provider(deepen=[DEEPEN_2])
        reply = self.turn(ANSWER_1, provider)
        self.assertEqual((provider.count('judge'), self.last(reply)), (0, DEEPEN_2['question']))
        self.assertIn('问：' + DEEPEN_1['question'] + '\n答：' + ANSWER_1, provider.inputs('deepen')[0])
        self.assertIn('已经深挖过：人物', provider.inputs('deepen')[0])
        # second answer: at the cap, the draft step with the speaking layer's acknowledgement
        provider = Provider(speaker=[{'reply': '还沿着河边走回去啊。那咱们再聊聊，刚组建家庭时生活条件怎么样？'}])
        reply = self.turn(ANSWER_2, provider)
        self.assertEqual(self.last(reply), '还沿着河边走回去啊。' + DRAFT)
        self.assertIsNotNone(reply['generation_offer'])
        self.assertEqual((provider.count('judge'), provider.count('deepen')), (0, 0))
        close_input = provider.inputs('speaker')[0]
        self.assertIn('收尾原因：这个话题已经聊完', close_input)
        self.assertIn('答：' + ANSWER_2, close_input)
        guide = self.guide()
        local = guide.contract_state
        self.assertEqual(guide.phase, 'supplement')
        self.assertEqual(local['fields'], fields)  # no field changed
        self.assertEqual([s['text'] for s in local['deepen']['sources']], [ANSWER_1, ANSWER_2])
        self.assertEqual([s['question'] for s in local['deepen']['sources']], [DEEPEN_1['question'], DEEPEN_2['question']])
        self.assertEqual(len(local['sources']), 1)
        self.assertEqual((local['deepen']['asked'], local['deepen']['dims']), (2, ['人物', '场景']))
        self.assertEqual(local['deepen']['log'][-1]['reason'], 'cap')

    def test_sensitive_question_deepens_once(self):
        self.enter_module('family')
        self.move_to('FM03')
        text = '刚结婚那几年老吵架，为了钱的事。他爱借钱给老家亲戚，我不同意，后来他慢慢就改了。'
        provider = Provider(judge=[judged(**{'FM03-E1': content('S1.1'), 'FM03-E2': content('S1.2')})],
                            deepen=[{'dimension': '人物', 'ack': '', 'question': '要是愿意的话，后来你们是怎么说开的？'}])
        reply = self.turn(text, provider)
        self.assertIn('敏感：是', provider.inputs('deepen')[0])
        self.assertEqual(self.last(reply), '要是愿意的话，后来你们是怎么说开的？')
        provider = Provider(speaker=[{'reply': '那会儿也真难为您了。那咱们说说，养育子女时什么让您觉得辛苦？'}])
        reply = self.turn('后来他自己也明白了，钱借出去要不回来，慢慢就不借了，我们也就不吵了。', provider)
        self.assertEqual((provider.count('deepen'), self.last(reply)), (0, '那会儿也真难为您了。' + DRAFT))
        self.assertEqual(self.guide().contract_state['deepen']['log'][-1]['reason'], 'cap')

    def test_short_answer_or_failed_or_invalid_deepen_goes_to_the_draft_step(self):
        self.enter_module('family')
        cases = (('在厂里认识的，后来就熟了。', [], 'short'),   # 11 characters: not asked
                 (FM01_TEXT, [LLMServiceError('down')], 'call_failed'),
                 (FM01_TEXT, [{'dimension': '人物', 'ack': '', 'question': '后来她也调过去了吗？'}], 'invalid'),
                 (FM01_TEXT, [{'dimension': '', 'ack': '', 'question': ''}], 'model_skip'))
        for text, deepen, why in cases:
            self.move_to('FM01')
            provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S1.1')}) if why == 'short' else FM01_READY],
                                deepen=deepen, speaker=[{'reply': '噢，原来如此。那您和伴侣平时是怎样相伴生活的？'}])
            reply = self.turn(text, provider)
            self.assertEqual(self.last(reply), '噢，原来如此。' + DRAFT, why)
            local = self.guide().contract_state
            self.assertEqual(local['deepen']['log'][-1]['reason'], why)
            self.assertEqual(provider.count('deepen'), len(deepen), why)
            if why == 'invalid':
                self.assertEqual(local['deepen']['log'][-1]['errors'], ['yes_no'])
            self.assertEqual(self.guide().phase, 'supplement', why)

    def test_retries_reuse_saved_judge_and_deepen_calls(self):
        self.enter_module('family')
        rid = uuid4()
        provider = Provider(judge=[FM01_READY], deepen=[DEEPEN_1])
        from app.services import contract_v3j_interview as flow
        with patch.object(flow, 'ask_deepen', side_effect=LLMServiceError('crash after the saved calls')):
            self.turn(FM01_TEXT, provider, rid=rid, status=502)
        self.assertEqual((provider.count('judge'), provider.count('deepen')), (1, 1))
        empty = Provider()
        reply = self.turn(FM01_TEXT, empty, rid=rid)  # same request: no new provider call
        self.assertEqual((self.last(reply), empty.seen), (DEEPEN_1['question'], []))
        rid = uuid4()
        provider = Provider(deepen=[DEEPEN_2])
        with patch.object(flow, 'ask_deepen', side_effect=LLMServiceError('crash after the saved calls')):
            self.turn(ANSWER_1, provider, rid=rid, status=502)
        reply = self.turn(ANSWER_1, empty, rid=rid)
        self.assertEqual((self.last(reply), empty.seen), (DEEPEN_2['question'], []))
        self.assertEqual(len(self.guide().contract_state['deepen']['sources']), 1)  # the answer kept once

    def test_partial_cant_remember_answer_gets_one_more_detail_question(self):
        self.enter_module('family')
        self.turn(FM01_TEXT, Provider(judge=[FM01_READY], deepen=[DEEPEN_1]))
        partial = '这个我记不太清了。就记得厂里的老师傅给我们做媒，还请我们吃了一顿饺子。'
        provider = Provider(deepen=[{'dimension': '场景', 'ack': '', 'question': '老师傅给你们做媒，后来是怎么说成的？'}])
        reply = self.turn(partial, provider)
        self.assertEqual(self.last(reply), '老师傅给你们做媒，后来是怎么说成的？')
        deepen_input = provider.inputs('deepen')[0]
        self.assertIn('老人刚说记不清的：这个我记不太清了。（这一点不再问）', deepen_input)
        self.assertIn('他接着讲的：就记得厂里的老师傅给我们做媒，还请我们吃了一顿饺子。', deepen_input)
        # a whole "can't remember" closes with the unknown reason
        provider = Provider(speaker=[{'reply': '记不清也不要紧。那您和伴侣平时是怎样相伴生活的？'}])
        reply = self.turn('这个记不清了。', provider)
        self.assertIn('收尾原因：老人说记不清了', provider.inputs('speaker')[0])
        self.assertEqual(self.last(reply), '记不清也不要紧。' + DRAFT)

    def test_skip_or_tired_while_a_detail_question_waits(self):
        self.enter_module('family')
        self.turn(FM01_TEXT, Provider(judge=[FM01_READY], deepen=[DEEPEN_1]))
        provider = Provider(speaker=[{'reply': '好，不多聊了。那您和伴侣平时是怎样相伴生活的？'}])
        reply = self.turn('跳过', provider)  # answered before the detail question: the draft step, not a skip
        self.assertEqual(self.last(reply), '好，不多聊了。' + DRAFT)
        self.assertIn('收尾原因：老人不想多说', provider.inputs('speaker')[0])
        guide = self.guide()
        self.assertEqual((guide.phase, guide.last_topic_skipped), ('supplement', False))
        self.assertNotIn('FM01', guide.processed_topics)
        self.move_to('FM01')
        self.turn(FM01_TEXT, Provider(judge=[FM01_READY], deepen=[DEEPEN_1]))
        reply = self.turn('哎，说了这么多，我累了，想歇会儿。', Provider())
        self.assertEqual(self.last(reply), '好，先休息。您的讲述和采访位置都已保留。')
        local = self.guide().contract_state
        self.assertEqual((self.guide().phase, local['deepen']['stopped'], local['deepen']['awaiting']), ('paused', 'rest', False))


# --------------------------------------------------------------------------- skeleton
class SkeletonTests(unittest.TestCase):
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown
    act, data, move_to, last = (skeleton.SkeletonFlowTests.act, skeleton.SkeletonFlowTests.data,
                                skeleton.SkeletonFlowTests.move_to, skeleton.SkeletonFlowTests.last)

    def test_story_skeleton_question_deepens_before_the_next_question(self):
        self.move_to('SK01c')
        text = '家乡在徐州乡下，村口有一条小河，河边全是柳树，我们小时候天天在那儿摸鱼。'
        provider = Provider(judge=[judged(**{'SK01-E4': content('S1.1'), 'SK01-E3.place': content('S1.1'),
                                             'SK01-E3.period': content('S1.1')})],
                            deepen=[{'dimension': '细节', 'ack': '', 'question': '在河边摸鱼那会儿，都跟谁一起去？'}])
        with patch.dict(os.environ, V5F), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act(text)
        self.assertEqual(self.last(life), '在河边摸鱼那会儿，都跟谁一起去？')
        local = self.data()['questions']['SK01c']
        self.assertEqual((local['pipeline'], local['status'], local['asked_question']),
                         ('v3j_v5f', 'pending', '在河边摸鱼那会儿，都跟谁一起去？'))
        next_q = MAIN('SK02')
        provider = Provider(speaker=[{'reply': '还跟哥哥摸鱼啊。那咱们再聊聊，' + next_q}])
        with patch.dict(os.environ, V5F), patch.object(V3jPipeline, '_call', side_effect=provider):
            life = self.act('就跟我哥哥一起。')  # a short answer: no second detail question
        self.assertEqual(provider.count('judge'), 0)
        self.assertEqual(self.last(life), '还跟哥哥摸鱼啊。那咱们再聊聊，' + next_q)
        local = self.data()['questions']['SK01c']
        self.assertEqual((local['status'], len(local['sources']), len(local['deepen']['sources'])), ('known', 1, 1))
        self.assertIn('问：在河边摸鱼那会儿，都跟谁一起去？', provider.inputs('speaker')[0])


if __name__ == '__main__':
    unittest.main()
