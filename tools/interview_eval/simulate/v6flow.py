"""Simulated full interviews in the production V6 flow (pipeline v3j_v5f, listening bundle, product commit 8799b52).

What is production code here and what is a port:
- judgment: the backend's own ``V3jPipeline`` over the pinned V6 bundle
  (cloud-deployment/backend/app/ai/interview_runtime_v3j_v5f_listening, manifest pin checked by ``V3jRuntime``),
  including the V6 ``literal_cause_span`` assembly. ``app.ai.llm_client`` (httpx / openai / pydantic) is replaced by
  a stub that only defines its three exception classes; provider requests are answered through the relay.
- speaking layer, story deepening, ending rules, supplement-intent reading: the backend's ``interview_speaker`` /
  ``interview_story`` functions, called with ``rt`` = that pinned runtime (listen_first, literal_cause_span,
  listening prompts and the V6 speaker-config come from the bundle files, not from docs/).
- step orchestration (which function runs when, what is shown, the draft / supplement / review steps, pause and
  resume, skips): a line-by-line port of contract_guided_interview.turn, contract_v3j_interview.question_turn /
  deepen_answer_turn / skip_turn / _draft_ack / _transition (module questions) and contract_life_overview.perform +
  contract_v3j_life_overview.turn (skeleton). Those modules need the App's pydantic schemas and database and are
  not imported.

Simulation choices (not production behaviour): the elder is the Haiku persona of interview.elder_call (same
behaviour draws and seeds; the first answer of a question sees only the entry question); the simulated user taps
"continue" right after a pause, picks the modules in menu order, and confirms the draft once the review step is
reached or after SUPPLEMENT_CAP answers in the supplement step; at most MAX_ELDER answers per question.

Questions are independent in production (question_context_mode=independent); the only state that crosses
questions is the speaking layer's "上次换话题时你说的" (speaker_last_close: one chain over the skeleton, one over the
guided interview). Each question runs as its own generator; a question asks the scheduler for the chain value
when it first needs it (route 'chain') and hands on its own last close when it ends, so all questions can run in
parallel and only the close calls are serial.
"""
from __future__ import annotations

import json
import re
import sys
import types
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import interview  # noqa: E402  (persona call, controls, constants of the simulator)
from persona import Personas  # noqa: E402

BACKEND = common.ROOT / 'cloud-deployment/backend'
BUNDLE = BACKEND / 'app/ai/interview_runtime_v3j_v5f_listening'
V6_PIN = '1062b6c2158fa8132c0a6ea9541a4dcdbec80f6dd32d21cfda0d816cd2a76487'
PIPELINE = 'v3j_v5f'

# texts of the production steps (contract_v3j_interview / contract_guided_interview / contract_life_overview)
DRAFT_TEXT = '这段可以先整理成草稿了。您还有什么想补充的吗？'
PAUSE_TEXT = '好，先休息。您的讲述和采访位置都已保留。'
REVIEW_TEXT = '好，先核对这段草稿，您确认后再保存。'
SUPPLEMENT_TEXT = '您还有别的想补充的吗？'
LIFE_PAUSE_TEXT = '好，先休息。您的回答和采访位置都已保留。'
LIFE_RESUME = '好，我们接着聊。'
NOTED_TEXT = '我记下了。'
LIFE_REVIEW_TEXT = '这些是您提供的人生线索。请先核对，有需要更正的地方可以告诉我；确认后再选想聊的部分。'
MODULE_NAMES = {'childhood': '家乡与童年', 'growth': '求学与成长', 'work': '工作与劳动', 'family': '家庭生活',
                'later_life': '后来的生活', 'reflection': '人生回望'}
PREFIXES = {'childhood': 'CH', 'growth': 'GR', 'work': 'WK', 'family': 'FM', 'later_life': 'LT', 'reflection': 'RV'}
GUIDED_PAUSE = re.compile(r'(?:先休息|先暂停|暂停|今天先不聊|暂时不想讲)[。！!\s]*')
LIFE_PAUSE = re.compile(r'(?:先休息|先暂停|暂停|今天先不聊|暂时不想聊)[。！!\s]*')
RESUME = re.compile(r'(?:继续|继续聊|接着讲)[。！!\s]*')
SUPPLEMENT_DONE = re.compile(r'(?:没有(?:了|补充了)?|没有别的补充了|先保存|确认保存|保存吧|就这些)[。！!\s]*')
MAX_ELDER = 12       # simulation cap on elder answers per question (production has none)
SUPPLEMENT_CAP = 3   # simulation: after this many answers in the supplement step the user confirms the draft


def module_menu():
    return '接下来您想聊哪个部分？可以选：' + '、'.join(MODULE_NAMES.values()) + '，也可以先休息。'


# --------------------------------------------------------------------------- backend modules
def load_backend():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    if 'app.ai.llm_client' not in sys.modules:
        stub = types.ModuleType('app.ai.llm_client')
        for name in ('LLMConfigurationError', 'LLMResponseFormatError', 'LLMServiceError'):
            setattr(stub, name, type(name, (Exception,), {}))
        sys.modules['app.ai.llm_client'] = stub
    from app.ai import contract_interview_v3j as cij
    from app.ai import interview_speaker as speaker
    from app.ai import interview_story as story
    return cij, speaker, story


