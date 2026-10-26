"""Speaking layer v4d (and the shared pieces of v5f): how to say what the judgment layer decided, never what to ask.

Port of the parts of tools/interview_eval/simulate/interview.py that the tested
v4d configuration uses: the speaker input (speaker_user), reply parsing,
acknowledgement cleaning, close composition, validation and the natural-ending
rules (v4_decide with elder_signal). Wording rules are general; nothing depends
on a particular person. The prompt and its parameters come from the pinned
runtime bundle (``rt``); the judgment layer still decides every target.

Two helpers have no simulator counterpart because the backend keeps its existing
steps where the simulator moved straight to the next question: ``lead_ack``
keeps only the acknowledgement of a close (for the existing draft sentence and
the module menu), and ``compose_ask`` bundles the simulator's follow-up branch.
``supplement_end`` (C03) reads the answers after the draft offer, a step the
simulator does not have. elder_signal, signal_scope, has_content and decide are kept identical
to the simulator's (C01, C02, v5d signal scope); the v5 deepen step and wording guards are in interview_story.
Every v5 rule is switched by a key of the bundle's speaker-config.json, so the v3j_v4d bundle (no such keys)
behaves exactly as before.
"""
import re

BANNED = re.compile(r'保存|整理|草稿|记录下|记下来|已记下|系统|App|APP|采访者|题目|下一题|要素|资料')
PRAISE = re.compile(r'太棒|真棒|了不起|非常精彩|谢谢您的分享|感谢您的分享|感谢分享|太感人|非常感人')
# 'declined_partial' (C02) tells the speaking layer the same as a refusal; only what follows differs.
CLOSE_REASON = {'done': '这个话题已经聊完', 'limited': '这个话题聊到这里就够了', 'unknown': '老人说记不清了', 'declined': '老人不想多说',
                'declined_partial': '老人不想多说',
                'deferred': '老人想以后再讲', 'cap': '这个话题已经追问过几次，不再追问', 'asked_once': '这一点刚才问过了，老人没接着讲，不再追问',
                'error': '这个话题聊到这里就够了', 'rest': '老人累了想歇一会儿',
                'rest_resume': '老人刚才说累了，歇了一会儿，刚点了“继续”；这个话题不再追问，接着聊下一题',
                # v5d signal scope: the elder could not remember one point and went on to tell more
                'unknown_partial': '老人说有一点记不清，接着又讲了别的；记不清的那一点不再问，这个话题聊到这里'}


def recorded_fields(rt, result):
    """What the speaker may echo as recorded: non-optional, non-missing fields (interview.judge_summary)."""
    fields = {}
    for fid, f in ((result or {}).get('fields') or {}).items():
        if rt.F[fid]['requirement'] == 'optional':
            continue
        st = f.get('state')
        if st and st != 'missing':
            v = f.get('value')
            v = '；'.join(x for x in v if isinstance(x, str)) if isinstance(v, list) else v
            fields[fid] = {'state': st, 'value': v}
    return fields


def recorded_lines(rt, fields, limit=4, width=40):
    out = []
    names = {'known': None, 'none': '明确说没有', 'unknown': '说记不清', 'declined': '不愿讲', 'deferred': '以后再讲', 'ambiguous': '说有但没说清'}
    for fid, f in fields.items():
        label = rt.F[fid]['label']
        if f['state'] == 'known' and f.get('value'):
            v = f['value'] if len(f['value']) <= width else f['value'][:width] + '…'
            out.append(f'{label}：「{v}」')
        elif names.get(f['state']):
            out.append(f'{label}：{names[f["state"]]}')
    return out[:limit]


def speaker_user(rt, qid, dialogue, fields, task, target=None, engine_question=None, reason=None, next_entry=None, prev_close=None):
    q = rt.questions[qid]
    lines = [f'当前话题：{q["main_question"]}', '对话：']
    for role, text in dialogue:
        lines.append(('问：' if role == 'system' else '答：') + text)
    rec = recorded_lines(rt, fields)
    lines.append('已记下：' + ('；'.join(rec) if rec else '（暂无）'))
    if task == 'ask':
        f = rt.F[target]
        usable = f['usable_answer'] if len(f['usable_answer']) <= 80 else f['usable_answer'][:80] + '…'
        lines += ['任务：ask', f'要问的一点：{f["label"]}', f'参考问法：{engine_question or f["question"]}', f'怎样算答上：{usable}']
        asked = [t for role, t in dialogue if role == 'system']
        if any(_norm(f['question']) in _norm(a) or _norm(a).endswith(_norm(q['main_question'])) and (f.get('activation') or {}).get('always')
               for a in asked):
            lines.append('提示：前面已经问过这一点，老人没有正面回答。别把原来的问法换几个字再问；从他刚讲的事里挑一个角度，把这一点问得更小、更具体、更好回答。')
    else:
        lines += ['任务：close', f'收尾原因：{CLOSE_REASON.get(reason, reason)}',
                  f'下一题：{next_entry}' if next_entry else '下一题：无（这是今天最后一个话题）']
        if prev_close:
            lines.append(f'上次换话题时你说的：{prev_close}')
    return '\n'.join(lines)


