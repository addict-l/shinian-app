#!/usr/bin/env python3
"""Book layer prototype: handoff inputs -> planned, written, fact-checked chapters -> book JSON/MD/HTML.

  python3 tools/memoir_eval/book.py --inputs <handoff.json>[,...] --run mb1-r1 \
      --variants v1-on=write-v1.txt:enabled,v1-off=write-v1.txt:disabled [--edition standard] [--offline]

Final configuration (round 3b / holdout; see docs/prototypes/memoir-v1/ITERATIONS.md):
  python3 tools/memoir_eval/book.py --inputs ... --run mb1-hold --premerge --plan-prompt plan-v3.txt --simplify \
      --check-thinking disabled --check-prompt check-v2.txt --fallback match --variants v3b-off=write-v3.txt:disabled
  (rounds 1-2 used the standard ratio 0.8: add --ratio 0.8 to rebuild them from the cache)

Stages (each stage of all people and variants is one relay job; every call is content-cached, so a rerun
with another writing prompt reuses plan calls, and an identical rerun costs nothing):
  plan   one call per book (prompts/plan.txt): sections (one story each, time order), reflection units moved
         to chapter ends, chapter titles quoted from the elder's words, motifs, private items.
         Code then validates (each unit exactly once, titles grounded), computes budgets and merges thin chapters.
  write  one call per chapter (prompts/write-*.txt); a chapter whose budget exceeds PART_CHARS is written in parts.
  check  code: numbers / place / person tokens of every sentence must occur in the sources;
         model: one call per chapter (prompts/check.txt) for facts not in the elder's words.
  fallback  a flagged added sentence is dropped; an unmarked feeling is relabelled as added (still shown for
         confirmation); any other flagged factual sentence sends its paragraph back to the confirmed grounded
         draft of the questions it cites; a failed chapter call sends the chapter back to the drafts.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict

import mb
import render

PLAN_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'enabled', 'json_mode': True, 'max_tokens': 32000, 'timeout': 900}
CHECK_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'enabled', 'json_mode': True, 'max_tokens': 32000, 'timeout': 900}
WRITE_BASE = {'model': 'deepseek-v4-pro', 'json_mode': True, 'temperature': 0.6}
PART_CHARS = 6000
ADD_TYPES = ('感受', '回望', '过渡', '意象', '呼应', '收束')
FACT_ISSUES = ('无来源事实', '张冠李戴', '确定化', '不愿讲', '加写含事实')


def write_params(thinking):
    p = dict(WRITE_BASE, thinking=thinking)
    p.update({'max_tokens': 32000, 'timeout': 900} if thinking == 'enabled' else {'max_tokens': 16000, 'timeout': 600})
    return p


# --------------------------------------------------------------------------- units
def units_of(handoff):
    """All source units of a book, with their question context, excluding declined sentences."""
    units = {}
    for q in handoff['questions']:
        declined = {d['quote'] for d in q['markers']['declined'] if d.get('source_id')}
        for t in q['turns']:
            text = t['text']
            for quote in declined:
                text = text.replace(quote, '')
            units[t['source_id']] = {'id': t['source_id'], 'qid': q['question_id'], 'module': q['module'], 'depth': q['depth'],
                                     'asked': t['asked'] or q['main_question'], 'text': text.strip(), 'raw': t['text'],
                                     'status': q['status'], 'clues': mb.time_clues(text)}
    return units


def module_groups(units):
    chars = Counter()
    for u in units.values():
        chars[u['module']] += mb.han_len(u['text'])
    return mb.premerge(chars)


def plan_call(key, handoff, units, prompt_name='plan.txt', groups=None):
    """groups=None: one chapter per module (v1, code merges thin chapters after planning); otherwise the
    chapters are pre-merged module groups and the planner orders sections by time across the whole group."""
    chapters = []
    for group in groups or [[m] for m, _, _ in mb.MODULES]:
        us = [u for u in units.values() if u['module'] in group and u['text']]
        if not us:
            continue
        us.sort(key=lambda u: group.index(u['module']))
        name = '序章（开篇）' if group[0] == 'skeleton' else ' · '.join(mb.MODULE_NAME[m] for m in group)
        entry = {'module': group[0], 'name': name,
                 'units': [{'id': u['id'], 'question': u['qid'], 'depth': u['depth'], 'asked': u['asked'],
                            'text': u['text'], 'time_clues': u['clues']} for u in us]}
        if groups:
            entry['modules'] = [mb.MODULE_NAME[m] for m in group]
            for x, u in zip(entry['units'], us):
                x['module'] = mb.MODULE_NAME[u['module']]
        chapters.append(entry)
    user = {'person': handoff['person']['name'], 'chapters': chapters}
    return {'id': 'plan-' + key, 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False), 'params': PLAN_PARAMS}


def module_id(value, group_of):
    """The planner sometimes echoes the chapter's display name ('开篇', '家庭生活 · 人生回望') instead of the module id."""
    if value in mb.MODULE_NAME:
        return value
    names = {n: m for m, n in mb.MODULE_NAME.items()}
    names.update({'序章': 'skeleton', '序章（开篇）': 'skeleton', '开篇': 'skeleton'})
    if isinstance(value, str):
        for part in re.split(r'\s*[·、/,，]\s*', value.strip()):
            if part in names:
                return names[part]
    return None


