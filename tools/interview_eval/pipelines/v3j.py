"""v3j = v3h + third-relay changes (runtime docs/prototypes/full-interview-v3j; judge/verify prompts unchanged):
  - literal fields: a value_text absent from the narrator's words (incl. script variants) is not recorded; one
    found only outside the judge's own core sentence yields to the core sentence (V3_EXP=no_literal_rules to undo);
  - runtime engine: inexpressibility is not a concept definition; plain good/bad livelihood wording is living
    conditions (with interpersonal wording exempt); sibling-target separation guards by semantic_role
    (influential_relative, luck_view, narrator_change_effect, selected_identifiable_story).
See docs/prototypes/full-interview-v3/ITERATIONS.md R9-R10.

v3h: one judge call per checkpoint + deterministic assembly (engine feedback loops) + a gated denial re-check.

Phase 1 judge (deepseek-v4-pro, thinking disabled, static system prompt judge-prompt.txt): per target
best/about/kind/concept/match/units/core/subject (+link_word/precision/value_text). Code derives the state and
assembles the engine proposal, then uses only the frozen engine's feedback (no extra model call):
  - subject: contract's first subject when it is the narrator, else the judge's allowed pick; retry others on
    engine subject errors; drop a field on other protocol errors;
  - stage-bound fields: value = core∪units span, narrowed to core when the engine cannot ground the stage or
    rejects it; 'now' fields whose selected sentence sits in a future/past frame retry with the nearest cited
    current-framed sentence (kept only if the engine then accepts it);
  - core guard probe: every recorded known field is re-checked by the engine with value = evidence = the
    judge's core sentences; a field the engine's semantic guards reject in that form is not recorded;
  - link explanations keep the preceding sentence that states the chosen link word.
Phase 2 denial re-check (verify-prompt.txt, static): only when the sentences of recorded fields contain explicit
denial wording (没有/不希望/不想/没什么/不需要/无悔/不后悔); one short call with just those targets and sentences.
Only a 'negation' direction is applied (known -> none, evidence = the sentences the checker read); assembly re-runs.
V3_EXP=verify_full restores the full verify experiment (itself=no rejections, all directions, ungated).

Env (offline experiments only): V3_EXP=comma flags (noverify, verify_full, added_rejects, no_link_span,
no_subject_rule, no_now_fallback, no_stage_wide, no_guard_probe, old_child_note, no_literal_rules);
V3_JUDGE_PROMPT / V3_VERIFY_PROMPT = paths to replay other prompt versions.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

NAME = 'v3j'
RUNTIME = common.ROOT / 'docs/prototypes/full-interview-v3j'
PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 1500, 'temperature': 0, 'json_mode': True}
VERIFY_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'max_tokens': 900, 'temperature': 0, 'json_mode': True}
import os
EXP = set(filter(None, os.environ.get('V3_EXP', '').split(',')))  # offline assembly experiments
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
CHAR_MAP = json.loads((RUNTIME / 'opencc-ts-char-map.json').read_text(encoding='utf-8'))


def script_view(t):
    """Traditional->simplified single-character view, as the engine uses for literal matching (never stored)."""
    return ''.join(CHAR_MAP.get(c, c) for c in str(t))


def link_pieces(value):
    """Same candidate pieces the engine accepts as link targets."""
    out = []
    for v in ([value] if isinstance(value, str) else [x for x in (value or []) if isinstance(x, str)]):
        out.append(v)
        out += [t.strip() for t in re.split(r'[、，,；;]|(?:和|与|及)', v) if t.strip()]
        out += re.findall(r'[“「『‘"]([^”」』’"\n]+)[”」』’"]', v)
    return list(dict.fromkeys(out))


class CallFailed(RuntimeError):
    pass


class Ctx:
    pass


def setup():
    ctx = Ctx()
    ctx.engine = common.Engine(RUNTIME)
    ctx.prompt = Path(os.environ.get('V3_JUDGE_PROMPT') or RUNTIME / 'judge-prompt.txt').read_text(encoding='utf-8')
    ctx.verify_prompt = Path(os.environ.get('V3_VERIFY_PROMPT') or RUNTIME / 'verify-prompt.txt').read_text(encoding='utf-8')
    contracts = json.loads((RUNTIME / 'contracts.json').read_text(encoding='utf-8'))
    ctx.F = {f['id']: f for q in contracts['questions'] for f in q['elements']}
    return ctx


def is_clarification(f):
    act = f.get('activation') or {}
    return any(k.startswith('if_') or k == 'reported_without_self' for k in act)


def judged_fields(payload, ctx):
    return [fid for fid in payload['field_contract']
            if ctx.F[fid]['requirement'] != 'optional' and not is_clarification(ctx.F[fid])]


def parents_of(f):
    act = f.get('activation') or {}
    return act.get('known') or act.get('after_answer') or []


def target_block(fid, ctx):
    f = ctx.F[fid]
    lines = [f'- id: {fid}', f'  名称: {f["label"]}', f'  问法: {f["question"]}', f'  算作回答: {f["usable_answer"]}',
             f'  subjects: {", ".join(f["scope"]["subjects"])}']
    notes = []
    act = f.get('activation') or {}
    if act.get('premise_check'):
        notes.append('这是本题的适用前提。只判断受访者是否明确表示自己没有过这类经历（如没上过学、没结过婚、没有子女）→ none；'
                     '只要讲到了本人的这类经历，或根本没提，一律 not_answered')
    parents = parents_of(f)
    if parents:
        notes.append(('这是「%s」的后续补充：只在父项已回答时判定，且必须针对父项说的同一个对象、同一件事'
                      + ('' if 'old_child_note' in EXP else '（可以是同一句话）'))  # old wording only to replay v3d/v3f caches
                     % '、'.join(ctx.F[p]['label'] for p in parents))
    if f.get('link'):
        notes.append('answered 时填写 link_word：父项「%s」答案中被本项解释的那个原词' % ctx.F[f['link']['field_id']]['label'])
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


def user_message(payload, ctx, fids):
    units = payload['evidence_units']
    out = [f'main_question: {payload["main_question"]}']
    for n, source in enumerate(payload['sources'], 1):
        out.append(f'第{n}段 原问：{source.get("question") or "（无，受访者自述）"}')
        out += [f'{u["id"]} {u["text"]}' for u in units if u['source_id'] == source['id']]
    out.append('targets:')
    out += [target_block(fid, ctx) for fid in fids]
    return '\n'.join(out)


def DRY_RESPONSE(call):
    return json.dumps({'control': {'action': 'continue', 'units': []}, 'targets': {}})


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


def first_work_cause_span(raw, word):
    """V6 (backend contract_interview_v3j.first_work_cause_span, line for line): the literal cause of one explicit
    causal sentence that is both the first-work answer and its explanation; None when not that exact shape."""
    original = raw.strip()
    view, selected = script_view(original), script_view(word)
    if not selected:
        return None
    time = r'(?:当时|那时|那时候|最初|起初|最早)'
    prefix = time + r'?(?:我|本人)?' + time + '?'
    action = r'(?:(?:去|做|干|到|进|在|当|从事|开始)(?:了)?)'
    own_work_prefix = prefix + r'(?:就|才|只好)?' + action
    patterns = (
        prefix + r'(?:因为|由于|因)(?P<cause>[^，,。！？；;\n]+?)(?:[，,](?:所以)?|所以|才|只好)(?P<work>[^。！？；;\n]+)[。！]?$',
        r'(?P<work>[^，,。！？；;\n]+?)(?:[，,](?:是)?|是)(?:因为|由于)(?P<cause>[^，,。！？；;\n]+)[。！]?$',
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, view)
        if not match:
            continue
        work, cause = match.group('work').strip(), match.group('cause').strip()
        if selected not in work or not cause or selected in cause:
            continue
        if re.search(r'^(?:不是|并非)|什么|不清楚|不记得|不知道|记不清', cause):
            continue
        before_work = work[:work.index(selected)]
        if not re.match(own_work_prefix, work) or not re.fullmatch(
                prefix + r'(?:就|才|只好)?' + action + r'{0,2}', before_work):
            continue
        return original[match.start('cause'):match.end('cause')].strip()
    return None


def assemble(payload, output, ctx, fids, subject_choice, value_override=None, wide=()):
    units = payload['evidence_units']
    index = {u['id']: i for i, u in enumerate(units)}
    text = {u['id']: u['text'] for u in units}
    targets = (output or {}).get('targets') or {}
    fields, notes = {}, {}
    for fid in fids:
        f = ctx.F[fid]
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
            if isinstance(literal, str) and literal.strip() and 'no_literal_rules' not in EXP:
                if not holder and not any(script_view(literal.strip()) in script_view(u['text']) for u in units):
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
                if f.get('link') and 'no_link_span' not in EXP:
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
                if 'next_neighbor' in EXP:
                    k = index[value_ids[-1]]
                    if k + 1 < len(units) and units[k + 1]['source_id'] == units[k]['source_id']:
                        ids = sorted(set(ids) | {units[k + 1]['id']}, key=index.get)
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
        act = ctx.F[fid].get('activation') or {}
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
        link = ctx.F[fid].get('link')
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
        # V6 listening bundle (speaker-config literal_cause_span, backend assemble): when WK01-E2 and its parent share
        # one explicit causal sentence, the explanation's value is that sentence's literal cause. Off by default.
        child = fields[fid]
        child_units = child.get('value_unit_ids') or []
        if getattr(ctx, 'literal_cause_span', False) and fid == 'WK01-E2' and parent \
                and child_units == parent.get('value_unit_ids') and len(child_units) == 1 \
                and all((targets.get(key) or {}).get('subject') == 'self' for key in (fid, link['field_id'])):
            cause = first_work_cause_span(text[child_units[0]], word)
            if cause is not None:
                child.pop('value_unit_ids')
                child['value'] = cause
                notes[fid] = 'explicit_first_work_cause_literal_subspan'
    c = (output or {}).get('control') or {}
    action = c.get('action') if c.get('action') in CONTROL else 'continue'
    cids = [i for i in (c.get('units') or []) if i in index] if action != 'continue' else []
    if action != 'continue' and not cids:
        action = 'continue'
    return {'control': {'action': action, 'evidence_unit_ids': cids}, 'fields': fields}, notes


SUBJECT_ERRORS = ('subject', 'wrong_subject')


def current_stage_fallback(payload, output, ctx, fids, dropped, subject_choice, proposal, result, attempts, wide=()):
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
        if (ctx.F[fid].get('scope') or {}).get('stage_binding_required') != 'now':
            continue
        first = index[prop['value_unit_ids'][0]]
        src = units[first]['source_id']
        cands = [i for i in prop['evidence_unit_ids'] if i not in prop['value_unit_ids'] and units[index[i]]['source_id'] == src
                 and STAGE_ANCHORS['now'].search(units[index[i]]['text'])]
        if cands:
            override[fid] = [min(cands, key=lambda i: abs(index[i] - first))]
    if not override:
        return result, {}
    prop2, _ = assemble(payload, output, ctx, [f for f in fids if f not in dropped], subject_choice, override, wide=wide)
    res2 = ctx.engine.op('analyze', payload=payload, proposal=prop2, raw=None)
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


def settle(payload, output, ctx, fids):
    """Code-only assembly loop: subject retries / drops on engine protocol errors, then the current-stage fallback."""
    targets = output.get('targets') or {}
    subject_choice, tried, attempts = {}, {}, []
    for fid in fids:
        j = targets.get(fid) or {}
        allowed = ctx.F[fid]['scope']['subjects']
        # the narrator is the default subject; when the contract's primary subject is someone else
        # (parents, family, teacher ...) the judge's pick among the allowed roles is used
        first = j.get('subject') if (allowed[0] != 'self' and 'no_subject_rule' not in EXP and j.get('subject') in allowed) else allowed[0]
        subject_choice[fid] = first
        tried[fid] = [first] + [s for s in [j.get('subject')] + allowed if s in allowed and s != first]
    dropped = set()
    wide = set()
    if 'no_stage_wide' not in EXP:
        wide = {f for f in fids if (ctx.F[f].get('scope') or {}).get('stage_binding_required')}
    probe_info = {}
    for attempt in range(12):
        proposal, notes = assemble(payload, output, ctx, [f for f in fids if f not in dropped], subject_choice, wide=wide)
        result = ctx.engine.op('analyze', payload=payload, proposal=proposal, raw=None)
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
            if 'no_guard_probe' not in EXP and not probe_info:
                rejected = core_guard_probe(payload, output, ctx, proposal, result)
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
    if 'no_now_fallback' not in EXP and result.get('decision') != 'invalid':
        result, fallback = current_stage_fallback(payload, output, ctx, fids, dropped, subject_choice, proposal, result, attempts, wide)
        if fallback.get('accepted'):
            proposal = attempts[-1]['proposal']
    return result, proposal, {'notes': notes, 'attempts': attempts, 'stage_fallback': fallback, 'guard_probe': probe_info}


def core_guard_probe(payload, output, ctx, proposal, result):
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
    res = ctx.engine.op('analyze', payload=payload, proposal=probe, raw=None)
    return {r.get('field_id') for r in res.get('semantic_rejections') or []} & probed



def verify_candidates(payload, result, proposal, ctx):
    """Judge-proposed targets that the engine actually records with a non-missing state."""
    out = []
    for fid, prop in (proposal.get('fields') or {}).items():
        got = (result.get('fields') or {}).get(fid) or {}
        if got.get('state') not in STATE_KIND or not prop.get('evidence_unit_ids'):
            continue
        if (ctx.F[fid].get('activation') or {}).get('premise_check'):
            continue
        out.append(fid)
    return out


def verify_message(payload, proposal, ctx, fids):
    """Only the sentences that will be recorded as the claim's evidence, with their actual questions."""
    units = payload['evidence_units']
    order = {u['id']: k for k, u in enumerate(units)}
    question = {s['id']: s.get('question') for s in payload['sources']}
    lines = [f'main_question: {payload["main_question"]}']
    for fid in fids:
        f = ctx.F[fid]
        lines += [f'目标 {fid}', f'  名称: {f["label"]}', f'  问法: {f["question"]}', f'  算作回答: {f["usable_answer"]}',
                  f'  可选主体: {", ".join(f["scope"]["subjects"])}']
        notes = []
        parents = parents_of(f)
        if parents:
            notes.append('这是「%s」的后续：须针对父项所说的同一对象或同一件事（可以是同一句话）' % '、'.join(ctx.F[p]['label'] for p in parents))
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
    else:  # older verdict-style judge output (replays)
        j['verdict'] = KIND_TO_VERDICT[kind]