def _norm(s):
    return re.sub(r'[\s，。！？、,.!?；;：:“”"‘’…~—]', '', s or '')


INFER = re.compile(r'一定|肯定|想必|准是|必定|必然|应该很|估计很|记住了|记下了|记下来了|记着了')
# evaluations the interviewer may only echo, never introduce: dropped when the elder's own words in this topic lack them
EVAL = ('热闹', '踏实', '舒坦', '自在', '豁达', '清净', '了不起', '有分量', '开创', '难得', '不简单', '真足', '厉害', '自豪', '骄傲', '幸福',
        '温馨', '欣慰', '感动', '扎实', '乐观', '坚强', '勇敢', '能干', '懂事', '孝顺', '放心', '满足', '快乐', '开心', '高兴', '难过',
        '伤心', '委屈', '害怕', '孤单', '别扭')
HARDSHIP = re.compile(r'苦|难|累|辛苦|艰|受罪|吃亏|不容易|穷|饿|病|死|走了|去世|过世|逃|躲')
ACK_MAX = 36
LISTENING_EVAL = re.compile(r'真仔细|真贴心|真细心|有深意|真用心|真懂事|真孝顺|真了不起|'
                           r'真好|挺好|有意思|有趣|挺重要|很重要|真温暖|听着就实在')
BARE_ACK = re.compile(r'^(?:嗯|噢|哦|喔|啊|唉|哎|呀|好|好的|对|是|行|原来)*$')
LISTENING_FALLBACK = '嗯，这段我听到了。'
LISTENING_QUESTION = re.compile(r'多大|几岁|怎样|怎么样|怎么|谁|什么|哪(?:年|天|里|儿|个|一|位)|'
                               r'^(?:那)?(?:后来|以后|之后|当时|现在|您|他|她|师傅|父亲|母亲)呢[，,。！!；;]?$')


def simp_text(rt, text):
    return ''.join(rt.char_map.get(c, c) for c in str(text or ''))


def clean_ack(rt, text, elder_text=''):
    """Drop ack clauses that infer, evaluate beyond the elder's own words, or ask a question of their own; keep the
    rest in order. Returns (text, [reasons])."""
    elder = simp_text(rt, elder_text)
    parts = [p for p in re.findall(r'[^，,。！!；;？?]*[，,。！!；;？?]?', text or '') if p.strip()]
    kept, why = [], []
    for p in parts:
        reason = None
        if INFER.search(p):
            reason = 'inference'
        elif rt.speaker_config.get('listen_first') and LISTENING_QUESTION.search(p.strip()):
            reason = 'question_in_ack'
        elif re.search(r'[？?]$', p) or re.search(
                r'(?:吧|吗|么)[，,。！!；;]?$' if rt.speaker_config.get('listen_first')
                else r'(?:吧|吗|么|呢)[，,。！!；;]?$', p):
            reason = 'question_in_ack'
        elif rt.speaker_config.get('listen_first') and LISTENING_EVAL.search(p):
            reason = 'evaluation'
        else:
            for w in EVAL:
                if w in p and w not in elder:
                    reason = 'evaluation'
                    break
            if not reason and '不容易' in p and not HARDSHIP.search(elder):
                reason = 'evaluation'
        if reason:
            why.append(reason)
            if kept and re.search(r'[。！!；;？?]$', p):  # the dropped clause ended a sentence: so does the one before it
                kept[-1] = re.sub(r'[，,]$', '。', kept[-1])
            continue
        kept.append(p)
    while len(''.join(kept)) > ACK_MAX and len(kept) > 1:  # long echo: keep the first clauses
        kept.pop()
        why.append('trimmed')
    out = ''.join(kept).strip()
    out = re.sub(r'[，,；;]$', '。', out)
    return out, why


def listening_ack(rt, ack, elder_text=''):
    """The listening candidate must not silently turn a removed ack into a bare question.

    Short factual acknowledgements are intentional, even if their words overlap the
    answer/question. The provider normally supplies them. An empty/unsafe response
    gets a disclosed conservative fallback, never an invented fact or feeling.
    Historical bundles do not opt in and retain their exact composition.
    """
    if not rt.speaker_config.get('listen_first'):
        return ack, []
    ack, notes = clean_ack(rt, ack, elder_text)
    if ack and not BARE_ACK.fullmatch(_norm(ack)) and not check_close(ack):
        return ack, notes
    return LISTENING_FALLBACK, notes + ['ack_fallback']


