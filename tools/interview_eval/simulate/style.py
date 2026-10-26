#!/usr/bin/env python3
"""Code metrics for how an interviewer turn is put together (0 token, no gold): restating, template framing.

  python3 tools/interview_eval/simulate/style.py RUN [RUN ...]            # summary per run (RUN1+RUN2 pools runs)
  python3 tools/interview_eval/simulate/style.py --list RUN               # every counted turn with its parts and flags
  python3 tools/interview_eval/simulate/style.py --story RUN              # story questions only (story-questions.json)

A turn = what the interviewer says after an elder answer: a follow-up, a deepen question (v5) or a close (+ the next
entry). It is split into
  core    : the question itself (the next entry for a close; the last clause of the question sentence otherwise)
  lead    : everything said before the core, clause by clause, each one of
            ack     - a reaction / acknowledgement (a statement before the question sentence, or a clause inside it
                      that quotes the elder (您说/您提到…) or is followed by a clause starting with 那: "X，那Y？")
            pointer - a clause inside the question sentence that names the event the question is about
                      (说到您哥哥，/ 跟着父亲打游击那会儿，)
            transit - a clause that only moves on (那、好、那咱们再聊聊、换个话题、今天先聊到这儿…)
Definitions (general, the same for every person and version):
  restate_any   : the same test against all of the elder's words in this question so far (catches a pointer that
                  restates an earlier answer: "您跟两个同学一起跑去高雄报考，那天……？").
  restate (复述) : the ack + pointer part repeats or rewords the elder's latest answer: it opens by quoting
                  (您说/您提到/您刚才讲…, ≥6 characters), or ≥3 of its content bigrams occur in that answer and they
                  are ≥1/3 of its content bigrams, or it shares a run of ≥6 Chinese characters with that answer.
                  Content bigram = persona.bigrams (function characters dropped) plus Latin words; the elder's
                  stop-signal phrases (记不清/不想讲/累了…) are taken out of the answer first, so a short "记不清也没关系"
                  is a reaction, not a restatement. A short pointer (fewer than 3 shared bigrams) never counts.
  frame   (套路结构)  : the turn has an ack (≥3 Chinese characters) and what follows it starts with 那 (那/那咱们/那您…):
                  "承接句 + 那 + 问句".
  template(套路短语)  : a stock move-on phrase: 咱们(再)聊聊/说说/谈谈、换个话题/话头、接着聊.
  opener repeat : within one session, a turn whose first clause starts with the same 4 characters as an earlier turn.
  lead repeat   : within one session, a transit / pointer clause before the core (normalised, > 2 characters) that an
                  earlier turn already used.
  routine (套路率) : frame or template or opener repeat or lead repeat.
Rates are over speaker-written turns; fixed texts (the pause / resume line, the session-end line) are not counted.
A turn's raw speaker output (before code guards) is measured as well when the record has it (``raw``).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from persona import bigrams, simp  # noqa: E402

TRANSIT = re.compile(r'换个话题|换个话头|换一个话题|不聊这个|再聊聊|接着聊|聊聊别的|说说别的|下一个话题|再说说|再问问|聊聊|说说|谈谈|'
                     r'今天先聊到|先聊到这|就先到这|先到这儿|今天就聊到|聊了这么多|(?:您)?(?:也)?辛苦(?:您)?了')
TEMPLATE = re.compile(r'咱们(?:就|再|来|也)?(?:再)?(?:聊聊|说说|谈谈)|换(?:一)?个话(?:题|头)|接着(?:聊|说)')
INTERJ = re.compile(r'^(?:那|好|好的|嗯|噢|哦|喔|啊|对|是|行|成)$')
POINTER_HEAD = re.compile(r'^(?:那)?(?:说到|说起|提到|提起|讲到|讲起|聊到|谈到|关于|至于)')
POINTER_TAIL = re.compile(r'(?:那会儿|那会|那时候|那时|那阵子|那几年|那些年|那一年|的时候|时候|以后|之后|之前|以前|期间|那天)$')
QUOTE = re.compile(r'^(?:您|你)(?:刚才|刚刚|刚)?(?:说|提到|讲到|讲|谈到|说到|提起|说起)')
SENT = re.compile(r'[^。！？!?]*[。！？!?]?')
CLAUSE = re.compile(r'[^，,。！？!?；;：:]*[，,。！？!?；;：:]?')
CJK = re.compile(r'[一-鿿]')
NA = re.compile(r'^\s*那(?!会|时|年|阵|几年|些年|天|里|儿|边|段|次|位|个|些|种|件|回|样|么)')  # 那 linking a question, not 那会儿/那位… naming


def _norm(s):
    return re.sub(r'[\s，。！？、,.!?；;：:“”"‘’…~—]', '', s or '')


def cjk(s):
    return ''.join(CJK.findall(simp(s or '')))


def units(text):
    return bigrams(text) | {w.lower() for w in re.findall(r'[A-Za-z]{2,}', text or '')}


def lcs_run(a, b):
    a, b = cjk(a), cjk(b)
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def _kind(clause, in_question, following=''):
    bare = re.sub(r'[，,。！？!?；;：:\s]', '', clause)
    if not bare or INTERJ.match(bare) or TRANSIT.search(bare) and len(cjk(bare)) <= 12:
        return 'transit'
    if in_question:
        if QUOTE.match(bare):
            return 'ack'
        if NA.match(following or '') and not POINTER_HEAD.match(bare) and not POINTER_TAIL.search(bare):
            return 'ack'
        return 'pointer'
    return 'ack'


def split_turn(text, tail=None):
    """(clauses, core): clauses = [(kind, text)] before the core, kind in ack / pointer / transit."""
    t = (text or '').strip()
    pre, core, in_q = t, '', []
    if tail and _norm(t).endswith(_norm(tail)):
        body = tail.rstrip('？?')
        pos = t.rfind(body)
        if pos < 0:
            pos = max(0, len(t) - len(tail))
        pre, core = t[:pos], t[pos:]
        sents = [s for s in SENT.findall(pre) if s.strip()]
        if sents and not re.search(r'[。！？!?]$', sents[-1]):  # lead-in inside the entry's sentence
            in_q = [c for c in CLAUSE.findall(sents[-1]) if c.strip()]
            pre = ''.join(sents[:-1])
    else:
        sents = [s for s in SENT.findall(t) if s.strip()]
        qi = max((i for i, s in enumerate(sents) if re.search(r'[？?]', s)), default=None)
        if qi is None:
            return [(_kind(c, False), c) for c in CLAUSE.findall(t) if c.strip()], ''
        cl = [c for c in CLAUSE.findall(sents[qi]) if c.strip()]
        core, in_q = cl[-1], cl[:-1]
        pre = ''.join(sents[:qi])
    out = [(_kind(c, False), c) for c in CLAUSE.findall(pre) if c.strip()]
    for k, c in enumerate(in_q):
        nxt = in_q[k + 1] if k + 1 < len(in_q) else core
        out.append((_kind(c, True, nxt), c))
    return out, core


def strip_signals(elder):
    """The elder's words without the stop-signal phrases (记不清/不想讲/累了…)."""
    import interview
    for rx in (interview.SIG_REST, interview.SIG_DECLINE, interview.SIG_UNKNOWN, interview.DEEPEN_UNKNOWN):
        elder = rx.sub('，', elder or '')
    return elder