def apply_verify(output, checks, ctx, fids, proposal):
    new = json.loads(json.dumps(output, ensure_ascii=False))
    changes = {}
    for fid in fids:
        c = checks.get(fid)
        if not isinstance(c, dict):
            continue
        j = new['targets'][fid]
        added = c.get('added') if isinstance(c.get('added'), str) else ''
        if 'verify_full' in EXP and (c.get('itself') == 'no' or ('added_rejects' in EXP and added.strip() not in ('', '无', '没有', '没说'))):
            set_kind(j, 'absent')
            changes[fid] = 'rejected'
            continue
        kind = DIRECTION_KIND.get(c.get('direction'))
        if 'verify_full' not in EXP and kind != 'negation':
            kind = None
        current = {'answered': 'content', 'none': 'negation', 'unspecified': 'affirmed_unspecified'}.get(verdict_of(j))
        if kind and current and kind != current and VERDICT_STATE[KIND_VERDICT[kind]] in ctx.F[fid].get('allowed_states', []):
            set_kind(j, kind)
            # the new state rests on the sentences the verifier actually read (e.g. a denial just before the value)
            seen = (proposal.get('fields') or {}).get(fid, {}).get('evidence_unit_ids') or []
            j['units'] = list(dict.fromkeys(list(j.get('units') or []) + list(seen)))
            changes[fid] = 'direction:' + kind
    return new, changes