def compose_close(rt, reply, next_entry, elder_text=''):
    """Close message from the speaker's reply. The next entry must be the final (and only) question, asked as
    written (an optional short lead-in inside the same sentence is kept). Repairs instead of discarding: extra
    questions are dropped; a reworded entry is replaced by the original. Returns (text, ack_part, notes, ok)."""
    notes = []
    sents = [s for s in re.findall(r'[^。！？!?]*[。！？!?]?', (reply or '').strip()) if s.strip()]
    qs = [i for i, s in enumerate(sents) if re.search(r'[？?]', s)]
    entry_q = None
    lead = ''
    if next_entry and qs:
        last = sents[qs[-1]]
        if _norm(last).endswith(_norm(next_entry)):
            body = next_entry.rstrip('？?')
            pos = last.rfind(body)
            lead_raw = last[:pos] if pos > 0 else ''
            if len(_norm(lead_raw)) <= 20:
                entry_q = last.strip()
            else:  # a long lead-in becomes its own sentence; the entry follows as written
                lead = re.sub(r'[，,]\s*$', '。', lead_raw.strip())
                entry_q = next_entry
        else:
            notes.append('entry_reworded')
    if len(qs) > (1 if entry_q else 0):
        notes.append('extra_question')
    ack = ''.join(s for i, s in enumerate(sents) if i not in qs).strip() + lead
    ack, why = clean_ack(rt, ack, elder_text)
    notes += why
    # a statement that just announces the next topic in other words is redundant once the entry follows
    errs = check_close(ack) if ack else []
    if errs:
        return None, ack, notes + errs, False
    if not next_entry:
        return ack, ack, notes, bool(ack)
    if not ack and not entry_q:
        return None, ack, notes + ['empty'], False
    if entry_q:
        entry_q = re.sub(r'^那[，,]\s*', '那', entry_q)
    return join(ack, entry_q or next_entry), ack, notes, True


# Clauses that move the conversation on: they belong to the transition, not to the acknowledgement.
TRANSITION = re.compile(r'换个话题|换个话头|换一个话题|不聊这个|再聊聊|接着聊|聊聊别的|说说别的|下一个话题|今天先聊到|先聊到这|就先到这|先到这儿')


def lead_ack(rt, reply, next_entry=None, elder_text='', drop_transition=True):
    """The acknowledgement of a close reply, for a step where the backend's own fixed text follows instead of
    the next question (draft sentence, module menu). For a single next question it is compose_close's own ack
    part; otherwise (module menu) the sentences before the first question. Same cleaning and checks as a close;
    with drop_transition, clauses that move on to another topic are removed. Returns '' when nothing usable
    remains, so the caller keeps its fixed text alone."""
    if next_entry:
        _, ack, _, ok = compose_close(rt, reply, next_entry, elder_text)
        ack = ack if ok else ''
    else:
        sents = [s for s in re.findall(r'[^。！？!?]*[。！？!?]?', (reply or '').strip()) if s.strip()]
        first_q = next((i for i, s in enumerate(sents) if re.search(r'[？?]', s)), len(sents))
        ack, _ = clean_ack(rt, ''.join(sents[:first_q]).strip(), elder_text)
    if drop_transition and ack:
        kept = []
        for p in [p for p in re.findall(r'[^，,。！!；;]*[，,。！!；;]?', ack) if p.strip()]:
            if TRANSITION.search(p):
                if kept and re.search(r'[。！!；;]$', p):
                    kept[-1] = re.sub(r'[，,]$', '。', kept[-1])
                continue
            kept.append(p)
        ack = re.sub(r'[，,；;]$', '。', ''.join(kept).strip())
    if not ack or check_close(ack):
        return ''
    return ack


def check_ask(ack, question, prior):
    errs = []
    if not question or not question.rstrip().endswith(('？', '?')):
        errs.append('no_question')
    if len(re.findall(r'[？?]', ack + question)) != 1:
        errs.append('question_count')
    if len(question) > 60 or len(question) < 4:
        errs.append('question_length')
    if len(ack) > 40:
        errs.append('ack_length')
    if BANNED.search(ack + question):
        errs.append('meta_words')
    if PRAISE.search(ack + question):
        errs.append('praise')
    if question in prior:
        errs.append('repeat')
    return errs


def check_close(ack):
    errs = []
    if re.search(r'[？?]', ack):
        errs.append('question_in_close')
    if len(ack) > 60:
        errs.append('ack_length')
    if BANNED.search(ack):
        errs.append('meta_words')
    if PRAISE.search(ack):
        errs.append('praise')
    return errs


def parse_speaker(row):
    out = row.get('output') if isinstance(row.get('output'), dict) else {}
    ack = out.get('ack') if isinstance(out.get('ack'), str) else ''
    if not ack and isinstance(out.get('reply'), str):
        ack = out['reply']
    question = out.get('question') if isinstance(out.get('question'), str) else ''
    return ack.strip(), question.strip()