class NeedCall(Exception):
    pass


class RelayClient:
    """SDK stand-in for V3jPipeline: answers requests whose relay response is known; the first unknown request is
    remembered (``pending``) and raised, so the caller can fetch it and run the step again."""

    def __init__(self, known):
        self.known = known
        self.client = self
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.pending = None

    def with_options(self, **options):
        return self

    def create(self, **request):
        assert request['extra_body'] == {'thinking': {'type': 'disabled'}}
        system, user = [m['content'] for m in request['messages']]
        params = {'model': request['model'], 'thinking': 'disabled', 'max_tokens': request['max_tokens'],
                  'temperature': request['temperature'], 'json_mode': True}
        call = {'system': system, 'user': user, 'params': params}
        key = common.Relay.key(call)
        row = self.known.get(key)
        if row is None:
            self.pending = (call, key)
            raise NeedCall(key)
        if not row.get('ok'):
            raise RuntimeError('provider call failed')
        return SimpleNamespace(id=row.get('response_id') or row.get('id'), model=row.get('response_model'), usage=None,
                               choices=[SimpleNamespace(message=SimpleNamespace(content=row.get('content') or ''),
                                                        finish_reason=row.get('finish_reason'))])


class Setup:
    def __init__(self, sim_config=None, bundle=None, pin=None):
        """``bundle``/``pin``: another pinned v3j_v5f bundle, for offline replays of older runs (v6_replay.py)."""
        self.cij, self.speaker, self.story = load_backend()
        bundle, pin = Path(bundle or BUNDLE), pin or V6_PIN
        if sha256((bundle / 'manifest.json').read_bytes()).hexdigest() != pin:
            raise SystemExit('the bundle manifest does not match its pin')
        self.rt = self.cij.V3jRuntime(bundle, pin, PIPELINE)
        cfg = self.rt.speaker_config
        if bundle == BUNDLE:
            assert cfg.get('listen_first') and cfg.get('literal_cause_span'), 'not the V6 listening bundle'
        self.personas = Personas()
        self.Q = self.personas.Q  # persona material (same frozen bank: ids and entry questions checked below)
        for qid, q in self.rt.questions.items():
            if self.Q[qid]['main_question'] != q['main_question']:
                raise SystemExit('frozen bank mismatch at ' + qid)
        self.sim_prompt = (interview.V4 / 'simulator-prompt.txt').read_text(encoding='utf-8')
        self.sim_cfg = json.loads(Path(sim_config or interview.V4 / 'sim-config.json').read_text(encoding='utf-8'))
        self.order = list(self.rt.questions)
        self.skeleton = [q for q in self.order if q.startswith('SK')]
        self.modules = {m: [q for q in self.order if q.startswith(p)] for m, p in PREFIXES.items()}

    def plan(self):
        """Production order: the 11 skeleton questions, then the six modules in menu order."""
        return self.skeleton + [q for m in MODULE_NAMES for q in self.modules[m]]

    def module_of(self, qid):
        return next((m for m, qs in self.modules.items() if qid in qs), 'skeleton')

    def upcoming(self, qid):
        """What follows a guided question: (text, menu) exactly as contract_v3j_interview.upcoming shows it."""
        qs = self.modules[self.module_of(qid)]
        i = qs.index(qid)
        if i + 1 < len(qs):
            return self.rt.questions[qs[i + 1]]['main_question'], False
        return module_menu(), True

    def life_next(self, qid):
        i = self.skeleton.index(qid)
        return self.rt.questions[self.skeleton[i + 1]]['main_question'] if i + 1 < len(self.skeleton) else None


# --------------------------------------------------------------------------- provider calls through the scheduler
def provider(S, fn, known, tag, log):
    """Run fn(client) -- a V3jPipeline step -- until every provider request it makes is answered; each missing request
    is yielded to the scheduler as a DeepSeek call. Returns fn's value."""
    n = 0
    while True:
        client = RelayClient(known)
        try:
            value = fn(client)
        except S.cij.LLMServiceError:
            if client.pending is None:
                raise
            value = None
        if client.pending is None:
            return value
        call, key = client.pending
        n += 1
        [row] = yield [{'id': f'{tag}-{n}', 'route': 'ds', **call}]
        known[key] = row
        log.append({**interview.call_info(row), 'kind': tag.split('-')[-1]})


def judge(S, qid, sources, context, known, tag, log):
    pipe = lambda c: S.cij.V3jPipeline(S.rt, c).run(qid, deepcopy(sources), deepcopy(context))  # noqa: E731
    return (yield from provider(S, pipe, known, tag + '-judge', log))


def speak(S, user, known, tag, log):
    row, _ = yield from provider(S, lambda c: S.cij.V3jPipeline(S.rt, c).speak(user), known, tag + '-speak', log)
    return row


def deepen_call(S, user, known, tag, log):
    row, _ = yield from provider(S, lambda c: S.cij.V3jPipeline(S.rt, c).deepen(user), known, tag + '-deepen', log)
    return row