def is_restate(part, elder):
    """Whether ``part`` (ack + pointer clauses) mainly repeats / rewords ``elder``. Returns (flag, info)."""
    elder = strip_signals(elder)
    a = cjk(part)
    if not a:
        return False, {}
    A, E = units(part), units(elder)
    shared = A & E
    run = lcs_run(part, elder)
    info = {'shared': len(shared), 'units': len(A), 'run': run}
    if QUOTE.match(re.sub(r'^(?:嗯|噢|哦|好)[，,]?', '', (part or '').strip())) and len(a) >= 6:
        return True, {**info, 'why': 'quote'}
    if len(shared) >= 3 and 3 * len(shared) >= len(A):
        return True, {**info, 'why': 'overlap'}
    if run >= 6:
        return True, {**info, 'why': 'run'}
    return False, info


def turn_style(text, tail, elder, elder_all=''):
    clauses, core = split_turn(text, tail)
    ack = ''.join(c for k, c in clauses if k == 'ack')
    pointer = ''.join(c for k, c in clauses if k == 'pointer')
    restate, info = is_restate(ack + pointer, elder)
    restate_any = restate or is_restate(ack + pointer, elder_all)[0]
    # which clauses carry the restatement (for highlighting): ack / pointer clauses that restate on their own,
    # or all of them when only together they do
    marked = [c for k, c in clauses if k in ('ack', 'pointer') and is_restate(c, elder)[0]]
    if restate and not marked:
        marked = [c for k, c in clauses if k in ('ack', 'pointer')]
    after, seen_ack = '', False
    for k, c in clauses + [('core', core)]:
        if k == 'ack':
            seen_ack, after = True, ''
        elif seen_ack and not after:
            after = c
    frame = len(cjk(ack)) >= 3 and bool(NA.match(after or ''))
    lead = ''.join(c for k, c in clauses)
    template = bool(TEMPLATE.search(lead))
    first = next((c for c in CLAUSE.findall((text or '').strip()) if c.strip()), '')
    leads = [_norm(c) for k, c in clauses if k in ('transit', 'pointer') and len(_norm(c)) > 2]
    return {'ack': ack, 'pointer': pointer, 'core': core, 'restate': restate, 'restate_any': restate_any, 'restate_info': info,
            'restate_clauses': marked,
            'frame': frame, 'template': template, 'opener': cjk(first)[:4], 'leads': leads}