def join(*parts):
    parts = [p.strip() for p in parts if p and p.strip()]
    out = ''
    for p in parts:
        if out and not re.search(r'[。！？!?，,…~]$', out):
            out += '。'
        out += p
    return out


def compose_ask(rt, row, result, target, prior, elder_text=''):
    """Follow-up text: ack + question; a question failing the checks is replaced by the engine's question
    (a valid ack is kept, as in v4d). Returns (text, question_part, record)."""
    ack, question = parse_speaker(row)
    ack, fixes = clean_ack(rt, ack, elder_text)
    if rt.speaker_config.get('echo_guard'):  # v5d-v5f (the v3j_v5f bundle): a restating acknowledgement is dropped
        from app.ai.interview_story import restates
        if restates(ack, elder_text, rt.speaker_config.get('echo_names')):
            ack, fixes = '', fixes + ['restate_dropped']
    errs = check_ask(ack, question, prior)
    if INFER.search(question):
        errs.append('inference_in_question')
    if errs:
        question = result.get('question') or rt.F[target]['question']
        if check_close(ack):
            ack = ''
    ack, why = listening_ack(rt, ack, elder_text)
    fixes += why
    return join(ack, question), question, {'ack': ack, 'question': question, 'errors': errs,
                                          'fallback': bool(errs) or 'ack_fallback' in fixes,
                                          'repairs': fixes}


# What the elder just said, read literally (general wording, no per-person rules): signs that the person does not
# want to go on with this point, cannot remember it, or is tired. The judgment layer may still return 'ask' in these
# cases (the field stays missing); the natural-ending rule then closes instead of pressing.
SIG_REST = re.compile(r'累了|歇(?:一)?(?:会|下)|歇歇|休息(?:一)?(?:会|下)|先休息|缓一缓|喘口气|改天再(?:聊|说|讲)|下次再(?:聊|说|讲)|今天先(?:到这|聊到这)')
SIG_DECLINE = re.compile(r'不多(?:讲|说|谈)|不(?:想|愿|愿意|太想|大想)多?(?:讲|说|提|聊|谈)|(?:就|先|还是)不(?:讲|说|提|聊|谈)|不(?:讲|说|提|聊|谈)了|别问了|不想回答')
SIG_UNKNOWN = re.compile(r'记不(?:太|大)?清|记不(?:太|大)?得|不(?:太|大)?记得|想不(?:太|大)?起|说不(?:太|大)?上|说不(?:太|大)?清|说不(?:太|大)?好|没(?:什么|啥|多大)?印象|不(?:太|大)?清楚|忘(?:了|记了|得差不多)')


# A signal counts only as the elder's own request about the present (C01). The text is read clause by clause:
# a match is ignored when it is negated ("不是累了"), when the clause's subject is someone else ("她不想说",
# "我妈叫我歇一会儿"), or when the clause narrates the past, a habit or a condition ("那时候下工累了就歇一会儿",
# "要是记不清就算了"); a time word used as a topic ("那时候的事记不清了") is not narration. A wish to go on
# ("我还想接着聊") outweighs a rest signal. All general wording; nothing depends on a particular person.
CLAUSE = re.compile(r'[^，,。！!？?；;、\n]+[，,。！!？?；;、\n]*')
SENTENCE_END = re.compile(r'[。！!？?\n]')
# someone other than the elder: pronouns (not 其他/其它), kin, people around him and roles such as 队长 / 厂长,
# optionally "我妈", "我们家老伴"
OTHER = (r'(?:(?:我|俺|咱)们?家?的?)?(?:老伴儿?|爱人|丈夫|妻子|老婆|老公|媳妇|对象|父亲|母亲|爸爸?|妈妈?|爹|娘|父母|爹妈|爷爷|奶奶|'
         r'姥姥|姥爷|外公|外婆|公公|婆婆|哥哥?|姐姐?|弟弟?|妹妹?|兄弟|姐妹|叔叔?|伯伯|大伯|舅舅?|姑姑|阿姨|婶婶?|嫂子|'
         r'儿子|女儿|闺女|孩子|孙子|孙女|老师|师傅|领导|干部|书记|主任|医生|大夫|护士|老板|东家|掌柜|同事|工友|战友|邻居|'
         r'街坊|老乡|朋友|同学|亲戚|家里人|家人|大人|长辈|(?:队|(?<![上下加值轮早晚夜跟])班|组|厂|校|连|排|营|团|村|乡|社|院|所|局|处|科|(?<!全)部|船|机)长)|'
         r'(?<![其吉])(?:他|她|它)们?|人家|别人|大家|对方')