# --------------------------------------------------------------------------- shared helpers (ports)
def fresh(qid):
    return {'question_id': qid, 'sources': [], 'fields': {}, 'ask_counts': {}, 'last_result': None, 'pending': None,
            'audit': [], 'pipeline': PIPELINE, 'followups': 0, 'asked_target': None}


def context_for(local):
    return {'previous_fields': deepcopy(local.get('fields', {})), 'ask_counts': deepcopy(local.get('ask_counts', {})),
            'focus': {'field_id': local['asked_target']} if local.get('asked_target') else None}


def append_source(local, identity, text, asked):
    source = {'id': identity, 'text': text, 'question_id': local['question_id'], 'speaker': 'narrator', 'question': asked}
    if local.get('asked_target'):
        source['target_field_id'] = local['asked_target']
    local['sources'].append(source)


def question_answers(local, order):
    extra = (local.get('deepen') or {}).get('sources') or []
    if not extra:
        return local['sources']
    return sorted(local['sources'] + extra, key=lambda s: order.get(s['id'], len(order)))


def dialogue_from(entry, sources, before, latest_id, latest_text):
    texts = {s['id']: s['text'] for s in sources}
    asked = {s['id']: s.get('question') or '' for s in sources}
    if latest_id not in texts:
        texts[latest_id] = latest_text
    out = [('system', entry)]
    for k, identity in enumerate(texts):
        if k:
            out.append(('system', before.get(identity) or asked.get(identity, '')))
        out.append(('elder', texts[identity]))
    return out


def shown_before(messages):
    out, last = {}, ''
    for m in messages:
        out[m['id']] = last
        if m['role'] == 'system':
            last = m['text']
    return out


def finish(local, outcome, spoken, asked=None):
    result = outcome['result']
    local['audit'].append({'result': deepcopy(result), 'speaker': spoken})
    local['last_result'] = deepcopy(result)
    local['fields'] = deepcopy(result['fields'])
    if asked:
        local['ask_counts'][asked] = local['ask_counts'].get(asked, 0) + 1
        local['followups'] = local.get('followups', 0) + 1
    local['asked_target'] = asked


def clean_dz(dz):
    for key in ('asked_text', 'before', 'last', 'partial'):
        dz.pop(key, None)


def keep_log(dz, log):
    if log is not None:
        dz['log'].append({k: v for k, v in log.items() if k not in ('call', 'input')})


class Q:
    """One question's simulation state and record."""

    def __init__(self, S, nid, qid, chain, override=None):
        self.S, self.nid, self.qid = S, nid, qid
        # replay only: {'next': (text, menu) or text, 'seen': earlier closes for the v5f "repeat" guard, 'keep': True}
        self.override = override or {}
        self.seen = tuple(self.override.get('seen') or ())
        self.entry = S.rt.questions[qid]['main_question']
        self.local = fresh(qid)
        self.messages = []        # every message of the question, in order
        self.dialogue_sim = []    # what the persona has seen in this question
        self.prompt = self.entry  # the message the persona answers next
        self.k = 0                # persona answers so far (behaviour draws)
        self.known = {}           # relay responses of this question, by request key
        self.calls = []
        self.chain_name = chain
        self.chain = None
        self.chain_in = None
        self.chain_known = False
        self.status = None        # saved / skipped / error
        self.close_reason = None
        self.steps = []

    def sys(self, text, kind, **extra):
        self.messages.append({'id': f'{self.qid}-m{len(self.messages)}', 'role': 'system', 'text': text, 'kind': kind, **extra})
        self.prompt = text

    def get_chain(self):
        if not self.chain_known:
            [row] = yield [{'id': f'{self.qid}-chain', 'route': 'chain', 'chain': self.chain_name}]
            self.chain, self.chain_known = row['value'], True
            self.chain_in = row['value']
        return self.chain

    def elder(self):
        call, beh, asr = interview.elder_call(self.S, self.nid, self.qid, self.k, self.dialogue_sim, self.prompt)
        [row] = yield [call]
        text = interview.elder_text(row)
        msg = {'id': f'{self.qid}-m{len(self.messages)}', 'role': 'elder', 'text': text, 'behavior': beh, 'asr': asr,
               'k': self.k, 'calls': [{**interview.call_info(row), 'kind': 'sim'}]}
        self.messages.append(msg)
        self.dialogue_sim += [('system', self.prompt), ('elder', text)]
        self.k += 1
        return msg

    def scripted(self, text):
        msg = {'id': f'{self.qid}-m{len(self.messages)}', 'role': 'elder', 'text': text, 'scripted': True}
        self.messages.append(msg)
        self.dialogue_sim += [('system', self.prompt), ('elder', text)]
        return msg

    def record(self):
        local = self.local
        dz = local.get('deepen') or {}
        order = {m['id']: i for i, m in enumerate(self.messages)}
        return {'qid': self.qid, 'entry': self.entry, 'module': self.S.module_of(self.qid), 'status': self.status,
                'close_reason': self.close_reason, 'messages': self.messages,
                'sources': [dict(s) for s in question_answers(local, order)],
                'judged_sources': len(local['sources']), 'deepen_sources': len(dz.get('sources') or []),
                'deepen': {k: v for k, v in dz.items() if k not in ('sources', 'asked_text', 'before', 'last', 'partial')} if dz else None,
                'final': interview_summary(self.S, local.get('last_result')), 'followups': local.get('followups', 0),
                'steps': self.steps, 'calls': self.calls, 'chain_in': self.chain_in,
                'material_ids': [e['id'] for e in self.S.personas.material(self.nid, self.qid)]}