def last_elder(messages, upto):
    for m in reversed(messages[:upto]):
        if m['role'] == 'elder' and not m.get('scripted'):
            return m['text']
    return ''


def raw_text(m, tail):
    """The speaker's own output for this turn before code guards and repairs, as it would have been said."""
    sp = m.get('speaker') or {}
    raw = sp.get('raw')
    if not raw:
        return None
    try:
        out = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(out, dict):
        return None
    if m.get('kind') == 'close':
        reply = out.get('reply') if isinstance(out.get('reply'), str) else out.get('ack') or ''
        return reply.strip() or None
    ack = out.get('ack') if isinstance(out.get('ack'), str) else ''
    q = out.get('question') if isinstance(out.get('question'), str) else ''
    if not q:
        return None
    ack = ack.strip()
    return (ack + ('' if not ack or re.search(r'[。！？!?，,…~]$', ack) else '。') + q.strip())


def session_turns(sess, story=None):
    """Speaker-written turns of a simulated session: [(episode index, message, style, raw style or None)]."""
    out = []
    for i, ep in enumerate(sess.get('episodes') or []):
        if story is not None and ep['qid'] not in story:
            continue
        msgs = ep['messages']
        for j, m in enumerate(msgs):
            if m['role'] != 'system' or m.get('kind') not in ('followup', 'close', 'deepen'):
                continue
            sp = m.get('speaker') or {}
            if sess.get('mode') == 'v4' and (not sp or sp.get('fixed')):
                continue
            tail = m.get('entry_part') if m.get('kind') == 'close' else None
            elder = last_elder(msgs, j)
            elder_all = ''.join(x['text'] for x in msgs[:j] if x['role'] == 'elder' and not x.get('scripted'))
            raw = raw_text(m, tail)
            out.append((i, m, turn_style(m['text'], tail, elder, elder_all), turn_style(raw, tail, elder, elder_all) if raw else None))
    return out