def resolve_plan(handoff, units, row, edition, groups=None):
    """Validate the planner's output and turn it into chapters with budgets; log every repair."""
    log = []
    head = {m: g[0] for g in (groups or [[m] for m, _, _ in mb.MODULES]) for m in g}
    group_of = {g[0]: list(g) for g in (groups or [[m] for m, _, _ in mb.MODULES])}
    out = (row or {}).get('output') if (row or {}).get('ok') else None
    if not isinstance(out, dict):
        log.append('plan_failed:' + str((row or {}).get('error') or (row or {}).get('parse_error')))
        out = {}
    seen, private, unused = set(), [], []
    for p in out.get('private') or []:
        if isinstance(p, dict) and p.get('unit') in units and p.get('quote') and p['quote'] in units[p['unit']]['text']:
            private.append(p)
    for p in out.get('unused') or []:
        if isinstance(p, dict) and p.get('unit') in units:
            unused.append(p)
            seen.add(p['unit'])
    chapters = {}
    for c in out.get('chapters') or []:
        mod = module_id(c.get('module') if isinstance(c, dict) else None, group_of)
        if mod is None:
            log.append('plan_bad_module:%s' % (c.get('module') if isinstance(c, dict) else c))
            continue
        mod = head[mod]
        ch = chapters.setdefault(mod, {'modules': group_of[mod], 'title': None, 'sections': [], 'closing_units': []})
        quote, src = c.get('title_quote') or '', c.get('title_source')
        if c.get('title') and quote and quote in (c.get('title') or '') and src in units and quote in units[src]['raw']:
            ch['title'], ch['title_quote'], ch['title_source'] = c['title'], quote, src
        elif c.get('title'):
            log.append('title_not_grounded:%s:%s' % (c['module'], c.get('title')))
        for s in c.get('sections') or []:
            ids = [u for u in (s.get('units') or []) if u in units and u not in seen]
            seen |= set(ids)
            if ids:
                ch['sections'].append({'title': s.get('title') or units[ids[0]]['asked'], 'units': ids})
        for u in c.get('closing_units') or []:
            if u in units and u not in seen:
                seen.add(u)
                ch['closing_units'].append(u)
    # repairs: units the planner left out go to their own module chapter, as one section per question
    missing = [u for u in units if u not in seen and units[u]['text']]
    if missing:
        log.append('units_not_planned:' + ','.join(missing))
    for uid in missing:
        u = units[uid]
        mod = head[u['module']]
        ch = chapters.setdefault(mod, {'modules': group_of[mod], 'title': None, 'sections': [], 'closing_units': []})
        sec = next((s for s in ch['sections'] if s.get('repair') == u['qid']), None)
        if sec is None:
            sec = {'title': mb.catalog()[u['qid']]['title'], 'units': [], 'repair': u['qid']}
            # keep module order inside a merged chapter: after the last section holding units of the same module
            same = [i for i, s in enumerate(ch['sections']) if any(units[x]['module'] == u['module'] for x in s['units'])]
            later = [i for i, s in enumerate(ch['sections'])
                     if s['units'] and units[s['units'][0]]['module'] in ch['modules']
                     and ch['modules'].index(units[s['units'][0]]['module']) > ch['modules'].index(u['module'])
                     ] if u['module'] in ch['modules'] else []
            pos = same[-1] + 1 if same else (later[0] if later else len(ch['sections']))
            ch['sections'].insert(pos, sec)
        sec['units'].append(uid)
    # drop private sentences from the writer's view
    for p in private:
        units[p['unit']]['text'] = units[p['unit']]['text'].replace(p['quote'], '').strip()
    order = [m for m, _, _ in mb.MODULES]
    book = [chapters[m] for m in order if m in chapters and (chapters[m]['sections'] or chapters[m]['closing_units'])]
    ratio, cap = mb.EDITIONS[edition]
    for ch in book:
        for s in ch['sections']:
            s['elder_chars'] = sum(mb.han_len(units[u]['text']) for u in s['units'])
        ch['elder_chars'] = sum(s['elder_chars'] for s in ch['sections']) + sum(mb.han_len(units[u]['text']) for u in ch['closing_units'])
        ch['budget'] = int(min(ch['elder_chars'] * ratio, sum(mb.SHARE[m] for m in ch['modules']) * cap))
    # Merge thin chapters (never the prologue): a chapter whose own material cannot fill ~1500 chars even at
    # the 1.0x upper bound merges into the smaller neighbour (the previous one on ties).
    while not groups:  # v1 only: with pre-merged groups (at most two modules a chapter) nothing merges after planning
        body = [c for c in book if c['modules'][0] != 'skeleton']
        thin = [c for c in body if c['elder_chars'] < mb.MERGE_BELOW]
        if not thin or len(body) < 2:
            break
        c = min(thin, key=lambda x: x['elder_chars'])
        i = body.index(c)
        nbrs = [x for x in (body[i - 1] if i > 0 else None, body[i + 1] if i + 1 < len(body) else None) if x]
        into = min(nbrs, key=lambda x: (x['elder_chars'], 0 if x is (body[i - 1] if i > 0 else None) else 1))
        first, second = (into, c) if book.index(into) < book.index(c) else (c, into)
        merged = {'modules': first['modules'] + second['modules'],
                  'title': (into if into['elder_chars'] >= c['elder_chars'] else c)['title'] or first['title'] or second['title'],
                  'sections': first['sections'] + second['sections'],
                  'closing_units': first['closing_units'] + second['closing_units'],
                  'elder_chars': first['elder_chars'] + second['elder_chars'], 'budget': first['budget'] + second['budget']}
        for k in ('title_quote', 'title_source'):
            src = into if into['elder_chars'] >= c['elder_chars'] else c
            if src.get(k):
                merged[k] = src[k]
        log.append('merged:%s+%s' % ('/'.join(first['modules']), '/'.join(second['modules'])))
        book[book.index(first)] = merged
        book.remove(second)
    for ch in book:
        if not ch['title']:
            ch['title'] = ' · '.join(mb.MODULE_NAME[m] for m in ch['modules'])
            log.append('title_fallback:' + '/'.join(ch['modules']))
        for s in ch['sections']:
            s['budget'] = int(s['elder_chars'] * ratio) if ch['budget'] else 0
    motifs = [m for m in out.get('motifs') or [] if isinstance(m, dict) and m.get('source') in units
              and m.get('quote') and m['quote'] in units[m['source']]['raw']]
    habits = [h for h in out.get('voice_habits') or [] if isinstance(h, str) and any(h in u['raw'] for u in units.values())]
    return {'chapters': book, 'motifs': motifs, 'private': private, 'unused': unused, 'voice_habits': habits[:8],
            'moves': out.get('moves') or [], 'log': log}


