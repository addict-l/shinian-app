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
from copy import deepcopy

import mb
import render

PLAN_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'enabled', 'json_mode': True, 'max_tokens': 32000, 'timeout': 900}
CHECK_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'enabled', 'json_mode': True, 'max_tokens': 32000, 'timeout': 900}
WRITE_BASE = {'model': 'deepseek-v4-pro', 'json_mode': True, 'temperature': 0.6}
PART_CHARS = 6000
ADD_TYPES = ('感受', '回望', '过渡', '意象', '呼应', '收束', '画面', '氛围')  # 画面: v1.1 check, writer too from v2; 氛围: v2
# v2 expansion tiers (user decision 2026-11-03: the book may be longer than the elder's words): name -> (ratio, label)
TIERS = {'concise': (0.8, '简洁'), 'delicate': (1.5, '细腻'), 'rich': (2.0, '浓墨')}
SHORT_CHAPTER = 500  # v1.1 (user decision 4): a chapter shorter than this joins a neighbour as a section with its module heading
FACT_ISSUES = ('无来源事实', '张冠李戴', '确定化', '不愿讲', '加写含事实', '延伸事实')  # 延伸事实: check-v4


def write_params(thinking, long_output=False):
    p = dict(WRITE_BASE, thinking=thinking)
    p.update({'max_tokens': 32000, 'timeout': 900} if thinking == 'enabled' else {'max_tokens': 16000, 'timeout': 600})
    if long_output and thinking != 'enabled':  # v2 tiers write up to 2x the elder's words
        p.update({'max_tokens': 24000, 'timeout': 900})
    return p


_SENT = re.compile(r'[^。！？!?；;…\n]+[。！？!?；;…]*')


# v2 round 3b: short interview closers that are not material ("没有了，能想起来的都跟您讲了")
FILLER = re.compile(r'(想不起来了|没什么要补充|没有要补充|没有了[，。]|就是这些|就这些了|都跟您讲了|都讲了|没别的了|别的也没什么|也没什么了|没有别的|别的就没|'
                    r'说不上来了|讲不出什么|不乱讲|不敢乱说|不好乱说)')
LABEL_TITLE = re.compile(r'(本人|评价|程度|特质|认定|或错过|情况$|方面$|经历$)')  # a field label used as a section title


def novel_texts(plan, units, threshold=0.5):
    """v2 round 2: per unit, the text of its sentences that do not retell an earlier sentence of the book (plan order,
    same test as novel_chars). The writer gets these instead of the raw answers, so a story the elder told in fifteen
    answers reaches it once (the check still sees every raw answer)."""
    seen, out = set(), {}
    order = [u for ch in plan['chapters'] for s in ch['sections'] for u in s['units']] + \
        [u for ch in plan['chapters'] for u in ch['closing_units']]
    for u in order:
        kept = []
        for sent in _SENT.findall(units[u]['text']):
            g = _grams(sent)
            if g and len(g & seen) / len(g) < threshold and not FILLER.search(sent) if mb.han_len(sent) <= 20 else \
                    g and len(g & seen) / len(g) < threshold:
                kept.append(sent)
            seen |= g
        out[u] = ''.join(kept).strip()
    return out


def cover(text, grams, n=4):
    """Share of the n-grams of ``text`` found in ``grams`` (0 for a text too short to have any)."""
    g = _grams(text, n)
    return len(g & grams) / len(g) if g else 0.0


def novel_chars(plan, units, threshold=0.5):
    """v2: per unit, the characters of its sentences that do NOT retell an earlier sentence of the book (in plan order,
    4-gram coverage >= threshold, 0.5, by everything said before). The simulated elders (and real ones) retell the same story
    in many answers -- mb2-full84-long's rice-field story is in ~15 childhood answers -- so raw elder chars overstate the
    material and a ratio budget on them asks the writer to pad."""
    seen, out = set(), {}
    order = [u for ch in plan['chapters'] for s in ch['sections'] for u in s['units']] + \
        [u for ch in plan['chapters'] for u in ch['closing_units']]
    for u in order:
        n = 0
        for sent in _SENT.findall(units[u]['text']):
            g = _grams(sent)
            if g and len(g & seen) / len(g) < threshold:
                n += mb.han_len(sent)
            seen |= g
        out[u] = n
    return out


def rebudget(plan, ratio, cap, units=None):
    """v2: chapter and section budgets of a resolved plan for another ratio (same rule as resolve_plan). With ``units``
    the ratio applies to the novel (not retold) material, kept as ``novel_chars`` next to the raw ``elder_chars``."""
    novel = novel_chars(plan, units) if units else None
    for ch in plan['chapters']:
        if novel is not None:
            for s in ch['sections']:
                s['novel_chars'] = sum(novel[u] for u in s['units'])
            ch['novel_chars'] = sum(s['novel_chars'] for s in ch['sections']) + sum(novel[u] for u in ch['closing_units'])
        base = ch['novel_chars'] if novel is not None else ch['elder_chars']
        ch['budget'] = int(min(base * ratio, sum(mb.SHARE[m] for m in ch['modules']) * cap))
        for s in ch['sections']:
            s['budget'] = int((s['novel_chars'] if novel is not None else s['elder_chars']) * ratio) if ch['budget'] else 0
        ch['closing_budget'] = int(sum((novel[u] if novel is not None else mb.han_len(units[u]['text']) if units else 0)
                                       for u in ch['closing_units']) * ratio) if units else None
    return plan


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