def interview_summary(S, result):
    if not result:
        return None
    fields = S.speaker.recorded_fields(S.rt, result)
    return {'decision': result.get('decision'), 'target': result.get('target'),
            'effective': {k: v for k, v in (result.get('effective') or {}).items() if S.rt.F[k]['requirement'] != 'optional'},
            'fields': fields}


# --------------------------------------------------------------------------- guided (module) question
def guided_question(S, nid, qid, override=None):
    """Generator of one module question in the V6 guided-interview flow. Returns (record, chain_out)."""
    q = Q(S, nid, qid, 'guided', override)
    upcoming = (lambda: q.override['next']) if 'next' in q.override else (lambda: S.upcoming(qid))  # noqa: E731
    rt, sp, st_ = S.rt, S.speaker, S.story
    cfg = rt.speaker_config
    local = q.local
    state = {'phase': 'opening', 'pending_question': None, 'resume_phase': None}
    q.sys(q.entry, 'entry')

    def dialogue_for(latest):
        order = {m['id']: i for i, m in enumerate(q.messages)}
        return dialogue_from(q.entry, question_answers(local, order), shown_before(q.messages), latest['id'], latest['text'])

    def asked_part(latest):
        shown = shown_before(q.messages).get(latest['id'], '')
        candidates = ([state['pending_question']] if state['pending_question'] else []) + [q.entry, DRAFT_TEXT, SUPPLEMENT_TEXT]
        for c in candidates:
            if sp._norm(c) and sp._norm(shown).endswith(sp._norm(c)):
                return c
        return shown

    def draft_ack(dialogue, fields, reason, closing=DRAFT_TEXT, step='draft'):
        prev = yield from q.get_chain()
        next_text, menu = upcoming()
        elder_words = ''.join(t for role, t in dialogue if role == 'elder')
        user = sp.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text, prev_close=prev)
        row = yield from speak(S, user, q.known, f'{qid}-c{len(q.messages)}', q.calls)
        reply, _ = sp.parse_speaker(row)
        ack = st_.draft_ack(rt, reply, None if menu else next_text, elder_words, q.seen)  # V6 listen_first never reads seen
        notes = []
        if ack and step == 'supplement' and sp._norm(ack) == sp._norm(prev):
            ack, notes = '', ['repeat_ack']
        ack, why = sp.listening_ack(rt, ack, elder_words)
        notes += why
        if ack == sp.LISTENING_FALLBACK and 'ack_fallback' not in notes:
            notes.append('ack_fallback')
        text = sp.join(ack, closing) if ack else closing
        if ack:
            q.chain = ack
        return ack, text, {'task': 'close', 'close_reason': reason, 'step': step, 'ack': ack, 'notes': notes,
                           'raw': row.get('content'), 'input': user, 'next_entry': next_text}

    def transition(dialogue, fields, reason):
        prev = yield from q.get_chain()
        next_text, menu = upcoming()
        elder_words = ''.join(t for role, t in dialogue if role == 'elder')
        user = sp.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=next_text, prev_close=prev)
        row = yield from speak(S, user, q.known, f'{qid}-t{len(q.messages)}', q.calls)
        reply, _ = sp.parse_speaker(row)
        if menu:
            ack = st_.draft_ack(rt, reply, None, elder_words, q.seen)
            text, ok, notes = (sp.join(ack, next_text), True, []) if ack else (None, False, ['empty'])
        else:
            text, ack, notes, ok = st_.close_reply(rt, reply, next_text, elder_words, q.seen)
        if not ok:
            text = interview.CONTROLS.SKIP_ACK + '\n' + next_text
        q.chain = text
        return text, {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '',
                      'notes': notes, 'raw': row.get('content'), 'input': user, 'next_entry': next_text}

    def try_deepen(reason, text, dialogue, asked_text, before):
        if qid not in rt.story:
            return None, None, None, None
        dz = local.setdefault('deepen', st_.new_deepen(rt, qid))
        elder_words = ''.join(t for role, t in dialogue if role == 'elder')
        dz['asked_text'], dz['before'], dz['last'] = asked_text, before, text
        k = len(local['sources']) + len(dz.get('sources') or [])
        if dz.get('stopped'):
            ok, why, info = False, 'stopped_' + dz['stopped'], {}
        else:
            ok, why, info = st_.deepen_gate(cfg, reason, text, elder_words, dz, k)
        log = {'k': k, 'decision': 'asked' if ok else 'skip', 'reason': why, **info}
        if not ok:
            return None, None, None, log
        prior = [s.get('question') for s in question_answers(local, {})]
        user = st_.deepen_user(rt, qid, dialogue, dz)
        row = yield from deepen_call(S, user, q.known, f'{qid}-d{len(q.messages)}', q.calls)
        dim, ack, question, errs, repairs = st_.compose_deepen(rt, row, dz, prior, elder_words)
        log.update({'dimension': dim, 'ack': ack, 'question': question, 'errors': errs, 'repairs': repairs,
                    'raw': row.get('content'), 'input': user})
        if errs:
            log['decision'] = 'skip'
            log['reason'] = 'invalid' if errs[0] not in ('call_failed', 'model_skip') else errs[0]
            return None, None, None, log
        return dim, ack, question, log

    def ask_deepen(dim, ack, question):
        dz = local['deepen']
        dz['asked'] += 1
        dz['dims'].append(dim)
        dz['awaiting'] = True
        state['phase'] = 'exploring'
        state['pending_question'] = question
        return sp.join(ack, question)

    def end(status, reason):
        q.status, q.close_reason = status, reason

    while True:
        if q.k >= MAX_ELDER:
            q.steps.append({'step': 'sim_cap', 'answers': q.k})
            end('saved' if local['sources'] else 'error', 'max_answers')
            break
        latest = yield from q.elder()
        text = latest['text'].strip()
        step = {'answer': latest['id'], 'phase': state['phase']}
        q.steps.append(step)
        # ---- contract_guided_interview.turn
        if GUIDED_PAUSE.fullmatch(text):
            state['resume_phase'], state['phase'] = state['phase'], 'paused'
            step['reply'] = 'pause_control'
            q.sys(PAUSE_TEXT, 'pause')
            yield from resume(q, state)
            continue
        if interview.CONTROLS.skips_question(text):
            # skip_topic -> contract_v3j_interview.skip_turn
            fields = sp.recorded_fields(rt, local.get('last_result'))
            dz = local.get('deepen') or {}
            if dz.get('awaiting') and state['phase'] not in ('supplement', 'review'):
                ack, out, spoken = yield from draft_ack(dialogue_for(latest), fields, 'declined_partial')
                dz['awaiting'] = False
                dz['log'].append({'k': len(local['sources']) + len(dz.get('sources') or []) + 1, 'decision': 'stop',
                                  'reason': 'answer_skip_control'})
                step.update(reply='draft', spoken=spoken)
                state['pending_question'], state['phase'] = None, 'supplement'
                q.sys(out, 'draft', offer_generation=True)
                continue
            out, spoken = yield from transition(dialogue_for(latest), fields, 'declined')
            step.update(reply='skip', spoken=spoken)
            q.sys(out, 'transition')
            end('skipped', 'skip_control')
            break
        if state['phase'] in ('supplement', 'review') and SUPPLEMENT_DONE.fullmatch(text):
            step['reply'] = 'review'
            q.sys(REVIEW_TEXT, 'review', offer_generation=True)
            end('saved', 'confirmed')
            break
        # ---- contract_v3j_interview.question_turn
        supplementing = state['phase'] in ('supplement', 'review')
        ending = sp.supplement_end(latest['text'], listen_first=True) if supplementing else None
        if ending == 'only':
            step.update(reply='review', supplement_end=ending)
            q.sys(REVIEW_TEXT, 'review', offer_generation=True)
            end('saved', 'confirmed')
            break
        if (local.get('deepen') or {}).get('awaiting') and not supplementing:
            # ---- deepen_answer_turn
            dz = local['deepen']
            asked = asked_part(latest)
            dz.setdefault('sources', []).append({'id': latest['id'], 'text': latest['text'], 'question_id': qid,
                                                 'speaker': 'narrator', 'question': asked, 'dimension': dz['dims'][-1],
                                                 'deepen_answer': True})
            dialogue = dialogue_for(latest)
            elder_list = [t for role, t in dialogue if role == 'elder']
            before = ''.join(elder_list[:-1])
            scope = (asked, before, cfg.get('scope_min_chars', 15)) if cfg.get('signal_scope') else None
            action, reason = st_.deepen_close(latest['text'], None, cfg['deepen'].get('extra_guards'), scope)
            step.update(deepen_answer=True, rule={'action': action, 'reason': reason, 'signal': sp.elder_signal(latest['text'])})
            if action == 'rest':
                dz['stopped'], dz['awaiting'] = 'rest', False
                clean_dz(dz)
                state['pending_question'] = None
                state['resume_phase'], state['phase'] = state['phase'], 'paused'
                step['reply'] = 'pause'
                q.sys(PAUSE_TEXT, 'pause')
                yield from resume(q, state)
                continue
            dim, ack, question, log = yield from try_deepen(reason, latest['text'], dialogue, asked, before)
            keep_log(dz, log)
            if question:
                clean_dz(dz)
                step.update(reply='deepen', deepen=log)
                q.sys(ask_deepen(dim, ack, question), 'deepen', question_part=question, dimension=dim)
                continue
            clean_dz(dz)
            fields = sp.recorded_fields(rt, local.get('last_result'))
            ack, out, spoken = yield from draft_ack(dialogue, fields, reason)
            dz['awaiting'] = False
            step.update(reply='draft', spoken=spoken, deepen=log)
            state['pending_question'], state['phase'] = None, 'supplement'
            q.sys(out, 'draft', offer_generation=True)
            continue
        asked_now = asked_part(latest)
        append_source(local, latest['id'], latest['text'], asked_now)
        try:
            outcome = yield from judge(S, qid, local['sources'], context_for(local), q.known, f'{qid}-a{len(q.messages)}', q.calls)
        except Exception as exc:  # provider failure after the relay's own retries: the App would show an error
            step.update(reply='error', error=repr(exc)[:300])
            end('error' if len(local['sources']) <= 1 else 'saved', 'provider_error')
            break
        result = outcome['result']
        step['judge'] = interview_summary(S, result)
        if q.override.get('keep'):
            step['result'] = result
        if result['decision'] == 'invalid':
            step.update(reply='error', errors=result.get('errors'))
            end('error' if len(local['sources']) <= 1 else 'saved', 'invalid')
            break
        dialogue = dialogue_for(latest)
        before = ''.join([t for role, t in dialogue if role == 'elder'][:-1])
        st = {'followups': local.get('followups', 0), 'ask_counts': local.get('ask_counts', {}),
              'prev_eff': dict((local.get('last_result') or {}).get('effective') or {})}
        if cfg.get('signal_scope'):
            st.update(asked=asked_now, before=before, last_target=local.get('asked_target'))
        action, arg = sp.decide(cfg, result, st, latest['text'])
        refused = arg in ('declined', 'deferred')
        fields = sp.recorded_fields(rt, result)
        rule = {'action': action, 'reason': arg, 'signal': st['signal']}
        if st.get('scope'):
            rule['scope'] = st['scope'][0]
        if supplementing:
            rule['supplement_end'] = ending
        step['rule'] = rule
        if supplementing and action != 'rest' and not (refused and not sp.has_content(result)):
            if ending == 'with_content' or refused or arg == 'declined_partial' or st['signal'] == 'declined':
                finish(local, outcome, {'task': 'review', **rule})
                step['reply'] = 'review'
                q.sys(REVIEW_TEXT, 'review', offer_generation=True)
                end('saved', 'confirmed')
                break
            reason = arg if action == 'close' else 'limited'
            ack, out, spoken = yield from draft_ack(dialogue, fields, reason, closing=SUPPLEMENT_TEXT, step='supplement')
            finish(local, outcome, {**spoken, **rule})
            step.update(reply='supplement', spoken=spoken)
            state['pending_question'], state['phase'] = None, 'supplement'
            q.sys(out, 'supplement', offer_generation=True)
            if sum(1 for s in q.steps if s.get('phase') in ('supplement', 'review')) >= SUPPLEMENT_CAP:
                q.steps.append({'step': 'sim_confirm', 'why': 'supplement_cap'})
                end('saved', 'confirmed_cap')
                break
            continue
        if action == 'close' and not refused:
            dim, ack, question, log = yield from try_deepen(arg, latest['text'], dialogue, asked_now, before)
            if log is not None:
                dz = local['deepen']
                keep_log(dz, log)
                clean_dz(dz)
                if question:
                    finish(local, outcome, {'task': 'deepen', **{k: v for k, v in log.items() if k != 'input'}, **rule})
                    step.update(reply='deepen', deepen=log)
                    q.sys(ask_deepen(dim, ack, question), 'deepen', question_part=question, dimension=dim)
                    continue
                step['deepen'] = log
        if action == 'ask':
            user = sp.speaker_user(rt, qid, dialogue, fields, 'ask', arg, result.get('question'))
            row = yield from speak(S, user, q.known, f'{qid}-s{len(q.messages)}', q.calls)
            out, question, spoken = sp.compose_ask(rt, row, result, arg, [s['question'] for s in local['sources']],
                                                   ''.join(t for role, t in dialogue if role == 'elder'))
            finish(local, outcome, {'task': 'ask', **spoken, 'text': out, **rule}, asked=arg)
            step.update(reply='followup', spoken={**spoken, 'raw': row.get('content'), 'input': user})
            state['phase'], state['pending_question'] = 'exploring', question
            q.sys(out, 'followup', question_part=question, target=arg)
            continue
        if action == 'rest':
            finish(local, outcome, rule)
            state['pending_question'] = None
            state['resume_phase'], state['phase'] = state['phase'], 'paused'
            step['reply'] = 'pause'
            q.sys(PAUSE_TEXT, 'pause')
            yield from resume(q, state)
            continue
        if refused:
            out, spoken = yield from transition(dialogue, fields, arg)
            finish(local, outcome, {**spoken, **rule})
            step.update(reply='skip', spoken=spoken)
            q.sys(out, 'transition')
            end('skipped', arg)
            break
        ack, out, spoken = yield from draft_ack(dialogue, fields, arg)
        finish(local, outcome, {**spoken, **rule})
        step.update(reply='draft', spoken=spoken)
        state['pending_question'], state['phase'] = None, 'supplement'
        q.sys(out, 'draft', offer_generation=True)
    yield from q.get_chain()  # the chain passes through a question even if it never needed it
    return q.record(), q.chain


