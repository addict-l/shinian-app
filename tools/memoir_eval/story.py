"""Book layer v3 (BRIEF11, 2026-11-03): one story is written once, and tighter added writing.

  plan   prompts/plan-v5.txt (thinking on, one call per book): every sentence of every answer is assigned to a story
         (the elder retells the same story in many answers, in other words each time), and each story is placed in
         exactly one section of one chapter; other chapters only echo it in one marked sentence.
  write  prompts/write-v7.txt: each section gets its stories with all their tellings (near-identical sentences of a
         story removed), merged into one telling.
  fill   prompts/fill-v1.txt: source sentences whose content bigrams are not in the chapter's text come back as
         inserted fact sentences (v2 lost details: unit use 0.66).
  expand prompts/expand-v2.txt (as v2, tighter rules for pictures and other people).
  check  prompts/check-v6.txt: + 替人编 (another person's routine / gesture / line / motive), + nouns of added sentences.
  guard  code, after the check: an added sentence is dropped when a concrete noun in it (lexicon or the check's noun
         list) is not in the elder's words, when it gives another person an action / routine / thought that the
         chapter's words do not have, when it repeats a stock closing or an opening already used.

Imported by book.py (--stories); also ``python3 story.py metrics BOOK.json ...`` prints the v3 code metrics of any book
(v2 books too, for the comparison table).
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict

import mb

_SENT = re.compile(r'[^。！？!?；;…\n]+[。！？!?；;…]*')
_NORM = re.compile(r'[^一-鿿0-9A-Za-z]')
_HAN = re.compile(r'[一-鿿]')
FILLER = re.compile(r'(想不起来了|没什么要补充|没有要补充|没有了[，。]|就是这些|就这些了|都跟您讲了|都讲了|没别的了|别的也没什么|也没什么了|没有别的|别的就没|'
                    r'说不上来了|讲不出什么|不乱讲|不敢乱说|不好乱说|'
                    r'没什么补冲|补冲的了|就这些|歇会儿|先歇|有点累了|说不好|说不上来|没想过什么标准|先不讲了)')
BOOK_CAP = 20000  # user decision 2026-11-03 10:04: a book of about 15-20 thousand characters


def split(text):
    return [s.strip() for s in _SENT.findall(text or '') if s.strip()]


def norm(text):
    return _NORM.sub('', mb.t2s(text or ''))


def grams(text, n=4):
    t = norm(text)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def cover(text, gs, n=4):
    g = grams(text, n)
    return len(g & gs) / len(g) if g else 0.0


# --------------------------------------------------------------------------- plan
def numbered(text):
    return ''.join('〔%d〕%s' % (i, s) for i, s in enumerate(split(text), 1))


def plan_call(key, handoff, units, prompt_name, groups, params):
    chapters = []
    for group in groups:
        us = [u for u in units.values() if u['module'] in group and u['text']]
        if not us:
            continue
        name = '序章（开篇）' if group[0] == 'skeleton' else ' · '.join(mb.MODULE_NAME[m] for m in group)
        chapters.append({'module': group[0], 'name': name,
                         'units': [{'id': u['id'], 'question': u['qid'], 'depth': u['depth'], 'asked': u['asked'],
                                    'time_clues': u['clues'], 'text': numbered(u['text'])} for u in us]})
    user = {'person': handoff['person']['name'], 'chapters': chapters}
    return {'id': 'plan-' + key, 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False), 'params': params}


def parse_sents(spec, n):
    """'all' | '1-3' | '2,4' | 3 | [1, 2] -> sorted 1-based indices within 1..n."""
    if spec is None or (isinstance(spec, str) and spec.strip().lower() in ('all', '全部', '')):
        return list(range(1, n + 1))
    if isinstance(spec, int):
        return [spec] if 1 <= spec <= n else []
    if isinstance(spec, list):
        out = []
        for x in spec:
            out += parse_sents(x, n)
        return sorted(set(out))
    out = set()
    for part in re.split(r'[,，、\s]+', str(spec)):
        m = re.match(r'^(\d+)\s*[-–~～至到]\s*(\d+)$', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out |= {i for i in range(min(a, b), max(a, b) + 1) if 1 <= i <= n}
        elif part.isdigit() and 1 <= int(part) <= n:
            out.add(int(part))
    return sorted(out)


def majority_module(sent_keys, units, sents):
    c = Counter()
    for u, i in sent_keys:
        c[units[u]['module']] += mb.han_len(sents[u][i - 1])
    order = [m for m, _, _ in mb.MODULES]
    return min(c, key=lambda m: (-c[m], order.index(m))) if c else None


def resolve(handoff, units, row, groups, module_id, cap_total=BOOK_CAP):
    """The planner's stories and chapters -> a book plan whose sections carry their stories' tellings (and v2 fields:
    units, budget, novel_chars, closing_units=[]). Every repair is logged."""
    log = []
    out = (row or {}).get('output') if (row or {}).get('ok') else None
    if not isinstance(out, dict):
        log.append('plan_failed:' + str((row or {}).get('error') or (row or {}).get('parse_error')))
        out = {}
    sents = {u: split(x['text']) for u, x in units.items() if x['text']}
    private, unused, skip = [], [], set()
    for p in out.get('private') or []:
        if isinstance(p, dict) and p.get('unit') in sents and p.get('quote') and p['quote'] in units[p['unit']]['text']:
            private.append(p)
            for i, s in enumerate(sents[p['unit']], 1):
                if norm(s) and (norm(s) in norm(p['quote']) or norm(p['quote']) in norm(s)):
                    skip.add((p['unit'], i))
    for p in out.get('unused') or []:
        if isinstance(p, dict) and p.get('unit') in sents:
            idx = parse_sents(p.get('sents'), len(sents[p['unit']]))
            # only closers may be left out: a sentence with real content stays in the book
            idx = [i for i in idx if FILLER.search(sents[p['unit']][i - 1]) or mb.han_len(sents[p['unit']][i - 1]) <= 6]
            if idx:
                unused.append(dict(p, sents=idx))
                skip |= {(p['unit'], i) for i in idx}
    owner, stories, order = {}, {}, []
    for st in out.get('stories') or []:
        if not isinstance(st, dict) or not st.get('id') or st['id'] in stories:
            continue
        sid = str(st['id'])
        keys = []
        for part in st.get('parts') or []:
            if not isinstance(part, dict) or part.get('unit') not in sents:
                continue
            for i in parse_sents(part.get('sents'), len(sents[part['unit']])):
                k = (part['unit'], i)
                if k not in owner and k not in skip:
                    owner[k] = sid
                    keys.append(k)
        stories[sid] = {'id': sid, 'title': str(st.get('title') or ''), 'gist': str(st.get('gist') or ''),
                        'kind': st.get('kind') if st.get('kind') in ('story', 'fact', 'reflection') else 'story', 'keys': keys}
        order.append(sid)
    # sentences the planner left out: next to their unit's nearest assigned sentence, or a repair story per question
    left = 0
    for u, ss in sents.items():
        free = [i for i in range(1, len(ss) + 1) if (u, i) not in owner and (u, i) not in skip]
        if not free:
            continue
        had = [i for i in range(1, len(ss) + 1) if (u, i) in owner]
        for i in free:
            if FILLER.search(ss[i - 1]) and mb.han_len(ss[i - 1]) <= 20:
                skip.add((u, i))
                continue
            left += 1
            if had:
                j = min(had, key=lambda h: (abs(h - i), h > i))
                sid = owner[(u, j)]
            else:
                sid = 'R-' + units[u]['qid']
                if sid not in stories:
                    stories[sid] = {'id': sid, 'title': mb.catalog()[units[u]['qid']]['title'], 'gist': '', 'kind': 'story',
                                    'keys': [], 'repair': True}
                    order.append(sid)
            owner[(u, i)] = sid
            stories[sid]['keys'].append((u, i))
    if left:
        log.append('sentences_not_planned:%d' % left)
    for st in stories.values():  # keep the tellings in the planner's unit order, sentences in their own order
        first = {}
        for u, i in st['keys']:
            first.setdefault(u, len(first))
        st['keys'] = sorted(set(k for k in st['keys'] if owner.get(k) == st['id']), key=lambda k: (first[k[0]], k[1]))
    stories = {k: v for k, v in stories.items() if v['keys']}
    order = [s for s in order if s in stories]
    # placement: each story once
    head = {g[0]: g[0] for g in groups}
    chapters, placed = {}, {}
    for c in out.get('chapters') or []:
        mod = module_id(c.get('module') if isinstance(c, dict) else None, None)
        if mod not in head:
            log.append('plan_bad_module:%s' % (c.get('module') if isinstance(c, dict) else c))
            continue
        ch = chapters.setdefault(mod, {'modules': [mod], 'title': None, 'sections': [], 'echo_ids': []})
        quote, src = c.get('title_quote') or '', c.get('title_source')
        if c.get('title') and quote and quote in (c.get('title') or '') and src in units and quote in units[src]['raw']:
            ch['title'], ch['title_quote'], ch['title_source'] = c['title'], quote, src
        elif c.get('title'):
            log.append('title_not_grounded:%s:%s' % (mod, c.get('title')))
        for s in c.get('sections') or []:
            if not isinstance(s, dict):
                continue
            ids = []
            for x in s.get('stories') or []:
                x = str(x)
                if x in stories and x not in placed:
                    placed[x] = mod
                    ids.append(x)
                elif x in placed:
                    log.append('story_placed_twice:%s' % x)
            if ids:
                ch['sections'].append({'title': s.get('title') or stories[ids[0]]['title'], 'stories': ids})
        closing = [str(x) for x in c.get('closing') or [] if str(x) in stories and str(x) not in placed]
        for x in closing:
            placed[x] = mod
        if closing:
            ch['closing'] = closing
        for e in c.get('echoes') or []:
            x = str(e.get('story') if isinstance(e, dict) else e)
            if x in stories and x not in ch['echo_ids']:
                ch['echo_ids'].append(x)
    # v3 it2: a repair story (an answer the planner left out entirely) joins the planned story it shares most content
    # with (same module first) instead of becoming a section of its own under a question-bank label ("本人认定的中年收获")
    planned = [x for x in order if x in placed and not stories[x].get('repair')]
    pb = {x: set().union(*[content_bigrams(sents[u][i - 1]) for u, i in stories[x]['keys']] or [set()]) for x in planned}
    for sid in [x for x in order if stories[x].get('repair') and x not in placed]:
        keys = stories[sid]['keys']
        bg = set().union(*[content_bigrams(sents[u][i - 1]) for u, i in keys] or [set()])
        mod = majority_module(keys, units, sents)
        best, score = None, 0.0
        for x in planned:
            ov = len(bg & pb[x]) / max(1, len(bg))
            ov += 0.15 if placed[x] == mod else 0.0
            if ov > score:
                best, score = x, ov
        if best and (score >= 0.3 or sum(mb.han_len(sents[u][i - 1]) for u, i in keys) < 40):
            for k in keys:
                owner[k] = best
            stories[best]['keys'] += keys
            pb[best] |= bg
            stories[sid]['keys'] = []
            log.append('repair_merged:%s->%s(%.2f)' % (sid, best, score))
    stories = {k: v for k, v in stories.items() if v['keys']}
    order = [s for s in order if s in stories]
    for sid in order:  # stories the planner did not place: in the chapter of the module most of their words come from
        if sid in placed or not stories[sid]['keys']:
            continue
        m = majority_module(stories[sid]['keys'], units, sents)
        ch = chapters.setdefault(m, {'modules': [m], 'title': None, 'sections': [], 'echo_ids': []})
        kind = stories[sid]['kind']
        if kind == 'reflection':
            ch.setdefault('closing', []).append(sid)
        else:
            ch['sections'].append({'title': stories[sid]['title'], 'stories': [sid], 'repair': True})
        placed[sid] = m
        log.append('story_not_placed:%s->%s' % (sid, m))
    # v3 it2: a whole answer goes to one story ("all"), so a remark of a later module that does not retell the story
    # ("人在一起，日子就有个盼头" inside an answer about the borrowed rice field) went to the childhood chapter; such a
    # sentence (content bigrams covered < 0.35 by the rest of its story) goes back to its own module's chapter-end
    moved = defaultdict(list)
    for sid in list(order):
        m0 = placed.get(sid)
        if m0 is None or stories[sid]['kind'] == 'reflection':
            continue
        for u, i in list(stories[sid]['keys']):
            mu = units[u]['module']
            if mu not in ('family', 'later_life', 'reflection') or mu == m0 or mu not in head:
                continue
            t = sents[u][i - 1]
            bg = content_bigrams(t)
            if mb.han_len(t) < 6 or len(bg) < 3 or (FILLER.search(t) and mb.han_len(t) <= 20):
                continue
            rest = set().union(*[content_bigrams(sents[u2][i2 - 1]) for u2, i2 in stories[sid]['keys'] if (u2, i2) != (u, i)] or [set()])
            if len(bg & rest) / len(bg) < 0.35:
                stories[sid]['keys'].remove((u, i))
                moved[mu].append((u, i))
    for mu, keys in moved.items():
        vid = 'V-' + mu
        stories[vid] = {'id': vid, 'title': mb.MODULE_NAME[mu], 'gist': '', 'kind': 'reflection', 'keys': sorted(keys), 'repair': True}
        for k in keys:
            owner[k] = vid
        order.append(vid)
        placed[vid] = mu
        chapters.setdefault(mu, {'modules': [mu], 'title': None, 'sections': [], 'echo_ids': []}).setdefault('closing', []).append(vid)
        log.append('remark_moved:%s(%d sentences)' % (mu, len(keys)))
    # six chapters: a module with material keeps a chapter
    have = [g[0] for g in groups]
    for m in have:
        ch = chapters.get(m)
        if ch and (ch['sections'] or ch.get('closing')):
            continue
        def movable(sid):  # taking the story away must not empty the chapter it is in now
            c0 = chapters.get(placed.get(sid))
            if not c0:
                return True
            rest = [x for s0 in c0['sections'] for x in s0['stories'] if x != sid] + [x for x in c0.get('closing') or [] if x != sid]
            return bool(rest)
        own = [sid for sid in order if majority_module(stories[sid]['keys'], units, sents) == m and movable(sid)]
        if own:
            sid = max(own, key=lambda s: sum(mb.han_len(sents[u][i - 1]) for u, i in stories[s]['keys']))
            for c0 in chapters.values():
                for s0 in c0['sections']:
                    s0['stories'] = [x for x in s0['stories'] if x != sid]
                c0['sections'] = [s0 for s0 in c0['sections'] if s0['stories']]
                if c0.get('closing'):
                    c0['closing'] = [x for x in c0['closing'] if x != sid]
            log.append('module_restored:%s(story %s)' % (m, sid))
        else:  # split this module's sentences out of the stories that hold them
            keys = [k for k in owner if units[k[0]]['module'] == m and owner[k] in stories]
            if not keys:
                continue
            sid = 'M-' + m
            for k in keys:
                stories[owner[k]]['keys'].remove(k)
                owner[k] = sid
            stories[sid] = {'id': sid, 'title': mb.MODULE_NAME[m], 'gist': '', 'kind': 'story', 'keys': sorted(keys), 'repair': True}
            order.append(sid)
            log.append('module_split:%s(%d sentences)' % (m, len(keys)))
        ch = chapters.setdefault(m, {'modules': [m], 'title': None, 'sections': [], 'echo_ids': []})
        ch['sections'] = [{'title': stories[sid]['title'], 'stories': [sid], 'repair': True}]
        placed[sid] = m
    for p in private:
        units[p['unit']]['text'] = units[p['unit']]['text'].replace(p['quote'], '').strip()
    # tellings: near-identical sentences of a story (4-gram coverage >= 0.7 by the story's earlier sentences) and
    # closers are not given; novel chars (v2 rule, 0.5 by everything earlier in the book) set the budget
    book_seen = set()
    module_order = [m for m, _, _ in mb.MODULES]
    book = []
    for m in module_order:
        ch = chapters.get(m)
        if not ch or not (ch['sections'] or ch.get('closing')):
            continue
        secs = list(ch['sections'])
        if ch.get('closing'):
            secs.append({'title': '', 'stories': ch['closing'], 'role': 'closing'})
        for s in secs:
            s['story_meta'], s['units'], s['novel_chars'] = [], [], 0
            for sid in s['stories']:
                st, seen_st, tell = stories[sid], set(), {}
                for u, i in st['keys']:
                    t = sents[u][i - 1]
                    if (u, i) in skip:
                        continue
                    g = grams(t)
                    if FILLER.search(t) and mb.han_len(t) <= 20:
                        continue
                    if g and len(g & seen_st) / len(g) >= 0.7:
                        continue
                    if g and len(g & book_seen) / len(g) < 0.5:
                        s['novel_chars'] += mb.han_len(t)
                    seen_st |= g
                    book_seen |= g
                    tell.setdefault(u, []).append(t)
                st['tellings'] = [{'id': u, 'asked': units[u]['asked'], 'text': ''.join(ts)} for u, ts in tell.items()]
                s['story_meta'].append({'id': sid, 'title': st['title'], 'gist': st['gist'], 'kind': st['kind'],
                                        'tellings': st['tellings']})
                s['units'] += [u for u in tell if u not in s['units']]
        secs = [s for s in secs if s['units']]
        if not secs:
            continue
        ch['sections'] = secs
        ch['closing_units'] = []
        ch['novel_chars'] = sum(s['novel_chars'] for s in secs)
        ch['elder_chars'] = sum(mb.han_len(t['text']) for s in secs for x in s['story_meta'] for t in x['tellings'])
        for s in secs:
            s['elder_chars'] = sum(mb.han_len(t['text']) for x in s['story_meta'] for t in x['tellings'])
        cap = int(mb.SHARE[m] * cap_total)
        scale = min(1.0, cap / ch['novel_chars']) if ch['novel_chars'] else 1.0
        if scale < 1:
            log.append('chapter_capped:%s(%d->%d)' % (m, ch['novel_chars'], cap))
        for s in secs:
            s['budget'] = int(s['novel_chars'] * scale)
        ch['budget'] = sum(s['budget'] for s in secs)
        ch['cap'] = cap
        ch['echo_ids'] = [x for x in ch['echo_ids'] if placed.get(x) not in (None, m)][:2]
        ch['echoes'] = [{'story': x, 'title': stories[x]['title'], 'gist': stories[x]['gist'], 'chapter_module': mb.MODULE_NAME[placed[x]],
                         'units': list(dict.fromkeys(u for u, _ in stories[x]['keys']))} for x in ch['echo_ids']]
        ch['echo_units'] = [u for e in ch['echoes'] for u in e['units']]
        if not ch['title']:
            ch['title'] = mb.MODULE_NAME[m]
            log.append('title_fallback:' + m)
        book.append(ch)
    motifs = [x for x in out.get('motifs') or [] if isinstance(x, dict) and x.get('source') in units
              and x.get('quote') and x['quote'] in units[x['source']]['raw']]
    habits = [h for h in out.get('voice_habits') or [] if isinstance(h, str) and any(h in u['raw'] for u in units.values())]
    return {'chapters': book, 'motifs': motifs, 'private': private, 'unused': unused, 'voice_habits': habits[:8], 'moves': [],
            'stories': {k: {x: v[x] for x in ('id', 'title', 'gist', 'kind')} | {'units': list(dict.fromkeys(u for u, _ in v['keys'])),
                                                                                 'chapter': placed.get(k), 'keys': [list(x) for x in v['keys']]}
                        for k, v in stories.items()},
            'log': log}


# --------------------------------------------------------------------------- write
LABEL_TITLE = re.compile(r'(本人|评价|程度|特质|认定|或错过|情况$|方面$|经历$)')


def write_calls(key, handoff, units, plan, prompt_name, params, part_sections=2, only=None):
    calls = []
    titles = ['%s　%s（%s）' % ('序章' if c['modules'][0] == 'skeleton' else '第%d章' % i, c['title'], ' · '.join(mb.MODULE_NAME[m] for m in c['modules']))
              for i, c in enumerate(plan['chapters'], 0 if plan['chapters'][0]['modules'][0] == 'skeleton' else 1)]
    unknown = [{'unit': d.get('source_id'), 'quote': d['quote']} for q in handoff['questions'] for d in q['markers']['unknown'] if d.get('quote')]
    voice = {'称呼': list(handoff['voice']['kin_terms']), '口头语': plan['voice_habits']}
    system = mb.prompt(prompt_name)
    for ci, ch in enumerate(plan['chapters']):
        if only is not None and ci not in only:
            continue
        idx = list(range(len(ch['sections'])))
        parts = [idx[i:i + part_sections] for i in range(0, len(idx), part_sections)] if part_sections else [idx]
        for pi, ids in enumerate(parts):
            last = pi == len(parts) - 1
            secs = []
            for i in ids:
                s = ch['sections'][i]
                secs.append({'title': s['title'], 'budget_chars': s['budget'],
                             **({'role': 'closing'} if s.get('role') == 'closing' else {}),
                             **({'rename': True} if s['title'] and LABEL_TITLE.search(s['title']) else {}),
                             'stories': [{'title': x['title'], 'gist': x['gist'], 'tellings': x['tellings']} for x in s['story_meta']]})
            given = {t['id'] for x in secs for st in x['stories'] for t in st['tellings']}
            user = {'book': {'person': handoff['person']['name'], 'chapters': titles, 'motifs': plan['motifs']},
                    'chapter': {'index': titles[ci], 'modules': [mb.MODULE_NAME[m] for m in ch['modules']], 'title': ch['title'],
                                'budget_chars': sum(x['budget_chars'] for x in secs), 'part': '%d/%d' % (pi + 1, len(parts)),
                                'is_last_part': last, 'sections': secs},
                    'echoes': [{'story_units': e['units'], 'title': e['title'], 'gist': e['gist'], 'told_in': e['chapter_module']}
                               for e in ch['echoes']] if last else [],
                    'voice': voice, 'unknown': [u for u in unknown if u['unit'] in given]}
            calls.append({'id': 'w-%s-c%d-p%d' % (key, ci, pi), 'system': system, 'user': json.dumps(user, ensure_ascii=False),
                          'params': params, 'meta': {'chapter': ci, 'part': pi, 'sections': ids}})
    return calls


# --------------------------------------------------------------------------- fill (details the writer dropped)
STOP2 = set('我们 你们 他们 她们 那个 这个 就是 时候 一个 没有 什么 然后 因为 所以 还是 可以 自己 知道 觉得 不是 那时 这些 那些 '
            '的话 也是 都是 一些 这样 那样 怎么 现在 后来 已经 还有 比较 反正 其实 当时 那么 这么 一直 一下 起来 出来 过来 '
            '的时 了一 我就 我也 他就 了我 我爸 我妈 我家 家里 不过 但是 可是 只是 而且 还算 算是 应该 可能 好像 大概'.split())


def content_bigrams(text):
    t = ''.join(_HAN.findall(mb.t2s(text or '')))
    return {t[i:i + 2] for i in range(len(t) - 1)} - STOP2


def unit_df(units):
    """In how many answers each content bigram occurs: a bigram in at most two answers is a specific detail word."""
    return Counter(g for x in units.values() for g in content_bigrams(x.get('raw') or x.get('text')))


def specific(text, udf, max_df=2):
    return {g for g in content_bigrams(text) if udf.get(g, 0) <= max_df}


def missed(ch, secs, udf, threshold=0.5, min_chars=8):
    """Source sentences of a chapter's tellings with at least two specific detail bigrams (in at most two answers of the
    book) of which the written chapter has less than ``threshold``."""
    written = ' '.join(x['t'] for s in secs for p in s['paragraphs'] for x in p['sentences'])
    wg = content_bigrams(written)
    out = []
    for s in ch['sections']:
        for st in s['story_meta']:
            for t in st['tellings']:
                for x in split(t['text']):
                    if mb.han_len(x) < min_chars or (FILLER.search(x) and mb.han_len(x) <= 20) or \
                            (mb.UNKNOWN.search(x) and mb.han_len(x) <= 16):
                        continue
                    g = specific(x, udf)
                    if len(g) >= 2 and len(g & wg) / len(g) < threshold:
                        if out and out[-1]['unit'] == t['id'] and out[-1]['section'] == s['title']:
                            out[-1]['text'] += x
                        else:
                            out.append({'unit': t['id'], 'asked': t['asked'], 'text': x, 'section': s['title']})
    return out


def fill_call(key, ci, ch, secs, prompt_name, params, udf):
    miss = missed(ch, secs, udf)
    if not miss:
        return None
    sents = []
    for si, s in enumerate(secs):
        for pi, p in enumerate(s['paragraphs']):
            for k, x in enumerate(p['sentences']):
                x['xid'] = 's%d.p%d.%d' % (si, pi, k)
                sents.append({'sid': x['xid'], 't': x['t'], 'section': s['title']})
    user = {'chapter': {'title': ch['title']}, 'sentences': sents, 'missed': miss}
    return {'id': 'f-%s-c%d' % (key, ci), 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False),
            'params': params, 'meta': {'missed': len(miss), 'missed_chars': sum(mb.han_len(m['text']) for m in miss)}}


def apply_inserts(secs, out, allowed, simplify, stats, fact=False, key='expand'):
    """Insert sentences after their anchors (xid). fact=True: fill sentences (add None, 'filled')."""
    from book import ADD_TYPES
    ins = defaultdict(list)
    for it in (out or {}).get('insert') or [] if isinstance(out, dict) else []:
        if not isinstance(it, dict):
            continue
        t = (it.get('t') or '').strip()
        if simplify:
            t = mb.simplify(t)
        if not t:
            continue
        src = [u for u in (it.get('src') or []) if u in allowed]
        if fact:
            ins[str(it.get('after'))].append({'t': t, 'src': src, 'add': None, 'filled': True})
        else:
            add = it.get('add') if it.get('add') in ADD_TYPES else '感受'
            ins[str(it.get('after'))].append({'t': t, 'src': src, 'add': add, 'expanded': True})
    known = {x.get('xid') for s in secs for p in s['paragraphs'] for x in p['sentences']}
    stats[key + '_inserted'] = stats.get(key + '_inserted', 0) + sum(len(v) for k, v in ins.items() if k in known)
    stats[key + '_unanchored'] = stats.get(key + '_unanchored', 0) + sum(len(v) for k, v in ins.items() if k not in known)
    new = []
    for s in secs:
        paras = []
        for p in s['paragraphs']:
            ss = []
            for x in p['sentences']:
                ss.append({k: v for k, v in x.items() if k != 'xid'})
                ss.extend(dict(y) for y in ins.get(x.get('xid'), []))
            paras.append(dict(p, sentences=ss))
        new.append(dict(s, paragraphs=paras))
    return new


BANNED_OPENINGS = ['现在想想', '现在想起来', '如今想来', '回头看', '回想起来', '我记得', '有一回', '那天', '那些日子', '那段日子',
                   '这份情', '说起来', '想起', '那时候的光景']


def expand_call(key, ci, ch, secs, plan, titles, tier, prompt_name, params, k):
    from book import TIERS
    sents = []
    for si, s in enumerate(secs):
        for pi, p in enumerate(s['paragraphs']):
            for j, x in enumerate(p['sentences']):
                x['xid'] = 's%d.p%d.%d' % (si, pi, j)
                sents.append({'sid': x['xid'], 't': x['t'], 'add': x['add'], 'section': s['title']})
    facts = sum(mb.han_len(x['t']) for x in sents if not x['add'])
    target = int(facts * k)  # the book cap scales k in book.py (a chapter over its share may still be expanded)
    tell = defaultdict(list)
    for s in ch['sections']:
        for st in s['story_meta']:
            for t in st['tellings']:
                tell[t['id']].append(t['text'])
    user = {'book': {'person': plan['person'], 'chapters': titles, 'motifs': plan['motifs']},
            'chapter': {'title': ch['title'], 'tier': TIERS[tier][1], 'target_added_chars': target,
                        'target_sentences': max(1, round(target / 24))},
            'sentences': sents,
            'sources': [{'id': u, 'text': ''.join(ts)} for u, ts in tell.items()],
            'banned_openings': BANNED_OPENINGS}
    return {'id': 'x-%s-c%d' % (key, ci), 'system': mb.prompt(prompt_name), 'user': json.dumps(user, ensure_ascii=False),
            'params': params}


# --------------------------------------------------------------------------- guards on added sentences (code)
# concrete nouns the expansion invented in v2 / v1 holdout, and their neighbours in a rural / school memoir: an added
# sentence with one of these that the elder never said is dropped
LEXICON = set('''扁担 锄头 镰刀 箩筐 簸箕 麻袋 化肥 农药 犁头 水车 打谷机 拖拉机 牛车 板车 独轮车 斗笠 蓑衣 草帽 水桶 木桶 竹篮 篮子 背篓 竹竿 绳子 秤杆 秤
堂屋 灶台 灶房 灶膛 厨房 门槛 门框 院子 院坝 天井 屋檐 瓦片 青瓦 土墙 泥墙 窗户 窗台 窗棂 阁楼 楼梯 炕头 床头 床板 被子 蚊帐 席子 枕头 桌子 八仙桌 板凳 凳子 椅子 柜子 箱子 抽屉 门板
油灯 煤油灯 马灯 蜡烛 灯泡 电灯 手电筒 火柴 炉子 火盆 柴火 烟囱 炊烟 灯芯
田埂 地头 晒谷场 晒场 打谷场 粮站 供销社 公社 大队部 祠堂 庙里 水井 井边 池塘 山路 小路 土路 马路 车站 码头 集市 渡口 桥头 村口 路口
操场 教室 办公室 宿舍 食堂 礼堂 讲台 黑板 粉笔 课桌 讲桌 工地 车间 厂房 医院 病房 走廊 校门 大门 院门 旗杆
电话 电话铃 电视 收音机 缝纫机 手表 钢笔 本子 账本 钥匙 信封 照片 相片 奖状 课本 书包 算盘 存折 钱包 粮票 布票 饭盒 饭碗 搪瓷缸 茶缸 茶杯 香烟 旱烟 烟斗 烟袋 酒杯 鞭炮 对联 红纸 年画 两道杠 红领巾 袖章 喇叭 广播
茧子 老茧 皱纹 白发 补丁 布鞋 草鞋 棉袄 围裙 头巾 手套 背影 眉头 额头 肩膀 烟头 汗衫
米饭 稀饭 红薯 地瓜 馒头 咸菜 腊肉 鸡蛋 面条 米汤
稻叶 稻秆 汗珠子 汗珠 汗味 笔尖 纸上 门口 门前 窝里 稻穗 稻芒 稻草 秧苗 禾苗 麦子 麦穗 玉米 青蛙 知了 蝉鸣 蛙声 鸡叫 狗叫 牛棚 猪圈 鸡窝'''.split())
# v3 it2: one-character objects (no word segmenter here): an added sentence naming one the elder never said is dropped
OBJECT_CHARS = '纸笔门窗灯桌椅凳床碗筷锅灶墙瓦砖井伞镜钟鞋帽叶窝箱柜盆桶绳'
GENERIC_NOUN = set('''手 脚 脸 头 眼 眼睛 背 背上 心 心里 心头 肩 腿 嗓子 鼻子 耳朵 嘴 手心 手指 手上 身上 脚下 脚底 胳膊 腰 汗 眼泪
腰 腰杆 身子 个子 数字 天黑 天亮 太阳 阳光 日头 月亮 星星 风 雨 雪 天 天色 天气 光 声音 气味 味道 夜 夜里 早上 晚上 白天 日子 时候 事 事情 话 那年 那时 年头 一家人 家 家里 我'''.split())
OTHERS = re.compile(r'^(他们|她们|他|她|我爸爸|我爸|爸爸|我爹|父亲|我妈妈|我妈|妈妈|母亲|我娘|爹|娘|我哥|哥哥|我姐|姐姐|弟弟|妹妹|老伴|爱人|妻子|丈夫|老婆|媳妇|'
                    r'儿子|女儿|孩子们|孩子|学生们|学生|老师们|老师|校长|主任|同事们|同事|同学们|同学|大人们|大人|村里人|乡亲们|人家|大家|家里人|家里|亲戚们|亲戚|别人)')
LEAD = re.compile(r'^(?:可是|但是|不过|所以|而且|其实|反正|只是|倒是|那时候|那时|那阵子|那几年|那些年|后来|当时|每次|每回|有时候|平时|平日里|'
                  r'[可但就也还又却都])+')
ACTION = re.compile(r'(拍了?拍|拍着|蹲在|蹲着|抽烟|抽着|叼着|皱着?眉|皱过|笑了|笑着|都是笑|叹气|叹了|摸了?摸|摸着|握着|攥着|点了?点头|点头|摇了?摇头|摇头|低着头|'
                    r'抬起头|望着|盯着|看着我|瞪|递给|端着|扛着|挑着|弯腰|弯着|背着手|搓着|擦了?擦|抹了?把|拉着|牵着|抱着|站在|坐在|走路|轻快|进进出出|忙活|'
                    r'忙前忙后|下地|下田|出门|回来|吃饭都|吃不下|睡不着|手上|脸上|身上|身子|满身|满头|汗味|背影|眼里|眼圈|嘴上|嘴里|沉默|没吭声|不吭声|一声不吭|嘀咕|吆喝|红了眼)')
ROUTINE = re.compile(r'(天不亮|天没亮|起早贪黑|天黑透|天黑才|一大早|每天|天天|整天|总是|常常|从来不|从不|一辈子|一年到头|没日没夜|早出晚归)')
PSYCH = re.compile(r'(心里|心想|想着|觉得|明白|知道|盼着|指望|希望|高兴|难受|不好受|舍不得|担心|着急|放心|信得过|是想|为了|就为|咽|憋着|委屈|骄傲|得意|'
                   r'满意|欣慰|心疼|疼我|想让|要我|怕我|看重|在乎|惦记)')
CLICHE = [('记得', re.compile(r'记到现在|记了一辈子|一直记着|一直记得|到现在还记得|到现在都记得|到现在[都还]?[闻看听想]得[着见到]|忘不了|没忘|记在心里|记一辈子')),
          ('回望', re.compile(r'现在想想|现在想起来|如今想来|回头看|回想起来|现在回头|如今回头|想起来就|现在回过头')),
          ('情', re.compile(r'这份情|那份情|那份心|这份心')),
          ('暖', re.compile(r'心里(头)?(暖|热乎)|暖暖的|暖烘烘')),
          ('日子', re.compile(r'那些日子|那段日子|那几年的日子')),
          ('值得', re.compile(r'值得|都值了|熬过来'))]


QUANTITY = re.compile(r'([0-9一二两三四五六七八九十几百千万]+\s*(?:亩|斤|块|毛|元|年|个月|天|回|次|口|趟|遍|岁|里|分|节|间|栋)|好多年|好些年|多少年|一摞一摞|一捆一捆)')
MEMORY = re.compile(r'记不[清真得太]|记不住|想不起|忘了|模糊')


def noun_found(n, raw_norm):
    n = norm(n)
    n = re.sub(r'^(我们|我的|我|他的|她的|那个|这个|那|这|一个|一)', '', n) or n
    if not n or n in GENERIC_NOUN or n in raw_norm:
        return True
    # v3 it3: a modifier + a noun the elder said ("一万斤稻谷", "那栋房子") is found by its head (the last two chars)
    return len(n) >= 3 and (n[1:] in raw_norm or n[:-1] in raw_norm or n[-2:] in raw_norm)


def clauses(text):
    return [c for c in re.split(r'[，,；;：:、。！？!?…—]+', mb.t2s(text)) if c.strip()]


def other_person_action(text, chapter_grams):
    """(marker, clause) when a clause whose subject is someone else (explicit, or carried over from the previous clause)
    has an action / routine / thought marker, unless the clause restates the chapter's words (3-gram cover >= 0.5)."""
    subj = None
    for c in clauses(text):
        c0 = LEAD.sub('', c.strip())
        m = OTHERS.match(c0)
        if m:
            subj = m.group(1)
        elif c0.startswith('我'):
            subj = None
        if not subj:
            continue
        hit = ACTION.search(c0) or ROUTINE.search(c0) or PSYCH.search(c0)
        if hit and cover(c0, chapter_grams, 3) < 0.5:
            return hit.group(1), c0
    return None