SUBJECT = re.compile(rf'(?P<other>{OTHER})|(?P<self>我们|咱们|俺们|我|俺|咱)')
# someone else telling or letting the elder do something: what follows is reported, not the elder's request
REPORTED = re.compile(rf'(?:{OTHER})(?:就|也|总|老|常|还|又|都)?(?:说|讲|叫|让|劝|喊|催|告诉|嘱咐|交代|不让|不许|不准|问)(?!的)')
NEGATED = re.compile(r'(?:不是|并不是|倒不是|也不是|又不是|并非|没有|没|不用|不必|不需要|用不着|不)'
                     r'(?:因为|说|真的?|太|很|有点|有些|想|要|愿意|打算|再){0,2}$')
PAST = re.compile(r'(?:那时候|那时|那会儿?|当时|当年|那年|那些年|那阵子?|以前|从前|过去|早先|早年|年轻(?:的)?时(?:候)?|'
                  r'小时候|后来|每天|天天|每回|每次|常常|经常|总是|老是|平时|平常|一般|有时候?|往往|'
                  r'下工|下班|收工|放工|放学|干完活|干活|下地|上工)(?![的儿子候])')
CONDITION = re.compile(r'要是|如果|假如|万一|一旦|只要|每当|的话')
HABIT = re.compile(r'累了(?:就|便|也|还|才)|累了(?:(?:一|大?半)辈子|一生|一世|(?:几|好几|十几|几十|这么多|那么多|好多|多少)年)')
PRESENT = re.compile(r'现在|今天|今儿|这会儿?|眼下|如今|此刻|刚才|这阵子')
CONNECTIVE = re.compile(r'^\s*(?:就|便|也|又|还|才|再|然后|接着|于是|所以|结果)')
CONTINUE = re.compile(r'(?:还|再)?(?:想|要|能|可以)?(?:接着|继续|往下)(?:聊|说|讲|谈)|还(?:能|想|要|可以)(?:聊|说|讲|谈)|'
                      r'(?:不|没)(?:累|乏)|不用(?:歇|休息)')


def _clauses(text):
    """Clauses with their own subject ('self' / 'other' / None) and narration flag; a clause opened by a connective
    ("就歇一会儿") carries on the previous clause of the same sentence."""
    out, prev = [], None
    for c in CLAUSE.findall(text or ''):
        subject = None
        for m in SUBJECT.finditer(c):
            if c[m.end():m.end() + 1] != '的':  # "他的事" is a possessive, not a subject
                subject = 'other' if m.group('other') else 'self'
        narrative = bool(HABIT.search(c) or CONDITION.search(c) or (PAST.search(c) and not PRESENT.search(c)))
        item = {'text': c, 'subject': subject, 'narrative': narrative, 'inherit': None}
        if prev is not None and not SENTENCE_END.search(prev['text']):
            item['inherit'] = prev
        out.append(item)
        prev = item
    return out


def _own_now(clause, m, kind):
    """Whether the match ``m`` in ``clause`` is the elder's own present wording."""
    prefix = clause['text'][:m.start()]
    if NEGATED.search(prefix) or REPORTED.search(prefix):
        return False
    subject = None
    for s in SUBJECT.finditer(prefix):
        if prefix[s.end():s.end() + 1] != '的':
            subject = 'other' if s.group('other') else 'self'
    narrative = clause['narrative']
    prev = clause['inherit']
    # carried over: after a connective for every signal; for tiredness also by a clause without its own subject
    # ("她累了，想歇一会儿"), which mostly narrates
    if prev and (CONNECTIVE.search(clause['text']) or (kind == 'rest' and clause['subject'] is None)):
        subject = subject or prev['subject']
        narrative = narrative or prev['narrative']
    return not narrative and subject != 'other'


def elder_signal(text):
    clauses = _clauses(text)
    found = {kind: any(_own_now(c, m, kind) for c in clauses for m in pattern.finditer(c['text']))
             for kind, pattern in (('rest', SIG_REST), ('declined', SIG_DECLINE), ('unknown', SIG_UNKNOWN))}
    if found['rest'] and not any(_own_now(c, m, 'continue') for c in clauses for m in CONTINUE.finditer(c['text'])):
        return 'rest'
    if found['declined']:
        return 'declined'
    if found['unknown']:
        return 'unknown'
    return None


# v5d signal scope (policy "signal_scope", the v3j_v5f bundle; without it the C01 rules exactly as before): an answer
# that says it cannot remember (or cannot think of) one point and then goes on to tell something new is a partial
# "can't remember" -- only that point is not pressed; the question does not end because of it. Read literally and
# generally: the answer is cut into clauses; clauses carrying a stop signal or a hedge about memory ("好多都模糊了")
# are the signal part; in the other clauses, content bigrams (scope_bigrams) that are neither in the question just
# asked nor in the elder's earlier words of this question nor generic are new (a clause whose bigrams are mostly not
# new is a retelling and adds none). Partial when there are at least SCOPE_NEW_BIGRAMS new bigrams and the clauses
# carrying them hold at least ``min_chars`` characters. Only 'unknown' is scoped: "不想多讲" and "累了" are requests
# about the conversation itself and keep closing as before. The block from SCOPE_HEDGE to has_content is the
# simulator's text (tests/test_interview_c01_c03.py, tests/test_interview_v5f.py).
_CHAR_MAP = None