def rate(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


def run_style(sessions, story=None):
    by = {'followup': [], 'close': [], 'deepen': []}
    raws = []
    flags = []
    for s in sessions:
        seen_open, seen_lead = set(), set()
        for i, m, st, raw in session_turns(s, story):
            st['opener_repeat'] = bool(st['opener']) and st['opener'] in seen_open
            st['lead_repeat'] = any(x in seen_lead for x in st['leads'])
            st['routine'] = st['frame'] or st['template'] or st['opener_repeat'] or st['lead_repeat']
            if st['opener']:
                seen_open.add(st['opener'])
            seen_lead.update(st['leads'])
            by[m['kind']].append(st)
            if raw:
                raws.append(raw)
            flags.append((s, i, m, st))
    allt = by['followup'] + by['close'] + by['deepen']
    out = {'turns': len(allt), **{f'turns_{k}': len(v) for k, v in by.items()}}
    for key in ('restate', 'restate_any', 'frame', 'template', 'opener_repeat', 'lead_repeat', 'routine'):
        out[key + '_rate'] = rate([t[key] for t in allt])
        for k, v in by.items():
            out[f'{key}_rate_{k}'] = rate([t[key] for t in v])
    out['raw_turns'] = len(raws)
    out['raw_restate_rate'] = rate([t['restate'] for t in raws])
    out['raw_frame_rate'] = rate([t['frame'] for t in raws])
    out['raw_template_rate'] = rate([t['template'] for t in raws])
    out['ack_len_mean'] = round(sum(len(cjk(t['ack'])) for t in allt) / len(allt), 2) if allt else None
    out['no_ack_rate'] = rate([not cjk(t['ack']) for t in allt])
    return out, flags


def load_sessions(name):
    import common
    sessions = []
    for part in name.split('+'):
        sessions += [common.load(f) for f in sorted((common.RUNS / part / 'sessions').glob('*.json'))]
    return sessions


def story_ids():
    import common
    bank = common.load(common.ROOT / 'docs/prototypes/full-interview-v5/story-questions.json')
    return {q['id'] for q in bank['questions'] if q['depth'] == 'story'}


ROWS = [('计入的采访者发言', 'turns'), ('　追问 / 深挖 / 收尾', None),
        ('复述率（全部）', 'restate_rate'), ('　追问', 'restate_rate_followup'), ('　深挖', 'restate_rate_deepen'),
        ('　收尾转题', 'restate_rate_close'), ('　说话层原始输出（代码守卫前）', 'raw_restate_rate'),
        ('复述率（对本题老人全部回答）', 'restate_any_rate'),
        ('套路率（全部）', 'routine_rate'), ('　收尾转题', 'routine_rate_close'),
        ('　“承接句+那+问句”', 'frame_rate'), ('　套路短语（咱们再聊聊/换个话题…）', 'template_rate'),
        ('　同会话开头重复', 'opener_repeat_rate'), ('　同会话引子重复', 'lead_repeat_rate'),
        ('没有承接的发言占比', 'no_ack_rate'), ('承接平均字数', 'ack_len_mean')]


def cell(m, key):
    if key is None:
        return f"{m['turns_followup']} / {m['turns_deepen']} / {m['turns_close']}"
    v = m.get(key)
    return '' if v is None else str(v)


def main(argv):
    listing = '--list' in argv
    story = story_ids() if '--story' in argv else None
    runs = [a for a in argv if not a.startswith('--')]
    runs = [tuple(x.split('=', 1)) if '=' in x else (x, x) for x in runs]
    ms = []
    for lbl, name in runs:
        m, flags = run_style(load_sessions(name), story)
        ms.append(m)
        if listing:
            print(f'## {lbl}')
            for s, i, msg, st in flags:
                f = ('R' if st['restate'] else '-') + ('F' if st['frame'] else '-') + ('T' if st['template'] else '-') + \
                    ('O' if st['opener_repeat'] else '-') + ('L' if st['lead_repeat'] else '-')
                print(f"  {f} {s['name']} {s['episodes'][i]['qid']} [{msg['kind']}] {msg['text']}  | ack={st['ack']!r} ptr={st['pointer']!r} {st['restate_info']}")
    print('| 指标' + ('（故事题）' if story else '') + ' | ' + ' | '.join(f'{lbl}' for lbl, _ in runs) + ' |')
    print('|---|' + '---|' * len(runs))
    for name, key in ROWS:
        print(f'| {name} | ' + ' | '.join(cell(m, key) for m in ms) + ' |')
    sys.stdout.flush()
    if '--json' in argv:
        print(json.dumps({lbl: m for (lbl, _), m in zip(runs, ms)}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1:])