def guard(chapters, units, stats, by_sid_nouns=None):
    """Drop added sentences that bring in a noun the elder never said, give another person an action / routine / thought,
    repeat a stock closing family already used in the book, or reuse an opening (2 chars in a chapter, 3 chars twice in
    the book). Kept facts are untouched. Reasons are counted in stats['guard']."""
    raw_all = norm('\n'.join(u['raw'] for u in units.values()))
    reasons = Counter()
    used_family, open3 = set(), Counter()
    for c in chapters:
        cg = set()
        for u in c.get('units') or []:
            cg |= grams(units[u]['raw'], 3)
        open2 = Counter()
        for s in c['sections']:
            for p in s['paragraphs']:
                keep = []
                for x in p['sentences']:
                    if not x['add']:
                        keep.append(x)
                        continue
                    t = mb.t2s(x['t'])
                    why = None
                    lex = [w for w in LEXICON if w in t and not noun_found(w, raw_all)]
                    if lex:
                        why = 'noun_lexicon:' + lex[0]
                    if not why:
                        bad = [n for n in (x.get('nouns') or []) if isinstance(n, str) and not noun_found(n, raw_all)]
                        if bad:
                            why = 'noun_check:' + bad[0]
                    if not why:
                        oc = [ch for ch in OBJECT_CHARS if ch in t and ch not in raw_all]
                        if oc:
                            why = 'noun_char:' + oc[0]
                    if not why and x['add'] != '呼应':
                        hit = other_person_action(t, cg)
                        if hit:
                            why = 'other_person:' + hit[0]
                    if not why:  # v3 it3: quantities / durations and memory states belong to the elder's own words
                        q = QUANTITY.search(t)
                        if q and norm(q.group(0)) not in raw_all:
                            why = 'quantity:' + q.group(0)
                        elif MEMORY.search(t):
                            why = 'memory:' + MEMORY.search(t).group(0)
                    if not why and '一辈子' in t and '一辈子' not in raw_all:
                        why = 'cliche:一辈子'
                    if not why:
                        fam = [f for f, rx in CLICHE if rx.search(t)]
                        if any(f in used_family for f in fam):
                            why = 'cliche:' + fam[0]
                        else:
                            used_family |= set(fam)
                    if not why:
                        o2 = ''.join(_HAN.findall(t))[:2]
                        o3 = ''.join(_HAN.findall(t))[:3]
                        if open2[o2] >= 1 or open3[o3] >= 2:
                            why = 'opening:' + o2
                        else:
                            open2[o2] += 1
                            open3[o3] += 1
                    if why:
                        reasons[why.split(':')[0]] += 1
                        stats.setdefault('guard_dropped', []).append([x['add'], x['t'], why])
                        continue
                    keep.append(x)
                p['sentences'] = keep
            s['paragraphs'] = [p for p in s['paragraphs'] if p['sentences']]
        c['sections'] = [s for s in c['sections'] if s['paragraphs']]
    stats['guard'] = dict(reasons)
    return chapters