def _simp(text):
    """Simplified characters by the OpenCC map of the pinned runtimes (the same file in every v3j bundle)."""
    global _CHAR_MAP
    if _CHAR_MAP is None:
        import json
        from pathlib import Path
        _CHAR_MAP = json.loads((Path(__file__).resolve().parent / 'interview_runtime_v3j_v4d/opencc-ts-char-map.json')
                               .read_text(encoding='utf-8'))
    return ''.join(_CHAR_MAP.get(c, c) for c in str(text or ''))


# v5c1: "can't think of one" wordings elder_signal does not cover (deepen only, and the scope test with extra)
DEEPEN_UNKNOWN = re.compile(r'想不出|说不出|没(?:有)?(?:什么|啥)特别')


SCOPE_HEDGE = re.compile(r'模糊|记性|年纪大了|人老了|太久了|时间久了|年头久了|那么久|这么久')
SCOPE_GENERIC = None
SCOPE_NEW_BIGRAMS = 4
SCOPE_PARTICLE = re.compile(r'[嘛呀哎啊呢吧哦喔嗯哈啦咯呗]')  # a bigram with a sentence particle is not content
# content characters for the scope test: lighter than persona.FUNC, which also drops 对 上 去 来 说 想 … ("反对", "北上")
SCOPE_FUNC = set('的了是在我你您他她它们么这那就都也还又很吗呢吧啊着个一些其之和与及或把被得地')


def scope_bigrams(text):
    t = re.sub(r'[^一-鿿]', '', _simp(text))
    return {t[i:i + 2] for i in range(len(t) - 1) if t[i] not in SCOPE_FUNC and t[i + 1] not in SCOPE_FUNC}


def _scope_generic():
    global SCOPE_GENERIC
    if SCOPE_GENERIC is None:
        SCOPE_GENERIC = scope_bigrams('时候以后后来那时当时现在事情经历印象记得觉得一下一点一件这件那件这段那段日子生活好像大概反正就是这样'
                                '具体详细情形情况样子清楚知道真的实在其实自己特别一样')
    return SCOPE_GENERIC


def signal_scope(text, question='', before='', min_chars=15, extra=False):
    """For an answer whose literal signal is 'unknown' (or, with ``extra``, the v5c1 "想不出 / 说不出" wordings):
    ('partial', rest_text, signal_text) when besides the signal it tells something new (rest_text = all clauses
    outside the signal part), else ('whole', '', signal_text).
    ``question``: the interviewer's words just answered; ``before``: the elder's earlier words in this question."""
    seen = scope_bigrams(question) | scope_bigrams(before) | _scope_generic()
    new, rest, sig, fresh = [], [], [], set()
    for c in CLAUSE.findall(text or ''):
        if SIG_UNKNOWN.search(c) or SIG_DECLINE.search(c) or SIG_REST.search(c) or SCOPE_HEDGE.search(c) or \
                (extra and DEEPEN_UNKNOWN.search(c)):
            sig.append(c)
            continue
        rest.append(c)
        allb = {b for b in scope_bigrams(c) if not SCOPE_PARTICLE.search(b)}
        f = allb - seen
        if f and 2 * len(f) > len(allb):  # a clause at least half made of what was already said is a retelling, not new
            new.append(c)
            fresh |= f
    if len(fresh) >= SCOPE_NEW_BIGRAMS and len(_norm(''.join(new))) >= min_chars:  # rest_text: every clause outside the signal
        return 'partial', re.sub(r'[，,、；;]$', '。', ''.join(rest).strip()), ''.join(sig).strip()
    return 'whole', '', ''.join(sig).strip()


def has_content(result):
    """Whether this question already has a real answer (C02): an active field known or explicitly none (optional
    fields are not counted, so the backend and the simulator's judge summary read the same)."""
    eff = result.get('effective') or {}
    return any(eff.get(a) in ('known', 'none') for a in result.get('active') or [])