# --------------------------------------------------------------------------- write
def drafts_by_question(handoff):
    return {q['question_id']: q.get('draft') for q in handoff['questions']}


def chapter_parts(ch):
    if ch['budget'] <= PART_CHARS:
        return [list(range(len(ch['sections'])))]
    parts, cur, size = [], [], 0
    for i, s in enumerate(ch['sections']):
        if cur and size + s['budget'] > PART_CHARS:
            parts.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += s['budget']
    return parts + ([cur] if cur else [])


def write_calls(key, handoff, units, plan, prompt_name, thinking, ratio=0.8):
    calls = []
    drafts = drafts_by_question(handoff)
    titles = ['%s　%s（%s）' % ('序章' if c['modules'][0] == 'skeleton' else '第%d章' % i, c['title'], ' · '.join(mb.MODULE_NAME[m] for m in c['modules']))
              for i, c in enumerate(plan['chapters'], 0 if plan['chapters'][0]['modules'][0] == 'skeleton' else 1)]
    unknown = [{'unit': d.get('source_id'), 'quote': d['quote']} for q in handoff['questions'] for d in q['markers']['unknown'] if d.get('quote')]
    voice = {'称呼': list(handoff['voice']['kin_terms']), '口头语': plan['voice_habits']}
    system = mb.prompt(prompt_name)
    for ci, ch in enumerate(plan['chapters']):
        parts = chapter_parts(ch)
        for pi, idx in enumerate(parts):
            last = pi == len(parts) - 1
            secs = []
            for i in idx:
                s = ch['sections'][i]
                qids = list(dict.fromkeys(units[u]['qid'] for u in s['units']))
                secs.append({'title': s['title'], 'budget_chars': s['budget'],
                             'units': [{'id': u, 'asked': units[u]['asked'], 'text': units[u]['text']} for u in s['units'] if units[u]['text']],
                             'confirmed_drafts': [{'question': qid, 'title': (drafts.get(qid) or {}).get('title'),
                                                   'text': '\n'.join(p['text'] for p in (drafts.get(qid) or {}).get('paragraphs') or [])}
                                                  for qid in qids if drafts.get(qid)]})
            closing = [{'id': u, 'asked': units[u]['asked'], 'text': units[u]['text']} for u in ch['closing_units']] if last else []
            budget = sum(s['budget_chars'] for s in secs) + int(sum(mb.han_len(c['text']) for c in closing) * ratio)
            user = {'book': {'person': handoff['person']['name'], 'chapters': titles, 'motifs': plan['motifs']},
                    'chapter': {'index': titles[ci], 'modules': [mb.MODULE_NAME[m] for m in ch['modules']], 'title': ch['title'],
                                'budget_chars': budget, 'part': '%d/%d' % (pi + 1, len(parts)), 'is_last_part': last,
                                'sections': secs},
                    'closing_units': closing, 'voice': voice,
                    'unknown': [u for u in unknown if u['unit'] in {x for s in secs for x in (y['id'] for y in s['units'])}]}
            calls.append({'id': 'w-%s-c%d-p%d' % (key, ci, pi), 'system': system, 'user': json.dumps(user, ensure_ascii=False),
                          'params': write_params(thinking), 'meta': {'chapter': ci, 'part': pi, 'sections': idx}})
    return calls