def dedupe_bigrams(chapters, stats, fact_cover=0.55, add_cover=0.5, min_bigrams=5):
    """v3 it2: the 4-gram dedupe misses a retelling in other words ("每回考试至少要八十分" after "没到八十分就挨打骂",
    the prologue's birth told again at the top of chapter one, a fill sentence restating its neighbour, one flourish in
    two chapters). Content-bigram cover of a sentence by ONE earlier sentence: a fact sentence covered >= fact_cover by
    an earlier fact sentence anywhere in the book is dropped; an added sentence covered >= add_cover by any earlier
    sentence (added anywhere, or fact in its chapter) is dropped."""
    facts, adds, n = [], [], 0
    for c in chapters:
        chap = []
        for s0 in c['sections']:
            for p in s0['paragraphs']:
                keep = []
                for x in p['sentences']:
                    bg = content_bigrams(x['t'])
                    if len(bg) >= min_bigrams:
                        if not x['add']:
                            dup = any(len(bg & h) / len(bg) >= fact_cover for h in facts)
                        else:
                            dup = any(len(bg & h) / len(bg) >= add_cover for h in adds + chap)
                        if dup:
                            stats.setdefault('dedup_bigram_dropped', []).append([x['add'], x['t']])
                            n += 1
                            continue
                    if bg:
                        (adds if x['add'] else facts).append(bg)
                        if not x['add']:
                            chap.append(bg)
                    keep.append(x)
                p['sentences'] = keep
            s0['paragraphs'] = [p for p in s0['paragraphs'] if p['sentences']]
        c['sections'] = [s0 for s0 in c['sections'] if s0['paragraphs']]
    stats['dedup_bigram'] = n
    return chapters