def run_checkpoint(payload, ctx):
    fids = judged_fields(payload, ctx)
    tag = 't%d' % len(payload['sources'])
    if not fids:
        result = ctx.engine.op('analyze', payload=payload, proposal={'control': {'action': 'continue', 'evidence_unit_ids': []}, 'fields': {}}, raw=None)
        return result, {'note': 'no judged fields'}
    message = user_message(payload, ctx, fids)
    [r] = yield [{'id': tag + '-judge', 'system': ctx.prompt, 'user': message, 'params': PARAMS}]
    if not r.get('ok'):
        raise CallFailed(json.dumps({k: r.get(k) for k in ('error', 'http_status', 'error_detail')}, ensure_ascii=False))
    output = r.get('output') if isinstance(r.get('output'), dict) else {}
    if not isinstance(output.get('targets'), dict):
        output = {**output, 'targets': {}}
    result, proposal, info = settle(payload, output, ctx, fids)
    verify_trace = None
    if 'noverify' not in EXP and result.get('decision') != 'invalid':
        cands = verify_candidates(payload, result, proposal, ctx)
        if cands and 'verify_full' not in EXP:
            text = {u['id']: u['text'] for u in payload['evidence_units']}
            cited = ''.join(text[i] for f in cands for i in proposal['fields'][f]['evidence_unit_ids'])
            if not DIRECTION_CUES.search(cited):
                cands = []
        if cands:
            vmsg = verify_message(payload, proposal, ctx, cands)
            [v] = yield [{'id': tag + '-verify', 'system': ctx.verify_prompt, 'user': vmsg, 'params': VERIFY_PARAMS}]
            changes = {}
            if v.get('ok') and isinstance(v.get('output'), dict):
                output2, changes = apply_verify(output, v['output'].get('checks') or {}, ctx, cands, proposal)
                if changes:
                    result2, proposal2, info2 = settle(payload, output2, ctx, fids)
                    if result2.get('decision') != 'invalid':
                        result, proposal, info = result2, proposal2, info2
            verify_trace = {'user_message': vmsg, 'ok': v.get('ok'), 'error': v.get('error'), 'content': v.get('content'),
                            'usage': v.get('usage'), 'cached': v.get('cached'), 'changes': changes}
    trace = {'judge': {k: r.get(k) for k in ('content', 'usage', 'finish_reason', 'cached')}, 'user_message': message,
             'verify': verify_trace, 'assembly_notes': info['notes'], 'attempts': info['attempts'],
             'stage_fallback': info['stage_fallback'], 'guard_probe': info.get('guard_probe')}
    return result, trace