def _merge_pairs(pairs):
    """JSON object hook: the writer sometimes repeats "paragraphs" inside one section (one key per paragraph);
    plain json.loads keeps only the last one and silently drops the rest of the section."""
    out = {}
    for k, v in pairs:
        if k in out and k == 'paragraphs' and isinstance(out[k], list) and isinstance(v, list):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out


def written_output(row):
    if not row.get('ok'):
        return None
    try:
        return json.loads(row.get('content') or '', object_pairs_hook=_merge_pairs)
    except ValueError:
        return row.get('output')


def parse_written(ch, units, rows, calls, log, simplify=False):
    """Chapter sections from the writer's parts; None for a part whose call failed or did not parse."""
    allowed = {u for s in ch['sections'] for u in s['units']} | set(ch['closing_units'])
    out = []
    for call in calls:
        row = rows.get(call['id']) or {}
        data = written_output(row)
        secs = []
        try:
            for s in data['sections']:
                paras = []
                for p in s['paragraphs']:
                    sents = []
                    for x in p:
                        t = (x.get('t') or '').strip()
                        if simplify:
                            t = mb.simplify(t)
                        if not t:
                            continue
                        src = [u for u in (x.get('src') or []) if u in allowed]
                        add = x.get('add') if x.get('add') in ADD_TYPES else None
                        if x.get('add') and add is None:
                            add = '感受'
                        sents.append({'t': t, 'src': src, 'add': add})
                    if sents:
                        paras.append({'sentences': sents})
                if paras:
                    secs.append({'title': s.get('title') or '', 'paragraphs': paras})
            if not secs:
                raise ValueError('empty')
            out.append({'call': call['id'], 'sections': secs, 'meta': call['meta']})
        except (TypeError, KeyError, ValueError, AttributeError) as exc:
            log.append('write_failed:%s:%s' % (call['id'], row.get('error') or row.get('parse_error') or type(exc).__name__))
            out.append({'call': call['id'], 'sections': None, 'meta': call['meta']})
    return out


