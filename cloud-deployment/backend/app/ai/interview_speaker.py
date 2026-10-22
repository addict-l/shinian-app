"""Speaking layer v4d: how to say what the judgment layer decided, never what to ask.

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
"""
import re

BANNED = re.compile(r'保存|整理|草稿|记录下|记下来|已记下|系统|App|APP|采访者|题目|下一题|要素|资料')
PRAISE = re.compile(r'太棒|真棒|了不起|非常精彩|谢谢您的分享|感谢您的分享|感谢分享|太感人|非常感人')
CLOSE_REASON = {'done': '这个话题已经聊完', 'limited': '这个话题聊到这里就够了', 'unknown': '老人说记不清了', 'declined': '老人不想多说',
                'deferred': '老人想以后再讲', 'cap': '这个话题已经追问过几次，不再追问', 'asked_once': '这一点刚才问过了，老人没接着讲，不再追问',
                'error': '这个话题聊到这里就够了', 'rest': '老人累了想歇一会儿',
                'rest_resume': '老人刚才说累了，歇了一会儿，刚点了“继续”；这个话题不再追问，接着聊下一题'}


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
        elif re.search(r'[？?]$', p) or re.search(r'(?:吧|吗|么|呢)[，,。！!；;]?$', p):
            reason = 'question_in_ack'
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
    errs = check_ask(ack, question, prior)
    if INFER.search(question):
        errs.append('inference_in_question')
    if errs:
        question = result.get('question') or rt.F[target]['question']
        if check_close(ack):
            ack = ''
    return join(ack, question), question, {'ack': ack, 'question': question, 'errors': errs, 'fallback': bool(errs),
                                          'repairs': fixes}


# What the elder just said, read literally (general wording, no per-person rules): signs that the person does not
# want to go on with this point, cannot remember it, or is tired. The judgment layer may still return 'ask' in these
# cases (the field stays missing); the natural-ending rule then closes instead of pressing.
SIG_REST = re.compile(r'累了|歇(?:一)?(?:会|下)|歇歇|休息(?:一)?(?:会|下)|先休息|缓一缓|喘口气|改天再(?:聊|说|讲)|下次再(?:聊|说|讲)|今天先(?:到这|聊到这)')
SIG_DECLINE = re.compile(r'不多(?:讲|说|谈)|不(?:想|愿|愿意|太想|大想)多?(?:讲|说|提|聊|谈)|(?:就|先|还是)不(?:讲|说|提|聊|谈)|不(?:讲|说|提|聊|谈)了|别问了|不想回答')
SIG_UNKNOWN = re.compile(r'记不(?:太|大)?清|记不(?:太|大)?得|不(?:太|大)?记得|想不(?:太|大)?起|说不(?:太|大)?上|说不(?:太|大)?清|说不(?:太|大)?好|没(?:什么|啥|多大)?印象|不(?:太|大)?清楚|忘(?:了|记了|得差不多)')


def elder_signal(text):
    text = text or ''
    if SIG_REST.search(text):
        return 'rest'
    if SIG_DECLINE.search(text):
        return 'declined'
    if SIG_UNKNOWN.search(text):
        return 'unknown'
    return None


def decide(cfg, result, st, text=''):
    """Natural-ending rules on top of the engine decision (interview.v4_decide). ``st`` holds this question's
    'followups', 'ask_counts' (targets actually asked) and 'prev_eff'; 'signal' is set as a side effect.
    Returns (action, reason_or_target)."""
    d = result.get('decision')
    eff = result.get('effective') or {}
    active = result.get('active') or []
    sig = elder_signal(text) if cfg.get('signal_close') else None
    st['signal'] = sig
    if d == 'paused' or sig == 'rest':
        return 'rest', None
    if d in ('skipped',) or (d == 'limited' and 'declined' in [eff.get(a) for a in active]):
        return 'close', 'declined'
    if d == 'deferred':
        return 'close', 'deferred'
    if d == 'invalid':
        return 'close', 'error'
    if d == 'ready':
        return 'close', 'done'
    if d == 'limited':
        return 'close', 'unknown' if 'unknown' in [eff.get(a) for a in active] else 'limited'
    target = result.get('target')
    if sig in ('declined', 'unknown'):
        return 'close', sig
    if st['followups'] >= cfg['followup_cap']:
        return 'close', 'cap'
    if st['ask_counts'].get(target, 0) >= cfg['same_target_cap']:
        return 'close', 'asked_once'
    newly = [a for a in active if eff.get(a) in ('unknown', 'declined') and st['prev_eff'].get(a) not in ('unknown', 'declined')]
    if newly and st['followups'] >= cfg.get('stop_after_unknown_once_asked', 1):
        return 'close', 'unknown'
    return 'ask', target