def resume(q, state):
    """The simulated user taps "继续" right away (contract_guided_interview.turn, paused + 继续)."""
    q.scripted('继续')
    state['phase'] = state['resume_phase'] or 'exploring'
    state['resume_phase'] = None
    q.sys(state['pending_question'] or q.entry, 'resume')
    return
    yield  # generator


# --------------------------------------------------------------------------- skeleton (life overview) question
def life_question(S, nid, qid, override=None):
    """Generator of one skeleton question (contract_life_overview.perform + contract_v3j_life_overview.turn)."""
    q = Q(S, nid, qid, 'life', override)
    rt, sp, st_ = S.rt, S.speaker, S.story
    cfg = rt.speaker_config
    local = q.local
    local.update({'status': 'pending', 'asked_question': None})
    paused = False
    q.sys(q.entry, 'entry')

    def question_text():
        return local['asked_question'] if local['asked_question'] is not None else q.entry

    while True:
        if q.k >= MAX_ELDER:
            q.steps.append({'step': 'sim_cap', 'answers': q.k})
            q.status, q.close_reason = ('saved' if local['sources'] else 'error'), 'max_answers'
            break
        latest = yield from q.elder()
        text = latest['text'].strip()
        step = {'answer': latest['id']}
        q.steps.append(step)
        asked_q = question_text()
        if LIFE_PAUSE.fullmatch(text):
            paused = True
            step['reply'] = 'pause_control'
            q.sys(LIFE_PAUSE_TEXT, 'pause')
            q.scripted('继续')
            paused = False
            q.sys(LIFE_RESUME + question_text(), 'resume')
            continue
        order = {m['id']: i for i, m in enumerate(q.messages)}
        skip = interview.CONTROLS.skips_question(text)
        dz = local.get('deepen') or {}
        deepen_answer = bool(dz.get('awaiting'))
        outcome = None
        if deepen_answer:
            dz.setdefault('sources', [])
            if not skip:
                dz['sources'].append({'id': latest['id'], 'text': latest['text'], 'question_id': qid, 'speaker': 'narrator',
                                      'question': asked_q, 'dimension': dz['dims'][-1], 'deepen_answer': True})
            result = local.get('last_result') or {}
            if skip:
                action, reason = 'close', 'declined_partial'
            else:
                words = [s['text'] for s in question_answers(local, order)]
                before = ''.join(words[:-1])
                scope = (asked_q, before, cfg.get('scope_min_chars', 15)) if cfg.get('signal_scope') else None
                action, reason = st_.deepen_close(latest['text'], None, cfg['deepen'].get('extra_guards'), scope)
            rule = {'action': action, 'reason': reason, 'signal': sp.elder_signal(latest['text']), 'deepen_answer': True}
            step['deepen_answer'] = True
        elif skip:
            result = local.get('last_result') or {}
            action, reason, rule = 'close', 'declined', None
        else:
            append_source(local, latest['id'], latest['text'], asked_q)
            try:
                outcome = yield from judge(S, qid, local['sources'], context_for(local), q.known, f'{qid}-a{len(q.messages)}', q.calls)
            except Exception as exc:
                step.update(reply='error', error=repr(exc)[:300])
                q.status, q.close_reason = ('error' if len(local['sources']) <= 1 else 'saved'), 'provider_error'
                break
            result = outcome['result']
            step['judge'] = interview_summary(S, result)
            if q.override.get('keep'):
                step['result'] = result
            if result['decision'] == 'invalid':
                step.update(reply='error', errors=result.get('errors'))
                q.status, q.close_reason = ('error' if len(local['sources']) <= 1 else 'saved'), 'invalid'
                break
            st = {'followups': local.get('followups', 0), 'ask_counts': local.get('ask_counts', {}),
                  'prev_eff': dict((local.get('last_result') or {}).get('effective') or {})}
            if cfg.get('signal_scope'):
                order = {m['id']: i for i, m in enumerate(q.messages)}
                words = [s['text'] for s in question_answers(local, order)]
                st.update(asked=asked_q or q.entry, before=''.join(words[:-1]), last_target=local.get('asked_target'))
            action, reason = sp.decide(cfg, result, st, latest['text'])
            rule = {'action': action, 'reason': reason, 'signal': st['signal']}
            if st.get('scope'):
                rule['scope'] = st['scope'][0]
        step['rule'] = rule
        is_paused = paused if skip else action == 'rest'
        if deepen_answer:
            status = 'pending' if action == 'rest' else dz.get('status') or 'known'
        else:
            status = 'pending' if action in ('ask', 'rest') else close_status(result, reason, skip)
        if status in ('skipped', 'declined') and reason not in ('declined', 'deferred'):
            reason = 'declined'
        order = {m['id']: i for i, m in enumerate(q.messages)}
        dialogue = dialogue_from(q.entry, question_answers(local, order), shown_before(q.messages), latest['id'], latest['text'])
        elder_words = ''.join(t for role, t in dialogue if role == 'elder')
        fields = sp.recorded_fields(rt, result)
        question, spoken, close_text = None, None, None
        if action == 'rest' and deepen_answer:
            dz['stopped'] = 'rest'
        elif action == 'close' and not skip and not is_paused and status not in ('skipped', 'declined'):
            asked_text = asked_q or q.entry
            before = ''.join([t for role, t in dialogue if role == 'elder'][:-1])
            dim, ack, deepen_q, log = yield from life_try_deepen(S, q, reason, latest['text'], dialogue, asked_text, before)
            if log is not None:
                dz = local['deepen']
                keep_log(dz, log)
                clean_dz(dz)
                step['deepen'] = log
                if deepen_q:
                    dz['asked'] += 1
                    dz['dims'].append(dim)
                    dz['awaiting'] = True
                    dz['status'] = status
                    question, status = deepen_q, 'pending'
                    spoken = {'task': 'deepen', 'text': sp.join(ack, deepen_q)}
        if deepen_answer and question is None:
            dz['awaiting'] = False
        nxt = q.override['next'] if 'next' in q.override else S.life_next(qid)
        following = nxt if status != 'pending' else None
        if spoken is not None:
            pass
        elif action == 'ask':
            user = sp.speaker_user(rt, qid, dialogue, fields, 'ask', reason, result.get('question'))
            row = yield from speak(S, user, q.known, f'{qid}-s{len(q.messages)}', q.calls)
            reply, question, rec = sp.compose_ask(rt, row, result, reason, [s['question'] for s in local['sources']], elder_words)
            spoken = {'task': 'ask', **rec, 'text': reply, 'raw': row.get('content'), 'input': user}
        elif status != 'pending' and following and not is_paused:
            prev = yield from q.get_chain()
            user = sp.speaker_user(rt, qid, dialogue, fields, 'close', reason=reason, next_entry=following, prev_close=prev)
            row = yield from speak(S, user, q.known, f'{qid}-c{len(q.messages)}', q.calls)
            said, _ = sp.parse_speaker(row)
            close_text, ack, notes, ok = st_.close_reply(rt, said, following, elder_words, q.seen)
            if not ok:
                close_text = (interview.CONTROLS.SKIP_ACK + '\n' if status in ('skipped', 'declined') else NOTED_TEXT) + following
            spoken = {'task': 'close', 'close_reason': reason, 'step': 'next_question', 'ack': ack if ok else '', 'notes': notes,
                      'text': close_text, 'raw': row.get('content'), 'input': user}
        elif status != 'pending':
            spoken = {'task': 'close', 'close_reason': reason, 'step': 'review' if not following else 'paused'}
        if deepen_answer:
            pass
        elif skip:
            local['asked_target'] = None
        else:
            finish(local, outcome, {**(spoken or {}), **rule}, asked=reason if action == 'ask' else None)
        local['asked_question'] = question
        local['status'] = status
        if not skip:
            paused = is_paused
        if close_text is not None:
            q.chain = close_text
        step.update(reply=(spoken or {}).get('task') or ('pause' if paused else None), spoken=spoken)
        if paused:
            q.sys(LIFE_PAUSE_TEXT, 'pause')
            q.scripted('继续')
            paused = False
            q.sys(LIFE_RESUME + question_text(), 'resume')
            continue
        if question is not None:
            q.sys(spoken['text'], 'deepen' if spoken['task'] == 'deepen' else 'followup', question_part=question)
            continue
        q.sys(close_text or LIFE_REVIEW_TEXT, 'transition' if close_text else 'review')
        q.status = 'skipped' if status in ('skipped', 'declined') else 'saved'
        q.close_reason = reason
        break
    yield from q.get_chain()
    return q.record(), q.chain