def draft_paragraphs(qids, drafts, used, cited=None):
    """Confirmed draft paragraphs of these questions that cite the given units (all of them when cited is None)."""
    paras = []
    for qid in qids:
        d = drafts.get(qid)
        for k, p in enumerate((d or {}).get('paragraphs') or []):
            if (qid, k) in used or (cited is not None and not set(p['source_ids']) & set(cited)):
                continue
            used.add((qid, k))
            paras.append({'sentences': [{'t': s, 'src': p['source_ids'], 'add': None} for s in mb.sentences(p['text'])],
                          'fallback': True, 'from_questions': [qid]})
    return paras


# --------------------------------------------------------------------------- check
def check_calls(key, ci, ch, units, sections, handoff, thinking='enabled', prompt_name='check.txt'):
    sents = []
    for si, s in enumerate(sections):
        for pi, p in enumerate(s['paragraphs']):
            for k, x in enumerate(p['sentences']):
                x['sid'] = 'c%d.s%d.p%d.%d' % (ci, si, pi, k)
                sents.append({'sid': x['sid'], 't': x['t'], 'src': x['src'], 'add': x['add']})
    ids = [u for s in ch['sections'] for u in s['units']] + ch['closing_units']
    marks = [{'unit': d.get('source_id'), 'kind': kind, 'quote': d['quote']} for q in handoff['questions']
             for kind in ('unknown', 'declined') for d in q['markers'][kind] if d.get('source_id') in ids and d.get('quote')]
    user = {'sources': [{'id': u, 'asked': units[u]['asked'], 'text': units[u]['raw']} for u in ids],
            'markers': marks, 'sentences': sents}
    if prompt_name != 'check.txt':  # v2+: the rest of the book, so a cross-chapter echo is not reported as new
        user = {'sources': user['sources'], 'other_sources': [{'id': u, 'text': x['raw']} for u, x in units.items() if u not in ids and x['raw']],
                'markers': marks, 'sentences': sents}
    return {'id': 'k-%s-c%d' % (key, ci), 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False),
            'params': CHECK_PARAMS if thinking == 'enabled' else dict(CHECK_PARAMS, thinking='disabled', max_tokens=8000, timeout=600)}


def draft_matching(p, qids, drafts, used):
    """Fallback for one paragraph: for each of its sentences the most similar unused sentence of the confirmed drafts
    of the cited questions (similarity >= 0.3), kept in draft order. Unlike whole draft paragraphs, this does not
    bring back text the kept paragraphs around it already tell."""
    import difflib
    pool = []
    for qid in qids:
        for k, dp in enumerate((drafts.get(qid) or {}).get('paragraphs') or []):
            for j, t in enumerate(mb.sentences(dp['text'])):
                if (qid, k, j) not in used:
                    pool.append(((qid, k, j), t, dp['source_ids']))
    picked = {}
    for x in p['sentences']:
        if x['add']:
            continue
        best = max(pool, key=lambda c: difflib.SequenceMatcher(None, x['t'], c[1], autojunk=False).ratio(), default=None)
        if best and best[0] not in picked and difflib.SequenceMatcher(None, x['t'], best[1], autojunk=False).ratio() >= 0.3:
            picked[best[0]] = best
    if not picked:
        return []
    used.update(picked)
    order = sorted(picked.values(), key=lambda c: c[0])
    return [{'sentences': [{'t': t, 'src': src, 'add': None} for _, t, src in order], 'fallback': True,
             'from_questions': list(dict.fromkeys(c[0][0] for c in order))}]


