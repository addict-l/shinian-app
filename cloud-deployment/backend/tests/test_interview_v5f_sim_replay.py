"""v5f parity: replay the st7-b5f-it simulated interviews (story-question deepening) through the backend offline.

Each simulated module question goes through the backend's own question_turn / skip_turn on the v3j_v5f bundle
(judgment, ending rules with the signal scope, the deepen step, the v5f wording guards), the skeleton story
question SK01c through the skeleton entry (life_overview.perform on the isolated SQLite App setup,
INTERVIEW_PIPELINE=v3j_v5f). An SDK stand-in answers from the evaluation cache by Relay.key (system, user and
parameters), so a judge, deepen or speaker request the backend builds differently from the simulator misses the
cache and fails the test; nothing is sent to a provider and no token is spent.

Compared per elder answer: the judgment result and the ending-rule action (judged answers), that an answer to a
detail question is not judged, the deepen and speaking-layer inputs (the simulator's recorded inputs, and a cache
hit for every request, including deepen calls whose reply failed the checks), the follow-up, detail-question and
transition texts, and the deepen log (asked / skipped and why). As in the v4d replay, the next entry and the "last
close" lines are the simulator's (patched in), and so is the list of earlier closes the v5f "repeat" guard reads;
the draft step the guided interview keeps, and the backend pause, are listed as designed differences.

Needs the git-ignored evaluation data (.runtime/interview-eval runs/st7-b5f-it and cache) and the full repository;
skips when absent.

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_v5f_sim_replay -v
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_interview_v3j_full45_replay import CACHE, RUNS, RUNTIME, CachedDeepSeek, load_eval_common  # noqa: E402

SIM = RUNS / 'st7-b5f-it'
V5F_RUNTIME = BACKEND / 'app/ai/interview_runtime_v3j_v5f'
MODULES = ('childhood', 'growth', 'work', 'family', 'later_life', 'reflection')


def configure():
    main = BACKEND / 'app/ai/interview_runtime'
    os.environ.setdefault('INTERVIEW_RUNTIME_DIR', str(main))
    os.environ.setdefault('INTERVIEW_RUNTIME_MANIFEST_SHA256', sha256((main / 'manifest.json').read_bytes()).hexdigest())
    os.environ['INTERVIEW_V3J_RUNTIME_DIR'] = str(RUNTIME)
    os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'] = sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest()
    os.environ['INTERVIEW_V5F_RUNTIME_DIR'] = str(V5F_RUNTIME)
    os.environ['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256'] = sha256((V5F_RUNTIME / 'manifest.json').read_bytes()).hexdigest()


def message(role, content, session):
    return SimpleNamespace(id=uuid4(), role=role, content=content, type='text', session_id=session)


def summary(rt, result):
    """The simulator's judge_summary of a result."""
    from app.ai.interview_speaker import recorded_fields
    return {'decision': result.get('decision'), 'target': result.get('target'), 'question': result.get('question'),
            'effective': {k: v for k, v in (result.get('effective') or {}).items() if rt.F[k]['requirement'] != 'optional'},
            'active': result.get('active'), 'fields': recorded_fields(rt, result), 'errors': result.get('errors')}


def comparable(log):
    """Deepen log entries both sides write: the gate's decisions on a close (the simulator also logs the ends of
    refusals and pauses, where the backend does not consider deepening)."""
    return [(e.get('k'), e['decision'], e['reason'], e.get('question') or '', tuple(e.get('errors') or ()))
            for e in log if not str(e['reason']).startswith(('not_done_declined', 'not_done_deferred', 'not_done_rest'))
            and e['reason'] not in ('answer_skip_control',)]