# --------------------------------------------------------------------------- metrics
def section_texts(chapters):
    return [(ci, si, ''.join(x['t'] for p in s['paragraphs'] for x in p['sentences']))
            for ci, c in enumerate(chapters) for si, s in enumerate(c['sections'])]


def section_repeats(chapters, threshold=0.25):
    """Pairs of sections that tell the same thing: tf-idf cosine of their content bigrams >= threshold, split into
    pairs in two chapters and pairs inside one chapter (one story told in several sections)."""
    secs = [(ci, si, content_bigrams(t)) for ci, si, t in section_texts(chapters) if mb.han_len(t) >= 40]
    df = Counter(g for _, _, gs in secs for g in gs)
    n = len(secs)
    vec = []
    for ci, si, gs in secs:
        w = {g: math.log((1 + n) / (1 + df[g])) + 1 for g in gs}
        norm_ = math.sqrt(sum(v * v for v in w.values())) or 1
        vec.append((ci, si, {g: v / norm_ for g, v in w.items()}))
    cross, within, pairs = 0, 0, []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = vec[i][2], vec[j][2]
            if len(a) > len(b):
                a, b = b, a
            cos = sum(v * b.get(g, 0) for g, v in a.items())
            if cos >= threshold:
                if vec[i][0] == vec[j][0]:
                    within += 1
                else:
                    cross += 1
                pairs.append([vec[i][0], vec[i][1], vec[j][0], vec[j][1], round(cos, 3)])
    return {'cross_chapter_section_pairs': cross, 'within_chapter_section_pairs': within, 'section_pairs': pairs, 'sections': n}


