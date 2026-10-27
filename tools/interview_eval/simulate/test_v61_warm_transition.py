"""Offline tests of the V6.1 simulator's production close adapter."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import interview  # noqa: E402


POLICY = {'listen_first': True, 'warm_transition': True}
ENTRY = '小时候家里主要靠什么维持生活？'
WORDS = '我爸胆子大，从亲戚那里借了一块田，种了好几年双季稻。'


class WarmTransitionTests(unittest.TestCase):
    def close(self, reply, entry=ENTRY, seen=(), words=WORDS, reason=None):
        return interview.warm_transition_close(POLICY, reply, entry, words, seen, reason=reason)

    def test_user_example_keeps_ack_transition_and_exact_entry(self):
        reply = '您爸胆子大，还借田种双季稻。那咱们再来聊聊，' + ENTRY
        text, ack, notes, ok = self.close(reply)
        self.assertTrue(ok)
        self.assertEqual(text, reply)
        self.assertEqual(ack, '您爸胆子大，还借田种双季稻。')
        self.assertEqual(text.count('？'), 1)
        self.assertFalse(notes)

    def test_repeated_phrase_is_replaced_and_recorded(self):
        reply = '您爸借田种双季稻。那咱们再来聊聊，' + ENTRY
        text, ack, notes, ok = self.close(reply, seen=['以前种过地。那咱们再来聊聊，其他问题？'])
        self.assertTrue(ok)
        self.assertEqual(ack, '您爸借田种双季稻。')
        self.assertTrue(text.endswith(ENTRY))
        self.assertNotIn('那咱们再来聊聊', text)
        self.assertIn('transition_fallback', notes)

    def test_empty_model_output_uses_disclosed_safe_fallback(self):
        text, ack, notes, ok = self.close('')
        self.assertTrue(ok)
        self.assertEqual(ack, '嗯，这段我听到了。')
        self.assertTrue(text.startswith(ack))
        self.assertTrue(text.endswith(ENTRY))
        self.assertIn('ack_fallback', notes)
        self.assertIn('transition_fallback', notes)

    def test_no_next_question_does_not_insert_transition(self):
        text, ack, _, ok = self.close('您爸借田种双季稻。', None)
        self.assertTrue(ok)
        self.assertEqual(text, ack)
        self.assertNotIn('聊聊', text)
        self.assertNotIn('？', text)

    def test_move_on_alone_is_not_acknowledgement_for_refusal(self):
        reply = '接下来聊聊。那咱们再来聊聊，' + ENTRY
        text, ack, notes, ok = self.close(reply, words='这道题我不想说。', reason='declined')
        self.assertTrue(ok)
        self.assertNotIn('接下来聊聊', ack)
        self.assertEqual(ack, '好，这段咱们就不多说了。')
        self.assertIn('ack_fallback', notes)
        self.assertTrue(text.endswith(ENTRY))

    def test_unstated_opinions_are_not_added_to_ack(self):
        for reply, words, forbidden in (
            ('农闲时您父亲还做木工，真勤快。那咱们再来聊聊，' + ENTRY,
             '小时候家里主要靠父母种田，农闲时父亲也帮邻居做木工。', '真勤快'),
            ('苏州的小村庄，听着就亲切。那咱们再来聊聊，' + ENTRY,
             '我出生在江苏苏州的小村庄。', '听着就亲切'),
            ('答应别人的事要做到，这习惯好。那咱们再来聊聊，' + ENTRY,
             '家里人教我要诚实，答应别人的事要做到。', '这习惯好'),
        ):
            with self.subTest(forbidden=forbidden):
                text, ack, _, ok = self.close(reply, words=words)
                self.assertTrue(ok)
                self.assertNotIn(forbidden, ack)
                self.assertNotIn(forbidden, text)
                self.assertTrue(text.endswith(ENTRY))

    def test_consecutive_session_turns_do_not_repeat_the_transition(self):
        class FakePersonas:
            names = {'n': '模拟受访者'}

            def material(self, *_):
                return []

            def render(self, material):
                return ''

        entries = ['您小时候和谁住？', '家里靠什么维持生活？', '您有兄弟姐妹吗？', '家里人相处得怎么样？']
        keys = ['one', 'two', 'three', 'four']
        setup = SimpleNamespace(
            Q={key: {'main_question': entry} for key, entry in zip(keys, entries)},
            F={}, personas=FakePersonas(), sim_prompt='', speaker_prompt='', deepen=None,
            sim_cfg={'probabilities': {'first_answer': {'short': 1}, 'asr_typos': 0},
                     'behaviors': {'short': ''}, 'asr_note': '', 'model': {}},
            policy={**POLICY, 'model': {}},
        )
        g = interview.session(setup, 's', 'n', keys, 'v4')
        next(g)
        for i, entry in enumerate(entries):
            g.send([{'ok': True, 'output': {'reply': '跳过'}}])
            reply = ('接下来聊聊。那咱们再来聊聊，' + entries[i + 1]) if i + 1 < len(entries) else '好，这题先不说了。'
            try:
                g.send([{'ok': True, 'output': {'reply': reply}}])
            except StopIteration as done:
                record = done.value
        closes = [episode['messages'][-1] for episode in record['episodes'][:3]]
        prefixes = []
        for close, entry in zip(closes, entries[1:]):
            self.assertTrue(close['text'].endswith(entry))
            self.assertNotIn('接下来聊聊', close['speaker']['ack'])
            self.assertEqual(close['speaker']['ack'], '好，这段咱们就不多说了。')
            prefixes.append(close['text'][len(close['speaker']['ack']):-len(entry)])
        self.assertEqual(len(set(prefixes)), 3)

    def test_end_to_end_session_uses_adapter_and_preserves_old_path(self):
        class FakePersonas:
            names = {'n': '模拟受访者'}

            def material(self, *_):
                return []

            def render(self, material):
                return ''

        def run(policy, fail_first_speaker=False):
            setup = SimpleNamespace(
                Q={'one': {'main_question': '您小时候跟谁一起生活？'},
                   'two': {'main_question': ENTRY}},
                F={}, personas=FakePersonas(), sim_prompt='', speaker_prompt='', deepen=None,
                sim_cfg={'probabilities': {'first_answer': {'short': 1}, 'asr_typos': 0},
                         'behaviors': {'short': ''}, 'asr_note': '', 'model': {}},
                policy={**policy, 'model': {}},
            )
            g = interview.session(setup, 's', 'n', ['one', 'two'], 'v4')
            next(g)  # first elder
            g.send([{'ok': True, 'output': {'reply': '跳过'}}])
            first_close = '这道题就先不说。那咱们再来聊聊，' + ENTRY
            row = {'ok': False} if fail_first_speaker else {'ok': True, 'output': {'reply': first_close}}
            g.send([row])  # first close -> next elder
            g.send([{'ok': True, 'output': {'reply': '跳过'}}])
            with self.assertRaises(StopIteration) as done:
                g.send([{'ok': True, 'output': {'reply': '好的，今天先聊到这里。'}}])
            return done.exception.value['episodes'][0]['messages'][-1]

        warm = run(POLICY)
        old = run({})
        self.assertIn('那咱们再来聊聊', warm['text'])
        self.assertTrue(warm['text'].endswith(ENTRY))
        self.assertEqual(warm['entry_part'], ENTRY)
        self.assertEqual(old['text'], '这道题就先不说。那咱们再来聊聊，' + ENTRY)
        failed = run(POLICY, fail_first_speaker=True)
        self.assertTrue(failed['speaker']['fallback'])
        self.assertIn('ack_fallback', failed['speaker']['repairs'])
        self.assertTrue(failed['text'].startswith('好，这段咱们就不多说了。'))
        self.assertTrue(failed['text'].endswith(ENTRY))


if __name__ == '__main__':
    unittest.main()
