"""Regression tests for the cloud findings C01-C03 of 2026-10-23 (v3j_v4d flow only), offline.

C01  control signals are the elder's own present intent: narrated, negated or someone else's words are not a
     request to rest or stop.
C02  an answer followed by "这段我不想多讲" is not a refusal: no more follow-ups, the draft step (guided) or the
     next skeleton question (life overview); the same for the engine's limited with a declined field next to an
     answered one. A decline before any real answer stays a refusal; the explicit skip control is unchanged.
C03  after the draft offer: "nothing more" in general wording goes to the existing review step without a model call;
     a real addition is judged and recorded, answered by one acknowledgement and a short "anything else" question,
     and keeps the draft offer; an addition that also says it is all is recorded and goes to the review step.

Model calls are FIXED FIXTURES (Provider), not real model output; the real Node engine of the pinned runtime
bundle validates every proposal. The elder inputs of the cloud runs are quoted verbatim from the 2026-10-23
handoff and its QA records (AI respondent grounded in published material). Default v2 is checked to be unchanged.

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_c01_c03 -v
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_contract_interview_workflow as base  # noqa: E402
import test_interview_v3j_skeleton as skeleton  # noqa: E402  (modules, not classes: their tests are not run twice)
import test_interview_v3j_v4d as guided  # noqa: E402
from test_interview_v3j_v4d import DRAFT, V3J, Provider, content, judged  # noqa: E402

MAIN = skeleton.MAIN

from app.ai import interview_speaker as speaker  # noqa: E402
from app.ai.contract_interview import ContractInterviewPipeline  # noqa: E402
from app.ai.contract_interview_v3j import V3jPipeline  # noqa: E402
from app.ai.llm_client import LLMServiceError  # noqa: E402
from app.services import contract_v3j_interview as flow  # noqa: E402
from app.services.contract_interview_state import v3j_runtime  # noqa: E402

REVIEW = '好，先核对这段草稿，您确认后再保存。'
MORE = '您还有别的想补充的吗？'

# --- C01: wording that is / is not the elder's own present request -------------------------------------------
REST_NOW = ['我有点累了，想先歇一会儿。', '哎，累了。', '说了这么多，累了，歇会儿吧。', '今天先聊到这儿吧。', '改天再聊吧。',
            '我现在有点累了。', '有点累了，先休息一下。', '不行了，我得歇歇。', '我累了。', '今天就聊到这吧，我累了。',
            '我今天有点累了。', '有点累，我们下次再聊吧。', '哎呀，累了累了，歇会儿。', '说累了，喝口水再聊。', '让我歇一会儿吧。',
            '您让我歇会儿吧。', '孩子们全部长大了，我也累了。']
NOT_REST = ['那时候下工累了就歇一会儿。', '不是累了，我还想接着聊。', '我妈叫我歇一会儿再干。', '她累了，想歇一会儿。',
            '我妈身体不好，累了就得躺着。', '累了一辈子，也没享过福。', '以前干活累了，歇一会儿接着干。', '有点累了，不过我还想接着聊。',
            '我不累，接着说吧。', '要是累了我会跟您说。', '他说改天再聊，后来就没来了。', '当年在工地上，中午歇一会儿接着干。',
            '我老伴总说累了。', '不用歇，接着聊。', '晚上下班累了，我们就早早睡了。', '我妈说她累了想歇会儿。', '大家都累了，就歇了一会儿。',
            '老伴累了，我陪她歇会儿。', '我爸那时候常说，累了就歇歇。', '每次干完活累了就想睡。', '我还不累，接着问吧。',
            '没事，不累，您接着问。', '队长让我们歇一会儿。', '师傅叫我们歇一会儿。', '医生让我多休息一下。', '老板叫我们下次再说。']
DECLINE_NOW = ['这个就不多讲了。', '这些事我不想多讲。', '以前的事我不想多说了。', '他的事我不想多说。', '其他的不想多说了。',
               '她不想说，我也不想多讲。', '那时候的事，我不愿意提。', '别问了。', '这段我不想多讲。', '现在不想说了。',
               '我不想说她的事。', '不想讲。', '这事我不愿意提。', '这个我不太想说。', '我老伴的事，我不想多说。', '不是不记得，是不想讲。']
NOT_DECLINE = ['她不想说，后来我就没有再问。', '我妈不愿意提那些事。', '他们都说不想提那些事。', '当时我不想说，后来还是说了。',
               '如果不想说就不说。', '我也不是不想说，就是没什么好说的。', '人家不愿意讲，我也没法问。', '我老伴不想多说那几年的事。',
               '我儿子不想让我说这些。', '那会儿我不想说，现在可以讲讲。', '我并不是不想说。', '孩子们都不愿意提这事。',
               '别人不想说，我想说。', '我们队长不想讲那些事。', '他说下次再聊，后来再也没见过。']
UNKNOWN_NOW = ['记不清了。', '那时候我才三岁，记不清了。', '小时候的事都忘了。', '名字的来历我不知道，这个我记不清了。',
               '不是不想说，就是一时想不起来。', '是不是就在那个庄子出生的，我记不清了。', '没有不想说，就是记不清了。',
               '我不是不想讲，是真忘了。', '他不记得了，我也记不清了。', '记不清了，不过我还想接着聊。']
NOT_UNKNOWN = ['那时候不清楚这些规矩，后来才知道。', '她也不记得了。', '我老伴他记不清了，我记得是五八年。', '要是记不清就算了。',
               '我母亲记不清了。', '他忘了，我没忘。']

# --- C03: answers after the draft offer ----------------------------------------------------------------------
CLOUD_NOTHING_MORE = [  # every distinct "nothing more" answer of the three cloud module runs, verbatim
    '这件事我记得的就是这些，没有别的补充了。', '没有了，这段我没有别的要补充的。', '没有了，能想起来的我刚才都讲了。',
    '没什么补充了，这件事就是这样。', '没有了，我这段已经没有什么补充了。', '没有了，我能记得的已经都说过了。',
    '没有了，这个误会我记得的就是这些。', '没有了，关于最初工作这些事情，我能补充的就是这些。', '没有了，就这些。',
    '没有了，关于成家这件事，我能说的就是这些。', '没有了，能补充的我刚才都说了。']
NOTHING_MORE = CLOUD_NOTHING_MORE + ['没了', '嗯，没有了。', '别的没有了。', '差不多了。', '就这样吧。', '能想起来的都讲了',
                                     '没有别的了，就这些了。', '暂时想不起来了。', '别的我也想不起来了。', '好，先保存吧。',
                                     '这个就不多讲了。', '没有了，我就说到这儿吧。', '以后想起来再跟您说。', '没有太多要补充的了。',
                                     '没有太多了。', '也没什么太多要补充的了。', '也没什么特别的了。', '没多少要补充的了。',
                                     '没什么好说的了。', '好的，那就先这样。', '这个我就不多说了，也没什么特别想讲的。']
ADDITION = ['后来我妈把‘谋士’写给我看，我才明白不是磨刀的石头。', '也没什么特别原因，我就是好玩，从来不为成家这事伤脑筋。',
            '那时候粮食没有了，大家都饿肚子。', '就这些年变化最大。', '这件事就是这样开始的。', '我们那时候就是这样过日子的。',
            '还有一件事，我爸后来也去了工厂。', '没有，我还想说说我妈。', '我想补充一点，就是那时候很穷。', '我没说完，还有。',
            '那时候也没什么特别的了。', '还有就是，我们家原先在骑河楼住，有十三间房吧。', '还有一件事，就这些。',
            '这个我没太多想，就说说别的吧。', '先这样做，后来再改。']
ADDITION_AND_END = ['没有别的补充了，成家的事情我确实没考虑过。', '父母当时很反对，就这些。', '对了，我们后来还搬过一次家，就这些了。',
                    '没有了，就这些。那时候我失学后就跟哥哥下田。', '没有太多要补充的了。就是觉得当老师，既能发挥我的长处。',
                    '也没什么特别的了。平时我爱看书、跑步。', '好的，那就先这样。说起来，我当年报大学想学的是食品研究。']


class ReadingTests(unittest.TestCase):
    """The pure wording rules, broad positive and negative sets (general wording, not tuned to the three inputs)."""

    def test_c01_signals_are_the_elders_own_present_intent(self):
        for kind, now, other in (('rest', REST_NOW, NOT_REST), ('declined', DECLINE_NOW, NOT_DECLINE),
                                 ('unknown', UNKNOWN_NOW, NOT_UNKNOWN)):
            for text in now:
                self.assertEqual(speaker.elder_signal(text), kind, text)
            for text in other:
                self.assertNotEqual(speaker.elder_signal(text), kind, text)
        for text in ('那时候下工累了就歇一会儿。', '不是累了，我还想接着聊。', '她不想说，后来我就没有再问。'):  # the cloud inputs
            self.assertIsNone(speaker.elder_signal(text), text)

    def test_c01_c02_ending_rules(self):
        cfg = v3j_runtime().speaker_config
        st = lambda: {'followups': 0, 'ask_counts': {}, 'prev_eff': {}}  # noqa: E731
        ask = {'decision': 'ask', 'target': 'FM01-E2', 'effective': {'FM01-E1': 'missing'}, 'active': ['FM01-E1', 'FM01-E2']}
        answered = {**ask, 'effective': {'FM01-E1': 'known', 'FM01-E2': 'missing'}}
        for text in ('那时候下工累了就歇一会儿。', '不是累了，我还想接着聊。', '她不想说，后来我就没有再问。'):
            self.assertEqual(speaker.decide(cfg, ask, st(), text), ('ask', 'FM01-E2'), text)
        self.assertEqual(speaker.decide(cfg, ask, st(), '这段我不想多讲。'), ('close', 'declined'))
        self.assertEqual(speaker.decide(cfg, answered, st(), '我们是在工厂认识的。这段我不想多讲。'), ('close', 'declined_partial'))
        self.assertEqual(speaker.decide(cfg, {'decision': 'ready'}, st(), '这段我不想多讲。'), ('close', 'declined_partial'))
        self.assertEqual(speaker.decide(cfg, {'decision': 'ready'}, st(), '我们是在工厂认识的。'), ('close', 'done'))
        self.assertEqual(speaker.CLOSE_REASON['declined_partial'], speaker.CLOSE_REASON['declined'])
        # the engine's limited with a declined field: answered before -> not a refusal; nothing answered -> refusal
        limited = {'decision': 'limited', 'effective': {'SK04-E1': 'known', 'SK04-E3': 'declined'}, 'active': ['SK04-E1', 'SK04-E3']}
        self.assertEqual(speaker.decide(cfg, limited, st(), '对我性格有什么影响，我不想说了。'), ('close', 'declined_partial'))
        self.assertEqual(speaker.decide(cfg, {**limited, 'effective': {'SK04-E1': 'missing', 'SK04-E3': 'declined'}}, st(), ''),
                         ('close', 'declined'))
        self.assertEqual(speaker.decide(cfg, {'decision': 'skipped', 'effective': {'SK04-E1': 'known'}, 'active': ['SK04-E1']}, st(), ''),
                         ('close', 'declined'))
        # only an optional detail is not an answer of the question (the simulator's judge summary drops optional fields)
        optional = {**ask, 'effective': {'FM01-E1': 'missing', 'FM01-O1': 'known'}}
        self.assertEqual(speaker.decide(cfg, optional, st(), '这段我不想多讲。'), ('close', 'declined'))

    def test_c03_supplement_reading(self):
        for text in NOTHING_MORE:
            self.assertEqual(speaker.supplement_end(text), 'only', text)
        for text in ADDITION:
            self.assertIsNone(speaker.supplement_end(text), text)
        for text in ADDITION_AND_END:
            self.assertEqual(speaker.supplement_end(text), 'with_content', text)

    def test_backend_and_simulator_rules_are_the_same_code(self):
        root = Path(__file__).resolve().parents[3]
        sim = root / 'tools/interview_eval/simulate/interview.py'
        if not sim.exists():
            self.skipTest('tools/interview_eval is not part of this checkout')
        backend = (Path(speaker.__file__)).read_text(encoding='utf-8')
        simulator = sim.read_text(encoding='utf-8')
        block = backend[backend.index('SIG_REST = '):backend.index('def decide(')]
        self.assertIn(block, simulator)
        # decide and v4_decide: the same body after the docstring (the simulator reads its config from S.policy)
        body = lambda text, name: text[text.index("    d = result.get('decision')", text.index(name)):]  # noqa: E731
        rules = body(backend, 'def decide(')
        self.assertEqual(rules[:rules.index('\n\n\n')], body(simulator, 'def v4_decide(')[:len(rules[:rules.index('\n\n\n')])])


class GuidedTests(unittest.TestCase):
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown
    post_life, enter_module = base.WorkflowTests.post_life, base.WorkflowTests.enter_module
    url = guided.FlowTests.url
    say, guide, move_to = guided.FlowTests.say, guided.FlowTests.guide, guided.FlowTests.move_to

    def turn(self, text, provider):
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            return self.say(text)

    def last(self, reply):
        return reply['messages'][-1]['content']

    # --- C01 ---------------------------------------------------------------------------------------------
    def test_c01_cloud_inputs_continue_the_question(self):
        self.enter_module('family')
        for k, text in enumerate(('那时候下工累了就歇一会儿。', '不是累了，我还想接着聊。', '她不想说，后来我就没有再问。')):
            self.move_to('FM01')
            question = ('您们是在哪儿认识的呀？', '您们最早是怎么碰上的？', '您和伴侣是在什么地方认识的？')[k]
            provider = Provider(judge=[judged()], speaker=[{'ack': '', 'question': question}])
            reply = self.turn(text, provider)
            guide = self.guide()
            self.assertEqual(self.last(reply), question, text)
            self.assertEqual((guide.phase, guide.last_topic_skipped), ('exploring', False), text)
            self.assertNotIn('FM01', guide.processed_topics)
            self.assertEqual(guide.contract_state['audit'][-1]['speaker']['signal'], None)
            self.assertEqual(provider.count('speaker'), 1)
        # an own present request still pauses
        self.move_to('FM01')
        reply = self.turn('我有点累了，想先歇一会儿。', Provider(judge=[judged()]))
        self.assertEqual(self.last(reply), flow.PAUSE_TEXT)

    # --- C02 ---------------------------------------------------------------------------------------------
    def test_c02_answer_then_not_wanting_to_go_on_offers_the_draft(self):
        self.enter_module('family')
        text = '我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。这段我不想多讲。'  # the cloud input, engine ready
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1'), 'FM01-E2': content('S1.2')})],
                            speaker=[{'reply': '好，这段不多聊了。那您和伴侣平时是怎样相伴生活的？'}])
        reply = self.turn(text, provider)
        self.assertEqual(self.last(reply), '好，这段不多聊了。' + DRAFT)
        self.assertEqual(reply['generation_offer']['message_id'], reply['messages'][-1]['id'])
        guide = self.guide()
        self.assertEqual((guide.phase, guide.last_topic_skipped), ('supplement', False))
        self.assertNotIn('FM01', guide.processed_topics)
        self.assertEqual(guide.contract_state['audit'][-1]['speaker']['reason'], 'declined_partial')
        self.assertIn('收尾原因：老人不想多说', provider.seen[-1][1])
        # the engine still asking: no follow-up, the draft step (was: skipped to the next question)
        self.move_to('FM01')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})], speaker=[{'reply': '在工厂认识的，不多问了。'}])
        reply = self.turn('我们是在工厂认识的。别的我不想多讲。', provider)
        self.assertEqual(self.guide().contract_state['last_result']['decision'], 'ask')
        self.assertEqual(self.last(reply), '在工厂认识的，不多问了。' + DRAFT)
        self.assertIsNotNone(reply['generation_offer'])
        self.assertIn('任务：close', provider.seen[-1][1])
        # an addition while the engine still asks: recorded, no follow-up in the supplement step (C03)
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})], speaker=[{'reply': '后来成了家。'}])
        reply = self.turn('后来我们就结婚了。', provider)
        self.assertEqual(self.guide().contract_state['last_result']['decision'], 'ask')
        self.assertEqual(self.last(reply), '后来成了家。' + MORE)
        self.assertIsNotNone(reply['generation_offer'])
        self.assertEqual((self.guide().phase, self.guide().pending_question), ('supplement', None))
        self.assertEqual(self.guide().contract_state['ask_counts'], {})
        # the speaking layer failing: the draft sentence alone
        self.move_to('FM01')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})], speaker=[LLMServiceError('down')])
        reply = self.turn('我们是在工厂认识的。别的我不想多讲。', provider)
        self.assertEqual(self.last(reply), DRAFT)
        # no real answer yet: still a refusal, no draft offer
        self.move_to('FM01')
        provider = Provider(judge=[judged()], speaker=[{'reply': '好，这个咱们就不多聊了。'}])
        reply = self.turn('这段我不想多讲。', provider)
        self.assertEqual(self.last(reply), '好，这个咱们就不多聊了。' + MAIN('FM01b'))  # the transition into the next entry
        self.assertIsNone(reply['generation_offer'])
        self.assertEqual(self.guide().processed_topics['FM01'], 'skipped')

    def test_c02_engine_limited_with_a_declined_field_after_an_answer_offers_the_draft(self):
        self.enter_module('family')
        provider = Provider(judge=[judged(**{'FM01-E1': content('S1.1')})], speaker=[{'ack': '', 'question': '后来怎么熟起来的？'}])
        self.turn('我们是在工厂认识的。', provider)
        self.assertEqual(self.guide().contract_state['asked_target'], 'FM01-E2')
        # the follow-up answered with an explicit decline: engine limited (E1 known, E2 declined); was: skipped
        provider = Provider(judge=[judged(**{'FM01-E2': guided.stated('declined', 'S2.1')})], speaker=[{'reply': '好，这个不多问了。'}])
        reply = self.turn('怎么熟起来的，我不想说了。', provider)
        state = self.guide().contract_state
        self.assertEqual((state['last_result']['decision'], state['last_result']['effective']['FM01-E2']), ('limited', 'declined'))
        self.assertEqual(self.last(reply), '好，这个不多问了。' + DRAFT)
        self.assertIsNotNone(reply['generation_offer'])
        self.assertEqual((self.guide().phase, self.guide().last_topic_skipped), ('supplement', False))
        self.assertNotIn('FM01', self.guide().processed_topics)
        self.assertEqual(state['audit'][-1]['speaker']['reason'], 'declined_partial')
        # the explicit skip control is unchanged: it still skips
        reply = self.turn('跳过', Provider(speaker=[LLMServiceError('down')]))
        self.assertEqual(self.guide().processed_topics['FM01'], 'skipped')

    # --- C03 ---------------------------------------------------------------------------------------------
    def draft(self, module, qid, judge, text='我最早记得的是小时候的一件事。那时候家里还很穷。'):
        self.enter_module(module)
        self.move_to(qid)
        reply = self.turn(text, Provider(judge=[judge], speaker=[{'reply': '好的。'}]))
        self.assertTrue(self.last(reply).endswith(DRAFT))
        self.assertEqual(self.guide().phase, 'supplement')

    def test_c03_nothing_more_goes_to_review_without_model_calls(self):
        self.draft('childhood', 'CH01', judged(**{'CH01-E1': content('S1.1')}))
        for text in NOTHING_MORE:
            provider = Provider()
            reply = self.turn(text, provider)
            self.assertEqual(self.last(reply), REVIEW, text)
            self.assertIsNotNone(reply['generation_offer'], text)
            self.assertEqual(provider.seen, [], text)
            self.assertEqual(self.guide().phase, 'review')
            self.assertEqual(self.guide().contract_state['audit'][-1]['kind'], 'supplement_end')
        self.assertEqual(len(self.guide().contract_state['sources']), 1)  # nothing recorded as an answer

    def test_c03_addition_is_recorded_and_keeps_the_draft_offer(self):
        self.draft('childhood', 'CH01', judged(**{'CH01-E1': content('S1.1')}))
        provider = Provider(judge=[judged(**{'CH01-E1': content('S1.1'), 'CH01-O1': content('S2.1')})],
                            speaker=[{'reply': '后来妈妈写给您看，才弄明白。那咱们聊聊下一个？'}])
        reply = self.turn('后来我妈把‘谋士’写给我看，我才明白不是磨刀的石头。', provider)
        self.assertEqual(self.last(reply), '后来妈妈写给您看，才弄明白。' + MORE)
        self.assertNotIn(DRAFT, self.last(reply))
        self.assertIsNotNone(reply['generation_offer'])
        self.assertIn('第2段 原问：' + DRAFT, next(u for s, u in provider.seen if s == 'judge'))
        state = self.guide().contract_state
        self.assertEqual(len(state['sources']), 2)
        self.assertEqual(state['audit'][-1]['speaker']['step'], 'supplement')
        # the next addition is judged against the short question; the same acknowledgement is not said again
        provider = Provider(judge=[judged(**{'CH01-E1': content('S1.1')})], speaker=[{'reply': '后来妈妈写给您看，才弄明白。'}])
        reply = self.turn('我大伯老说这两个字，我听了好多年。', provider)
        self.assertEqual(self.last(reply), MORE)
        self.assertIn('第3段 原问：' + MORE, next(u for s, u in provider.seen if s == 'judge'))
        # addition and "that's all" in one message: recorded, then the review step without a speaking-layer call
        provider = Provider(judge=[judged(**{'CH01-E1': content('S1.1')})])
        reply = self.turn('我们后来还搬过一次家，就这些了。', provider)
        self.assertEqual(self.last(reply), REVIEW)
        self.assertEqual((provider.count('judge'), provider.count('speaker')), (1, 0))
        self.assertEqual(len(self.guide().contract_state['sources']), 4)

    def test_c03_cloud_module_runs(self):
        """The visible elder turns of the three cloud module runs, after the draft offer, in order (model calls are
        fixtures). Each "nothing more" now reaches the review step instead of repeating the draft sentence."""
        runs = (
            ('childhood', 'CH01', {'CH01-E1': content('S1.1')}, ['后来我妈把‘谋士’写给我看，我才明白不是磨刀的石头。'],
             CLOUD_NOTHING_MORE[:7] + ['没有了，这个误会我记得的就是这些。']),
            ('work', 'WK01', {'WK01-E1': content('S1.1'), 'WK01-E2': content('S1.2')},
             ['当时薪水好像每月九十块，另有两百块的工作勤务加勤。那两百块寄回家，九十块留作自己的零用钱。',
              '父母当时很反对，觉得女孩子不该离乡到部队工作。不过有两个同学一起，我们三个人还是北上报到了，做的是文教工作。'],
             ['没有了，关于最初工作这些事情，我能补充的就是这些。'] + ['没有了，就这些。'] * 4),
            ('family', 'FM01', {'FM01-E1': content('S1.1'), 'FM01-E2': content('S1.2')}, ['也没什么特别原因，我就是好玩，从来不为成家这事伤脑筋。'],
             ['没有了，关于成家这件事，我能说的就是这些。', '没有别的补充了，成家的事情我确实没考虑过。', '没有了，能补充的我刚才都说了。']
             + ['没有了，就这些。'] * 4),
        )
        for module, qid, fields, additions, endings in runs:
            with self.subTest(module=module):
                self.tearDown()
                self.setUp()
                self.draft(module, qid, judged(**fields))
                for text in additions:
                    provider = Provider(judge=[judged(**fields)], speaker=[{'reply': '好，记得很清楚。'}])
                    reply = self.turn(text, provider)
                    self.assertTrue(self.last(reply).endswith(MORE), text)
                    self.assertNotIn(DRAFT, self.last(reply))
                    self.assertIsNotNone(reply['generation_offer'])
                for text in endings:
                    with_content = speaker.supplement_end(text) == 'with_content'
                    provider = Provider(judge=[judged(**fields)] if with_content else [])
                    reply = self.turn(text, provider)
                    self.assertEqual(self.last(reply), REVIEW, text)
                    self.assertIsNotNone(reply['generation_offer'])
                    self.assertEqual((provider.count('judge'), provider.count('speaker')), (int(with_content), 0), text)
                    self.assertEqual(self.guide().phase, 'review')

    # --- default v2 unchanged --------------------------------------------------------------------------------
    def test_default_v2_supplement_and_signals_are_unchanged(self):
        self.enter_module('family')
        with patch.object(ContractInterviewPipeline, '_call', return_value=base.response(base.EMPTY)) as old, \
                patch.object(V3jPipeline, '_call') as new:
            self.say('那时候下工累了就歇一会儿。')
            self.assertEqual(old.call_count, 2)
            guide = self.guide()
            guide_phase = guide.phase
            self.assertNotIn('pipeline', guide.contract_state)
            self.assertNotEqual(guide_phase, 'review')
            # v2 in the supplement step: only the old exact phrases go to review; others are judged by v2
            with base.database.SessionLocal.begin() as db:
                from app.models.chat_session import ChatSessionModel
                from app.schemas.story_information import StoryInformation
                row = db.get(ChatSessionModel, str(self.session))
                info = StoryInformation.model_validate(row.information)
                info.guided_interview.phase = 'supplement'
                row.information = info.model_dump(mode='json')
            self.say('没有了，就这些。')
            self.assertEqual(old.call_count, 4)
            new.assert_not_called()


class SkeletonTests(unittest.TestCase):
    setUp, tearDown = base.WorkflowTests.setUp, base.WorkflowTests.tearDown
    flows = skeleton.SkeletonFlowTests
    act, data, move_to, last = flows.act, flows.data, flows.move_to, flows.last

    def turn(self, text, provider):
        with patch.dict(os.environ, V3J), patch.object(V3jPipeline, '_call', side_effect=provider):
            return self.act(text)

    def test_c01_cloud_inputs_continue_the_skeleton_question(self):
        for text in ('那时候下工累了就歇一会儿。', '不是累了，我还想接着聊。', '她不想说，后来我就没有再问。'):
            provider = Provider(judge=[judged()], speaker=[{'ack': '', 'question': '那您大概是哪一年出生的呀？'}])
            life = self.turn(text, provider)
            local = self.data()['questions']['SK01']
            self.assertEqual((life['question_id'], life['paused'], local['status']), ('SK01', False, 'pending'), text)
            self.assertEqual(self.last(life), '那您大概是哪一年出生的呀？')
            # each case is its own fresh question state
            with base.database.SessionLocal.begin() as db:
                from app.models.family_member import FamilyMemberModel
                from app.services import life_overview
                db.get(FamilyMemberModel, str(self.person)).life_interview = life_overview.new_data()

    def test_c02_answer_then_not_wanting_to_go_on_closes_as_answered(self):
        self.move_to('SK04')  # the engine asks a follow-up after the first answer
        provider = Provider(judge=[judged(**{'SK04-E1': content('S1.1')})],
                            speaker=[{'reply': '好，这个不多聊了。那' + MAIN('SK05')}])
        life = self.turn('家里人教我做人要老实。别的不想多说了。', provider)
        local = self.data()['questions']['SK04']
        self.assertEqual(local['last_result']['decision'], 'ask')
        self.assertEqual((local['status'], life['question_id']), ('known', 'SK05'))
        self.assertEqual(self.last(life), '好，这个不多聊了。那' + MAIN('SK05'))
        self.assertIn('收尾原因：老人不想多说', provider.seen[-1][1])
        self.assertEqual(local['audit'][-1]['speaker']['reason'], 'declined_partial')
        # the speaking layer failing: the answered fallback, not the refusal one
        self.move_to('SK05')
        provider = Provider(judge=[judged(**{'SK05-E1': content('S1.1')})], speaker=[LLMServiceError('down')])
        life = self.turn('我性子急。别的不想多说了。', provider)
        self.assertEqual(self.last(life), '我记下了。' + MAIN('SK06'))
        self.assertEqual(self.data()['questions']['SK05']['status'], 'known')
        # no real answer: still declined (existing behaviour)
        self.move_to('SK06')
        provider = Provider(judge=[judged()], speaker=[LLMServiceError('down')])
        life = self.turn('这个我不想多讲。', provider)
        self.assertEqual(self.data()['questions']['SK06']['status'], 'declined')

    def test_c02_engine_limited_with_a_declined_field_after_an_answer_closes_as_answered(self):
        self.move_to('SK04')
        provider = Provider(judge=[judged(**{'SK04-E1': content('S1.1'), 'SK04-E3': guided.stated('declined', 'S1.2')})],
                            speaker=[LLMServiceError('down')])
        life = self.turn('家里人教我做人要老实。对我性格有什么影响，我不想说了。', provider)
        local = self.data()['questions']['SK04']
        self.assertEqual(local['last_result']['decision'], 'limited')
        self.assertEqual((local['status'], life['question_id']), ('known', 'SK05'))  # v2 maps limited+declined to declined
        self.assertEqual(self.last(life), '我记下了。' + MAIN('SK05'))  # the answered fallback, not SKIP_ACK
        self.assertEqual(local['audit'][-1]['speaker']['reason'], 'declined_partial')


if __name__ == '__main__':
    unittest.main()
