#!/usr/bin/env python3
"""Memoir book layer v4 (BRIEF13): whole-story literary rewrite; the only hard rule is "no new events".

  python3 tools/memoir_eval/v4.py trial                      # 1 section x 2 styles x thinking on/off, check + Haiku
  python3 tools/memoir_eval/v4.py book --style a --thinking disabled   # 2 sample chapters: write -> check/fix loop
  python3 tools/memoir_eval/v4.py score                      # Haiku rubric-v4 on the v4 chapters and the v3 ones
  python3 tools/memoir_eval/v4.py render                     # Markdown + review HTML into /mnt/user-data/outputs

Input is the v3 story plan of the public-interview material (mb4-hold, N-6733a23cd1-rich): one story is still
written once, in one chapter. Unlike v3 there is no fact layer + marked insertions: each chapter is written in one
call as continuous first-person prose (write-v8.txt + a style block), then check-v7.txt (thinking on) looks only for
new events / people / changed facts / invented lines of other people / private matters; flagged sentences are
rewritten by fix-v1.txt and checked again (at most 3 checks; what is still flagged after the third is deleted).
Sentences that describe what someone other than the elder thinks or feels are marked for the elder to confirm.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import time
from pathlib import Path
from statistics import mean

import mb
import book_queue  # noqa: F401  (patches queue_worker for the memoir queue)
from book_queue import qw

SRC_RUN = mb.RUNS / 'mb4-hold' / 'd'
KEY = 'N-6733a23cd1-rich'
RUN = mb.RUNS / 'mb5-v4'
OUT = Path('/mnt/user-data/outputs')
BOOK_CAP, MAX_RATIO = 20000, 2.5
SAMPLE = {'childhood': (2000, 2150), 'work': (4200, 4400)}  # (target, max) Han chars, see budget()
TRIAL_STORIES = ['S19', 'S20', 'S25']  # mud-brick dorm + lamp, the old bicycle, the local teachers' dishes
KIND_WEIGHT = {'story': 1.0, 'fact': 0.8, 'reflection': 0.45}
# Family matter the v3 plan / style sample keep out of the book until the elder decides (colleagues' remarks about
# the wife's illness); redacted from the material the writer sees.
REDACT = [('“让你老婆去代……”，以我老婆的事来抗拒我的安排', '……（此处涉及家人的私事，不写）')]
PRIVATE_EXTRA = ['同事拿“我老婆的事”说的风凉话（“让你老婆去代……”）']
CHECK_PROMPT = 'check-v8.txt'  # check-v7 (trial) missed small new endings / actions / ages
CHECK_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'enabled', 'json_mode': True, 'max_tokens': 32000, 'timeout': 900}
FIX_PARAMS = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'json_mode': True, 'temperature': 0.6, 'max_tokens': 8000, 'timeout': 600}
RUBRIC_DIMS = ['literary', 'human', 'rewritten', 'coherent']
RUBRIC_NOTE = ('只输出一个 JSON 对象：{"literary": 1-5, "human": 1-5, "rewritten": 1-5, "coherent": 1-5, '
               '"new_events": [{"quote": "…", "why": "…"}], "note": "…"}，分数为整数，没有新增事件就给 "new_events": []。')
RUBRIC_SPEC = {'type': 'memoir', 'dims': RUBRIC_DIMS, 'list_field': 'new_events'}


def write_params(thinking):
    p = {'model': 'deepseek-v4-pro', 'json_mode': True, 'temperature': 0.8, 'thinking': thinking}
    p.update({'max_tokens': 32000, 'timeout': 900} if thinking == 'enabled' else {'max_tokens': 16000, 'timeout': 900})
    return p


def log(msg):
    line = time.strftime('%F %T ') + msg
    print(line, flush=True)
    with (RUN / 'v4.log').open('a', encoding='utf-8') as f:
        f.write(line + '\n')


# --------------------------------------------------------------------------- material
def load_material():
    plan = mb.load(SRC_RUN / 'plans' / (KEY + '.json'))
    book3 = mb.load(SRC_RUN / 'books' / (KEY + '.json'))
    return plan, book3


def redact(text):
    for a, b in REDACT:
        text = text.replace(a, b)
    return text


def chapter_index(plan, module):
    return next(i for i, c in enumerate(plan['chapters']) if c['modules'] == [module])


def stories_of(pch):
    out = []
    for s in pch['sections']:
        for m in s['story_meta']:
            out.append(m)
    return out


def elder_chars(stories):
    return sum(mb.han_len(t['text']) for m in stories for t in m['tellings'])


def budget(plan):
    """Per-chapter Han-char budget of the whole v4 book: min(share x 20,000, 2.5 x the chapter's own words)."""
    rows = []
    for c in plan['chapters']:
        mod = c['modules'][0]
        e = elder_chars(stories_of(c))
        rows.append({'module': mod, 'title': c['title'], 'elder': e, 'share_cap': int(mb.SHARE[mod] * BOOK_CAP),
                     'budget': int(min(mb.SHARE[mod] * BOOK_CAP, MAX_RATIO * e))})
    return rows


def suggest(stories, target):
    w = {m['id']: KIND_WEIGHT.get(m.get('kind'), 1.0) * elder_chars([m]) for m in stories}
    tot = sum(w.values()) or 1
    return {k: int(min(MAX_RATIO * elder_chars([m]), v / tot * target)) for m in stories for k, v in [(m['id'], w[m['id']])]}


def book_context(plan, here):
    rows = []
    for c in plan['chapters']:
        mod = c['modules'][0]
        rows.append({'module': mb.MODULE_NAME[mod], 'title': c['title'], 'this_chapter': mod == here,
                     'stories': [] if mod == here else ['%s：%s' % (m['title'], m['gist']) for m in stories_of(c)]})
    return rows


def write_call(cid, plan, module, style, thinking, story_ids=None, target=None, maxc=None, note=None, prompt_name='write-v8.txt'):
    pch = plan['chapters'][chapter_index(plan, module)]
    sts = [m for m in stories_of(pch) if story_ids is None or m['id'] in story_ids]
    target, maxc = target or SAMPLE[module][0], maxc or SAMPLE[module][1]
    sug = suggest(sts, target)
    texts = [t['text'] for c in plan['chapters'] for m in stories_of(c) for t in m['tellings']]
    user = {
        'book': {'name': '黄小荣', 'chapters': book_context(plan, module)},
        'chapter': {'module': mb.MODULE_NAME[module], 'reference_title': pch['title'], 'target_chars': target, 'max_chars': maxc,
                    'stories': [{'id': m['id'], 'title': m['title'], 'gist': m['gist'], 'kind': m.get('kind'),
                                 'suggested_chars': sug[m['id']],
                                 'tellings': [{'id': t['id'], 'asked': t['asked'], 'text': redact(t['text'])} for t in m['tellings']]}
                                for m in sts]},
        'voice': {**mb.voice_profile(texts), 'habits': plan.get('voice_habits', [])},
        'private': [p['quote'] for p in plan.get('private', [])] + PRIVATE_EXTRA,
        'unknown': [],
    }
    if note:
        user['note'] = note
    system = mb.prompt(prompt_name).replace('{{STYLE}}', mb.prompt('style-v8%s.txt' % style))
    return {'id': cid, 'system': system, 'user': json.dumps(user, ensure_ascii=False), 'params': write_params(thinking),
            'meta': {'module': module, 'stories': [m['id'] for m in sts], 'target': target, 'max': maxc}}


# --------------------------------------------------------------------------- text
_CLOSE = '”’」』）)'


def split_sents(text):
    """Sentences of a paragraph; never split inside “…” (a quoted line may hold several sentences)."""
    out, cur, depth = [], '', 0
    i = 0
    while i < len(text):
        ch = text[i]
        cur += ch
        if ch in '“「『':
            depth += 1
        elif ch in '”」』':
            depth = max(0, depth - 1)
        if depth == 0 and ch in '。！？!?…':
            while i + 1 < len(text) and (text[i + 1] in '。！？!?…' or text[i + 1] in _CLOSE):
                i += 1
                cur += text[i]
            out.append(cur.strip())
            cur = ''
        elif depth == 0 and ch in '”」』' and cur[-2:-1] in '。！？!?…':
            out.append(cur.strip())
            cur = ''
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return [s for s in out if s]


_NORM = re.compile(r'[^一-鿿0-9A-Za-z]')


def norm(text):
    return _NORM.sub('', mb.t2s(text or ''))


def copy_rate(text, source, n=8, skip_quotes=False):
    """Share of the written chars covered by an n-char run (punctuation ignored) that also occurs in the source."""
    if skip_quotes:
        text = re.sub(r'“[^”]*”', '', text)
    t, s = norm(text), norm(source)
    if not t:
        return None
    grams = {s[i:i + n] for i in range(len(s) - n + 1)}
    cov = [False] * len(t)
    for i in range(len(t) - n + 1):
        if t[i:i + n] in grams:
            for j in range(i, i + n):
                cov[j] = True
    return round(sum(cov) / len(t), 3)


def quotes(text):
    return re.findall(r'“([^”]{2,})”', text)


def code_hints(sents, source):
    """Quoted lines not found in the elder's words; numbers / places / person titles not in the elder's words."""
    src = norm(source)
    hints = []
    for x in sents:
        for q in quotes(x['t']):
            qn = norm(q)
            if len(qn) < 4:
                continue
            m = difflib.SequenceMatcher(None, qn, src, autojunk=False).find_longest_match(0, len(qn), 0, len(src))
            if m.size < 0.6 * len(qn):
                hints.append({'n': x['n'], 'hint': '引号里的话在原话里找不到：“%s”' % q})
        bad = mb.unsupported(x['t'], source)
        if bad:
            hints.append({'n': x['n'], 'hint': '原话里找不到：' + '、'.join('%s %s' % ({'number': '数字', 'place': '地名', 'person': '人名'}[k], v) for k, v in bad)})
    return hints


def parse_output(row):
    if not row or not row.get('ok'):
        return None
    out = row.get('output')
    if out is None:
        c = row.get('content') or ''
        m = re.search(r'\{.*\}', c, re.S)
        try:
            out = json.loads(m.group(0)) if m else None
        except ValueError:
            out = None
    return out


def to_chapter(out, module, meta):
    """Writer JSON -> chapter with globally numbered sentences."""
    secs, n = [], 0
    for s in out.get('sections') or []:
        paras = []
        for p in s.get('paragraphs') or []:
            p = mb.simplify(p if isinstance(p, str) else ''.join(x.get('t', '') if isinstance(x, dict) else str(x) for x in p))
            row = []
            for t in split_sents(p):
                n += 1
                row.append({'n': n, 't': t, 'orig': t, 'mind': False, 'history': []})
            if row:
                paras.append(row)
        secs.append({'title': mb.simplify(s.get('title') or ''), 'stories': s.get('stories') or [], 'paragraphs': paras})
    return {'module': module, 'title': mb.simplify(out.get('chapter_title') or ''), 'sections': secs, 'meta': meta,
            'events': out.get('events') or [], 'writer_mind': [mb.simplify(x) for x in out.get('others_mind') or [] if isinstance(x, str)]}


def live(ch):
    return [x for s in ch['sections'] for p in s['paragraphs'] for x in p if x['t']]


def chapter_plain(ch, marks=False):
    lines = []
    for s in ch['sections']:
        if s['title']:
            lines.append('【节】' + s['title'])
        for p in s['paragraphs']:
            t = ''.join(x['t'] for x in p if x['t'])
            if t:
                lines.append(t)
        lines.append('')
    return '\n'.join(lines).strip()


def chapter_len(ch):
    return sum(mb.han_len(x['t']) for x in live(ch))


def map_writer_mind(ch):
    for q in ch['writer_mind']:
        qn = norm(q)
        if len(qn) < 4:
            continue
        for x in live(ch):
            if x['t'] != x['orig']:
                continue
            xn = norm(x['t'])
            if qn in xn or xn in qn or difflib.SequenceMatcher(None, qn, xn).ratio() > 0.75:
                x['mind'] = True
                x.setdefault('mind_by', []).append('writer')


# --------------------------------------------------------------------------- calls
def sources_of(plan, module, story_ids):
    pch = plan['chapters'][chapter_index(plan, module)]
    own = [m for m in stories_of(pch) if story_ids is None or m['id'] in story_ids]
    src = [{'id': t['id'], 'story': m['title'], 'asked': t['asked'], 'text': redact(t['text'])} for m in own for t in m['tellings']]
    other = [{'id': t['id'], 'chapter': mb.MODULE_NAME[c['modules'][0]], 'text': t['text']}
             for c in plan['chapters'] for m in stories_of(c) if m['id'] not in {x['id'] for x in own} for t in m['tellings']]
    return src, other


def check_call(cid, plan, ch):
    src, other = sources_of(plan, ch['module'], ch['meta']['stories'])
    source_text = '\n'.join(x['text'] for x in src) + '\n' + '\n'.join(x['text'] for x in other)
    sents = live(ch)
    user = {'sources': {'units': src, 'unknown': [], 'private': [p['quote'] for p in plan.get('private', [])] + PRIVATE_EXTRA},
            'other_sources': other, 'code_hints': code_hints(sents, source_text),
            'sentences': [{'n': x['n'], 't': x['t']} for x in sents]}
    return {'id': cid, 'system': mb.prompt(CHECK_PROMPT), 'user': json.dumps(user, ensure_ascii=False), 'params': CHECK_PARAMS}


def fix_call(cid, plan, ch, issues):
    src, _ = sources_of(plan, ch['module'], ch['meta']['stories'])
    flagged = {i['n'] for i in issues}
    context = []
    for s in ch['sections']:
        for p in s['paragraphs']:
            if any(x['n'] in flagged for x in p):
                context.append([{'n': x['n'], 't': x['t']} for x in p if x['t']])
    by_n = {x['n']: x for x in live(ch)}
    fixes = [{'n': i['n'], 'sentence': by_n[i['n']]['t'], 'type': i.get('type'), 'why': i.get('why')} for i in issues if i['n'] in by_n]
    user = {'sources': {'units': src, 'private': [p['quote'] for p in plan.get('private', [])] + PRIVATE_EXTRA},
            'context': context, 'fixes': fixes}
    return {'id': cid, 'system': mb.prompt('fix-v1.txt'), 'user': json.dumps(user, ensure_ascii=False), 'params': FIX_PARAMS}


class Calls:
    def __init__(self):
        RUN.mkdir(parents=True, exist_ok=True)
        self.relay = mb.common.Relay(RUN, wait_seconds=6 * 3600)
        self.usage_file = RUN / 'usage.json'
        self.usage = mb.load(self.usage_file) if self.usage_file.exists() else {'jobs': {}}

    def run(self, stage, calls):
        job = 'mb5-%s-%s' % (stage, time.strftime('%m%d%H%M%S'))
        before = dict(self.relay.usage)
        sent0 = self.relay.calls_sent
        log('relay %s: %d calls' % (job, len(calls)))
        got = self.relay.run_batch(job, [{k: c[k] for k in ('id', 'system', 'user', 'params')} for c in calls])
        used = {k: v - before.get(k, 0) for k, v in self.relay.usage.items() if v - before.get(k, 0)}
        self.usage['jobs'][job] = {'calls': len(calls), 'sent': self.relay.calls_sent - sent0, 'usage': used}
        mb.save(self.usage_file, self.usage)
        bad = [c['id'] for c in calls if not (got.get(c['id']) or {}).get('ok')]
        log('relay %s back: sent %d, usage %s, failed %s' % (job, self.relay.calls_sent - sent0, used, bad))
        return got


def check_fix_loop(calls, plan, chapters, tag, max_checks=3):
    """check -> fix -> check ... (at most max_checks checks); what is still flagged after the last check is deleted."""
    for rnd in range(1, max_checks + 1):
        got = calls.run('%s-check%d' % (tag, rnd), [check_call('chk%d-%s' % (rnd, ch['module']), plan, ch) for ch in chapters])
        todo = []
        for ch in chapters:
            out = parse_output(got.get('chk%d-%s' % (rnd, ch['module']))) or {}
            by_n = {x['n']: x for x in live(ch)}
            issues = [i for i in out.get('issues') or [] if isinstance(i, dict) and isinstance(i.get('n'), int) and i['n'] in by_n]
            ch.setdefault('checks', []).append({'round': rnd, 'issues': [{**i, 'sentence': by_n[i['n']]['t']} for i in issues],
                                               'others_mind': sorted({m['n'] for m in out.get('others_mind') or []
                                                                      if isinstance(m, dict) and m.get('n') in by_n})})
            for m in ch['checks'][-1]['others_mind']:
                by_n[m]['mind_round'] = rnd
            if issues:
                todo.append((ch, issues))
        log('%s check%d: %s' % (tag, rnd, {ch['module']: len(ch['checks'][-1]['issues']) for ch in chapters}))
        if not todo:
            break
        if rnd == max_checks:
            for ch, issues in todo:
                by_n = {x['n']: x for x in live(ch)}
                for i in issues:
                    x = by_n[i['n']]
                    x['history'].append({'round': rnd, 'action': 'deleted', 'old': x['t'], 'type': i.get('type'), 'why': i.get('why')})
                    x['t'] = ''
            break
        got = calls.run('%s-fix%d' % (tag, rnd), [fix_call('fix%d-%s' % (rnd, ch['module']), plan, ch, issues) for ch, issues in todo])
        for ch, issues in todo:
            out = parse_output(got.get('fix%d-%s' % (rnd, ch['module']))) or {}
            by_n = {x['n']: x for x in live(ch)}
            why = {i['n']: i for i in issues}
            rep = {r['n']: mb.simplify(r.get('new') or '') for r in out.get('replace') or [] if isinstance(r, dict) and r.get('n') in why}
            for n, i in why.items():
                if n not in by_n:
                    continue
                x = by_n[n]
                new = rep.get(n, x['t'])  # a fix the model skipped stays flagged and is checked again
                x['history'].append({'round': rnd, 'action': 'rewritten' if new else 'deleted', 'old': x['t'], 'new': new,
                                     'type': i.get('type'), 'why': i.get('why')})
                x['t'] = new
    # others' minds: the writer's own list (unchanged sentences) + the last check that saw each sentence's final text
    for ch in chapters:
        map_writer_mind(ch)
        last = ch['checks'][-1]['others_mind'] if ch.get('checks') else []
        for x in live(ch):
            if x['n'] in last:
                x['mind'] = True
                x.setdefault('mind_by', []).append('check')
            elif x.get('mind_by') == ['writer'] and x['t'] != x['orig']:
                x['mind'] = False
    return chapters


# --------------------------------------------------------------------------- metrics + Haiku
def chapter_sources_text(plan, module, story_ids=None):
    src, _ = sources_of(plan, module, story_ids)
    return '\n'.join(x['text'] for x in src)


def metrics(plan, ch):
    src = chapter_sources_text(plan, ch['module'], ch['meta']['stories'])
    allsrc = '\n'.join(t['text'] for c in plan['chapters'] for m in stories_of(c) for t in m['tellings'])
    text = ''.join(x['t'] for x in live(ch))
    checks = ch.get('checks') or []
    hist = [h for x in live(ch) + [y for s in ch['sections'] for p in s['paragraphs'] for y in p if not y['t']] for h in y_hist(x)]
    covered = {sid for s in ch['sections'] for sid in s['stories']}
    return {'chars': chapter_len(ch), 'target': ch['meta']['target'], 'max': ch['meta']['max'], 'elder_chars': mb.han_len(src),
            'ratio_to_elder': round(chapter_len(ch) / max(1, mb.han_len(src)), 2),
            'copy8': copy_rate(text, src, 8), 'copy8_outside_quotes': copy_rate(text, src, 8, True), 'copy12': copy_rate(text, src, 12),
            'copy8_book': copy_rate(text, allsrc, 8),
            'sentence_copy_ratio': mb.copy_ratio([x['t'] for x in live(ch)], src),
            'quotes': len(quotes(text)),
            'new_events_found': len(checks[0]['issues']) if checks else None,
            'new_events_by_round': [len(c['issues']) for c in checks],
            'rewritten_sents': sum(1 for h in hist if h['action'] == 'rewritten'), 'deleted_sents': sum(1 for h in hist if h['action'] == 'deleted'),
            'new_events_left': len(checks[-1]['issues']) if checks and len(checks) == 3 else 0,
            'others_mind': sum(1 for x in live(ch) if x['mind']),
            'stories_missing': [m for m in ch['meta']['stories'] if m not in covered]}


def y_hist(x):
    return x.get('history') or []


def rubric_input(plan, module, story_ids, title, body):
    pch = plan['chapters'][chapter_index(plan, module)]
    own = [m for m in stories_of(pch) if story_ids is None or m['id'] in story_ids]
    lines = ['[%s] 问：%s\n答：%s' % (t['id'], t['asked'], redact(t['text'])) for m in own for t in m['tellings']]
    other = ['%s（%s）' % (m['title'], mb.MODULE_NAME[c['modules'][0]]) for c in plan['chapters'] if c is not pch for m in stories_of(c)]
    lines.append('（本书其他章另写的故事，本章不重讲是对的，最多一句带过：%s）' % '；'.join(other))
    n = mb.han_len(body)
    m = elder_chars(own)
    return ('===== 这一章（%d 字；老人这部分原话约 %d 字）=====\n章名：%s（%s）\n\n%s\n\n===== 老人原话 =====\n%s'
            % (n, m, title, mb.MODULE_NAME[module], body, '\n\n'.join(lines)))


def haiku(items, wait=4 * 3600):
    """items: {key: input_text} -> {key: answer}"""
    q = qw.HaikuQueue('memoir')
    instr = mb.prompt('rubric-v4.txt')
    pending, res = {}, {}
    for k, text in items.items():
        rid, hit = q.submit(instr, text, RUBRIC_NOTE, RUBRIC_SPEC, meta={'run': 'mb5-v4'})
        if hit:
            res[k] = hit['output']
        else:
            pending[k] = rid
    log('haiku: %d submitted, %d cached' % (len(pending), len(res)))
    deadline = time.time() + wait
    while pending and time.time() < deadline:
        for k, rid in list(pending.items()):
            r = q.poll(rid)
            if r:
                res[k] = r['output']
                del pending[k]
        if pending:
            time.sleep(15)
    log('haiku back: %d, pending %d' % (len(res), len(pending)))
    return res


def v3_chapter_text(book3, module):
    c = next(x for x in book3['chapters'] if x['modules'] == [module])
    lines = []
    for s in c['sections']:
        if s['title']:
            lines.append('【节】' + s['title'])
        for p in s['paragraphs']:
            lines.append(''.join(x['t'] for x in p['sentences']))
        lines.append('')
    return c['title'], '\n'.join(lines).strip(), c


# --------------------------------------------------------------------------- stages
def cmd_trialcheck(a):
    """Re-check the four trial texts with the current CHECK_PROMPT (check-v7 there missed small new endings)."""
    plan, _ = load_material()
    calls = Calls()
    chs = mb.load(RUN / 'trial.json')
    got = calls.run('trial-chk2', [check_call('chk2-' + k, plan, ch) for k, ch in chs.items()])
    res = {}
    for k, ch in chs.items():
        out = parse_output(got.get('chk2-' + k)) or {}
        by_n = {x['n']: x for x in live(ch)}
        res[k] = {'issues': [{**i, 'sentence': by_n[i['n']]['t']} for i in out.get('issues') or [] if isinstance(i, dict) and i.get('n') in by_n],
                  'others_mind': [by_n[m['n']]['t'] for m in out.get('others_mind') or [] if isinstance(m, dict) and m.get('n') in by_n]}
    mb.save(RUN / 'trial-check-v8.json', res)
    log('trial recheck (%s): %s' % (CHECK_PROMPT, {k: len(v['issues']) for k, v in res.items()}))


def cmd_trial(a):
    plan, _ = load_material()
    calls = Calls()
    variants = [(s, t) for s in ('a', 'b') for t in ('disabled', 'enabled')]
    note = '这是“工作与劳动”一章中的一节（只写这三个故事，合成一节或两节；chapter_title 照样给）。'
    wc = [write_call('trial-%s-%s' % (s, t[:2]), plan, 'work', s, t, TRIAL_STORIES, 1000, 1150, note) for s, t in variants]
    got = calls.run('trial-w', wc)
    chs = {}
    for c in wc:
        out = parse_output(got.get(c['id']))
        if out:
            chs[c['id']] = to_chapter(out, 'work', c['meta'])
    ck = calls.run('trial-chk', [check_call('chk-' + k, plan, ch) for k, ch in chs.items()])
    for k, ch in chs.items():
        out = parse_output(ck.get('chk-' + k)) or {}
        by_n = {x['n']: x for x in live(ch)}
        ch['checks'] = [{'round': 1, 'issues': [{**i, 'sentence': by_n[i['n']]['t']} for i in out.get('issues') or []
                                                if isinstance(i, dict) and i.get('n') in by_n],
                         'others_mind': sorted({m['n'] for m in out.get('others_mind') or [] if isinstance(m, dict) and m.get('n') in by_n})}]
        for n in ch['checks'][0]['others_mind']:
            by_n[n]['mind'] = True
        map_writer_mind(ch)
    mb.save(RUN / 'trial.json', chs)
    scores = haiku({k: rubric_input(plan, 'work', TRIAL_STORIES, ch['title'], chapter_plain(ch)) for k, ch in chs.items()})
    rows = {}
    for k, ch in chs.items():
        m = metrics(plan, ch)
        rows[k] = {**{d: (scores.get(k) or {}).get(d) for d in RUBRIC_DIMS}, 'haiku_new_events': len((scores.get(k) or {}).get('new_events') or []),
                   'note': (scores.get(k) or {}).get('note'), **m, 'usage': None}
    for job, u in calls.usage['jobs'].items():
        pass
    mb.save(RUN / 'trial-summary.json', {'rows': rows, 'scores': scores})
    log('trial summary: ' + json.dumps({k: {x: v[x] for x in RUBRIC_DIMS + ['chars', 'copy8', 'new_events_found', 'others_mind', 'haiku_new_events']}
                                        for k, v in rows.items()}, ensure_ascii=False))


# One call per section (a few related stories, like the trial). Whole-chapter calls (mb5-book-w, 2026-11-08) copied
# the elder's words almost verbatim once the input grew past ~2,000 chars (work chapter, first half 3,500 chars of
# material), and the childhood chapter came out at 60% of its target. Each section call sees the chapter outline and
# its neighbours so it can open and close in place; the first section opens the chapter, the last one ends it.
GROUPS = {
    'childhood': [['S01'], ['S04'], ['S05'], ['S06']],
    'work': [['S14', 'S19'], ['S20', 'S25'], ['S15', 'S16'], ['S17', 'S21'], ['S18'], ['S22'], ['S23', 'S24'],
             ['S27', 'S28'], ['S31'], ['S26', 'S29', 'S30']],
}
WHO = {'childhood': '这一章的“我”是大游村的孩子、小学生。',
       'work': '这一章的“我”是师范毕业分到乡村小学的老师（不是学生）；后几节是后来在万安乡任教、做教导处和总务处工作的这些年。'}
UNDERSHOOT = 1.25  # trial: the writer reached 63-79% of the asked length; the asked target is scaled up by this


def book_write_calls(plan, style, thinking, prompt_name):
    calls = []
    for module, groups in GROUPS.items():
        pch = plan['chapters'][chapter_index(plan, module)]
        sts = {m['id']: m for m in stories_of(pch)}
        assert sorted(sts) == sorted(x for g in groups for x in g), module
        sug = suggest(list(sts.values()), SAMPLE[module][0])
        outline = ['第%d节：%s' % (i + 1, '；'.join(sts[x]['title'] for x in g)) for i, g in enumerate(groups)]
        for i, g in enumerate(groups):
            alloc = sum(sug[x] for x in g)
            pos = ('这是本章的第一节，要开篇：先把读者带进这一章的时空。' if i == 0 else
                   '这是本章的最后一节，结尾就是全章的结尾，要有余味（可以回到本章前面出现过的意象或物件）。' if i == len(groups) - 1 else
                   '这是本章中间的一节：开头一两句接上上一节，结尾不做全章总结。')
            note = ('这次只写本章（%s）的一节，共 %d 节。本章各节：%s。这次写第 %d 节。%s%s只写这一节的故事（%s，每个都要写到），其他节的故事不要写进来。'
                    '只输出一个 section。只有第一节需要给 chapter_title，其余节给空字符串。'
                    % (mb.MODULE_NAME[module], len(groups), '；'.join(outline), i + 1, pos, WHO[module], '、'.join(sts[x]['title'] for x in g)))
            t = int(alloc * UNDERSHOOT)
            calls.append(write_call('w-%s-%02d' % (module, i + 1), plan, module, style, thinking, g, t, int(t * 1.1), note, prompt_name))
            calls[-1]['meta'].update({'alloc': alloc, 'section': i})
    return calls


META = re.compile(r'(上|这|下|本)一?节|本章')
FORMAL_KIN = ('父亲', '母亲')


def section_problems(plan, call, out):
    """Code checks of one section draft: copying, missing stories, structure talk, formal kin terms."""
    if not out or not out.get('sections'):
        return ['没有输出']
    s = out['sections'][0]
    text = mb.simplify(''.join(p if isinstance(p, str) else '' for p in s.get('paragraphs') or []))
    src = chapter_sources_text(plan, call['meta']['module'], call['meta']['stories'])
    probs = []
    cr = copy_rate(text, src, 8, skip_quotes=True)  # the elder's own quoted lines are allowed
    if cr is not None and cr > 0.3:
        probs.append('有 %d%% 的文字是照抄原话的连续片段（引号外；要求低于 20%%）' % round(100 * cr))
    pch = plan['chapters'][chapter_index(plan, call['meta']['module'])]
    sts = {m['id']: m for m in stories_of(pch)}
    miss = [x for x in call['meta']['stories'] if x not in (s.get('stories') or [])]
    if miss and len(call['meta']['stories']) > 1:
        probs.append('漏写了故事：' + '、'.join(sts[x]['title'] for x in miss))
    if META.search(text):
        probs.append('写了“上一节……这一节……”这类交代结构的话')
    for k in FORMAL_KIN:
        if k in text and k not in src:
            probs.append('用了“%s”，老人自己说“%s”' % (k, '我爸' if k == '父亲' else '我妈'))
    if mb.han_len(text) < 0.6 * call['meta']['target'] / UNDERSHOOT:
        probs.append('太短：只写了 %d 字，这一节约需 %d 字' % (mb.han_len(text), call['meta']['target']))
    return probs


def cmd_book(a):
    plan, _ = load_material()
    calls = Calls()
    tag = 'book' + (a.tag or '')
    wc = book_write_calls(plan, a.style, a.thinking, a.prompt)
    got = calls.run(tag + '-w', wc)
    redo = []
    for c in wc:
        probs = section_problems(plan, c, parse_output(got.get(c['id'])))
        c['meta']['problems'] = probs
        if probs:
            u = json.loads(c['user'])
            u['note'] += ('上一次写这一节时出了这些问题，这次务必避免：' + '；'.join(probs) + '。'
                          '先读懂原话，再完全用自己的话重新讲，不要顺着原话的句子写。')
            redo.append({**c, 'id': c['id'] + '-r', 'user': json.dumps(u, ensure_ascii=False), 'meta': dict(c['meta'])})
    log('%s redo %d sections: %s' % (tag, len(redo), {c['id']: c['meta']['problems'] for c in redo}))
    if redo:
        got2 = calls.run(tag + '-w2', redo)
        for r in redo:
            o = parse_output(got2.get(r['id']))
            p2 = section_problems(plan, r, o)
            orig = r['id'][:-2]
            log('redo %s: %s -> %s' % (orig, r['meta']['problems'], p2))
            if o and len(p2) <= len(r['meta']['problems']):
                got[orig] = got2[r['id']]
                next(c for c in wc if c['id'] == orig)['meta'].update({'redone': True, 'problems_after': p2})
    chapters = []
    for module in ('childhood', 'work'):
        parts = sorted([c for c in wc if c['meta']['module'] == module], key=lambda c: c['meta']['section'])
        outs = [parse_output(got.get(c['id'])) for c in parts]
        if not all(outs):
            raise SystemExit('write failed: ' + ','.join(c['id'] for c, o in zip(parts, outs) if not o))
        meta = {'module': module, 'stories': [x for c in parts for x in c['meta']['stories']],
                'target': SAMPLE[module][0], 'max': SAMPLE[module][1], 'parts': len(parts)}
        merged = {'chapter_title': outs[0].get('chapter_title'), 'sections': [x for o in outs for x in (o.get('sections') or [])[:1]],
                  'events': [x for o in outs for x in o.get('events') or []], 'others_mind': [x for o in outs for x in o.get('others_mind') or []]}
        chapters.append(to_chapter(merged, module, meta))
    mb.save(RUN / ('%s-written.json' % tag), chapters)
    log('%s written: %s' % (tag, {ch['module']: chapter_len(ch) for ch in chapters}))
    check_fix_loop(calls, plan, chapters, tag)
    for ch in chapters:
        ch['metrics'] = metrics(plan, ch)
        if not ch['title'] or norm(ch['title']) not in norm('\n'.join(t['text'] for c in plan['chapters'] for m in stories_of(c) for t in m['tellings'])):
            ch['title_fallback'] = ch['title']
            ch['title'] = plan['chapters'][chapter_index(plan, ch['module'])]['title']
    mb.save(RUN / ('%s-final.json' % tag), {'style': a.style, 'thinking': a.thinking, 'chapters': chapters})
    log('%s final: %s' % (tag, json.dumps({ch['module']: ch['metrics'] for ch in chapters}, ensure_ascii=False)))


def cmd_score(a):
    plan, book3 = load_material()
    fin = mb.load(RUN / ('book%s-final.json' % (a.tag or '')))
    items = {}
    for ch in fin['chapters']:
        items['v4-' + ch['module']] = rubric_input(plan, ch['module'], ch['meta']['stories'], ch['title'], chapter_plain(ch))
        t3, body3, _ = v3_chapter_text(book3, ch['module'])
        items['v3-' + ch['module']] = rubric_input(plan, ch['module'], ch['meta']['stories'], t3, body3)
    res = haiku(items)
    out = {}
    for k, text in items.items():
        mod = k.split('-', 1)[1]
        body = text.split('=====\n', 1)[1].split('\n\n===== 老人原话')[0]
        src = chapter_sources_text(plan, mod)
        out[k] = {**(res.get(k) or {}), 'chars': mb.han_len(body.split('\n', 1)[1]), 'copy8': copy_rate(body.split('\n', 1)[1], src, 8),
                  'copy8_outside_quotes': copy_rate(body.split('\n', 1)[1], src, 8, True), 'copy12': copy_rate(body.split('\n', 1)[1], src, 12)}
    mb.save(RUN / ('scores%s.json' % (a.tag or '')), out)
    log('scores: ' + json.dumps({k: {d: v.get(d) for d in RUBRIC_DIMS + ['copy8']} | {'new_events': len(v.get('new_events') or [])}
                                 for k, v in out.items()}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['trial', 'trialcheck', 'book', 'score', 'render', 'budget'])
    ap.add_argument('--style', default='a', choices=['a', 'b'])
    ap.add_argument('--thinking', default='disabled', choices=['enabled', 'disabled'])
    ap.add_argument('--tag', default='')
    ap.add_argument('--prompt', default='write-v10.txt')
    a = ap.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    if a.cmd == 'budget':
        plan, _ = load_material()
        rows = budget(plan)
        print(json.dumps(rows, ensure_ascii=False, indent=1), sum(r['budget'] for r in rows))
        return
    if a.cmd == 'render':
        import render_v4
        render_v4.main(a)
        return
    {'trial': cmd_trial, 'trialcheck': cmd_trialcheck, 'book': cmd_book, 'score': cmd_score}[a.cmd](a)


if __name__ == '__main__':
    main()
