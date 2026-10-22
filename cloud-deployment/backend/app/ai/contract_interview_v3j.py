"""Judgment layer v3j and the v4d speaking-layer call, on a pinned runtime bundle.

Port of tools/interview_eval/pipelines/v3j.py (offline candidate, full45 197/204):
one judge call per checkpoint, deterministic assembly against the frozen engine's
feedback, and a denial re-check that is only sent when recorded sentences contain
explicit denial wording. System/user messages, request parameters, assembly,
verify gating and engine calls are the evaluated ones; offline experiment switches
(V3_EXP, prompt overrides) are not carried over, so every ``'x' in EXP`` branch is
resolved as in the evaluated configuration (EXP empty).

Like ContractInterviewPipeline this module never changes another question's
state, advances an interview, writes a database row or sends anything to a user.
Each provider call is bound to a request digest and handed to ``save_call``
before the next stage starts, so a retry resumes without repeating a call.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
from time import monotonic

from app.ai.llm_client import LLMConfigurationError, LLMResponseFormatError, LLMServiceError

PIPELINE = 'v3j_v4d'
PARAM_KEYS = {'model', 'thinking', 'max_tokens', 'temperature', 'json_mode'}
REQUIRED_FILES = {'engine.js', 'contracts.json', 'judge-prompt.txt', 'verify-prompt.txt', 'speaker-prompt.txt',
                  'speaker-config.json', 'provider-settings.json', 'opencc-ts-char-map.json'}
BRIDGE_TIMEOUT = 10.0
JUDGE_TIMEOUT = 110.0
SPEAKER_TIMEOUT = 30.0


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def _params(value):
    # Exactly the evaluated request shape: no reasoning_effort or other provider
    # switches can be added, and thinking stays disabled.
    if not isinstance(value, dict) or set(value) != PARAM_KEYS:
        raise ValueError('unsupported_provider_configuration')
    if value['thinking'] != 'disabled' or value['json_mode'] is not True or not isinstance(value['model'], str):
        raise ValueError('unsupported_provider_configuration')
    return value


class V3jRuntime:
    """An immutable deployment artifact; only its directory is configurable."""

    def __init__(self, directory=None, expected_manifest_sha256=None):
        location = directory or os.getenv('INTERVIEW_V3J_RUNTIME_DIR', '')
        expected = expected_manifest_sha256 or os.getenv('INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256', '')
        if not location or not expected:
            raise LLMConfigurationError('A pinned v3j interview runtime manifest is required')
        self.directory = Path(location).resolve()
        try:
            manifest_bytes = (self.directory / 'manifest.json').read_bytes()
            if sha256(manifest_bytes).hexdigest() != expected:
                raise ValueError('manifest_mismatch')
            manifest = json.loads(manifest_bytes)
            for name, digest in manifest['files'].items():
                target = (self.directory / name).resolve()
                if not target.is_relative_to(self.directory) or sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError('runtime_file_mismatch')
            if not REQUIRED_FILES.issubset(manifest['files']):
                raise ValueError('runtime_files_missing')
            # Node resolves require('./x') to an exact file before x.js, so an
            # unlisted file could shadow a verified module: none is allowed.
            if {p.name for p in self.directory.iterdir()} != set(manifest['files']) | {'manifest.json'}:
                raise ValueError('runtime_unlisted_file')
            if manifest.get('pipeline') != PIPELINE:
                raise ValueError('unsupported_runtime_pipeline')
            read = lambda name: (self.directory / name).read_text(encoding='utf-8')
            self.contracts = json.loads(read('contracts.json'))
            settings = json.loads(read('provider-settings.json'))
            if set(settings) != {'judge', 'verify'}:
                raise ValueError('unsupported_provider_configuration')
            self.judge_params = _params(settings['judge'])
            self.verify_params = _params(settings['verify'])
            self.speaker_config = json.loads(read('speaker-config.json'))
            self.speaker_params = _params(self.speaker_config['model'])
            for key in ('followup_cap', 'same_target_cap', 'stop_after_unknown_once_asked'):
                if not isinstance(self.speaker_config[key], int):
                    raise ValueError('unsupported_speaker_configuration')
            if self.speaker_config.get('rest_resume_by_speaker') or not isinstance(self.speaker_config.get('signal_close'), bool):
                raise ValueError('unsupported_speaker_configuration')
            self.judge_prompt = read('judge-prompt.txt')
            self.verify_prompt = read('verify-prompt.txt')
            self.speaker_prompt = read('speaker-prompt.txt')
            self.char_map = json.loads(read('opencc-ts-char-map.json'))
            self.version = self.contracts['version']
            if manifest['catalog_version'] != self.version:
                raise ValueError('catalog_version_mismatch')
            self.runtime_version = manifest['version']
            self.manifest_sha256 = expected
            self.questions = {q['id']: q for q in self.contracts['questions']}
            self.F = {f['id']: f for q in self.contracts['questions'] for f in q['elements']}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LLMConfigurationError('Interview v3j runtime integrity check failed') from exc
        self._defs = None
        self._defs_lock = threading.Lock()

    def engine(self):
        return EngineSession(self.directory)

    def defs(self, engine):
        with self._defs_lock:
            if self._defs is None:
                self._defs = engine.op('contracts')
            return self._defs

    def payload(self, engine, question_id, sources, context):
        """Same construction as the evaluation's Engine.payload_for (independent question)."""
        defs = self.defs(engine)
        qid = question_id
        built = []
        for item in sources:
            source = deepcopy(item)
            source.update(question_id=qid, speaker='narrator')
            source.setdefault('question', None)
            if defs.get('model_source_fields'):
                source = {k: source[k] for k in defs['model_source_fields'] if k in source}
            built.append(source)
        payload = {'question_id': qid, 'main_question': defs['questions'][qid], 'question_context_mode': 'independent',
                   'current_question': built[-1]['question'] or '', 'source_kind': 'live_interview',
                   'historical_question_verified': bool(built[-1]['question']), 'focus': context.get('focus'),
                   'field_contract': {k: v for k, v in defs['fields'].items() if v['question_id'] == qid},
                   'question_contract': defs.get('question_contracts', {}).get(qid, {}),
                   'sources': built, 'previous_fields': deepcopy(context.get('previous_fields') or {}),
                   'ask_counts': deepcopy(context.get('ask_counts') or {})}
        if defs.get('model_field_contract_keys'):
            payload['field_contract'] = {fid: {k: v for k, v in f.items() if k in defs['model_field_contract_keys']}
                                         for fid, f in payload['field_contract'].items()}
        if defs.get('evidence_unit_protocol'):
            payload['evidence_units'] = engine.op('evidence_units', question_id=qid, sources=built)
        return payload