def decide(cfg, result, st, text=''):
    """Natural-ending rules on top of the engine decision (interview.v4_decide). ``st`` holds this question's
    'followups', 'ask_counts' (targets actually asked) and 'prev_eff'; 'signal' is set as a side effect.
    Returns (action, reason_or_target).

    'declined_partial' (C02, decision of 2026-10-23): the elder has answered and then says he does not want to
    go into it further (his own words, or the engine's limited with a declined field next to an answered one). Not
    a refusal: no more follow-ups, the question finishes as answered (draft step in the
    guided interview, the next skeleton question in the life overview); the speaking layer is told the same
    close reason as a refusal ('老人不想多说'). A decline before any real answer stays a refusal ('declined').

    v5d signal scope (cfg 'signal_scope', the v3j_v5f bundle): a 'can't remember' that goes on to tell something new
    closes as 'unknown_partial' and only the point just asked is not pressed; ``st`` then also carries 'asked' (the
    question part just answered), 'before' (the elder's earlier words of this question) and 'last_target'."""
    d = result.get('decision')
    eff = result.get('effective') or {}
    active = result.get('active') or []
    sig = elder_signal(text) if cfg.get('signal_close') else None
    st['signal'] = sig
    # v5d signal scope (policy signal_scope; off = the rules exactly as the backend has them)
    partial = False
    if cfg.get('signal_scope') and sig == 'unknown':
        scope = signal_scope(text, st.get('asked', ''), st.get('before', ''), cfg.get('scope_min_chars', 15))
        st['scope'] = scope
        partial = scope[0] == 'partial'
    if d == 'paused' or sig == 'rest':
        return 'rest', None
    if d in ('skipped',) or (d == 'limited' and 'declined' in [eff.get(a) for a in active]):
        return 'close', 'declined_partial' if d == 'limited' and has_content(result) else 'declined'
    if d == 'deferred':
        return 'close', 'deferred'
    if d == 'invalid':
        return 'close', 'error'
    if d == 'ready':
        return 'close', 'declined_partial' if sig == 'declined' else 'done'
    if d == 'limited':
        if 'unknown' in [eff.get(a) for a in active]:
            return 'close', 'unknown_partial' if partial else 'unknown'
        return 'close', 'limited'
    target = result.get('target')
    if sig == 'declined':
        return 'close', 'declined_partial' if has_content(result) else 'declined'
    if sig == 'unknown':
        if not partial:
            return 'close', sig
        # v5d: only the point just asked is not pressed; another open point the engine wants may still be asked
        if not (target and st.get('last_target') and target != st['last_target']):
            return 'close', 'unknown_partial'
    if st['followups'] >= cfg['followup_cap']:
        return 'close', 'cap'
    if st['ask_counts'].get(target, 0) >= cfg['same_target_cap']:
        return 'close', 'asked_once'
    newly = [a for a in active if eff.get(a) in ('unknown', 'declined') and st['prev_eff'].get(a) not in ('unknown', 'declined')]
    if newly and st['followups'] >= cfg.get('stop_after_unknown_once_asked', 1):
        return 'close', 'unknown_partial' if partial else 'unknown'
    return 'ask', target


# After the draft offer (supplement step, C03): does the elder say there is nothing more to add? Read per clause, as
# general wording ("没有了，就这些" / "这件事我记得的就是这些，没有别的补充了" / "能想起来的都讲了" /
# "没什么补充了，这件事就是这样"). A clause counts as an ending only when the whole clause is one, so
# "也没什么特别原因" or "那时候粮食没有了" stay content.
_FILL = r'(?:嗯|啊|哦|噢|呃|唉|哎|好的|好|行|对|是的|是|那就|那|我们|咱们|我|俺|咱|您|刚才|刚刚|已经|都|也|再|确实|真的|实在|' \
        r'暂时|目前|现在|大概|基本上?|其实|反正|应该|别的|其他的?|其它的?|呀|吧|啦|了|呢|就)*'
_TOPIC = r'(?:(?:关于|对于|至于|说到|讲到|说起)[\u4e00-\u9fff]{1,10}|(?:这|那)(?:件|个|段|些|回)?(?:事情|事儿|事|误会|经历|情况|方面)?)'
_REL = (r'(?:我|俺)?(?:能|所|还|该)?(?:记得|记着|记住|记起来|想起来|想得起来|想到|知道|补充|要补充|要说|要讲|想说|能说|能讲|'
        r'可说|可讲|说|讲)的(?:东西|事情|事|内容)?')
_SUMMARY = (r'(?:就|就是|也就是?|只有|大概就|差不多就)(?:这些|这么多|这样|这么些|这点|这么回事)(?:了|吧|啦)?|'
            r'(?:都|全|全都|基本都)(?:讲|说|聊|告诉您|讲给您听|说给您听)(?:过|完)?了|(?:讲|说|聊)(?:完|得差不多)了|差不多了|就到这(?:儿|里)?(?:吧|了)?|先这样(?:吧|了)?|'
            r'(?:就)?(?:说|讲|聊)(?:到)?这(?:些|儿|里)(?:吧|了)?|(?:就)?(?:知道|记得|记着|想起来)(?:的)?(?:就是|就)?这些(?:了|吧)?|'
            r'就(?:是)?刚才(?:说|讲)的(?:那些|这些)|不多(?:说|讲|谈|聊)了|不(?:想|愿意?)(?:再|多)?(?:说|讲|谈|聊)了|不(?:说|讲)了')
