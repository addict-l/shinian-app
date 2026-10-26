"""Wording measures of the v5 speaking layer, ported from tools/interview_eval/simulate/style.py (and the content
bigrams of simulate/persona.py): how an interviewer turn is split into acknowledgement, pointer, move-on clauses and
the core question, and the restate test that the v5d-v5f echo guards use. The functions below are the simulator's
own code; only the imports differ (the OpenCC map is the pinned runtime's, the stop-signal patterns are
interview_speaker's). tests/test_interview_v5f.py runs both implementations over the same texts.
"""
import re

from app.ai.interview_speaker import _simp as simp


FUNC = set('的您你我他她它们么样怎里候得了是有在或及与本这那对把被就都也还又很最什哪谁吗呢吧啊着过来去上下中为以于从和跟会能要想说一个些其所之')


def bigrams(text):
    t = re.sub(r'[^一-鿿]', '', simp(text))
    return {t[i:i + 2] for i in range(len(t) - 1) if t[i] not in FUNC and t[i + 1] not in FUNC}


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
    from app.ai import interview_speaker as interview
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