def apply_checks(ch, units, sections, row, drafts, all_text, stats, fallback_mode='paragraph'):
    """Code + model checks; returns the final sections (with fallbacks)."""
    issues = defaultdict(list)
    out = (row or {}).get('output') if (row or {}).get('ok') else None
    if isinstance(out, dict):
        for it in out.get('issues') or []:
            if isinstance(it, dict) and it.get('sid'):
                issues[it['sid']].append(it)
                stats['model_issues'][it.get('type') or '?'] += 1
    else:
        stats['check_failed'] += 1
    chapter_text = '\n'.join(units[u]['raw'] for s in ch['sections'] for u in s['units']) + '\n' + \
        '\n'.join(units[u]['raw'] for u in ch['closing_units'])
    used, used_sents = set(), set()
    final = []
    for s in sections:
        paras = []
        for p in s['paragraphs']:
            keep, fall = [], False
            for x in p['sentences']:
                cited = '\n'.join(units[u]['raw'] for u in x['src']) if x['src'] else chapter_text
                bad = mb.unsupported(x['t'], cited)
                bad_any = mb.unsupported(x['t'], all_text)
                x['code'] = bad_any
                if bad and not bad_any:
                    stats['cross_cited'] += 1
                types = [i.get('type') for i in issues.get(x.get('sid'), [])]
                x['issues'] = issues.get(x.get('sid'), [])
                if bad_any:
                    stats['code_flags'] += len(bad_any)
                if x['add']:
                    if bad_any or any(t in FACT_ISSUES for t in types):
                        stats['dropped_added'] += 1
                        continue
                    keep.append(x)
                    continue
                if bad_any or any(t in FACT_ISSUES for t in types):
                    fall = True
                    stats['fallback_reasons'].update(['code:' + b[0] for b in bad_any] + [t for t in types if t in FACT_ISSUES])
                elif '未标加写' in types:
                    x['add'] = '感受'
                    stats['relabelled'] += 1
                keep.append(x)
            if fall:
                cited_units = [u for x in p['sentences'] for u in x['src']]
                qids = list(dict.fromkeys(units[u]['qid'] for u in cited_units))
                repl = (draft_matching(p, qids, drafts, used_sents) if fallback_mode == 'match'
                        else draft_paragraphs(qids, drafts, used, cited_units))
                stats['fallback_paragraphs'] += 1
                if repl:
                    paras.extend(repl)
                else:
                    stats['fallback_empty'] += 1  # nothing confirmed to fall back to: the paragraph is left out
                continue
            if keep:
                paras.append({'sentences': keep})
        if paras:
            final.append({'title': s['title'], 'paragraphs': paras})
    return final


# --------------------------------------------------------------------------- metrics
def metrics(book, units, plan):
    sents = [x for c in book['chapters'] for s in c['sections'] for p in s['paragraphs'] for x in p['sentences']]
    added = [x for x in sents if x['add']]
    chars = lambda xs: sum(mb.han_len(x['t']) for x in xs)
    planned = {u for c in plan['chapters'] for s in c['sections'] for u in s['units']} | {u for c in plan['chapters'] for u in c['closing_units']}
    cited = {u for x in sents for u in x['src']}
    per = []
    for c in book['chapters']:
        n = sum(mb.han_len(x['t']) for s in c['sections'] for p in s['paragraphs'] for x in p['sentences'])
        per.append({'title': c['title'], 'modules': c['modules'], 'chars': n, 'budget': c['budget'],
                    'deviation': round((n - c['budget']) / c['budget'], 3) if c['budget'] else None})
    elder = sum(mb.han_len(u['text']) for u in units.values())
    total = chars(sents)
    written = [x['t'] for x in sents if not x['add']]
    return {'chars': total, 'elder_chars': elder,
            'copy_ratio': mb.copy_ratio(written, '\n'.join(u['raw'] for u in units.values())), 'ratio_to_elder': round(total / elder, 3) if elder else None,
            'sentences': len(sents), 'added_sentences': len(added),
            'added_ratio': round(len(added) / len(sents), 3) if sents else 0,
            'added_char_ratio': round(chars(added) / total, 3) if total else 0,
            'unsupported_tokens': sum(len(x.get('code') or []) for x in sents),
            'unsupported_list': [b for x in sents for b in (x.get('code') or [])],
            'unit_use': round(len(cited & planned) / len(planned), 3) if planned else None,
            'elder_char_use': round(sum(mb.han_len(units[u]['text']) for u in cited & planned) /
                                    max(1, sum(mb.han_len(units[u]['text']) for u in planned)), 3),
            'chapters': per,
            'mean_abs_deviation': round(sum(abs(p['deviation']) for p in per if p['deviation'] is not None) /
                                        max(1, sum(1 for p in per if p['deviation'] is not None)), 3),
            'fallback_paragraphs': sum(1 for c in book['chapters'] for s in c['sections'] for p in s['paragraphs'] if p.get('fallback'))}


