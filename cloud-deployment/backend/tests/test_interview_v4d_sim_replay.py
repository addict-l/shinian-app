"""Speaking-layer parity: replay the sim-hv4d simulated interviews through the backend flow offline.

Each simulated module question is driven through the backend's own
question_turn / skip_turn (judgment, natural-ending rules, speaker input built
from session messages and question state, reply composition), and each SK
question through the skeleton entry (life_overview.perform on the isolated
SQLite App setup, INTERVIEW_PIPELINE=v3j_v4d), with an SDK stand-in answering
from the evaluation cache by Relay.key. A request the backend builds differently
misses the cache; nothing is sent to a provider and no token is spent.

Two inputs differ between the simulator and the backend by design, so the parity
run gives the backend the simulator's values and the real values are compared
separately: the next entry (the simulator's 4-question plan versus the module's
next question / module menu) and the "last close" line (after a draft step the
backend remembers only the acknowledgement it showed). Expected differences
coming from the kept draft step and pause are listed, not failed.

For the skeleton the simulator's 4-question plan is reproduced by the fixture:
skeleton questions outside the plan count as answered earlier, so the backend's
own next question is the plan's next one and its own "last close" is used (no
substitution). After the plan's last question the backend has no next skeleton
question and keeps its review text; after a pause the fixture moves on to the
plan's next question. Both are listed, as are the next questions a full
skeleton would really have there.

Needs the git-ignored evaluation data (.runtime/interview-eval runs/sim-hv4d and
cache, or SHINIAN_EVAL_*) and the full repository; skips when absent.

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_v4d_sim_replay -v
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


def life_overview_review():
    from app.services.contract_life_overview import REVIEW_TEXT
    return REVIEW_TEXT


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
        failures, draft_diffs, rest_diffs, prev_close_diffs, next_diffs = [], [], [], [], []
        sk = {'stats': dict.fromkeys(('questions', 'judged', 'judge_equal', 'action_equal', 'speaker_calls', 'speaker_input_equal',
                                      'followups', 'followup_equal', 'closes', 'close_equal', 'last', 'rest'), 0),
              'failures': failures, 'differences': [], 'real': []}
        life = None
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
                if module is None:
                    life = self.skeleton_episode(session, plan, ei, episode, fake, life if ei else None, sk)
                    close = next((x for x in reversed(episode['messages']) if x['role'] == 'system' and x.get('kind') == 'close'), None)
                    if close and not (close.get('speaker') or {}).get('fixed'):
                        sim_prev_close = close['text']
                    continue
                fields = dict(version=3, module=module, module_selected=True, runtime_version=rt.version,
                              topic_index=[q['id'] for q in questions(module)].index(qid), phase='opening',
                              speaker_last_close=sim_prev_close)
                state = GuidedInterviewState(**fields)
                real_next = real_upcoming(state)[0]
                if real_next != sim_next:
                    next_diffs.append(f'{session["name"]} {qid}: 模拟下一题 {sim_next!r}；后端模块内下一项 {real_next[:40]!r}')
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
        print('skeleton questions through the life-overview entry:', json.dumps(sk['stats'], ensure_ascii=False))
        print(f'skeleton differences from the simulator ({len(sk["differences"])}):\n  ' + '\n  '.join(sk['differences']))
        print(f'skeleton inputs a full skeleton would really send (need real calls) ({len(sk["real"])}):\n  ' + '\n  '.join(sk['real']))
        self.assertEqual(failures, [])
        self.assertEqual(fake.misses, [])
        self.assertEqual(stats['judged'], stats['judge_equal'])
        self.assertEqual(stats['speaker_calls'], stats['speaker_input_equal'])
        self.assertEqual((stats['followups'], stats['transitions'], stats['draft'], stats['rest']), (1, 3, 17, 0))
        st = sk['stats']
        self.assertEqual((st['questions'], st['judged'], st['judge_equal'], st['action_equal']), (12, 14, 14, 14))
        self.assertEqual((st['speaker_calls'], st['speaker_input_equal']), (10, 10))
        self.assertEqual((st['followups'], st['followup_equal'], st['closes'], st['close_equal'], st['last'], st['rest']),
                         (2, 2, 8, 8, 2, 2))
        self.assertEqual(stats['judged'] + st['judged'], 35)

    def skeleton_episode(self, session, plan, ei, episode, fake, life, sk):
        """One simulated SK question through the skeleton entry; returns the stored overview for the next one."""
        import test_contract_interview_workflow as base
        from app.models.family_member import FamilyMemberModel
        from app.schemas.life_overview import LifeAction
        from app.services import life_overview
        from app.services.contract_interview_state import questions, v3j_runtime
        rt = v3j_runtime()
        stats, failures, differences, real = sk['stats'], sk['failures'], sk['differences'], sk['real']
        qid = episode['qid']
        stats['questions'] += 1
        if not hasattr(self, 'fixture'):
            self.fixture = base.WorkflowTests('test_catalog_routes_contain_all_six_modules_and_72_questions')
            self.fixture.setUp()
            self.addCleanup(self.fixture.tearDown)
        person = self.fixture.person
        catalog = [q['id'] for q in questions('skeleton')]
        if life is None:  # the session's first question: outside the plan counts as answered earlier
            life = life_overview.new_data()
            for key in catalog:
                if key not in plan:
                    life['questions'][key]['status'] = 'skipped'
            life['turns'].append({'id': str(uuid4()), 'role': 'assistant', 'content': rt.questions[qid]['main_question'],
                                  'created_at': 'replay'})
            if catalog.index(plan[0]):
                real.append(f'{session["name"]} {qid}: 完整骨架里此前还有 {catalog[catalog.index(plan[0]) - 1]}，'
                            '若那道题以新流程收尾，“上次换话题时你说的”会是那句收尾，模拟器为空')
        elif life['questions'][plan[ei - 1]]['status'] == 'pending':  # paused before: the plan moved on
            differences.append(f'{session["name"]} {plan[ei - 1]}: 后端暂停后这道题仍未结束、点“继续”会接着问它；'
                               f'模拟器歇完直接进 {qid}（回放把它记为已结束以接着回放）')
            life['questions'][plan[ei - 1]]['status'] = 'skipped'
            life['paused'] = False
            life['status'] = 'collecting'
        sims = episode['messages']
        for j, m in enumerate(sims):
            if m['role'] != 'elder' or m.get('scripted'):
                continue
            where = f'{session["name"]} {qid} #{j}'
            reply_sim = next(x for x in sims[j + 1:] if x['role'] == 'system')
            with base.database.SessionLocal.begin() as db:
                db.get(FamilyMemberModel, str(person)).life_interview = deepcopy(life)
            before = len(fake.requests)
            with patch.dict(os.environ, {'INTERVIEW_PIPELINE': 'v3j_v4d'}):
                life_overview.perform(person, LifeAction(action='answer', text=m['text'], expected_version=life['version'],
                                                         client_request_id=uuid4()), fake)
            with base.database.SessionLocal() as db:
                life = deepcopy(db.get(FamilyMemberModel, str(person)).life_interview)
            local = life['questions'][qid]
            if local.get('pipeline') != 'v3j_v4d':
                failures.append(where + ' skeleton question not in the v3j_v4d flow')
            audit = local['audit'][-1]
            text = life['turns'][-1]['content']
            spoken = [r for r in fake.requests[before:] if r['system'] == rt.speaker_prompt]
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
            kind, reason = reply_sim['kind'], reply_sim.get('reason')
            if kind == 'followup':
                stats['followups'] += 1
                stats['followup_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or local['status'] != 'pending' or not sim_input or not spoken:
                    failures.append(where + f' follow-up {text!r} vs {reply_sim["text"]!r}')
            elif kind == 'close' and reason != 'rest' and reply_sim.get('entry_part'):
                stats['closes'] += 1
                stats['close_equal'] += text == reply_sim['text']
                if text != reply_sim['text'] or not spoken or life.get('speaker_last_close') != text:
                    failures.append(where + f' close {text!r} vs {reply_sim["text"]!r}')
                if local['status'] == 'pending':
                    failures.append(where + ' closed question still pending')
            elif kind == 'close' and reason != 'rest':  # the plan's last question: no next skeleton question here
                stats['last'] += 1
                differences.append(f'{where} [{reason}] 计划内最后一题，后端保持核对句、不调说话层。模拟：{reply_sim["text"]}\n'
                                   f'    后端：{text}')
                if spoken or text != life_overview_review() or life['status'] != 'review':
                    failures.append(where + ' review step changed')
                following = next((k for k in catalog[catalog.index(qid) + 1:]), None)
                if following:
                    real.append(f'{where}: 完整骨架里下一题是 {following}「{rt.questions[following]["main_question"]}」，'
                                '说话层输入的“下一题”会是它，模拟器为“无”')
            else:  # tired: the skeleton keeps its existing pause
                stats['rest'] += 1
                later = [x['text'] for x in sims[j + 1:] if x['role'] == 'system']
                differences.append(f'{where} [rest] 模拟：{" / ".join(later)}\n    后端：{text}')
                if spoken or text != '好，先休息。您的回答和采访位置都已保留。' or not life['paused'] or local['status'] != 'pending':
                    failures.append(where + ' pause changed')
            if kind in ('close', 'pause'):
                break
        return life


if __name__ == '__main__':
    unittest.main()
