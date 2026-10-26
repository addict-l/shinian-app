"""Listening candidate's supplement intent boundaries; API + SQLite, synthetic provider fixtures."""
from hashlib import sha256
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_interview_v5f as base
from app.ai import interview_speaker as speaker
from app.ai.contract_interview_v3j import V3jPipeline
from app.services.contract_v3j_interview import DRAFT_TEXT, REVIEW_TEXT, SUPPLEMENT_TEXT


RUNTIME = Path(__file__).resolve().parents[1] / 'app/ai/interview_runtime_v3j_v5f_listening'
LISTENING = {'INTERVIEW_PIPELINE': 'v3j_v5f', 'INTERVIEW_V5F_RUNTIME_DIR': str(RUNTIME),
             'INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256': sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest()}
ACTOR_REPLY = '嗯，认识那会儿的事，就先说这些吧，没有别的要补充了。'


class ReadingTests(unittest.TestCase):
    def test_negated_supplement_wish_is_an_ending(self):
        for text in ('没有别的要补充了。', '嗯，没什么要补充了。', '我没有想补充了。', '没有要补充了。'):
            self.assertEqual(speaker.supplement_end(text, listen_first=True), 'only', text)
        # A topic label is kept conservatively; it must not be mistaken for a wish to continue.
        self.assertEqual(speaker.supplement_end(ACTOR_REPLY, listen_first=True), 'with_content')
        self.assertEqual(speaker.supplement_end('那时候的事我都说完了，没有别的要补充了。', listen_first=True),
                         'with_content')

    def test_addition_and_ending_remain_content(self):
        for text in ('老伴去世那会儿我手头也没钱，没有别的要补充了。',
                     '没有别的要补充了，我们认识时我才十八岁。',
                     '对了，后来我妈也去了工厂，就这些了。'):
            self.assertEqual(speaker.supplement_end(text, listen_first=True), 'with_content', text)

    def test_actual_more_intent_wins(self):
        for text in ('没有，我还想说说我妈。', '没有别的要补充了。不过我还想说说我妈。',
                     '我想补充一点，我妈妈后来也去了厂里。'):
            self.assertIsNone(speaker.supplement_end(text, listen_first=True), text)

    def test_historical_and_reported_endings_are_not_current_intent(self):
        for text in ('那时候她没有别的要补充了。', '她当时说，没有了，就这些。',
                     '当时我说，没有了，就这些。', '我妈说：“没有了，就这些。”',
                     '她说，没有了。我后来又问了一次。'):
            self.assertIsNone(speaker.supplement_end(text, listen_first=True), text)
        self.assertEqual(speaker.supplement_end('她说：“没有了。”没有别的要补充了。', listen_first=True),
                         'with_content')

    def test_historical_bundles_keep_existing_reading(self):
        self.assertIsNone(speaker.supplement_end(ACTOR_REPLY))
        self.assertIsNone(speaker.supplement_end(ACTOR_REPLY, listen_first=False))
        self.assertIsNone(speaker.supplement_end('没有别的要补充了。'))


class GuidedTests(unittest.TestCase):
    setUp, tearDown = base.GuidedTests.setUp, base.GuidedTests.tearDown
    post_life, enter_module = base.GuidedTests.post_life, base.GuidedTests.enter_module
    url = base.GuidedTests.url
    say, guide, move_to = base.GuidedTests.say, base.GuidedTests.guide, base.GuidedTests.move_to
    last = base.GuidedTests.last

    def turn(self, text, provider):
        with patch.dict(os.environ, LISTENING), patch.object(V3jPipeline, '_call', side_effect=provider):
            return self.say(text)

    def draft(self):
        self.enter_module('family')
        reply = self.turn(base.FM01_TEXT, base.Provider(judge=[base.FM01_READY],
            deepen=[{'dimension': '', 'ack': '', 'question': ''}],
            speaker=[{'reply': '是在厂里慢慢熟起来的。那您和伴侣平时是怎样相伴生活的？'}]))
        self.assertEqual(self.guide().phase, 'supplement')
        self.assertTrue(self.last(reply).endswith(DRAFT_TEXT))

    def test_actor_reply_stops_at_review_and_preserves_words(self):
        self.draft()
        provider = base.Provider(judge=[base.FM01_READY],
                                 speaker=[{'reply': '认识那会儿的事先聊到这里。'}])
        reply = self.turn(ACTOR_REPLY, provider)
        self.assertEqual(self.guide().phase, 'review')
        self.assertEqual(self.last(reply), REVIEW_TEXT)
        self.assertEqual((provider.count('judge'), provider.count('speaker')), (1, 0))
        self.assertEqual(self.guide().contract_state['sources'][-1]['text'], ACTOR_REPLY)

    def test_only_negated_wish_goes_to_review_without_model(self):
        self.draft()
        provider = base.Provider()
        reply = self.turn('没有别的要补充了。', provider)
        self.assertEqual(self.last(reply), REVIEW_TEXT)
        self.assertEqual(self.guide().phase, 'review')
        self.assertEqual(provider.seen, [])
        self.assertEqual(len(self.guide().contract_state['sources']), 1)

    def test_real_addition_is_retained_before_review(self):
        self.draft()
        text = '老伴去世那会儿我手头也没钱，没有别的要补充了。'
        provider = base.Provider(judge=[base.FM01_READY])
        reply = self.turn(text, provider)
        self.assertEqual(self.last(reply), REVIEW_TEXT)
        self.assertEqual(self.guide().phase, 'review')
        self.assertEqual(self.guide().contract_state['sources'][-1]['text'], text)
        self.assertEqual((provider.count('judge'), provider.count('speaker')), (1, 0))

    def test_current_wish_to_continue_and_reported_ending_keep_supplement(self):
        self.draft()
        for text in ('没有，我还想说说我妈。', '她当时说，没有了，就这些。'):
            provider = base.Provider(judge=[base.FM01_READY], speaker=[{'reply': '您说到妈妈了。'}])
            reply = self.turn(text, provider)
            self.assertEqual(self.guide().phase, 'supplement', text)
            self.assertTrue(self.last(reply).endswith(SUPPLEMENT_TEXT), text)
            self.assertEqual(self.guide().contract_state['sources'][-1]['text'], text)
            self.assertEqual((provider.count('judge'), provider.count('speaker')), (1, 1))


if __name__ == '__main__':
    unittest.main()
