"""Speaking-layer parity: replay the sim-hv4d simulated interviews through the backend flow offline.

Each simulated question is driven through the backend's own question_turn /
skip_turn (judgment, natural-ending rules, speaker input built from session
messages and question state, reply composition) with an SDK stand-in answering
from the evaluation cache by Relay.key. A request the backend builds differently
misses the cache; nothing is sent to a provider and no token is spent.

Two inputs differ between the simulator and the backend by design, so the parity
run gives the backend the simulator's values and the real values are compared
separately: the next entry (the simulator's 4-question plan versus the module's
next question / module menu) and the "last close" line (after a draft step the
backend remembers only the acknowledgement it showed). Expected differences
coming from the kept draft step and pause are listed, not failed.

Needs the git-ignored evaluation data (.runtime/interview-eval runs/sim-hv4d and
cache, or SHINIAN_EVAL_*) and the full repository; skips when absent.

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_v4d_sim_replay -v
"""
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

SIM = RUNS / 'sim-hv4d'


def configure():
    main = BACKEND / 'app/ai/interview_runtime'
    os.environ.setdefault('INTERVIEW_RUNTIME_DIR', str(main))
    os.environ.setdefault('INTERVIEW_RUNTIME_MANIFEST_SHA256', sha256((main / 'manifest.json').read_bytes()).hexdigest())
    os.environ['INTERVIEW_V3J_RUNTIME_DIR'] = str(RUNTIME)
    os.environ['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'] = sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest()


def message(role, content, session):
    return SimpleNamespace(id=uuid4(), role=role, content=content, type='text', session_id=session)


def summary(rt, result):
    """The simulator's judge_summary of a result."""
    from app.ai.interview_speaker import recorded_fields
    return {'decision': result.get('decision'), 'target': result.get('target'), 'question': result.get('question'),
            'effective': {k: v for k, v in (result.get('effective') or {}).items() if rt.F[k]['requirement'] != 'optional'},
            'active': result.get('active'), 'fields': recorded_fields(rt, result), 'errors': result.get('errors')}


class SimReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ((SIM / 'sessions').is_dir() and CACHE.is_dir()):
            raise unittest.SkipTest('Evaluation data (sim-hv4d, response cache) not present')
        cls.common = load_eval_common()
        configure()

    def test_sim_hv4d_speaker_inputs_and_replies(self):
        from app.schemas.guided_interview import GuidedInterviewState
        from app.schemas.story_information import StoryInformation
        from app.services import contract_v3j_interview as flow
        from app.services.contract_interview_state import questions, v3j_runtime
        rt = v3j_runtime()
        real_upcoming = flow.upcoming
        fake = CachedDeepSeek(self.common.Relay.key)
        stats = {'judged': 0, 'judge_equal': 0, 'action_equal': 0, 'speaker_calls': 0, 'speaker_input_equal': 0,
                 'followup_equal': 0, 'followups': 0, 'transition_equal': 0, 'transitions': 0, 'draft': 0, 'rest': 0}
        failures, draft_diffs, rest_diffs, prev_close_diffs, next_diffs, skeleton = [], [], [], [], [], set()
        for path in sorted((SIM / 'sessions').glob('*.json')):
            session = json.loads(path.read_text(encoding='utf-8'))
            plan = session['questions']
            sim_prev_close = None      # the simulator's last close text (its "上次换话题时你说的")
            backend_last_close = None  # what the backend itself would remember (ack only after a draft step)
            transition_shown = None    # a transition close also shows the next entry
            for ei, episode in enumerate(session['episodes']):
                qid = episode['qid']
                sim_next = rt.questions[plan[ei + 1]]['main_question'] if ei + 1 < len(plan) else None
                module = next((m for m in ('childhood', 'growth', 'work', 'family', 'later_life', 'reflection')
                               if any(q['id'] == qid for q in questions(m))), None)
                fields = dict(version=3, module=module or 'skeleton', module_selected=True, runtime_version=rt.version,
                              topic_index=[q['id'] for q in questions(module or 'skeleton')].index(qid), phase='opening',
                              speaker_last_close=sim_prev_close)
                if module:
                    state = GuidedInterviewState(**fields)
                    real_next = real_upcoming(state)[0]
                    if real_next != sim_next:
                        next_diffs.append(f'{session["name"]} {qid}: 模拟下一题 {sim_next!r}；后端模块内下一项 {real_next[:40]!r}')
                else:
                    # SK questions are asked by the life overview in the backend (fixed wording, v2
                    # judgment); the guided flow is driven here only to check message construction.
                    skeleton.add(f'{session["name"]} {qid}')
                    state = GuidedInterviewState.model_construct(**{**GuidedInterviewState().model_dump(), **fields})
                if ei and sim_prev_close != backend_last_close:
                    prev_close_diffs.append(f'{session["name"]} {qid}: 模拟 {sim_prev_close!r}；后端 {backend_last_close!r}')
                sid = uuid4()
                # after a backend draft step the next segment opens with the bare entry; after a transition the
                # narrator saw the close text ending with the entry (both are recorded as the entry question)
                msgs = [message('assistant', transition_shown or rt.questions[qid]['main_question'], sid)]
                transition_shown = None
                information = StoryInformation(guided_interview=state)
                sims = episode['messages']
                for j, m in enumerate(sims):
                    if m['role'] != 'elder' or m.get('scripted'):
                        continue
                    reply_sim = next(x for x in sims[j + 1:] if x['role'] == 'system')
                    msgs.append(message('user', m['text'], sid))
                    before = len(fake.requests)
                    with patch('app.services.contract_guided_interview._persist_pending'), \
                            patch.object(flow, 'upcoming', lambda s: (sim_next, False)):
                        if m.get('judge') is None:
                            information, reply = flow.skip_turn(fake, information, state, msgs)
                        else:
                            information, reply = flow.question_turn(fake, information, state, msgs, msgs[-1])
                    new = fake.requests[before:]
                    spoken = [r for r in new if r['system'] == rt.speaker_prompt]
                    where = f'{session["name"]} {qid} #{j}'
                    local = state.contract_state
                    audit = local['audit'][-1]
                    if m.get('judge') is not None:
                        stats['judged'] += 1
                        if summary(rt, local['last_result']) == m['judge']:
                            stats['judge_equal'] += 1
                        else:
                            failures.append(where + ' judge result differs')
                        if [audit['speaker']['action'], audit['speaker']['reason']] == m['v4_action']:
                            stats['action_equal'] += 1
                        else:
                            failures.append(where + f' action {audit["speaker"]["action"]} vs {m["v4_action"]}')
                    sim_input = (reply_sim.get('speaker') or {}).get('input')
                    if spoken:
                        stats['speaker_calls'] += 1
                        if sim_input == spoken[-1]['user']:
                            stats['speaker_input_equal'] += 1
                        else:
                            failures.append(where + ' speaker input differs')
                    elif sim_input:
                        failures.append(where + ' no speaker call')
                    kind, reason = reply_sim['kind'], reply_sim.get('reason')
                    if kind == 'followup':
                        stats['followups'] += 1
                        stats['followup_equal'] += reply.text == reply_sim['text']
                        if reply.text != reply_sim['text'] or reply.action != 'continue':
                            failures.append(where + f' follow-up {reply.text!r} vs {reply_sim["text"]!r}')
                    elif kind == 'close' and reason in ('declined', 'deferred'):
                        stats['transitions'] += 1
                        stats['transition_equal'] += reply.text == reply_sim['text']
                        if reply.text != reply_sim['text'] or reply.action != 'continue':
                            failures.append(where + f' transition {reply.text!r} vs {reply_sim["text"]!r}')
                        backend_last_close = transition_shown = reply.text
                    elif kind == 'close' and reason != 'rest':
                        stats['draft'] += 1
                        if reply.action != 'offer_generation' or not reply.text.endswith(flow.DRAFT_TEXT):
                            failures.append(where + ' draft step lost')
                        draft_diffs.append(f'{where} [{reason}] 模拟：{reply_sim["text"]}\n    后端：{reply.text}')
                        backend_last_close = audit['speaker']['ack'] or backend_last_close
                    else:  # tired: the backend keeps its existing pause
                        stats['rest'] += 1
                        later = [x['text'] for x in sims[j + 1:] if x['role'] == 'system']
                        rest_diffs.append(f'{where} 模拟：{" / ".join(later)}\n    后端：{reply.text}')
                        if reply.text != flow.PAUSE_TEXT or reply.action != 'continue':
                            failures.append(where + ' pause text changed')
                    msgs.append(message('assistant', reply.text, sid))
                    state = information.guided_interview
                    if kind in ('close', 'pause'):
                        break
                close = next((x for x in reversed(sims) if x['role'] == 'system' and x.get('kind') == 'close'), None)
                if close and not (close.get('speaker') or {}).get('fixed'):
                    sim_prev_close = close['text']
        print('\nsim-hv4d backend replay:', json.dumps(stats, ensure_ascii=False))
        print(f'cache misses {len(fake.misses)}; provider requests {len(fake.requests)}')
        print(f'draft-step differences ({len(draft_diffs)}):\n  ' + '\n  '.join(draft_diffs))
        print(f'pause differences ({len(rest_diffs)}):\n  ' + '\n  '.join(rest_diffs))
        print(f'"上次换话题时你说的" the backend would send instead ({len(prev_close_diffs)}):\n  ' + '\n  '.join(prev_close_diffs))
        print(f'next entry differs from the simulator plan ({len(next_diffs)}):\n  ' + '\n  '.join(next_diffs))
        print(f'skeleton questions (life overview in the backend) ({len(skeleton)}): ' + '、'.join(sorted(skeleton)))
        self.assertEqual(failures, [])
        self.assertEqual(fake.misses, [])
        self.assertEqual(stats['judged'], stats['judge_equal'])
        self.assertEqual(stats['speaker_calls'], stats['speaker_input_equal'])
        self.assertEqual((stats['followups'], stats['transitions'], stats['draft'], stats['rest']), (3, 3, 27, 2))


if __name__ == '__main__':
    unittest.main()
