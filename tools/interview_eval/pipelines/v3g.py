"""v3g: v3 judge (one focused call per checkpoint) + short verify call for accepted targets + code assembly.

Phase 1 (judge, same as v3_judge): per target best/about/kind/concept/units/core/subject (+link_word/precision/value_text).
Phase 2 (verify, new): only for targets the judge would record (content/negation/affirmed_unspecified with
concept=same), one call per checkpoint whose user message holds just those targets' standards and the
sentences the judge cited. Output per target: says / direction / itself. Code: itself=no -> missing;
direction overrides the judge's kind (content / negation / unspecified) when the resulting state is allowed.
The verify system prompt is static (prefix cache). Assembly, engine validation and follow-up as v3_judge.

Env (offline experiments only): V3_EXP=comma flags; V3_JUDGE_PROMPT=path to replay another judge prompt.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

NAME = 'v3g'
RUNTIME = common.ROOT / 'docs/prototypes/full-interview-v3'
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
    ctx.verify_prompt = (RUNTIME / 'verify-prompt.txt').read_text(encoding='utf-8')
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
        notes.append('这是「%s」的后续补充：只在父项已回答时判定，且必须针对父项说的同一个对象、同一件事'
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


def assemble(payload, output, ctx, fids, subject_choice):
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
            if holder:
                prop['value'] = literal
                ids = sorted(set(ids) | {holder[0]}, key=index.get)
            else:
                # value spans every cited sentence (gold phrases often sit beside the core), except for
                # stage-bound fields where unrelated clauses would break the engine's stage proof
                staged_field = bool((f.get('scope') or {}).get('stage_binding_required'))
                value_ids = contiguous_value((core or ids) if staged_field else (core + ids), units)
                if not value_ids:
                    continue
                if f.get('link') and 'link_span' in EXP:
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
    c = (output or {}).get('control') or {}
    action = c.get('action') if c.get('action') in CONTROL else 'continue'
    cids = [i for i in (c.get('units') or []) if i in index] if action != 'continue' else []
    if action != 'continue' and not cids:
        action = 'continue'
    return {'control': {'action': action, 'evidence_unit_ids': cids}, 'fields': fields}, notes


SUBJECT_ERRORS = ('subject', 'wrong_subject')

# --------------------------------------------------------------------------- verify phase
DIRECTION_KIND = {'content': 'content', 'negation': 'negation', 'unspecified': 'affirmed_unspecified'}
KIND_TO_VERDICT = {'absent': 'not_answered', **{k: v for k, v in KIND_VERDICT.items()}}


def cited_ids(j, order):
    return sorted({i for i in (j.get('units') or []) + (j.get('core') or []) if i in order}, key=order.get)


def verify_candidates(payload, output, ctx, fids):
    """Targets the judge would record with a non-missing state (the only ones a verify can correct)."""
    order = {u['id']: k for k, u in enumerate(payload['evidence_units'])}
    targets = output.get('targets') or {}
    out = []
    for fid in fids:
        j = targets.get(fid)
        if not isinstance(j, dict) or verdict_of(j) not in ('answered', 'none', 'unspecified'):
            continue
        f = ctx.F[fid]
        if VERDICT_STATE[verdict_of(j)] not in f.get('allowed_states', []) or (f.get('activation') or {}).get('premise_check'):
            continue
        if cited_ids(j, order):
            out.append(fid)
    return out


def verify_message(payload, output, ctx, fids):
    units = payload['evidence_units']
    order = {u['id']: k for k, u in enumerate(units)}
    question = {s['id']: s.get('question') for s in payload['sources']}
    lines = [f'main_question: {payload["main_question"]}']
    for fid in fids:
        f, j = ctx.F[fid], output['targets'][fid]
        lines += [f'目标 {fid}', f'  名称: {f["label"]}', f'  问法: {f["question"]}', f'  算作回答: {f["usable_answer"]}',
                  f'  可选主体: {", ".join(f["scope"]["subjects"])}']
        notes = []
        parents = parents_of(f)
        if parents:
            notes.append('针对「%s」所说的同一对象或同一件事' % '、'.join(ctx.F[p]['label'] for p in parents))
        if f.get('notes'):
            notes.append(f['notes'])
        if notes:
            lines.append('  说明: ' + '；'.join(notes))
        current = None
        for i in cited_ids(j, order):
            u = units[order[i]]
            if u['source_id'] != current:
                current = u['source_id']
                lines.append(f'  原问: {question.get(current) or "（无，受访者自述）"}')
            lines.append(f'  {i} {u["text"]}')
    return '\n'.join(lines)


def set_kind(j, kind):
    if 'kind' in j:
        j['kind'] = kind
        if kind != 'absent':
            j['concept'] = 'same'
    else:  # older verdict-style judge output (replays)
        j['verdict'] = KIND_TO_VERDICT[kind]


def apply_verify(output, checks, ctx, fids):
    new = json.loads(json.dumps(output, ensure_ascii=False))
    changes = {}
    for fid in fids:
        c = checks.get(fid)
        if not isinstance(c, dict):
            continue
        j = new['targets'][fid]
        if c.get('itself') == 'no':
            set_kind(j, 'absent')
            changes[fid] = 'rejected'
            continue
        kind = DIRECTION_KIND.get(c.get('direction'))
        current = {'answered': 'content', 'none': 'negation', 'unspecified': 'affirmed_unspecified'}[verdict_of(j)]
        if kind and kind != current and VERDICT_STATE[KIND_VERDICT[kind]] in ctx.F[fid].get('allowed_states', []):
            set_kind(j, kind)
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
    verify_trace = None
    if 'noverify' not in EXP and isinstance(output.get('targets'), dict):
        cands = verify_candidates(payload, output, ctx, fids)
        if cands:
            vmsg = verify_message(payload, output, ctx, cands)
            [v] = yield [{'id': tag + '-verify', 'system': ctx.verify_prompt, 'user': vmsg, 'params': VERIFY_PARAMS}]
            changes = {}
            if v.get('ok') and isinstance(v.get('output'), dict):
                output, changes = apply_verify(output, v['output'].get('checks') or {}, ctx, cands)
            verify_trace = {'user_message': vmsg, 'ok': v.get('ok'), 'error': v.get('error'), 'content': v.get('content'),
                            'usage': v.get('usage'), 'cached': v.get('cached'), 'changes': changes}
    targets = output.get('targets') or {}
    subject_choice, tried, attempts = {}, {}, []
    for fid in fids:
        j = targets.get(fid) or {}
        allowed = ctx.F[fid]['scope']['subjects']
        first = j.get('subject') if ('model_subject' in EXP and j.get('subject') in allowed) else allowed[0]
        subject_choice[fid] = first
        tried[fid] = [first] + [s for s in [j.get('subject')] + allowed if s in allowed and s != first]
    dropped = set()
    for attempt in range(8):
        proposal, notes = assemble(payload, output, ctx, [f for f in fids if f not in dropped], subject_choice)
        result = ctx.engine.op('analyze', payload=payload, proposal=proposal, raw=None)
        attempts.append({'proposal': proposal, 'decision': result.get('decision'), 'errors': result.get('errors'),
                         'semantic_rejections': result.get('semantic_rejections')})
        if result.get('decision') != 'invalid':
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
            else:
                dropped.add(fid)
    trace = {'judge': {k: r.get(k) for k in ('content', 'usage', 'finish_reason', 'cached')}, 'user_message': message,
             'verify': verify_trace, 'assembly_notes': notes, 'attempts': attempts}
    return result, trace