def six_groups(units):
    """v2 six-chapter book: one group per module that has material (singleton groups also switch off the v1
    thin-chapter merge in resolve_plan)."""
    have = {u['module'] for u in units.values() if u['text']}
    return [[m] for m, _, _ in mb.MODULES if m in have]


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
    # six chapters (singleton groups): a module with material but no chapter after the planner's moves gets its own
    # units back, one section per question, so the book keeps the prologue + six-module structure
    if groups and all(len(g) == 1 for g in groups):
        for g in groups:
            m = g[0]
            if m in chapters and (chapters[m]['sections'] or chapters[m]['closing_units']):
                continue
            own = [uid for uid, u in units.items() if u['module'] == m and u['text'] and uid not in {x['unit'] for x in unused}]
            if not own:
                continue
            for ch0 in chapters.values():
                for s0 in ch0['sections']:
                    s0['units'] = [x for x in s0['units'] if x not in own]
                ch0['sections'] = [s0 for s0 in ch0['sections'] if s0['units']]
                ch0['closing_units'] = [x for x in ch0['closing_units'] if x not in own]
            ch = chapters.setdefault(m, {'modules': [m], 'title': None, 'sections': [], 'closing_units': []})
            for uid in own:
                q = units[uid]['qid']
                sec = next((s0 for s0 in ch['sections'] if s0.get('repair') == q), None)
                if sec is None:
                    sec = {'title': mb.catalog()[q]['title'], 'units': [], 'repair': q}
                    ch['sections'].append(sec)
                sec['units'].append(uid)
            log.append('module_restored:%s(%d units)' % (m, len(own)))
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


def merge_short(chapters, chars_of, log, where, min_chars=SHORT_CHAPTER):
    """v1.1 (user decision 4): a chapter (never the prologue) with fewer than ``min_chars`` characters -- its budget
    after planning, its written text after writing -- joins the previous chapter (the next one when the previous
    is the prologue or missing) as sections carrying their module heading. Returns the new chapter list."""
    chapters = list(chapters)
    while True:
        body = [c for c in chapters if c['modules'][0] != 'skeleton']
        short = [c for c in body if chars_of(c) < min_chars]
        if not short or len(body) < 2:
            return chapters
        c = min(short, key=chars_of)
        i = body.index(c)
        into = body[i - 1] if i > 0 else body[i + 1]
        heading = ' · '.join(mb.MODULE_NAME[m] for m in c['modules'])
        moved = [dict(s, module_heading=s.get('module_heading') or heading) for s in c['sections']]
        if c.get('closing_units'):
            if moved:
                moved[-1] = dict(moved[-1], units=list(moved[-1].get('units') or []) + c['closing_units'])
                if c.get('closing_budget') and 'budget' in moved[-1]:  # v2: the closing words keep their budget
                    moved[-1]['budget'] += c['closing_budget']
            else:
                moved = [{'title': heading, 'units': list(c['closing_units']), 'module_heading': heading}]
        before = chapters.index(into) < chapters.index(c)
        merged = dict(into)
        merged['modules'] = into['modules'] + c['modules'] if before else c['modules'] + into['modules']
        merged['sections'] = (into['sections'] + moved) if before else (moved + into['sections'])
        for k in ('budget', 'elder_chars', 'novel_chars'):
            if into.get(k) is not None:
                merged[k] = into.get(k, 0) + c.get(k, 0)
        if 'units' in into or 'units' in c:  # v2 book chapters carry their source units
            merged['units'] = (list(into.get('units') or []) + list(c.get('units') or [])) if before else \
                (list(c.get('units') or []) + list(into.get('units') or []))
        log.append('short_merged_%s:%s(%d)->%s' % (where, '/'.join(c['modules']), chars_of(c), '/'.join(into['modules'])))
        chapters[chapters.index(into)] = merged
        chapters.remove(c)


# --------------------------------------------------------------------------- write
def drafts_by_question(handoff):
    return {q['question_id']: q.get('draft') for q in handoff['questions']}


PART_SECTIONS = 0  # v2 round 3 (--part-sections): at most this many sections per writer call (0: by PART_CHARS only)


def chapter_parts(ch):
    if PART_SECTIONS:
        idx = list(range(len(ch['sections'])))
        return [idx[i:i + PART_SECTIONS] for i in range(0, len(idx), PART_SECTIONS)] or [[]]
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