class V5fSimReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ((SIM / 'sessions').is_dir() and CACHE.is_dir() and V5F_RUNTIME.is_dir()):
            raise unittest.SkipTest('Evaluation data (st7-b5f-it, response cache) not present')
        cls.common = load_eval_common()
        configure()

    def test_st7_b5f_it_deepen_and_speaker_inputs_and_replies(self):
        from app.schemas.guided_interview import GuidedInterviewState
        from app.schemas.story_information import StoryInformation
        from app.services import contract_v3j_interview as flow
        from app.services.contract_interview_state import questions, v5f_runtime
        rt = v5f_runtime()
        fake = self.fake = CachedDeepSeek(self.common.Relay.key)
        stats = dict.fromkeys(('answers', 'judged', 'judge_equal', 'action_equal', 'deepen_answers', 'deepen_calls',
                               'deepen_input_equal', 'deepens', 'deepen_equal', 'speaker_calls', 'speaker_input_equal',
                               'followups', 'followup_equal', 'transitions', 'transition_equal', 'draft', 'rest',
                               'skeleton_closes', 'skeleton_close_equal', 'logs_equal', 'episodes'), 0)
        failures, draft_diffs = [], []
        for path in sorted((SIM / 'sessions').glob('*.json')):
            session = json.loads(path.read_text(encoding='utf-8'))
            plan = session['questions']
            sim_prev_close, sim_seen, life = None, [], None
            for ei, episode in enumerate(session['episodes']):
                qid = episode['qid']
                stats['episodes'] += 1
                sim_next = rt.questions[plan[ei + 1]]['main_question'] if ei + 1 < len(plan) else None
                module = next((m for m in MODULES if any(q['id'] == qid for q in questions(m))), None)
                seen = list(sim_seen)
                if module is None:
                    life = self.skeleton_episode(session, plan, ei, episode, fake, life, sim_next, seen, stats, failures)
                else:
                    self.module_episode(session, episode, module, fake, sim_next, sim_prev_close, seen, stats, failures,
                                        draft_diffs, flow, questions, GuidedInterviewState, StoryInformation, rt)
                close = next((x for x in reversed(episode['messages']) if x['role'] == 'system' and x.get('kind') == 'close'), None)
                if close and not (close.get('speaker') or {}).get('fixed'):
                    sim_prev_close = close['text']
                    sim_seen.append(close['text'])
        print('\nst7-b5f-it backend replay:', json.dumps(stats, ensure_ascii=False))
        print(f'cache misses {len(fake.misses)}; provider requests {len(fake.requests)}')
        print(f'draft-step differences ({len(draft_diffs)}):\n  ' + '\n  '.join(draft_diffs))
        self.assertEqual(failures, [])
        self.assertEqual(fake.misses, [])
        self.assertEqual(stats['judged'], stats['judge_equal'])
        self.assertEqual(stats['judged'], stats['action_equal'])
        self.assertEqual(stats['deepen_calls'], stats['deepen_input_equal'])
        self.assertEqual(stats['deepens'], stats['deepen_equal'])
        self.assertEqual(stats['speaker_calls'], stats['speaker_input_equal'])
        self.assertEqual(stats['episodes'], stats['logs_equal'])
        self.assertEqual((stats['episodes'], stats['deepens'], stats['deepen_answers']), (16, 10, 10))

    def module_episode(self, session, episode, module, fake, sim_next, sim_prev_close, seen, stats, failures, draft_diffs,
                       flow, questions, GuidedInterviewState, StoryInformation, rt):
        qid = episode['qid']
        state = GuidedInterviewState(version=3, module=module, module_selected=True, runtime_version=rt.version,
                                     topic_index=[q['id'] for q in questions(module)].index(qid), phase='opening',
                                     speaker_last_close=sim_prev_close)
        sid = uuid4()
        sims = episode['messages']
        msgs = [message('assistant', sims[0]['text'], sid)]
        information = StoryInformation(guided_interview=state)
        for j, m in enumerate(sims):
            if m['role'] != 'elder' or m.get('scripted'):
                continue
            stats['answers'] += 1
            reply_sim = next(x for x in sims[j + 1:] if x['role'] == 'system')
            msgs.append(message('user', m['text'], sid))
            before = len(fake.requests)
            env = {'INTERVIEW_PIPELINE': 'v3j_v5f'}
            with patch.dict(os.environ, env), patch('app.services.contract_guided_interview._persist_pending'), \
                    patch.object(flow, 'upcoming', lambda s: (sim_next, False)), \
                    patch.object(flow, 'seen_closes', lambda s: list(seen)):
                if m.get('judge') is None and not m.get('deepen_answer'):
                    information, reply = flow.skip_turn(fake, information, state, msgs)
                else:
                    information, reply = flow.question_turn(fake, information, state, msgs, msgs[-1])
            state = information.guided_interview
            where = f'{session["name"]} {qid} #{j}'
            local = state.contract_state if (state.contract_state or {}).get('question_id') == qid else \
                state.contract_history.get(qid, {})  # a transition moved the question to the history
            if local.get('pipeline') != 'v3j_v5f':
                failures.append(where + ' question not in the v3j_v5f flow')
            self.compare(where, m, reply_sim, fake.requests[before:], local, stats, failures, rt)
            kind, reason = reply_sim['kind'], reply_sim.get('reason')
            text = reply.text
            if kind == 'followup':
                stats['followups'] += 1
                stats['followup_equal'] += text == reply_sim['text']
                if text != reply_sim['text']:
                    failures.append(where + f' follow-up {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'deepen':
                stats['deepens'] += 1
                stats['deepen_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or reply.action != 'continue':
                    failures.append(where + f' deepen {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'close' and reason in ('declined', 'deferred'):
                stats['transitions'] += 1
                stats['transition_equal'] += text == reply_sim['text']
                if text != reply_sim['text']:
                    failures.append(where + f' transition {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'close' and reason != 'rest':
                stats['draft'] += 1
                if reply.action != 'offer_generation' or not text.endswith(flow.DRAFT_TEXT):
                    failures.append(where + ' draft step lost')
                draft_diffs.append(f'{where} [{reason}] 模拟：{reply_sim["text"]}\n    后端：{text}')
            else:
                stats['rest'] += 1
                if text != flow.PAUSE_TEXT:
                    failures.append(where + ' pause text changed')
            msgs.append(message('assistant', text, sid))
            if kind in ('close', 'pause'):
                break
        local = state.contract_state if (state.contract_state or {}).get('question_id') == qid else state.contract_history.get(qid, {})
        self.compare_log(session, episode, local.get('deepen'), stats, failures)

    def compare(self, where, m, reply_sim, new, local, stats, failures, rt):
        """Judgment, action and the inputs of this answer's deepen and speaker calls."""
        deepen_requests = [r for r in new if r['system'] == rt.deepen_prompt]
        speaker_requests = [r for r in new if r['system'] == rt.speaker_prompt]
        if m.get('deepen_answer'):
            stats['deepen_answers'] += 1
            if any(r['system'] not in (rt.deepen_prompt, rt.speaker_prompt) for r in new):
                failures.append(where + ' an answer to a detail question was judged')
        elif m.get('judge') is not None:
            stats['judged'] += 1
            stats['judge_equal'] += summary(rt, local['last_result']) == m['judge']
            if summary(rt, local['last_result']) != m['judge']:
                failures.append(where + ' judge result differs')
            action = [x for x in local['audit'] if x.get('result') is not None][-1]['speaker']
            if [action['action'], action['reason']] == m['v4_action']:
                stats['action_equal'] += 1
            else:
                failures.append(where + f' action {action["action"]}/{action["reason"]} vs {m["v4_action"]}')
        stats['deepen_calls'] += len(deepen_requests)
        missed = {r['key'] for r in self.fake.misses}
        stats['deepen_input_equal'] += len([r for r in deepen_requests if r['key'] not in missed])
        sim_input = (reply_sim.get('speaker') or {}).get('input')
        if reply_sim['kind'] == 'deepen':
            if not deepen_requests or deepen_requests[-1]['user'] != sim_input:
                failures.append(where + ' deepen input differs')
        if speaker_requests:
            stats['speaker_calls'] += 1
            if reply_sim['kind'] != 'deepen' and sim_input == speaker_requests[-1]['user']:
                stats['speaker_input_equal'] += 1
            else:
                failures.append(where + ' speaker input differs')
        elif sim_input and reply_sim['kind'] != 'deepen':
            failures.append(where + ' no speaker call')

    def compare_log(self, session, episode, dz, stats, failures):
        sim = comparable((episode.get('deepen') or {}).get('log') or [])
        mine = comparable((dz or {}).get('log') or [])
        if sim == mine:
            stats['logs_equal'] += 1
        else:
            failures.append(f'{session["name"]} {episode["qid"]} deepen log {mine} vs {sim}')

    def skeleton_episode(self, session, plan, ei, episode, fake, life, sim_next, seen, stats, failures):
        """The simulated SK question through the skeleton entry, the plan's next question patched in."""
        import test_contract_interview_workflow as base
        from app.models.family_member import FamilyMemberModel
        from app.schemas.life_overview import LifeAction
        from app.services import contract_v3j_life_overview as skeleton
        from app.services import life_overview
        from app.services.contract_interview_state import questions, v5f_runtime
        rt = v5f_runtime()
        qid = episode['qid']
        if not hasattr(self, 'fixture'):
            self.fixture = base.WorkflowTests('test_catalog_routes_contain_all_six_modules_and_72_questions')
            self.fixture.setUp()
            self.addCleanup(self.fixture.tearDown)
        person = self.fixture.person
        life = life_overview.new_data()
        for key in [q['id'] for q in questions('skeleton')]:
            if key != qid:
                life['questions'][key]['status'] = 'skipped'
        life['turns'].append({'id': str(uuid4()), 'role': 'assistant', 'content': rt.questions[qid]['main_question'],
                              'created_at': 'replay'})
        sims = episode['messages']
        for j, m in enumerate(sims):
            if m['role'] != 'elder' or m.get('scripted'):
                continue
            stats['answers'] += 1
            where = f'{session["name"]} {qid} #{j}'
            reply_sim = next(x for x in sims[j + 1:] if x['role'] == 'system')
            with base.database.SessionLocal.begin() as db:
                db.get(FamilyMemberModel, str(person)).life_interview = deepcopy(life)
            before = len(fake.requests)
            with patch.dict(os.environ, {'INTERVIEW_PIPELINE': 'v3j_v5f'}), \
                    patch.object(skeleton, 'next_question', lambda data, q: sim_next), \
                    patch.object(skeleton, 'seen_closes', lambda data: list(seen)):
                life_overview.perform(person, LifeAction(action='answer', text=m['text'], expected_version=life['version'],
                                                         client_request_id=uuid4()), fake)
            with base.database.SessionLocal() as db:
                life = deepcopy(db.get(FamilyMemberModel, str(person)).life_interview)
            local = life['questions'][qid]
            if local.get('pipeline') != 'v3j_v5f':
                failures.append(where + ' skeleton question not in the v3j_v5f flow')
            self.compare(where, m, reply_sim, fake.requests[before:], local, stats, failures, rt)
            text = life['turns'][-1]['content']
            kind = reply_sim['kind']
            if kind == 'deepen':
                stats['deepens'] += 1
                stats['deepen_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or local['status'] != 'pending':
                    failures.append(where + f' deepen {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'followup':
                stats['followups'] += 1
                stats['followup_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or local['status'] != 'pending':
                    failures.append(where + f' follow-up {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'close':
                stats['skeleton_closes'] += 1
                stats['skeleton_close_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or local['status'] == 'pending':
                    failures.append(where + f' close {text!r} vs {reply_sim["text"]!r}')
            if kind in ('close', 'pause'):
                break
        self.compare_log(session, episode, local.get('deepen'), stats, failures)
        return life


if __name__ == '__main__':
    unittest.main()