def detail_use(book, threshold=0.5):
    """Share of the elder's distinct sentences (>= 8 chars, not a closer, not a retelling of an earlier answer in question
    order: 4-gram cover < 0.5, at least two specific detail bigrams -- bigrams in at most two answers) of whose specific
    bigrams the book has >= threshold. Plan-independent, so v2 and v3 books compare on the same set."""
    text = ' '.join(x['t'] for c in book['chapters'] for s in c['sections'] for p in s['paragraphs'] for x in p['sentences'])
    wg = content_bigrams(text)
    udf = unit_df(book['units'])
    seen, total, used = set(), 0, 0
    private = [p.get('quote') or '' for p in (book.get('not_written') or {}).get('private') or []]
    for u, x in book['units'].items():
        for s in split(x['text']):
            g = grams(s)
            novel = g and len(g & seen) / len(g) < 0.5
            seen |= g
            if not novel or mb.han_len(s) < 8 or FILLER.search(s) or any(q and norm(s) in norm(q) for q in private):
                continue
            sp = specific(s, udf)
            if len(sp) < 2:
                continue
            total += 1
            used += len(sp & wg) / len(sp) >= threshold
    return round(used / total, 3) if total else None


def story_spread(book, plan, min_hits=3, share=0.25):
    """Independent of how a book was written: the v3 plan's stories (same handoff) as the reference. A story's
    signature = its specific bigrams that no other story has; a section 'tells' the story when it holds at least
    max(min_hits, share x signature) of them. Returns stories told in more than one chapter / more than one section of
    one chapter."""
    udf = unit_df(book['units'])
    sents = {u: split(x['text']) for u, x in book['units'].items()}
    bag = {}
    for sid, st in plan['stories'].items():
        g = set()
        for u, i in st.get('keys') or []:
            if u in sents and i - 1 < len(sents[u]):
                g |= specific(sents[u][i - 1], udf, 3)
        bag[sid] = g
    owners = Counter(g for gs in bag.values() for g in gs)
    sig = {sid: {g for g in gs if owners[g] == 1} for sid, gs in bag.items()}
    told = defaultdict(list)
    for ci, si, t in section_texts(book['chapters']):
        tg = content_bigrams(t)
        for sid, gs in sig.items():
            if len(gs) >= min_hits and len(gs & tg) >= max(min_hits, share * len(gs)):
                told[sid].append((ci, si))
    multi_ch = {sid: v for sid, v in told.items() if len({c for c, _ in v}) > 1}
    multi_sec = {sid: v for sid, v in told.items() if any(sum(1 for c2, _ in v if c2 == c) > 1 for c, _ in v)}
    return {'stories_told': len(told), 'stories_in_several_chapters': len(multi_ch),
            'extra_chapter_tellings': sum(len({c for c, _ in v}) - 1 for v in multi_ch.values()),
            'stories_in_several_sections_of_a_chapter': len(multi_sec),
            'examples': {plan['stories'][sid]['title']: v for sid, v in list(multi_ch.items())[:6]}}