def write_calls(key, handoff, units, plan, prompt_name, thinking, ratio=0.8, tier=None, only=None, texts=None):
    """``texts`` (v2 round 2, --novel-units): unit -> the text the writer gets (retold sentences removed; a unit left
    empty is not given), and the confirmed drafts are cut to the sentences about that text."""
    calls = []
    text_of = (lambda u: texts.get(u, '')) if texts is not None else (lambda u: units[u]['text'])
    drafts = drafts_by_question(handoff)
    titles = ['%s　%s（%s）' % ('序章' if c['modules'][0] == 'skeleton' else '第%d章' % i, c['title'], ' · '.join(mb.MODULE_NAME[m] for m in c['modules']))
              for i, c in enumerate(plan['chapters'], 0 if plan['chapters'][0]['modules'][0] == 'skeleton' else 1)]
    unknown = [{'unit': d.get('source_id'), 'quote': d['quote']} for q in handoff['questions'] for d in q['markers']['unknown'] if d.get('quote')]
    voice = {'称呼': list(handoff['voice']['kin_terms']), '口头语': plan['voice_habits']}
    system = mb.prompt(prompt_name)
    for ci, ch in enumerate(plan['chapters']):
        if only is not None and ci not in only:
            continue
        parts = chapter_parts(ch)
        for pi, idx in enumerate(parts):
            last = pi == len(parts) - 1
            secs = []
            for i in idx:
                s = ch['sections'][i]
                given = [u for u in s['units'] if text_of(u)]
                qids = list(dict.fromkeys(units[u]['qid'] for u in given))
                if texts is not None:  # drafts retell too: keep the draft sentences about the text given
                    sg = _grams(' '.join(text_of(u) for u in given), 3)
                    dseen, dtext = set(), {}
                    for qid in qids:  # ... and each such sentence once in the section
                        keep = []
                        for p in (drafts.get(qid) or {}).get('paragraphs') or []:
                            for x in mb.sentences(p['text']):
                                if cover(x, sg, 3) >= 0.3 and cover(x, dseen) < 0.5:
                                    keep.append(x)
                                    dseen |= _grams(x)
                        dtext[qid] = ''.join(keep)
                else:
                    dtext = {qid: '\n'.join(p['text'] for p in (drafts.get(qid) or {}).get('paragraphs') or []) for qid in qids}
                secs.append({'title': s['title'], 'budget_chars': s['budget'],
                             **({'rename': True} if texts is not None and LABEL_TITLE.search(s['title']) else {}),
                             **({'module_heading': s['module_heading']} if s.get('module_heading') else {}),
                             'units': [{'id': u, 'asked': units[u]['asked'], 'text': text_of(u)} for u in given],
                             'confirmed_drafts': [{'question': qid, 'title': (drafts.get(qid) or {}).get('title'), 'text': dtext[qid]}
                                                  for qid in qids if drafts.get(qid) and dtext[qid]]})
            closing = [{'id': u, 'asked': units[u]['asked'], 'text': text_of(u)} for u in ch['closing_units'] if text_of(u)] if last else []
            closing_budget = ch.get('closing_budget')
            if closing_budget is None:
                closing_budget = int(sum(mb.han_len(c['text']) for c in closing) * ratio)
            budget = sum(s['budget_chars'] for s in secs) + (closing_budget if closing else 0)
            if tier and texts is not None:  # v2 round 2: the writer is told how much is facts and how much is added writing
                facts = sum(mb.han_len(u['text']) for x in secs for u in x['units']) + sum(mb.han_len(c['text']) for c in closing)
                facts_target = min(facts, int(budget * 0.9))
                expand = {'expand': {'tier': TIERS[tier][1], 'ratio': TIERS[tier][0], 'facts_chars': facts_target,
                                     'added_chars': max(0, budget - facts_target)}}
            else:
                expand = None
            user = {'book': {'person': handoff['person']['name'], 'chapters': titles, 'motifs': plan['motifs']},
                    'chapter': {'index': titles[ci], 'modules': [mb.MODULE_NAME[m] for m in ch['modules']], 'title': ch['title'],
                                'budget_chars': budget, 'part': '%d/%d' % (pi + 1, len(parts)), 'is_last_part': last,
                                **(expand or {}),
                                **({'expand': {'tier': TIERS[tier][1], 'ratio': TIERS[tier][0],
                                               'elder_chars': sum(s['elder_chars'] for s in (ch['sections'][i] for i in idx))
                                               + sum(mb.han_len(c['text']) for c in closing),
                                               **({'novel_chars': sum(s.get('novel_chars', 0) for s in (ch['sections'][i] for i in idx))
                                                   + (closing_budget / ratio if closing and ratio else 0) // 1}
                                                  if 'novel_chars' in ch else {})}} if tier and expand is None else {}),
                                'sections': secs},
                    'closing_units': closing, 'voice': voice,
                    'unknown': [u for u in unknown if u['unit'] in {x for s in secs for x in (y['id'] for y in s['units'])}]}
            calls.append({'id': 'w-%s-c%d-p%d' % (key, ci, pi), 'system': system, 'user': json.dumps(user, ensure_ascii=False),
                          'params': write_params(thinking, bool(tier)), 'meta': {'chapter': ci, 'part': pi, 'sections': idx}})
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


_SENT_OBJ = re.compile(r'\{\s*"t"\s*:')
_TITLE = re.compile(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"')


def salvage_sections(content):
    """v2: sections from writer JSON whose brackets are broken (seen: "paragraphs" closed after the first paragraph and
    the next paragraphs left outside it). Reads every sentence object in order; a "title" between two sentences opens
    a new section, a '[' between them a new paragraph. None when nothing can be read."""
    dec = json.JSONDecoder()
    sections, pos, cur = [], 0, None
    for m in _SENT_OBJ.finditer(content):
        if m.start() < pos:
            continue
        gap = content[pos:m.start()]
        try:
            obj, end = dec.raw_decode(content, m.start())
        except ValueError:
            continue
        titles = _TITLE.findall(gap)
        if titles or cur is None:
            cur = {'title': json.loads('"%s"' % titles[-1]) if titles else '', 'paragraphs': [[]]}
            sections.append(cur)
        elif '[' in gap:
            cur['paragraphs'].append([])
        cur['paragraphs'][-1].append(obj)
        pos = end
    return {'sections': sections} if sections else None


def written_output(row):
    if not row.get('ok'):
        return None
    try:
        return json.loads(row.get('content') or '', object_pairs_hook=_merge_pairs)
    except ValueError:
        return row.get('output') or salvage_sections(row.get('content') or '')


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


NO_PROBLEM = re.compile(r'(无问题|没有问题|不算问题|此句无|句子一致|与原话一致|一致[。，]?$|没有新增事实[。，]?$)')


def apply_checks(ch, units, sections, row, drafts, all_text, stats, fallback_mode='paragraph'):
    """Code + model checks; returns the final sections (with fallbacks)."""
    issues = defaultdict(list)
    out = (row or {}).get('output') if (row or {}).get('ok') else None
    if isinstance(out, dict):
        for it in out.get('issues') or []:
            if isinstance(it, dict) and it.get('sid'):
                if NO_PROBLEM.search(it.get('detail') or ''):  # v2: thinking-off checks list clean sentences too
                    stats['ignored_no_problem'] = stats.get('ignored_no_problem', 0) + 1
                    continue
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
                its = issues.get(x.get('sid'), [])
                if not x['add'] and its and cover(x['t'], _grams(cited)) >= 0.7:
                    # v2: a fact sentence that retells its cited words almost verbatim carries no picture or added
                    # feeling (round 1: one check answer reported 85 such sentences as 画面, "句子一致")
                    soft = [i for i in its if i.get('type') in ('画面', '未标加写')]
                    if soft:
                        stats['ignored_soft_issues'] = stats.get('ignored_soft_issues', 0) + len(soft)
                        its = [i for i in its if i not in soft]
                types = [i.get('type') for i in its]
                x['issues'] = its
                if '画面' in types:  # v1.1: a small picture is kept and shown for the elder's confirmation
                    x['picture'] = True
                    stats['pictures'] += 1
                if bad_any:
                    stats['code_flags'] += len(bad_any)
                if x['add']:
                    if bad_any or any(t in FACT_ISSUES for t in types):
                        stats['dropped_added'] += 1
                        continue
                    if quotes_not_in(x['t'], all_text):  # v2: an added sentence never puts new words in anyone's mouth
                        stats['dropped_added_quote'] = stats.get('dropped_added_quote', 0) + 1
                        continue
                    keep.append(x)
                    continue
                if bad_any or any(t in FACT_ISSUES for t in types):
                    fall = True
                    stats['fallback_reasons'].update(['code:' + b[0] for b in bad_any] + [t for t in types if t in FACT_ISSUES])
                elif '未标加写' in types:
                    x['add'] = '感受'
                    stats['relabelled'] += 1
                elif '画面' in types:  # v1.1: a factual sentence that only adds a small picture becomes an added one
                    x['add'] = '画面'
                    stats['relabelled_picture'] += 1
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


_QUOTE = re.compile(r'[“「‘"]([^”」’"]{2,})[”」’"]')
_NORM = re.compile(r'[^一-鿿0-9A-Za-z]')


def quotes_not_in(sentence, source_text):
    """Quoted spans of a sentence that do not occur in the sources (punctuation and t/s ignored)."""
    src = _NORM.sub('', mb.t2s(source_text))
    return [q for q in _QUOTE.findall(sentence) if _NORM.sub('', mb.t2s(q)) and _NORM.sub('', mb.t2s(q)) not in src]


def backfill(plan_ch, secs, units, drafts, min_chars, stats, texts=None, prior=None):
    """v2: a planned unit of at least ``min_chars`` that no written sentence cites comes back as the confirmed draft
    paragraphs citing it, at the end of the section the plan put it in (writers sometimes drop a whole unit).
    Round 2 (``texts``: the novel text of each unit): only units with that much NOVEL text, and only the draft
    sentences not already told (4-gram coverage < 0.5 by this chapter's text and ``prior``, the grams of the earlier
    chapters) -- round 1 backfilled every retelling of the rice-field story as its draft."""
    if not min_chars or not secs:
        return secs
    told = set(prior or ())
    for s0 in secs:
        for p in s0['paragraphs']:
            for x in p['sentences']:
                told |= _grams(x['t'])
    cited = {u for s in secs for p in s['paragraphs'] for x in p['sentences'] for u in x['src']}
    used = set()
    for si, ps in enumerate(plan_ch['sections']):
        target = next((s for s in secs if s['title'] == ps['title']), None)
        if target is None:
            target = secs[si] if len(secs) == len(plan_ch['sections']) else secs[-1]
        for u in ps['units']:
            if u in cited or mb.han_len(texts[u] if texts is not None else units[u]['text']) < min_chars:
                continue
            got = draft_paragraphs([units[u]['qid']], drafts, used, [u])
            if texts is not None:
                for g in got:
                    g['sentences'] = [x for x in g['sentences'] if cover(x['t'], told) < 0.5]
                    for x in g['sentences']:
                        told |= _grams(x['t'])
                got = [g for g in got if g['sentences']]
            if got:
                for g in got:
                    g['backfill'] = u
                target['paragraphs'].extend(got)
                stats['backfilled_units'] = stats.get('backfilled_units', 0) + 1
                cited |= {v for g in got for x in g['sentences'] for v in x['src']}
    return secs


def _grams(text, n=4):
    t = _NORM.sub('', mb.t2s(text))
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def near_repeats(chapters, threshold=0.6, min_len=10):
    """Sentences (with chapter index) whose 4-gram set is covered >= threshold by one sentence of ANOTHER chapter."""
    rows = []
    for ci, c in enumerate(chapters):
        for s in c['sections']:
            for p in s['paragraphs']:
                for x in p['sentences']:
                    if mb.han_len(x['t']) >= min_len:
                        rows.append((ci, x, _grams(x['t'])))
    index = defaultdict(set)
    for i, (_, _, g) in enumerate(rows):
        for k in g:
            index[k].add(i)
    out = []
    for i, (ci, x, g) in enumerate(rows):
        hits = Counter(j for k in g for j in index[k] if j != i and rows[j][0] != ci)
        if hits and g:
            j, n = hits.most_common(1)[0]
            if n / len(g) >= threshold:
                out.append((ci, x, rows[j][0], rows[j][1]))
    return out


def dedupe(chapters, stats, threshold=0.7):
    """v2: a sentence that repeats one of an EARLIER chapter (4-gram coverage >= threshold) is dropped -- the same event
    told in two questions was written twice -- and an added sentence that repeats an earlier added one anywhere is
    dropped (the same flourish twice)."""
    drop = set()
    for ci, x, cj, y in near_repeats(chapters, threshold):
        if cj < ci and (x['add'] or not y['add']):
            drop.add(id(x))
    for c in chapters:  # v2 round 2: also within a chapter (a draft paragraph or a writer retelling the same thing)
        seen_c = []
        for s0 in c['sections']:
            for p in s0['paragraphs']:
                for x in p['sentences']:
                    g = _grams(x['t'])
                    if mb.han_len(x['t']) >= 10 and g and any(len(g & h) / len(g) >= threshold for h in seen_c):
                        drop.add(id(x))
                    elif g:
                        seen_c.append(g)
    seen = []
    for c in chapters:
        for s in c['sections']:
            for p in s['paragraphs']:
                for x in p['sentences']:
                    if x['add'] and id(x) not in drop:
                        g = _grams(x['t'])
                        if g and any(len(g & h) / len(g) >= threshold for h in seen):
                            drop.add(id(x))
                        else:
                            seen.append(g)
    for c in chapters:
        for s in c['sections']:
            for p in s['paragraphs']:
                before = len(p['sentences'])
                p['sentences'] = [x for x in p['sentences'] if id(x) not in drop]
                n = before - len(p['sentences'])
                if n:
                    stats['dedup_dropped'] = stats.get('dedup_dropped', 0) + n
            s['paragraphs'] = [p for p in s['paragraphs'] if p['sentences']]
        c['sections'] = [s for s in c['sections'] if s['paragraphs']]
    return chapters


_OPENING = re.compile(r'[一-鿿]')


def opening(text, n=3):
    return ''.join(_OPENING.findall(text)[:n])


def style_metrics(chapters):
    """v2 code metrics of the added writing: type distribution, repeated openings, cross-chapter repeats."""
    sents = [x for c in chapters for s in c['sections'] for p in s['paragraphs'] for x in p['sentences']]
    added = [x for x in sents if x['add']]
    opens = Counter(opening(x['t']) for x in added)
    opens2 = Counter(opening(x['t'], 2) for x in added)
    reps = near_repeats(chapters)
    return {'added_types': dict(Counter(x['add'] for x in added).most_common()),
            'added_opening_repeat': round(sum(1 for x in added if opens[opening(x['t'])] > 1) / len(added), 3) if added else 0,
            'added_opening2_repeat': round(sum(1 for x in added if opens2[opening(x['t'], 2)] > 1) / len(added), 3) if added else 0,
            'added_top_openings': [[k, v] for k, v in opens.most_common(6) if v > 1],
            'looking_back_openers': sum(1 for x in added if re.match(r'^(现在|如今|后来|回头|那时候?我?常)?(想想|想起|想来|回想|看来|想到)', _NORM.sub('', x['t']))
                                        or re.match(r'^(现在|如今)(想|看|回)', _NORM.sub('', x['t']))),
            'cross_chapter_repeats': len(reps),
            'cross_chapter_repeat_ratio': round(len(reps) / len(sents), 3) if sents else 0}


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
    in_book = {u for c in book['chapters'] for u in c.get('units') or []}
    elder = sum(mb.han_len(u['text']) for k, u in units.items() if not in_book or k in in_book)
    total = chars(sents)
    written = [x['t'] for x in sents if not x['add']]
    novel = sum(c['novel_chars'] for c in book['chapters'] if c.get('novel_chars') is not None) \
        if all(c.get('novel_chars') is not None for c in book['chapters']) and book['chapters'] else None
    return {'chars': total, 'elder_chars': elder, 'novel_chars': novel,
            'ratio_to_novel': round(total / novel, 3) if novel else None,
            'copy_ratio': mb.copy_ratio(written, '\n'.join(u['raw'] for u in units.values())), 'ratio_to_elder': round(total / elder, 3) if elder else None,
            'sentences': len(sents), 'added_sentences': len(added),
            'added_ratio': round(len(added) / len(sents), 3) if sents else 0,
            'added_char_ratio': round(chars(added) / total, 3) if total else 0,
            'unsupported_tokens': sum(len(x.get('code') or []) for x in sents),
            'unsupported_list': [b for x in sents for b in (x.get('code') or [])],
            'unit_use': round(len(cited & planned) / len(planned), 3) if planned else None,
            # v2 round 2: units with at least 10 chars of novel (not retold) text that some sentence cites
            'novel_unit_use': (lambda nv: round(len(cited & nv) / len(nv), 3) if nv else None)(
                {u for u in planned if mb.han_len((plan.get('novel_texts') or {}).get(u, '')) >= 10}) if plan.get('novel_texts') else None,
            'elder_char_use': round(sum(mb.han_len(units[u]['text']) for u in cited & planned) /
                                    max(1, sum(mb.han_len(units[u]['text']) for u in planned)), 3),
            'chapters': per,
            'mean_abs_deviation': round(sum(abs(p['deviation']) for p in per if p['deviation'] is not None) /
                                        max(1, sum(1 for p in per if p['deviation'] is not None)), 3),
            'fallback_paragraphs': sum(1 for c in book['chapters'] for s in c['sections'] for p in s['paragraphs'] if p.get('fallback')),
            **style_metrics(book['chapters'])}


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
    if call['id'].startswith('x-'):
        return json.dumps({'insert': [{'after': x['sid'], 't': '那时候的光景，我还记得。', 'add': '画面', 'src': []}
                                      for x in user['sentences'][::3]]}, ensure_ascii=False)
    return json.dumps({'issues': []})


EXPAND_K = {'concise': 0.1, 'delicate': 0.5, 'rich': 1.0}  # v2 round 3: added chars = k x fact-layer chars


def expand_call(key, ci, ch, secs, units, texts, plan, titles, tier, used_openings, prompt_name):
    """v2 round 3: one call that only INSERTS added sentences into a written (fact-layer) chapter."""
    sents = []
    for si, s in enumerate(secs):
        for pi, p in enumerate(s['paragraphs']):
            for k, x in enumerate(p['sentences']):
                x['xid'] = 's%d.p%d.%d' % (si, pi, k)
                sents.append({'sid': x['xid'], 't': x['t'], 'add': x['add'], 'section': s['title']})
    facts = sum(mb.han_len(x['t']) for x in sents if not x['add'])
    target = int(facts * EXPAND_K[tier])
    ids = [u for s in ch['sections'] for u in s['units']] + ch['closing_units']
    user = {'book': {'person': plan['person'], 'chapters': titles, 'motifs': plan['motifs']},
            'chapter': {'title': ch['title'], 'tier': TIERS[tier][1], 'target_added_chars': target,
                        'target_sentences': max(1, round(target / 24))},
            'sentences': sents,
            'sources': [{'id': u, 'asked': units[u]['asked'], 'text': (texts or {}).get(u) or units[u]['text']} for u in ids
                        if ((texts or {}).get(u) if texts is not None else units[u]['text'])],
            'used_openings': used_openings}
    return {'id': 'x-%s-c%d' % (key, ci), 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False),
            'params': write_params('disabled', True)}


def apply_expand(secs, row, allowed, simplify, stats):
    """Insert the expansion call's sentences after their anchors (unknown anchors: dropped). Returns new sections."""
    out = written_output(row) if row else None
    ins = defaultdict(list)
    for it in (out or {}).get('insert') or [] if isinstance(out, dict) else []:
        if not isinstance(it, dict):
            continue
        t = (it.get('t') or '').strip()
        if simplify:
            t = mb.simplify(t)
        add = it.get('add') if it.get('add') in ADD_TYPES else '感受'
        if t:
            ins[str(it.get('after'))].append({'t': t, 'src': [u for u in (it.get('src') or []) if u in allowed], 'add': add,
                                              'expanded': True})
    known = {x.get('xid') for s in secs for p in s['paragraphs'] for x in p['sentences']}
    stats['expand_inserted'] = stats.get('expand_inserted', 0) + sum(len(v) for k, v in ins.items() if k in known)
    stats['expand_unanchored'] = stats.get('expand_unanchored', 0) + sum(len(v) for k, v in ins.items() if k not in known)
    if not isinstance(out, dict):
        stats['expand_failed'] = stats.get('expand_failed', 0) + 1
    new = []
    for s in secs:
        paras = []
        for p in s['paragraphs']:
            sents = []
            for x in p['sentences']:
                sents.append({k: v for k, v in x.items() if k != 'xid'})
                sents.extend(dict(y) for y in ins.get(x.get('xid'), []))
            paras.append(dict(p, sentences=sents))
        new.append(dict(s, paragraphs=paras))
    return new


def run_unique(relay, job, calls):
    """Send each distinct request once (tiers sharing a fact layer ask the same thing) and answer every id."""
    first, rows = {}, {}
    for c in calls:
        first.setdefault(relay.key(c), c)
    got = relay.run_batch(job, [{x: c[x] for x in ('id', 'system', 'user', 'params')} for c in first.values()]) if first else {}
    for c in calls:
        r = got.get(first[relay.key(c)]['id'])
        rows[c['id']] = dict(r, id=c['id']) if r else r
    return rows


def stop_on_lost(rows, stage, a):
    """Failed calls (network, provider) are not answers: stop, so a rerun resends them, instead of silently falling back
    to the drafts. Successful answers are already cached, so the rerun only resends the lost ones."""
    lost = [i for i, r in rows.items() if not r.get('ok')]
    if lost and not a.offline and not a.dry:
        raise SystemExit('%s: %d/%d calls failed (%s); rerun with the same arguments' % (
            stage, len(lost), len(rows), ', '.join(sorted({str(rows[i].get('error')) for i in lost}))))


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
    ap.add_argument('--short-merge', type=int, default=0,
                    help='v1.1: a chapter below this many characters (budget after planning, text after writing) joins a '
                         'neighbour as a section with its module heading (user decision 4: 500)')
    ap.add_argument('--prefix', default='mb1', help='relay job name prefix (mb2 for the v1.1 full-interview test)')
    ap.add_argument('--modules', default='', help='v2 iteration: write/check only the chapters holding these modules '
                                                  '(the writer still sees the whole book\'s chapter list, so a later full run hits the cache)')
    ap.add_argument('--backfill', type=int, default=0, help='v2: planned units of >= N chars no sentence cites come back as their drafts')
    ap.add_argument('--novel-budget', action='store_true', help='v2 round 2: tier budgets on the novel (not retold) material')
    ap.add_argument('--novel-units', action='store_true', help='v2 round 2: the writer gets each answer without the sentences '
                                                                 'that retell an earlier answer (plan order); backfill likewise')
    ap.add_argument('--expand-prompt', default='', help='v2 round 3: tiers share one fact layer (budget 1.0 x novel material) '
                                                         'and differ only in an expansion call that inserts added sentences')
    ap.add_argument('--part-sections', type=int, default=0, help='v2 round 3: at most N sections per writer call')
    ap.add_argument('--dedupe', action='store_true', help='v2: drop sentences repeating an earlier chapter / an earlier added sentence')
    ap.add_argument('--six', action='store_true', help='v2 (user decision 2026-11-03 06:42): prologue + one chapter per module, '
                                                       'never merged (no premerge, no thin/short-chapter merge); use plan-v4.txt')
    a = ap.parse_args()
    if a.six and (a.premerge or a.short_merge):
        raise SystemExit('--six never merges chapters: drop --premerge / --short-merge')
    global PART_SECTIONS
    PART_SECTIONS = a.part_sections
    if a.ratio:
        mb.EDITIONS[a.edition] = (a.ratio, mb.EDITIONS[a.edition][1])
    run_dir = mb.RUNS / a.run
    relay = mb.common.Relay(run_dir, offline=a.offline, wait_seconds=7200, dry=dry_model if a.dry else None)
    books = {}
    for path in a.inputs.split(','):
        h = mb.load(path)
        key = '%s-%s' % (h['person']['id'], h['material']['kind'])
        books[key] = {'handoff': h, 'units': units_of(h)}
        books[key]['groups'] = module_groups(books[key]['units']) if a.premerge else \
            six_groups(books[key]['units']) if a.six else None
    tag = time.strftime('%H%M%S')  # job names must be unique; answers are cached by content anyway
    rows = relay.run_batch('%s-plan-%s-%s' % (a.prefix, a.run, tag), [plan_call(k, b['handoff'], b['units'], a.plan_prompt, b['groups'])
                                                                       for k, b in books.items()])
    # a transport failure (network, timeout) is not a planner answer: stop instead of writing from a fallback plan
    lost = [k for k in books if not (rows.get('plan-' + k) or {}).get('ok') and not a.dry]
    if lost and not a.offline:
        raise SystemExit('plan call failed (%s); rerun with the same arguments -- a new job name is used, answers are cached'
                         % ', '.join('%s:%s' % (k, (rows.get('plan-' + k) or {}).get('error')) for k in lost))
    for k, b in books.items():
        b['plan'] = resolve_plan(b['handoff'], b['units'], rows.get('plan-' + k), a.edition, b['groups'])
        b['plan_raw'] = deepcopy(b['plan'])  # before the short-chapter merge: v2 tiers rebudget and merge from here
        if a.short_merge:
            b['plan']['chapters'] = merge_short(b['plan']['chapters'], lambda c: c['budget'], b['plan']['log'], 'plan', a.short_merge)
        mb.save(run_dir / 'plans' / (k + '.json'), b['plan'])
        print(json.dumps({'plan': k, 'chapters': [(c['title'], c['modules'], c['budget']) for c in b['plan']['chapters']],
                          'log': b['plan']['log']}, ensure_ascii=False), flush=True)
    if a.stop_after == 'plan':
        return
    variants = []
    for spec in a.variants.split(','):
        name, rest = spec.split('=')
        prompt_name, thinking, *tier = rest.split(':')
        variants.append((name, prompt_name, thinking, tier[0] if tier else None))
    only_modules = {m for m in a.modules.split(',') if m}
    vplans = {}
    for vname, _, _, tier in variants:
        for k, b in books.items():
            if tier is None:
                vp = b['plan']
            else:  # v2: budgets = tier ratio x elder chars, then the short-chapter merge on those budgets
                # module caps of the full edition: the standard caps (built for 0.7x) would clip a 2x prologue
                vp = rebudget(deepcopy(b['plan_raw']), 1.0 if a.expand_prompt else TIERS[tier][0],
                              max(mb.EDITIONS[a.edition][1], mb.EDITIONS['full'][1]), b['units'] if a.novel_budget else None)
                if a.short_merge:
                    vp['log'] = list(vp['log'])
                    vp['chapters'] = merge_short(vp['chapters'], lambda c: c['budget'], vp['log'], 'plan', a.short_merge)
            only = {ci for ci, c in enumerate(vp['chapters']) if not only_modules or set(c['modules']) & only_modules}
            vp['novel_texts'] = novel_texts(vp, b['units']) if a.novel_units else None
            vplans[(vname, k)] = (vp, only)
            mb.save(run_dir / vname / 'plans' / (k + '.json'), vp)
    calls, owner = [], {}
    for vname, prompt_name, thinking, tier in variants:
        for k, b in books.items():
            vp, only = vplans[(vname, k)]
            ratio = 1.0 if a.expand_prompt and tier else TIERS[tier][0] if tier else mb.EDITIONS[a.edition][0]
            cs = write_calls(vname + '-' + k, b['handoff'], b['units'], vp, prompt_name, thinking, ratio,
                             None if a.expand_prompt else tier, only, vp.get('novel_texts'))
            owner[(vname, k)] = cs
            calls += cs
    rows = run_unique(relay, '%s-write-%s-%s' % (a.prefix, a.run, tag), calls)
    stop_on_lost(rows, 'write', a)
    written = {}
    for (vname, k), cs in owner.items():
        b = books[k]
        vp, only = vplans[(vname, k)]
        log = []
        per_chapter = defaultdict(list)
        for c in cs:
            per_chapter[c['meta']['chapter']].append(c)
        chapters = {}
        drafts = drafts_by_question(b['handoff'])
        for ci, ch in enumerate(vp['chapters']):
            if ci not in only:
                continue
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
            chapters[ci] = secs
        written[(vname, k)] = {'chapters': chapters, 'log': log}
        mb.save(run_dir / vname / 'written' / (k + '.json'), {'chapters': [chapters.get(ci) for ci in range(len(vp['chapters']))], 'log': log})
    if a.expand_prompt:  # v2 round 3: tiers differ only here
        xcalls, xowner = [], {}
        for vname, _, _, tier in variants:
            if not tier:
                continue
            for k, b in books.items():
                vp, only = vplans[(vname, k)]
                w = written[(vname, k)]
                titles = ['%s　%s' % ('序章' if c['modules'][0] == 'skeleton' else '第%d章' % i, c['title'])
                          for i, c in enumerate(vp['chapters'], 0 if vp['chapters'][0]['modules'][0] == 'skeleton' else 1)]
                for ci in sorted(w['chapters']):
                    w['chapters'][ci] = deepcopy(w['chapters'][ci])  # tiers share the written fact layer object
                    c = expand_call(vname + '-' + k, ci, vp['chapters'][ci], w['chapters'][ci], b['units'], vp.get('novel_texts'),
                                    {'person': b['handoff']['person']['name'], 'motifs': vp.get('motifs') or b['plan']['motifs']},
                                    titles, tier, [], a.expand_prompt)
                    xcalls.append(c)
                    xowner[c['id']] = (vname, k, ci)
        xrows = run_unique(relay, '%s-expand-%s-%s' % (a.prefix, a.run, tag), xcalls)
        stop_on_lost(xrows, 'expand', a)
        xstats = defaultdict(dict)
        for cid, (vname, k, ci) in xowner.items():
            vp, _ = vplans[(vname, k)]
            ch = vp['chapters'][ci]
            allowed = {u for s0 in ch['sections'] for u in s0['units']} | set(ch['closing_units'])
            w = written[(vname, k)]
            w['chapters'][ci] = apply_expand(w['chapters'][ci], xrows.get(cid), allowed, a.simplify, xstats[(vname, k)])
        for (vname, k), st in xstats.items():
            written[(vname, k)]['expand_stats'] = st
            vp, _ = vplans[(vname, k)]
            mb.save(run_dir / vname / 'expanded' / (k + '.json'),
                    {'chapters': [written[(vname, k)]['chapters'].get(ci) for ci in range(len(vp['chapters']))], 'stats': st})
    if a.stop_after == 'write':
        return
    kcalls = []
    for (vname, k), w in written.items():
        b = books[k]
        vp, only = vplans[(vname, k)]
        for ci, ch in enumerate(vp['chapters']):
            if ci in only:
                kcalls.append(check_calls(vname + '-' + k, ci, ch, b['units'], w['chapters'][ci], b['handoff'], a.check_thinking, a.check_prompt))
    ingest = dict(x.split('=') for x in a.ingest.split(',') if x)
    if 'check' in ingest:
        print(json.dumps({'ingested': mb.ingest_staged(relay, ingest['check'], kcalls), 'of': len(kcalls)}), flush=True)
    rows = relay.run_batch('%s-check-%s-%s' % (a.prefix, a.run, tag), kcalls)
    stop_on_lost(rows, 'check', a)
    summary = {}
    for (vname, k), w in written.items():
        b = books[k]
        vp, only = vplans[(vname, k)]
        all_text = '\n'.join(u['raw'] for u in b['units'].values())
        drafts = drafts_by_question(b['handoff'])
        stats = {'model_issues': Counter(), 'fallback_reasons': Counter(), 'check_failed': 0, 'cross_cited': 0, 'code_flags': 0,
                 'dropped_added': 0, 'relabelled': 0, 'fallback_paragraphs': 0, 'fallback_empty': 0, 'pictures': 0,
                 'relabelled_picture': 0, **(w.get('expand_stats') or {})}
        chapters = []
        for ci, ch in enumerate(vp['chapters']):
            if ci not in only:
                continue
            secs = apply_checks(ch, b['units'], w['chapters'][ci], rows.get('k-%s-%s-c%d' % (vname, k, ci)), drafts, all_text, stats,
                                a.fallback)
            prior = {g for c0 in chapters for s0 in c0['sections'] for p0 in s0['paragraphs'] for x0 in p0['sentences']
                     for g in _grams(x0['t'])} if vp.get('novel_texts') else None
            secs = backfill(ch, secs, b['units'], drafts, a.backfill, stats, vp.get('novel_texts'), prior)
            chapters.append({'title': ch['title'], 'modules': ch['modules'], 'budget': ch['budget'], 'sections': secs,
                             'novel_chars': ch.get('novel_chars'),
                             'title_quote': ch.get('title_quote'), 'title_source': ch.get('title_source'),
                             'units': [u for s in ch['sections'] for u in s['units']] + list(ch['closing_units'])})
        if a.dedupe:
            chapters = dedupe(chapters, stats)
        for c0 in chapters:  # a renamed label section may take the title of an earlier section: it reads on under it
            titles0 = set()
            for s0 in c0['sections']:
                if s0.get('title') in titles0:
                    s0['title'] = ''
                    stats['dup_titles'] = stats.get('dup_titles', 0) + 1
                elif s0.get('title'):
                    titles0.add(s0['title'])
        if a.short_merge:
            written_chars = lambda c: sum(mb.han_len(x['t']) for s2 in c['sections'] for p2 in s2['paragraphs'] for x in p2['sentences'])  # noqa: E731
            chapters = merge_short(chapters, written_chars, w['log'], 'written', a.short_merge)
        book = {'person': b['handoff']['person'], 'material': b['handoff']['material'], 'variant': vname, 'edition': a.edition,
                'tier': ({'name': tiers_name, 'ratio': TIERS[tiers_name][0], 'label': TIERS[tiers_name][1]}
                         if (tiers_name := next(t for n, _, _, t in variants if n == vname)) else None),
                'modules_only': sorted(only_modules) or None,
                'chapters': chapters, 'motifs': b['plan']['motifs'],
                'not_written': {'private': b['plan']['private'], 'unused': b['plan']['unused'],
                                'declined': [d for q in b['handoff']['questions'] for d in q['markers']['declined']]},
                'units': {u: {'qid': x['qid'], 'asked': x['asked'], 'text': x['raw']} for u, x in b['units'].items()},
                'log': vp['log'] + w['log']}
        mplan = {'chapters': [c for ci, c in enumerate(vp['chapters']) if ci in only], 'novel_texts': vp.get('novel_texts')}
        book['metrics'] = metrics(book, b['units'], mplan)
        book['metrics']['pipeline'] = {k2: (dict(v) if isinstance(v, Counter) else v) for k2, v in stats.items()}
        mb.save(run_dir / vname / 'books' / (k + '.json'), book)
        render.write_all(book, run_dir / vname / 'books' / k)
        summary['%s/%s' % (vname, k)] = {x: book['metrics'][x] for x in ('chars', 'elder_chars', 'ratio_to_elder', 'copy_ratio', 'added_ratio',
                                                                           'added_char_ratio', 'unsupported_tokens', 'unit_use', 'novel_unit_use',
                                                                           'ratio_to_novel',
                                                                           'mean_abs_deviation', 'fallback_paragraphs', 'added_types',
                                                                           'added_opening_repeat', 'looking_back_openers',
                                                                           'cross_chapter_repeats')}
        summary['%s/%s' % (vname, k)]['pipeline'] = book['metrics']['pipeline']
    mb.save(run_dir / 'summary.json', summary)
    mb.save(run_dir / 'usage.json', {'calls_sent': relay.calls_sent, 'calls_cached': relay.calls_cached, 'usage': relay.usage})
    print(json.dumps({'summary': summary, 'calls_sent': relay.calls_sent, 'usage': relay.usage}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