class EngineSession:
    """One Node process for one judgment run (the assembly loop needs several analyses)."""

    def __init__(self, directory):
        try:
            self.proc = subprocess.Popen(
                [os.getenv('INTERVIEW_NODE_BINARY', 'node'), str(Path(__file__).with_name('contract_interview_v3j_bridge.js')),
                 str(directory)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8')
        except OSError as exc:
            raise LLMResponseFormatError('Interview contract validation unavailable') from exc
        self.lines = queue.Queue()
        self.n = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def op(self, name, **args):
        self.n += 1
        try:
            self.proc.stdin.write(json.dumps({'id': self.n, 'op': name, 'args': args}, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
            line = self.lines.get(timeout=BRIDGE_TIMEOUT)
            reply = json.loads(line) if line is not None else None
        except (OSError, ValueError, TypeError, queue.Empty) as exc:
            self.close()
            raise LLMResponseFormatError('Interview contract validation unavailable') from exc
        if not isinstance(reply, dict) or reply.get('id') != self.n or 'error' in reply:
            self.close()
            raise LLMResponseFormatError('Interview contract validation unavailable')
        return reply['result']

    def analyze(self, payload, proposal):
        return self.op('analyze', payload=payload, proposal=proposal)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
            self.proc.wait()
        self.reader.join(timeout=5)
        self.proc.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class V3jPipeline:
    def __init__(self, runtime, client):
        self.runtime = runtime
        self.client = client

    def _call(self, system, user, params, timeout):
        started = monotonic()
        try:
            response = self.client.client.with_options(timeout=timeout, max_retries=0).chat.completions.create(
                model=params['model'],
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                max_tokens=params['max_tokens'], temperature=params['temperature'],
                response_format={'type': 'json_object'}, extra_body={'thinking': {'type': 'disabled'}},
            )
        except Exception as exc:
            # Never expose an upstream exception containing private data.
            raise LLMServiceError('Interview provider request failed') from exc
        content = response.choices[0].message.content or ''
        try:
            output, parse_error = json.loads(content), None
        except ValueError:
            output, parse_error = None, 'JSONDecodeError'
        return {'kind': 'model_call', 'ok': True, 'content': content, 'output': output, 'parse_error': parse_error,
                'finish_reason': response.choices[0].finish_reason, 'response_id': response.id,
                'response_model': response.model, 'params': deepcopy(params),
                'usage': response.usage.model_dump(mode='json') if response.usage else {},
                'seconds': monotonic() - started}

    def _invoker(self, calls, saved_calls, save_call):
        def invoke(stage, system, user, params, timeout=JUDGE_TIMEOUT, tolerate_failure=False):
            digest = sha256(_json({'runtime': self.runtime.manifest_sha256, 'stage': stage, 'params': params,
                                   'system': system, 'user': user}).encode()).hexdigest()
            saved = (saved_calls or {}).get(stage)
            if saved is not None:
                if saved.get('request_sha256') != digest:
                    raise LLMResponseFormatError('Saved provider response does not match pending input')
                call = deepcopy(saved['response'])
            else:
                try:
                    call = self._call(system, user, params, timeout)
                except LLMServiceError:
                    if not tolerate_failure:
                        raise
                    # A speaking-layer failure falls back to fixed wording; it is
                    # recorded so that a retry gives the same reply without a call.
                    call = {'kind': 'model_call', 'ok': False, 'error': 'provider_request_failed', 'output': None}
            entry = {'request_sha256': digest, 'payload': user, 'response': call}
            calls[stage] = entry
            if save_call is not None and saved is None:
                save_call(stage, deepcopy(entry))
            return call
        return invoke

    def run(self, question_id, sources, context=None, saved_calls=None, save_call=None):
        """One v3j checkpoint. Saved calls must be server-owned records of the same pending request."""
        rt = self.runtime
        if question_id not in rt.questions or not sources:
            raise LLMResponseFormatError('A known question and its own sources are required')
        if any(source.get('question_id') != question_id for source in sources):
            raise LLMResponseFormatError('Cross-question source use is prohibited')
        context = deepcopy(context or {})
        fields = {field['id'] for field in rt.questions[question_id]['elements']}
        if not set(context.get('previous_fields') or {}).issubset(fields):
            raise LLMResponseFormatError('Cross-question state use is prohibited')
        calls = {}
        invoke = self._invoker(calls, saved_calls, save_call)
        with rt.engine() as engine:
            payload = rt.payload(engine, question_id, sources, context)
            result, trace = run_checkpoint(payload, rt, engine, invoke)
        return {'pipeline': 'v3j', 'runtime_version': rt.runtime_version, 'catalog_version': rt.version,
                'runtime_manifest_sha256': rt.manifest_sha256, 'result': result, 'calls': calls, 'trace': trace}

    def speak(self, user, saved_calls=None, save_call=None):
        """One v4d speaking-layer call; a provider failure returns an unsuccessful row instead of raising."""
        calls = {}
        invoke = self._invoker(calls, saved_calls, save_call)
        row = invoke('speaker', self.runtime.speaker_prompt, user, self.runtime.speaker_params,
                     timeout=SPEAKER_TIMEOUT, tolerate_failure=True)
        return row, calls['speaker']


# --------------------------------------------------------------------------- judge phase (v3j.py)
PERIODS = {'birth', 'childhood', 'school_years', 'youth', 'middle_age', 'adulthood', 'lifelong', 'now', 'unspecified', 'as_stated'}
STAGE_NAMES = {'youth': '青年时期', 'now': '现在', 'childhood': '童年', 'birth': '出生时', 'school_years': '求学时期', 'middle_age': '中年'}
VERDICT_STATE = {'answered': 'known', 'none': 'none', 'unknown': 'unknown', 'declined': 'declined',
                 'deferred': 'deferred', 'unspecified': 'ambiguous'}
CONTROL = {'continue', 'pause', 'skip_question', 'defer_question'}
STAGE_ANCHORS = {
    'youth': re.compile(r'(?:1[5-9]|2[0-9]|3[0-5]|十[五六七八九]|二十|三十)(?:多|来|出头)?(?:岁|歲)|年轻|年輕|青年|年少|少年'),
    'now': re.compile(r'现在|現在|目前|如今|最近|近来|近來|这几年|這幾年|眼下|当下|當下'),
}
LITERAL_TYPES = {'place', 'time', 'duration', 'life_summary', 'period'}  # engine expects a short literal value


def script_view(t, rt):
    """Traditional->simplified single-character view, as the engine uses for literal matching (never stored)."""
    return ''.join(rt.char_map.get(c, c) for c in str(t))


def link_pieces(value):
    """Same candidate pieces the engine accepts as link targets."""
    out = []
    for v in ([value] if isinstance(value, str) else [x for x in (value or []) if isinstance(x, str)]):
        out.append(v)
        out += [t.strip() for t in re.split(r'[、，,；;]|(?:和|与|及)', v) if t.strip()]
        out += re.findall(r'[“「『‘"]([^”」』’"\n]+)[”」』’"]', v)
    return list(dict.fromkeys(out))


def is_clarification(f):
    act = f.get('activation') or {}
    return any(k.startswith('if_') or k == 'reported_without_self' for k in act)


def judged_fields(payload, rt):
    return [fid for fid in payload['field_contract']
            if rt.F[fid]['requirement'] != 'optional' and not is_clarification(rt.F[fid])]


def parents_of(f):
    act = f.get('activation') or {}
    return act.get('known') or act.get('after_answer') or []


def target_block(fid, rt):
    f = rt.F[fid]
    lines = [f'- id: {fid}', f'  名称: {f["label"]}', f'  问法: {f["question"]}', f'  算作回答: {f["usable_answer"]}',
             f'  subjects: {", ".join(f["scope"]["subjects"])}']
    notes = []
    act = f.get('activation') or {}
    if act.get('premise_check'):
        notes.append('这是本题的适用前提。只判断受访者是否明确表示自己没有过这类经历（如没上过学、没结过婚、没有子女）→ none；'
                     '只要讲到了本人的这类经历，或根本没提，一律 not_answered')
    parents = parents_of(f)
    if parents:
        notes.append('这是「%s」的后续补充：只在父项已回答时判定，且必须针对父项说的同一个对象、同一件事（可以是同一句话）'
                     % '、'.join(rt.F[p]['label'] for p in parents))
    if f.get('link'):
        notes.append('answered 时填写 link_word：父项「%s」答案中被本项解释的那个原词' % rt.F[f['link']['field_id']]['label'])
    fmt = f.get('answer_format') or {}
    if 'precision' in (fmt.get('known_required_attributes') or []):
        notes.append('answered 时填写 precision，取值之一：' + '/'.join(fmt.get('precision', [])))
    if f.get('type') in LITERAL_TYPES:
        notes.append('answered 时填写 value_text：从原话逐字抄写能单独表达答案的最短完整片段（不改字、不拼接）')
    stage = (f.get('scope') or {}).get('stage_binding_required')
    if stage:
        notes.append('要求阶段：' + STAGE_NAMES.get(stage, stage))
    if 'none' not in f.get('allowed_states', []) or f.get('none') is False:
        notes.append('不适用 none')
    if f.get('notes'):
        notes.append(f['notes'])
    if notes:
        lines.append('  说明: ' + '；'.join(notes))
    return '\n'.join(lines)


def user_message(payload, rt, fids):
    units = payload['evidence_units']
    out = [f'main_question: {payload["main_question"]}']
    for n, source in enumerate(payload['sources'], 1):
        out.append(f'第{n}段 原问：{source.get("question") or "（无，受访者自述）"}')
        out += [f'{u["id"]} {u["text"]}' for u in units if u['source_id'] == source['id']]
    out.append('targets:')
    out += [target_block(fid, rt) for fid in fids]
    return '\n'.join(out)


KIND_VERDICT = {'content': 'answered', 'negation': 'none', 'unknown': 'unknown', 'declined': 'declined',
                'deferred': 'deferred', 'affirmed_unspecified': 'unspecified'}


def verdict_of(j):
    """The final state is derived in code from the judge's categorical checks."""
    if 'kind' in j:
        if j.get('kind') == 'absent' or j.get('concept') != 'same':
            return 'not_answered'
        return KIND_VERDICT.get(j.get('kind'), 'not_answered')
    return j.get('verdict')


def contiguous_value(ids, units):
    """One contiguous span inside one source covering the chosen core sentences."""
    index = {u['id']: i for i, u in enumerate(units)}
    ids = sorted((i for i in ids if i in index), key=index.get)
    if not ids:
        return []
    source = units[index[ids[0]]]['source_id']
    same = [index[i] for i in ids if units[index[i]]['source_id'] == source]
    return [units[k]['id'] for k in range(min(same), max(same) + 1)]


def assemble(payload, output, rt, fids, subject_choice, value_override=None, wide=()):
    units = payload['evidence_units']
    index = {u['id']: i for i, u in enumerate(units)}
    text = {u['id']: u['text'] for u in units}
    targets = (output or {}).get('targets') or {}
    fields, notes = {}, {}
    for fid in fids:
        f = rt.F[fid]
        j = targets.get(fid)
        if not isinstance(j, dict):
            continue
        state = VERDICT_STATE.get(verdict_of(j))
        if not state or state not in f.get('allowed_states', []):
            continue
        if (f.get('activation') or {}).get('premise_check') and state == 'known':
            notes[fid] = 'premise_known_not_recorded'
            continue
        ids = sorted({i for i in (j.get('units') or []) if i in index}, key=index.get)
        core = sorted({i for i in (j.get('core') or []) if i in index}, key=index.get)
        prop = {'state': state}
        if state == 'known':
            literal = j.get('value_text') if f.get('type') in LITERAL_TYPES else None
            holder = [u['id'] for u in units if isinstance(literal, str) and literal.strip() and literal in u['text']]
            literal_core_only = False
            if isinstance(literal, str) and literal.strip():
                if not holder and not any(script_view(literal.strip(), rt) in script_view(u['text'], rt) for u in units):
                    # the literal answer is not in the narrator's words at all (e.g. copied from the question)
                    notes[fid] = 'literal_not_in_narrator_words'
                    continue
                if holder and core and not set(holder) & set(core):
                    # the literal contradicts the judge's own answer sentence: trust the answer sentence
                    holder, literal_core_only = [], True
                    notes[fid] = 'literal_outside_core_uses_core'
            if holder:
                prop['value'] = literal
                ids = sorted(set(ids) | {holder[0]}, key=index.get)
            else:
                # value spans every cited sentence (gold phrases often sit beside the core), except for
                # stage-bound fields where unrelated clauses would break the engine's stage proof
                staged_field = bool((f.get('scope') or {}).get('stage_binding_required'))
                value_ids = contiguous_value((core or ids) if (staged_field and fid not in wide) or literal_core_only else (core + ids), units)
                if value_override and fid in value_override:
                    value_ids = list(value_override[fid])
                if not value_ids:
                    continue
                if f.get('link'):
                    # an explanation tied to a chosen word keeps the adjacent sentence that states the word
                    word = j.get('link_word') if isinstance(j.get('link_word'), str) else ''
                    k = index[value_ids[0]]
                    if word.strip() and k > 0 and units[k - 1]['source_id'] == units[k]['source_id'] \
                            and word.strip() in units[k - 1]['text']:
                        value_ids = [units[k - 1]['id']] + value_ids
                prop['value_unit_ids'] = value_ids
                ids = sorted(set(ids) | set(value_ids), key=index.get)
                # the sentence just before the answer usually carries its subject/object context
                k = index[value_ids[0]]
                if k > 0 and units[k - 1]['source_id'] == units[k]['source_id']:
                    ids = sorted(set(ids) | {units[k - 1]['id']}, key=index.get)
        else:
            if not ids:
                continue
            prop['value'] = None
            if state == 'ambiguous':
                prop['clarifications'] = ['referent']
        period = (f.get('scope') or {}).get('period') or 'as_stated'
        stage = (f.get('scope') or {}).get('stage_binding_required')
        if stage in STAGE_ANCHORS and ids and not any(STAGE_ANCHORS[stage].search(text[i]) for i in ids):
            # attach the nearest sentence that states the life stage (same source first)
            anchor_pos = [k for k, u in enumerate(units) if STAGE_ANCHORS[stage].search(u['text'])]
            if anchor_pos:
                first = index[ids[0]]
                src = units[first]['source_id']
                best = min(anchor_pos, key=lambda k: (units[k]['source_id'] != src, abs(k - first)))
                ids = sorted(set(ids) | {units[best]['id']}, key=index.get)
                notes[fid + ':stage_anchor'] = units[best]['id']
        prop['evidence_unit_ids'] = ids
        prop['scope'] = {'subject': subject_choice.get(fid) or f['scope']['subjects'][0],
                         'period': period if period in PERIODS else 'as_stated', 'relation_unit_ids': 'same_as_evidence'}
        fmt = f.get('answer_format') or {}
        if state == 'known' and 'precision' in (fmt.get('known_required_attributes') or []):
            allowed = fmt.get('precision', [])
            prop['precision'] = j.get('precision') if j.get('precision') in allowed else ('as_stated' if 'as_stated' in allowed else allowed[0])
        fields[fid] = prop
    # activation: a follow-up child is only recorded when its parent is answered (or explicitly none for after_answer)
    previous = payload.get('previous_fields') or {}
    for fid in list(fields):
        act = rt.F[fid].get('activation') or {}
        need = act.get('known') or act.get('after_answer')
        if not need:
            continue
        ok_states = {'known'} if act.get('known') else {'known', 'none'}
        for p in need:
            st = (fields.get(p) or previous.get(p) or {}).get('state')
            if st not in ok_states:
                notes[fid] = 'inactive_child_dropped'
                fields.pop(fid, None)
                break
    # links: child explanation bound to the parent's literal value
    for fid in list(fields):
        link = rt.F[fid].get('link')
        if not link or fields[fid]['state'] != 'known':
            continue
        parent = fields.get(link['field_id'])
        if parent and parent.get('value_unit_ids'):
            parent_value = ''.join(text[i] for i in parent['value_unit_ids'])
        elif parent:
            parent_value = parent.get('value')
        else:
            parent_value = (previous.get(link['field_id']) or {}).get('value')
        pieces = link_pieces(parent_value)
        word = (targets.get(fid) or {}).get('link_word')
        word = word.strip() if isinstance(word, str) else ''
        exact = [p for p in pieces if p == word]
        containing = sorted([p for p in pieces[1:] if word and (word in p or p in word)], key=len) if word else []
        value = (exact or containing or pieces[:1] or [None])[0]
        if value:
            fields[fid]['links'] = [{'field_id': link['field_id'], 'value': value}]
    c = (output or {}).get('control') or {}
    action = c.get('action') if c.get('action') in CONTROL else 'continue'
    cids = [i for i in (c.get('units') or []) if i in index] if action != 'continue' else []
    if action != 'continue' and not cids:
        action = 'continue'
    return {'control': {'action': action, 'evidence_unit_ids': cids}, 'fields': fields}, notes


SUBJECT_ERRORS = ('subject', 'wrong_subject')


def current_stage_fallback(payload, output, rt, engine, fids, dropped, subject_choice, proposal, result, attempts, wide=()):
    """A 'now'-bound answer whose selected sentence the engine cannot tie to the present (e.g. it sits in a
    future-plan frame) is re-proposed with the cited sentence of the same source that is itself framed as
    current. Kept only if the engine then accepts it as known; otherwise the original result stands."""
    units = payload['evidence_units']
    index = {u['id']: i for i, u in enumerate(units)}
    override = {}
    for fid, got in (result.get('fields') or {}).items():
        prop = (proposal.get('fields') or {}).get(fid) or {}
        if got.get('provenance') != 'required_stage_not_grounded' or prop.get('state') != 'known' or not prop.get('value_unit_ids'):
            continue
        if (rt.F[fid].get('scope') or {}).get('stage_binding_required') != 'now':
            continue
        first = index[prop['value_unit_ids'][0]]
        src = units[first]['source_id']
        cands = [i for i in prop['evidence_unit_ids'] if i not in prop['value_unit_ids'] and units[index[i]]['source_id'] == src
                 and STAGE_ANCHORS['now'].search(units[index[i]]['text'])]
        if cands:
            override[fid] = [min(cands, key=lambda i: abs(index[i] - first))]
    if not override:
        return result, {}
    prop2, _ = assemble(payload, output, rt, [f for f in fids if f not in dropped], subject_choice, override, wide=wide)
    res2 = engine.analyze(payload, prop2)
    attempts.append({'proposal': prop2, 'decision': res2.get('decision'), 'errors': res2.get('errors'),
                     'semantic_rejections': res2.get('semantic_rejections'), 'stage_fallback': override})
    ok = res2.get('decision') != 'invalid' and all((res2.get('fields') or {}).get(f, {}).get('state') == 'known' for f in override)
    return (res2 if ok else result), {'override': override, 'accepted': ok}


# --------------------------------------------------------------------------- verify phase
DIRECTION_KIND = {'content': 'content', 'negation': 'negation', 'unspecified': 'affirmed_unspecified'}
KIND_TO_VERDICT = {'absent': 'not_answered', **{k: v for k, v in KIND_VERDICT.items()}}
STATE_KIND = {'known': 'content', 'none': 'negation', 'ambiguous': 'affirmed_unspecified'}
# explicit denial wording: the only material where the denial re-check can change the state
DIRECTION_CUES = re.compile(r'没有|沒有|不希望|不想|没什么|沒什麼|不需要|无悔|無悔|不后悔|不後悔')


def settle(payload, output, rt, engine, fids):
    """Code-only assembly loop: subject retries / drops on engine protocol errors, then the current-stage fallback."""
    targets = output.get('targets') or {}
    subject_choice, tried, attempts = {}, {}, []
    for fid in fids:
        j = targets.get(fid) or {}
        allowed = rt.F[fid]['scope']['subjects']
        # the narrator is the default subject; when the contract's primary subject is someone else
        # (parents, family, teacher ...) the judge's pick among the allowed roles is used
        first = j.get('subject') if (allowed[0] != 'self' and j.get('subject') in allowed) else allowed[0]
        subject_choice[fid] = first
        tried[fid] = [first] + [s for s in [j.get('subject')] + allowed if s in allowed and s != first]
    dropped = set()
    wide = {f for f in fids if (rt.F[f].get('scope') or {}).get('stage_binding_required')}
    probe_info = {}
    for attempt in range(12):
        proposal, notes = assemble(payload, output, rt, [f for f in fids if f not in dropped], subject_choice, wide=wide)
        result = engine.analyze(payload, proposal)
        attempts.append({'proposal': proposal, 'decision': result.get('decision'), 'errors': result.get('errors'),
                         'semantic_rejections': result.get('semantic_rejections')})
        if result.get('decision') != 'invalid':
            # a stage-bound value spanning all cited sentences that the engine cannot ground (or rejects) is
            # retried with the judge's core sentences only
            narrow = {f for f in wide if f in (proposal.get('fields') or {}) and
                      (((result.get('fields') or {}).get(f) or {}).get('provenance') == 'required_stage_not_grounded'
                       or ((result.get('fields') or {}).get(f) or {}).get('state') == 'missing')}
            if narrow:
                wide -= narrow
                continue
            if not probe_info:
                rejected = core_guard_probe(payload, output, rt, engine, proposal, result)
                probe_info = {'rejected': sorted(rejected)} if rejected else {'rejected': []}
                if rejected:
                    dropped |= rejected
                    continue
            break
        bad = {}
        for e in result.get('errors') or []:
            fid, _, reason = e.partition(':')
            if fid in fids:
                bad[fid] = reason
        if not bad:
            break
        for fid, reason in bad.items():
            options = tried[fid]
            current = options.index(subject_choice[fid]) if subject_choice[fid] in options else 0
            if any(k in reason for k in SUBJECT_ERRORS) and current + 1 < len(options):
                subject_choice[fid] = options[current + 1]
            elif fid in wide:
                wide.discard(fid)
            else:
                dropped.add(fid)
    fallback = {}
    if result.get('decision') != 'invalid':
        result, fallback = current_stage_fallback(payload, output, rt, engine, fids, dropped, subject_choice, proposal, result, attempts, wide)
        if fallback.get('accepted'):
            proposal = attempts[-1]['proposal']
    return result, proposal, {'notes': notes, 'attempts': attempts, 'stage_fallback': fallback, 'guard_probe': probe_info}


def core_guard_probe(payload, output, rt, engine, proposal, result):
    """The engine's semantic guards were written for a short selected answer. Our recorded value spans every
    cited sentence, which can hide a guard's signal (e.g. a complaint or an occupational fact diluted by
    neighbouring sentences). Probe each recorded known field once with value = evidence = the judge's core
    sentences only; a field the engine semantically rejects in that form is not recorded."""
    units = payload['evidence_units']
    index = {u['id']: i for i, u in enumerate(units)}
    targets = output.get('targets') or {}
    probe = json.loads(json.dumps(proposal, ensure_ascii=False))
    probed = set()
    for fid, prop in (proposal.get('fields') or {}).items():
        if prop.get('state') != 'known' or not prop.get('value_unit_ids'):
            continue
        if ((result.get('fields') or {}).get(fid) or {}).get('state') in (None, 'missing'):
            continue
        core = contiguous_value([i for i in (targets.get(fid) or {}).get('core') or [] if i in index], units)
        if not core or (core == prop['value_unit_ids'] and core == prop['evidence_unit_ids']):
            continue
        probe['fields'][fid] = {**prop, 'value_unit_ids': core, 'evidence_unit_ids': core}
        probed.add(fid)
    if not probed:
        return set()
    res = engine.analyze(payload, probe)
    return {r.get('field_id') for r in res.get('semantic_rejections') or []} & probed


def verify_candidates(payload, result, proposal, rt):
    """Judge-proposed targets that the engine actually records with a non-missing state."""
    out = []
    for fid, prop in (proposal.get('fields') or {}).items():
        got = (result.get('fields') or {}).get(fid) or {}
        if got.get('state') not in STATE_KIND or not prop.get('evidence_unit_ids'):
            continue
        if (rt.F[fid].get('activation') or {}).get('premise_check'):
            continue
        out.append(fid)
    return out


def verify_message(payload, proposal, rt, fids):
    """Only the sentences that will be recorded as the claim's evidence, with their actual questions."""
    units = payload['evidence_units']
    order = {u['id']: k for k, u in enumerate(units)}
    question = {s['id']: s.get('question') for s in payload['sources']}
    lines = [f'main_question: {payload["main_question"]}']
    for fid in fids:
        f = rt.F[fid]
        lines += [f'目标 {fid}', f'  名称: {f["label"]}', f'  问法: {f["question"]}', f'  算作回答: {f["usable_answer"]}',
                  f'  可选主体: {", ".join(f["scope"]["subjects"])}']
        notes = []
        parents = parents_of(f)
        if parents:
            notes.append('这是「%s」的后续：须针对父项所说的同一对象或同一件事（可以是同一句话）' % '、'.join(rt.F[p]['label'] for p in parents))
        if f.get('notes'):
            notes.append(f['notes'])
        stage = (f.get('scope') or {}).get('stage_binding_required')
        if stage:
            notes.append('要求阶段：' + STAGE_NAMES.get(stage, stage))
        if notes:
            lines.append('  说明: ' + '；'.join(notes))
        current = None
        for i in sorted(proposal['fields'][fid]['evidence_unit_ids'], key=order.get):
            u = units[order[i]]
            if u['source_id'] != current:
                current = u['source_id']
                lines.append(f'  原问: {question.get(current) or "（无，受访者自述）"}')
            lines.append(f'  {i} {u["text"].strip()}')
    return '\n'.join(lines)


def set_kind(j, kind):
    if 'kind' in j:
        j['kind'] = kind
        if kind != 'absent':
            j['concept'] = 'same'
    else:  # older verdict-style judge output
        j['verdict'] = KIND_TO_VERDICT[kind]


def apply_verify(output, checks, rt, fids, proposal):
    new = json.loads(json.dumps(output, ensure_ascii=False))
    changes = {}
    for fid in fids:
        c = checks.get(fid)
        if not isinstance(c, dict):
            continue
        j = new['targets'][fid]
        # only a denial direction is applied (known -> none)
        kind = DIRECTION_KIND.get(c.get('direction'))
        if kind != 'negation':
            kind = None
        current = {'answered': 'content', 'none': 'negation', 'unspecified': 'affirmed_unspecified'}.get(verdict_of(j))
        if kind and current and kind != current and VERDICT_STATE[KIND_VERDICT[kind]] in rt.F[fid].get('allowed_states', []):
            set_kind(j, kind)
            # the new state rests on the sentences the verifier actually read (e.g. a denial just before the value)
            seen = (proposal.get('fields') or {}).get(fid, {}).get('evidence_unit_ids') or []
            j['units'] = list(dict.fromkeys(list(j.get('units') or []) + list(seen)))
            changes[fid] = 'direction:' + kind
    return new, changes


def run_checkpoint(payload, rt, engine, invoke):
    fids = judged_fields(payload, rt)
    if not fids:
        result = engine.analyze(payload, {'control': {'action': 'continue', 'evidence_unit_ids': []}, 'fields': {}})
        return result, {'note': 'no judged fields'}
    message = user_message(payload, rt, fids)
    r = invoke('judge', rt.judge_prompt, message, rt.judge_params)
    output = r.get('output') if isinstance(r.get('output'), dict) else {}
    if not isinstance(output.get('targets'), dict):
        output = {**output, 'targets': {}}
    result, proposal, info = settle(payload, output, rt, engine, fids)
    verify_trace = None
    if result.get('decision') != 'invalid':
        cands = verify_candidates(payload, result, proposal, rt)
        if cands:
            text = {u['id']: u['text'] for u in payload['evidence_units']}
            cited = ''.join(text[i] for f in cands for i in proposal['fields'][f]['evidence_unit_ids'])
            if not DIRECTION_CUES.search(cited):
                cands = []
        if cands:
            vmsg = verify_message(payload, proposal, rt, cands)
            v = invoke('verify', rt.verify_prompt, vmsg, rt.verify_params)
            changes = {}
            if v.get('ok') and isinstance(v.get('output'), dict):
                output2, changes = apply_verify(output, v['output'].get('checks') or {}, rt, cands, proposal)
                if changes:
                    result2, proposal2, info2 = settle(payload, output2, rt, engine, fids)
                    if result2.get('decision') != 'invalid':
                        result, proposal, info = result2, proposal2, info2
            verify_trace = {'ok': v.get('ok'), 'candidates': cands, 'changes': changes}
    trace = {'verify': verify_trace, 'assembly_notes': info['notes'], 'attempts': info['attempts'],
             'stage_fallback': info['stage_fallback'], 'guard_probe': info.get('guard_probe')}
    return result, trace
