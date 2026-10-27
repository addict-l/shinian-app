#!/usr/bin/env python3
"""Build memoir handoff inputs (docs/prototypes/memoir-v1/handoff.schema.json) for test people.

(a) rich: public interview excerpts of the 45 development people (.runtime testset excerpts.jsonl).
    The test set carries no question IDs (question_ids is empty everywhere), so one DeepSeek call per
    person routes every excerpt to the single best-fitting question of the frozen 83-question bank
    (prompts/classify.txt). Gold annotations are never read.
(b) thin: what the simulated elder actually said in the simulated interview runs (sim-*/st5-*/st6-*):
    real runs only (no off-* replays, dry or smoke runs); per question the newest interview version
    (st6 > st5 > sim-h*), with the run's final field states.

Confirmed drafts: the App shows each question's grounded draft (GROUNDED_DRAFT_PROMPT, organise only)
for the elder to confirm before saving. The test material has none, so the drafts are produced here by
the production prompt (one call per question) and treated as confirmed.

  python3 tools/memoir_eval/inputs.py --people N-6733a23cd1,... [--thin N-25486466f6] --run mb1-inputs [--offline]
(c) full84 (v1.1): one complete simulated interview in the production V6 flow (simulate/run_full.py): every
    question's sources as production keeps them (judged answers incl. supplement additions, answers to detail
    questions), the question part each answered, final field states and the close (saved / skipped).
  python3 tools/memoir_eval/inputs.py --full mb2-full84:N-6733a23cd1 --run mb2-inputs --prefix mb2
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

import mb

EXCLUDE_POLICIES = ('do_not_use_entire_excerpt_without_manual_clipping', 'exclude_from_self_evidence_for_catalog_narrator')
DRAFT_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'temperature': 0.0, 'json_mode': True,
                'max_tokens': 4000, 'timeout': 240}
CLASSIFY_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'temperature': 0.0, 'json_mode': True,
                   'max_tokens': 4000, 'timeout': 240}
DRAFT_FORMAT = ('\n输出 JSON：{"title": {"text": "标题", "source_indices": [1]}, '
                '"paragraphs": [{"text": "一段正文", "source_indices": [1, 2]}]}。')
# The App's guided-interview addition to the draft prompt (llm_client.compose_story), profile omitted.
DRAFT_GUIDED = ('\n当前模块见输入 module。仅整理当前已接受原话。寄语、回望、原话和前后对照按原类型保留，'
                '不扩写成发生过的事件，不补当年想法或人生结论；明确大意的他人话不能加引号。'
                '标题和正文都不能把“有一次”或“刚开始接活”改写成“第一次”，也不把通常做的事情变成某天发生。')


def excluded_ids():
    warn = mb.load(mb.TESTSET / 'provenance-warning.json')['warnings']
    ids, sources = set(), set()
    for w in warn:
        if w.get('policy') in EXCLUDE_POLICIES:
            ids |= set(w.get('source_excerpt_ids') or [])
            sources |= set(w.get('source_ids') or [])
    return ids, sources


def rich_turns(pid):
    bad_ids, bad_sources = excluded_ids()
    rows = [json.loads(line) for line in (mb.TESTSET / 'excerpts.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    rows = [r for r in rows if r['narrator_id'] == pid]
    if not rows:
        raise SystemExit('no excerpts for ' + pid)
    name = mb.clean(rows[0]['speaker'])
    kept, dropped = [], []
    for r in rows:
        if r['id'] in bad_ids or r['source_id'] in bad_sources or r.get('speaker_role') != 'interviewee':
            dropped.append(r['id'])
            continue
        kept.append(r)
    # Interview order: source order as listed, then position in the source body.
    order = {s: i for i, s in enumerate(dict.fromkeys(r['source_id'] for r in kept))}
    kept.sort(key=lambda r: (order[r['source_id']], r.get('body_char_start') or 0))
    turns = []
    for i, r in enumerate(kept, 1):
        turns.append({'source_id': 'U%02d' % i, 'origin_id': r['id'], 'asked': mb.clean(r.get('interviewer_question') or ''),
                      'text': mb.clean(r['text'])})
    return name, turns, dropped


def classify_call(pid, turns, cat):
    lines = ['%s｜%s｜%s｜%s' % (q['id'], mb.MODULE_NAME[q['module']], q['title'], q['main_question']) for q in cat.values()]
    user = {'catalog': lines, 'excerpts': [{'id': t['source_id'], '原问': t['asked'] or '（无）', 'text': t['text']} for t in turns]}
    return {'id': 'cls-' + pid, 'system': mb.prompt('classify.txt'), 'user': json.dumps(user, ensure_ascii=False), 'params': CLASSIFY_PARAMS}


def thin_episodes(pid):
    """Per question: the newest real simulated interview episode of this person."""
    rank = lambda run: 3 if run.startswith('st6') else 2 if run.startswith('st5') else 1
    best = {}
    for f in sorted(glob.glob(str(mb.RUNS / ('*/sessions/*%s.json' % pid)))):
        run = Path(f).parts[-3]
        if run.startswith('off') or 'dry' in run or 'smoke' in run or not re.match(r'(sim-|st5-|st6-)', run):
            continue
        s = mb.load(f)
        for e in s['episodes']:
            key = (rank(run), run)
            if e['qid'] not in best or key > best[e['qid']][0]:
                best[e['qid']] = (key, run, s['name'], e)
    return best


def thin_question(qid, run, ep, cat, counter):
    turns, asked = [], ''
    for m in ep['messages']:
        if m['role'] == 'system':
            asked = m.get('entry_part') or m.get('question_part') or m['text']
            if m.get('kind') == 'entry':
                asked = m['text']
            continue
        if m['role'] != 'elder':
            continue
        counter[0] += 1
        turns.append({'source_id': 'U%02d' % counter[0], 'origin_id': '%s:%s:%d' % (run, qid, m.get('k', 0)),
                      'asked': mb.clean(asked), 'text': mb.clean(m['text'])})
        # what the interviewer asked next is the system message following this answer
    fields = {}
    for fid, f in ((ep.get('final') or {}).get('fields') or {}).items():
        fields[fid] = {'state': f.get('state'), 'value': f.get('value')}
    close = ep.get('close_reason')
    status = {'done': 'saved', 'declined': 'skipped', 'deferred': 'skipped'}.get(close, 'saved')
    q = cat[qid]
    return {'question_id': qid, 'module': q['module'], 'depth': q['depth'], 'main_question': q['main_question'],
            'title': q['title'], 'status': status, 'close_reason': close, 'turns': turns, 'fields': fields,
            'origin': {'run': run}}


def full_questions(run, pid, cat):
    """Questions of a run_full.py session (V6 flow) in interview order."""
    sess = mb.load(mb.RUNS / run / 'sessions' / ('%s.json' % pid))
    qs, n = [], 0
    for rec in sess['questions']:
        if rec.get('error'):
            continue
        q = cat[rec['qid']]
        turns = []
        for src in rec['sources']:
            n += 1
            turns.append({'source_id': 'U%03d' % n, 'origin_id': '%s:%s:%s' % (run, rec['qid'], src['id']),
                          'asked': mb.clean(src.get('question') or q['main_question']), 'text': mb.clean(src['text']),
                          **({'deepen': src.get('dimension') or True} if src.get('deepen_answer') else {})})
        status = 'skipped' if rec['status'] == 'skipped' else 'saved' if turns else 'skipped'
        fields = {fid: {'state': f.get('state'), 'value': f.get('value')} for fid, f in ((rec.get('final') or {}).get('fields') or {}).items()}
        qs.append({'question_id': rec['qid'], 'module': q['module'], 'depth': q['depth'], 'main_question': q['main_question'],
                   'title': q['title'], 'status': status, 'close_reason': rec.get('close_reason'), 'turns': turns, 'fields': fields,
                   'origin': {'run': run, 'flow': 'v6', 'followups': rec.get('followups'), 'deepen_answers': rec.get('deepen_sources')}})
    return mb.clean(sess['name']), qs


def markers(question):
    """Unknown / declined markers: field states first, then the elder's own wording (code regex)."""
    unknown, declined = [], []
    for fid, f in (question.get('fields') or {}).items():
        if f.get('state') == 'unknown':
            unknown.append({'field_id': fid, 'quote': f.get('value')})
        if f.get('state') in ('declined', 'deferred'):
            declined.append({'field_id': fid, 'quote': f.get('value')})
    for t in question['turns']:
        for s in mb.sentences(t['text']):
            if mb.UNKNOWN.search(s):
                unknown.append({'source_id': t['source_id'], 'quote': s})
            if mb.DECLINE.search(s):
                declined.append({'source_id': t['source_id'], 'quote': s})
    return {'unknown': unknown, 'declined': declined}