def life_try_deepen(S, q, reason, text, dialogue, asked_text, before):
    """contract_v3j_interview.try_deepen as the skeleton calls it."""
    rt, st_ = S.rt, S.story
    local, qid = q.local, q.qid
    if qid not in rt.story:
        return None, None, None, None
    dz = local.setdefault('deepen', st_.new_deepen(rt, qid))
    elder_words = ''.join(t for role, t in dialogue if role == 'elder')
    dz['asked_text'], dz['before'], dz['last'] = asked_text, before, text
    k = len(local['sources']) + len(dz.get('sources') or [])
    if dz.get('stopped'):
        ok, why, info = False, 'stopped_' + dz['stopped'], {}
    else:
        ok, why, info = st_.deepen_gate(rt.speaker_config, reason, text, elder_words, dz, k)
    log = {'k': k, 'decision': 'asked' if ok else 'skip', 'reason': why, **info}
    if not ok:
        return None, None, None, log
    prior = [s.get('question') for s in question_answers(local, {})]
    user = st_.deepen_user(rt, qid, dialogue, dz)
    row = yield from deepen_call(S, user, q.known, f'{qid}-d{len(q.messages)}', q.calls)
    dim, ack, question, errs, repairs = st_.compose_deepen(rt, row, dz, prior, elder_words)
    log.update({'dimension': dim, 'ack': ack, 'question': question, 'errors': errs, 'repairs': repairs,
                'raw': row.get('content'), 'input': user})
    if errs:
        log['decision'] = 'skip'
        log['reason'] = 'invalid' if errs[0] not in ('call_failed', 'model_skip') else errs[0]
        return None, None, None, log
    return dim, ack, question, log


def close_status(result, reason, skip):
    """contract_v3j_life_overview.close_status."""
    if skip:
        return 'skipped'
    if reason == 'declined_partial':
        return 'known'
    decision = result.get('decision')
    effective = result.get('effective') or {}
    if decision == 'ready':
        return 'known'
    if decision == 'limited':
        return 'declined' if 'declined' in effective.values() else 'unknown'
    if decision in ('skipped', 'deferred'):
        return 'skipped'
    if reason in ('declined', 'unknown'):
        return reason
    return 'known' if any(v in ('known', 'none') for v in effective.values()) else 'unknown'