def v3_metrics(book):
    from book import near_repeats
    sents = [x for c in book['chapters'] for s in c['sections'] for p in s['paragraphs'] for x in p['sentences']]
    added = [x for x in sents if x['add']]
    sr = section_repeats(book['chapters'])
    loose = near_repeats(book['chapters'], threshold=0.5)
    return {'chars': sum(mb.han_len(x['t']) for x in sents),
            'chapter_chars': [sum(mb.han_len(x['t']) for s in c['sections'] for p in s['paragraphs'] for x in p['sentences'])
                              for c in book['chapters']],
            'sections': sr['sections'], 'cross_chapter_section_pairs': sr['cross_chapter_section_pairs'],
            'within_chapter_section_pairs': sr['within_chapter_section_pairs'],
            'cross_chapter_repeats_05': len(loose),
            'detail_use': detail_use(book),
            'added_sentences': len(added), 'picture_sentences': sum(1 for x in added if x['add'] == '画面' or x.get('picture')),
            'echo_sentences': sum(1 for x in added if x['add'] == '呼应'),
            'added_char_ratio': round(sum(mb.han_len(x['t']) for x in added) / max(1, sum(mb.han_len(x['t']) for x in sents)), 3),
            'fallback_sentences': sum(1 for x in sents if x.get('fallback')),
            'filled_sentences': sum(1 for x in sents if x.get('filled'))}


if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == 'metrics':
    # python3 story.py metrics [--plan V3PLAN.json] BOOK.json ...
    args, ref = sys.argv[2:], None
    if args[0] == '--plan':
        ref, args = mb.load(args[1]), args[2:]
    for path in args:
        b = mb.load(path)
        m = v3_metrics(b)
        if ref:
            m['spread'] = story_spread(b, ref)
        print(path, json.dumps(m, ensure_ascii=False))