def draft_call(pid, question, name):
    excerpts = [{'index': i, 'id': t['source_id'], 'dimension': 'narrative', 'content': t['text']}
                for i, t in enumerate(question['turns'], 1)]
    # One system prompt for every draft call (the relay warms its prefix cache per distinct system prompt);
    # the App puts the module name into the system text, here it travels in the input.
    system = mb.grounded_draft_prompt() + DRAFT_GUIDED + DRAFT_FORMAT
    user = {'record_subject': {'name': name, 'relationship': '本人'}, 'module': mb.MODULE_NAME[question['module']],
            'accepted_user_excerpts': excerpts}
    return {'id': 'drf-%s-%s' % (pid, question['question_id']), 'system': system,
            'user': json.dumps(user, ensure_ascii=False), 'params': DRAFT_PARAMS}


def resolve_draft(question, row):
    out = (row or {}).get('output') if row and row.get('ok') else None
    n = len(question['turns'])
    ids = lambda idx: [question['turns'][i - 1]['source_id'] for i in idx if isinstance(i, int) and 1 <= i <= n]
    try:
        paras = [{'text': p['text'].strip(), 'source_ids': ids(p.get('source_indices') or [])} for p in out['paragraphs'] if p['text'].strip()]
        title = out['title']['text'].strip()
        if not paras:
            raise ValueError
        return {'title': title, 'paragraphs': paras, 'confirmed': True, 'generated_by': 'GROUNDED_DRAFT_PROMPT'}
    except (TypeError, KeyError, ValueError, AttributeError):
        # No usable draft: the elder's own words are the confirmed text (never invented).
        return {'title': question['title'], 'paragraphs': [{'text': t['text'], 'source_ids': [t['source_id']]} for t in question['turns']],
                'confirmed': True, 'generated_by': 'verbatim_fallback'}