# how much is left: "没什么", "没有太多", "没什么特别的" (an ending only as a whole clause, so "没什么特别原因" stays content)
_HOW_MUCH = r'(?:(?:什么|啥)?(?:太多|更多|特别)的?|什么|啥|别的|其他的?|其它的?|更多的?|多少)'
_ABSENCE = (rf'没有?{_HOW_MUCH}?(?:要|可|好|想|能|再)?补充(?:的)?(?:了|啦)?|'
            rf'没有?{_HOW_MUCH}(?:(?:要|可|好|想|能|再)?(?:说|讲|聊)的?)?(?:了|啦)?|'
            r'不用(?:再)?(?:补充|说|讲)?了|(?:先|那就|就)?(?:确认)?保存(?:吧|了|一下)?|(?:先|那就|就)?整理(?:吧|一下)|'
            r'(?:别的|其他的?)(?:我)?(?:也|真|就)?(?:想不起来|记不清|记不得|想不起|想不到)(?:了|啦)?|'
            r'(?:暂时|一时)?想不(?:到|起来)(?:别的|还有什么(?:要补(?:充)?的)?)?(?:了|啦)|(?:以后|回头|改天)想起来再(?:跟您)?(?:说|讲)(?:吧)?')
_BARE = r'没有了|没有啦|没了|没啦|没有|没|没啥|没什么'
SUPPLEMENT_END = re.compile(rf'{_FILL}(?:{_TOPIC}{_FILL})?(?:{_REL}{_FILL})?(?:{_SUMMARY}|{_ABSENCE}){_FILL}|{_FILL}(?:{_BARE}){_FILL}')
SUPPLEMENT_NEUTRAL = re.compile(rf'{_FILL}(?:{_TOPIC})?{_FILL}')
# saying there is still more ("没有，我还想说说我妈") is not an ending, whatever else the message says
SUPPLEMENT_MORE = re.compile(r'还(?:想|要)(?:再)?(?:说|讲|补充|聊)|再(?:说说|讲讲|补充)|(?:想|要)补充(?!的)|'
                             r'还有(?:一件|一点|个事|件事|几句|话)|(?:还)?没(?:说|讲)完')


def supplement_end(text, *, listen_first=False):
    """'only': the elder only says there is nothing more; 'with_content': something new and an ending in the same
    message; None: no ending. Clauses are compared without punctuation or spaces."""
    if listen_first:
        return _listening_supplement_end(text)
    if SUPPLEMENT_MORE.search(text or ''):
        return None
    ends = content = False
    for clause in CLAUSE.findall(text or ''):
        bare = re.sub(r'[\s，,。！!？?；;、…~—“”"‘’「」]', '', clause)
        if not bare:
            continue
        if SUPPLEMENT_END.fullmatch(bare):
            ends = True
        elif not SUPPLEMENT_NEUTRAL.fullmatch(bare):
            content = True
    if not ends:
        return None
    return 'with_content' if content else 'only'


def _listening_supplement_end(text):
    """Read a whole negative ending before its embedded words such as "要补充".

    Only this candidate opts in. Do not remove topic fragments or possible facts:
    anything outside the existing ending/neutral grammar remains content and is
    recorded by the normal judgment path before review. Quoted or reported words
    are content, not the elder's current instruction to end the supplement step.
    """
    def quoted_content(match):
        # Mask only for intent reading, never the stored source. Preserve sentence
        # boundaries so a current ending after a quotation can still be read.
        return '引用内容' + (match.group()[-2] if SENTENCE_END.search(match.group()[-2:-1]) else '')

    reading = re.sub(r'“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*"', quoted_content, text or '')
    ends = content = reported = False
    previous = ''
    for clause in CLAUSE.findall(reading):
        if SENTENCE_END.search(previous) or PRESENT.search(clause):
            reported = False
        past_report = PAST.search(clause) and re.search(r'(?:说|讲)\s*(?=[：:，,“"‘「]|没有|没了|就这些)', clause)
        reported = reported or bool(REPORTED.search(clause) or past_report)
        previous = clause
        bare = re.sub(r'[\s，,。！!？?；;、…~—“”"‘’「」]', '', clause)
        if not bare:
            continue
        if SUPPLEMENT_END.fullmatch(bare):
            if reported:
                content = True
            else:
                ends = True
        else:
            # "没有别的要补充了" was handled as a whole ending above;
            # "没有，我还想说说我妈" still has an affirmative continuation.
            if not reported and SUPPLEMENT_MORE.search(clause):
                return None
            if not SUPPLEMENT_NEUTRAL.fullmatch(bare):
                content = True
    return ('with_content' if content else 'only') if ends else None