def dry_model(call):
    user = json.loads(call['user'])
    if call['id'].startswith('plan-'):
        chs = []
        for c in user['chapters']:
            by_q = defaultdict(list)
            for u in c['units']:
                by_q[u['question']].append(u['id'])
            first = c['units'][0]
            chs.append({'module': c['module'], 'title': first['text'][:4], 'title_quote': first['text'][:4], 'title_source': first['id'],
                        'sections': [{'title': q, 'units': ids} for q, ids in by_q.items()], 'closing_units': []})
        return json.dumps({'chapters': chs, 'motifs': [], 'private': [], 'unused': [], 'voice_habits': []}, ensure_ascii=False)
    if call['id'].startswith('w-'):
        secs = [{'title': s['title'], 'paragraphs': [[{'t': t, 'src': [u['id']], 'add': None} for t in mb.sentences(u['text'])]
                                                     for u in s['units']]} for s in user['chapter']['sections']]
        if secs and secs[-1]['paragraphs']:
            secs[-1]['paragraphs'][-1].append({'t': '那些日子，我一直记着。', 'src': [], 'add': '收束'})
        return json.dumps({'sections': secs}, ensure_ascii=False)
    return json.dumps({'issues': []})


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--variants', default='v1-on=write-v1.txt:enabled')
    ap.add_argument('--edition', default='standard', choices=list(mb.EDITIONS))
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--stop-after', default='', choices=['', 'plan', 'write'])
    ap.add_argument('--dry', action='store_true', help='plumbing test with canned model outputs (never cached)')
    ap.add_argument('--plan-prompt', default='plan.txt')
    ap.add_argument('--ratio', type=float, default=None, help='override the edition ratio (written chars / elder chars)')
    ap.add_argument('--premerge', action='store_true', help='merge thin modules before planning (plan-v2)')
    ap.add_argument('--simplify', action='store_true', help='traditional -> simplified on the written sentences')
    ap.add_argument('--check-thinking', default='enabled', choices=['enabled', 'disabled'])
    ap.add_argument('--check-prompt', default='check.txt')
    ap.add_argument('--fallback', default='paragraph', choices=['paragraph', 'match'],
                    help='paragraph: whole draft paragraphs of the cited questions (v1); match: the most similar draft sentences')
    ap.add_argument('--ingest', default='', help='stage=job_name[,…]: cache answers of a sent job before running that stage')
    a = ap.parse_args()
    if a.ratio:
        mb.EDITIONS[a.edition] = (a.ratio, mb.EDITIONS[a.edition][1])
    run_dir = mb.RUNS / a.run
    relay = mb.common.Relay(run_dir, offline=a.offline, wait_seconds=7200, dry=dry_model if a.dry else None)
    books = {}
    for path in a.inputs.split(','):
        h = mb.load(path)
        key = '%s-%s' % (h['person']['id'], h['material']['kind'])
        books[key] = {'handoff': h, 'units': units_of(h)}
        books[key]['groups'] = module_groups(books[key]['units']) if a.premerge else None
    tag = time.strftime('%H%M%S')  # job names must be unique; answers are cached by content anyway
    rows = relay.run_batch('mb1-plan-%s-%s' % (a.run, tag), [plan_call(k, b['handoff'], b['units'], a.plan_prompt, b['groups'])
                                                                       for k, b in books.items()])
    for k, b in books.items():
        b['plan'] = resolve_plan(b['handoff'], b['units'], rows.get('plan-' + k), a.edition, b['groups'])
        mb.save(run_dir / 'plans' / (k + '.json'), b['plan'])
        print(json.dumps({'plan': k, 'chapters': [(c['title'], c['modules'], c['budget']) for c in b['plan']['chapters']],
                          'log': b['plan']['log']}, ensure_ascii=False), flush=True)
    if a.stop_after == 'plan':
        return
    variants = []
    for spec in a.variants.split(','):
        name, rest = spec.split('=')
        prompt_name, thinking = rest.split(':')
        variants.append((name, prompt_name, thinking))
    calls, owner = [], {}
    for vname, prompt_name, thinking in variants:
        for k, b in books.items():
            cs = write_calls(vname + '-' + k, b['handoff'], b['units'], b['plan'], prompt_name, thinking, mb.EDITIONS[a.edition][0])
            owner[(vname, k)] = cs
            calls += cs
    rows = relay.run_batch('mb1-write-%s-%s' % (a.run, tag), [{x: c[x] for x in ('id', 'system', 'user', 'params')} for c in calls])
    written = {}
    for (vname, k), cs in owner.items():
        b = books[k]
        log = []
        per_chapter = defaultdict(list)
        for c in cs:
            per_chapter[c['meta']['chapter']].append(c)
        chapters = []
        drafts = drafts_by_question(b['handoff'])
        for ci, ch in enumerate(b['plan']['chapters']):
            parts = parse_written(ch, b['units'], rows, per_chapter[ci], log, a.simplify)
            secs, fallback_used = [], set()
            for part in parts:
                if part['sections'] is None:  # the call failed: these sections fall back to the confirmed drafts
                    for i in part['meta']['sections']:
                        s = ch['sections'][i]
                        qids = list(dict.fromkeys(b['units'][u]['qid'] for u in s['units']))
                        secs.append({'title': s['title'], 'paragraphs': draft_paragraphs(qids, drafts, fallback_used), 'call_failed': True})
                else:
                    secs.extend(part['sections'])
            chapters.append(secs)
        written[(vname, k)] = {'chapters': chapters, 'log': log}
        mb.save(run_dir / vname / 'written' / (k + '.json'), written[(vname, k)])
    if a.stop_after == 'write':
        return
    kcalls = []
    for (vname, k), w in written.items():
        b = books[k]
        for ci, ch in enumerate(b['plan']['chapters']):
            kcalls.append(check_calls(vname + '-' + k, ci, ch, b['units'], w['chapters'][ci], b['handoff'], a.check_thinking, a.check_prompt))
    ingest = dict(x.split('=') for x in a.ingest.split(',') if x)
    if 'check' in ingest:
        print(json.dumps({'ingested': mb.ingest_staged(relay, ingest['check'], kcalls), 'of': len(kcalls)}), flush=True)
    rows = relay.run_batch('mb1-check-%s-%s' % (a.run, tag), kcalls)
    summary = {}
    for (vname, k), w in written.items():
        b = books[k]
        all_text = '\n'.join(u['raw'] for u in b['units'].values())
        drafts = drafts_by_question(b['handoff'])
        stats = {'model_issues': Counter(), 'fallback_reasons': Counter(), 'check_failed': 0, 'cross_cited': 0, 'code_flags': 0,
                 'dropped_added': 0, 'relabelled': 0, 'fallback_paragraphs': 0, 'fallback_empty': 0}
        chapters = []
        for ci, ch in enumerate(b['plan']['chapters']):
            secs = apply_checks(ch, b['units'], w['chapters'][ci], rows.get('k-%s-%s-c%d' % (vname, k, ci)), drafts, all_text, stats,
                                a.fallback)
            chapters.append({'title': ch['title'], 'modules': ch['modules'], 'budget': ch['budget'], 'sections': secs,
                             'title_quote': ch.get('title_quote'), 'title_source': ch.get('title_source')})
        book = {'person': b['handoff']['person'], 'material': b['handoff']['material'], 'variant': vname, 'edition': a.edition,
                'chapters': chapters, 'motifs': b['plan']['motifs'],
                'not_written': {'private': b['plan']['private'], 'unused': b['plan']['unused'],
                                'declined': [d for q in b['handoff']['questions'] for d in q['markers']['declined']]},
                'units': {u: {'qid': x['qid'], 'asked': x['asked'], 'text': x['raw']} for u, x in b['units'].items()},
                'log': b['plan']['log'] + w['log']}
        book['metrics'] = metrics(book, b['units'], b['plan'])
        book['metrics']['pipeline'] = {k2: (dict(v) if isinstance(v, Counter) else v) for k2, v in stats.items()}
        mb.save(run_dir / vname / 'books' / (k + '.json'), book)
        render.write_all(book, run_dir / vname / 'books' / k)
        summary['%s/%s' % (vname, k)] = {x: book['metrics'][x] for x in ('chars', 'elder_chars', 'ratio_to_elder', 'copy_ratio', 'added_ratio',
                                                                           'unsupported_tokens', 'unit_use', 'mean_abs_deviation',
                                                                           'fallback_paragraphs')}
        summary['%s/%s' % (vname, k)]['pipeline'] = book['metrics']['pipeline']
    mb.save(run_dir / 'summary.json', summary)
    mb.save(run_dir / 'usage.json', {'calls_sent': relay.calls_sent, 'calls_cached': relay.calls_cached, 'usage': relay.usage})
    print(json.dumps({'summary': summary, 'calls_sent': relay.calls_sent, 'usage': relay.usage}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