def assemble(pid, name, kind, questions, cat, extra):
    for q in questions:
        q['markers'] = markers(q)
        q['time_clues'] = [{'source_id': t['source_id'], 'clues': mb.time_clues(t['text'])} for t in q['turns'] if mb.time_clues(t['text'])]
    order = {qid: i for i, qid in enumerate(cat)}
    questions.sort(key=lambda q: order[q['question_id']])
    texts = [t['text'] for q in questions for t in q['turns']]
    skeleton = [q for q in questions if q['module'] == 'skeleton']
    return {'schema': 'shinian.memoir-handoff/v1', 'person': {'id': pid, 'name': name, 'relationship': '本人'},
            'material': {'kind': kind, **extra, 'elder_chars': sum(mb.han_len(t) for t in texts),
                         'questions': len(questions), 'turns': len(texts)},
            'catalog': {'bank': 'docs/question-bank-freeze-v2.json (83 题)', 'depth': 'docs/prototypes/memoir-v1/question-depth.json'},
            'skeleton': {'question_ids': [q['question_id'] for q in skeleton]},
            'questions': [q for q in questions],
            'voice': mb.voice_profile(texts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--people', default='')
    ap.add_argument('--thin', default='')
    ap.add_argument('--run', default='mb1-inputs')
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--full', default='', help='RUN:PERSON[,…] complete simulated interviews (simulate/run_full.py)')
    ap.add_argument('--prefix', default='mb1')
    a = ap.parse_args()
    cat = mb.catalog()
    run_dir = mb.RUNS / a.run
    relay = mb.common.Relay(run_dir, offline=a.offline, wait_seconds=3600)
    people = [p for p in a.people.split(',') if p]
    thin = [p for p in a.thin.split(',') if p]
    rich = {pid: rich_turns(pid) for pid in people}
    cls = relay.run_batch(a.prefix + '-cls-%s' % mb.sha(','.join(people))[:8], [classify_call(pid, rich[pid][1], cat) for pid in people]) if people else {}
    built = {}
    for pid in people:
        name, turns, dropped = rich[pid]
        row = cls.get('cls-' + pid) or {}
        assign = ((row.get('output') or {}).get('assign') or {}) if row.get('ok') else {}
        bad = [t['source_id'] for t in turns if assign.get(t['source_id']) not in cat]
        if bad:
            print(json.dumps({'person': pid, 'unassigned': bad, 'error': row.get('error') or row.get('parse_error')}, ensure_ascii=False))
        groups = defaultdict(list)
        for t in turns:
            groups[assign.get(t['source_id']) or 'RV16'].append(t)  # unassigned -> 想补充留下的心里话 (logged)
        qs = []
        for qid, ts in groups.items():
            q = cat[qid]
            qs.append({'question_id': qid, 'module': q['module'], 'depth': q['depth'], 'main_question': q['main_question'],
                       'title': q['title'], 'status': 'saved', 'turns': ts, 'fields': {}})
        built[pid] = (name, 'rich', qs, {'source': 'testset excerpts.jsonl', 'dropped_by_provenance': dropped,
                                         'routing': 'DeepSeek classify (prompts/classify.txt)', 'unassigned': bad})
    for pid in thin:
        best = thin_episodes(pid)
        counter = [0]
        qs, runs, name = [], {}, pid
        for qid in sorted(best, key=lambda q: list(cat).index(q)):
            _, run, name, ep = best[qid]
            qs.append(thin_question(qid, run, ep, cat, counter))
            runs[qid] = run
        built[pid + ':thin'] = (mb.clean(name), 'thin', qs, {'source': 'simulated interview runs', 'runs': runs})
    for spec in [x for x in a.full.split(',') if x]:
        run, pid = spec.split(':')
        name, qs = full_questions(run, pid, cat)
        built[pid + ':full84'] = (name, 'full84', qs, {'source': 'complete simulated interview (V6 production flow)', 'run': run,
                                                      'drafts': 'GROUNDED_DRAFT_PROMPT per saved question, treated as confirmed; '
                                                                'skeleton questions have no draft step in production, '
                                                                'theirs are built only for the book layer fallback'})
    calls = []
    for key, (name, kind, qs, _) in built.items():
        for q in qs:
            if q['turns'] and q['status'] == 'saved':
                calls.append(draft_call(key.replace(':', '-'), q, name))
    drafts = relay.run_batch(a.prefix + '-drf-%s' % mb.sha(json.dumps([c['id'] for c in calls]))[:8], calls) if calls else {}
    for key, (name, kind, qs, extra) in built.items():
        for q in qs:
            if q['turns'] and q['status'] == 'saved':
                q['draft'] = resolve_draft(q, drafts.get('drf-%s-%s' % (key.replace(':', '-'), q['question_id'])))
        pid = key.split(':')[0]
        doc = assemble(pid, name, kind, qs, cat, extra)
        path = run_dir / ('%s-%s.json' % (pid, kind))
        mb.save(path, doc)
        print(json.dumps({'built': str(path), 'questions': len(qs), 'elder_chars': doc['material']['elder_chars'],
                          'drafts_fallback': sum(1 for q in qs if (q.get('draft') or {}).get('generated_by') == 'verbatim_fallback')}, ensure_ascii=False))
    mb.save(run_dir / 'usage.json', {'calls_sent': relay.calls_sent, 'calls_cached': relay.calls_cached, 'usage': relay.usage})


if __name__ == '__main__':
    main()
