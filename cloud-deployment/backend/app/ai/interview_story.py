"""Speaking layer v5f on top of v4d: story-question deepening, the v5d-v5f wording guards and their checks.

Port of the v5 parts of tools/interview_eval/simulate/interview.py (docs/prototypes/full-interview-v5, version v5f).
The prompt, the 23 story-question labels and the configuration come from the pinned v3j_v5f runtime bundle
(``rt.deepen_prompt``, ``rt.story``, ``rt.speaker_config``); the judgment layer still decides every target and
whether the elements of a question are complete. Function bodies are the simulator's; only how they receive the
policy differs (the simulator's ``S.policy`` / ``S.deepen`` are ``cfg`` / ``cfg['deepen']`` here).
tests/test_interview_v5f.py runs both implementations over the same texts, and tests/test_interview_v5f_sim_replay.py
replays the v5f simulated interviews through the backend flow.

Deepening (decision of 2026-10-26, the defaults of 《故事题清单》): on one of the 23 story questions, after the
ending rules say the question is done (engine ready) -- or, with signal_scope, 'can't remember that, but ...'
(unknown_partial) -- and before the close, at most ``max_per_question`` (2) detail questions are asked, one on
sensitive questions (WK09 FM03 RV02). A separate speaking-layer call writes each (deepen-prompt.txt). The gate
does not ask after a short answer (20 characters, 12 before the first one), a stop signal, an answer already told
in full, or at the cap. Answers to detail questions are not judged again: they are kept verbatim as sources of the
question and change no field. A failed call, a model that does not ask or a question failing the checks means no
deepening: the normal close (draft step / next skeleton question) follows, never a fixed question.
"""
import re

from app.ai import interview_speaker as speaker
from app.ai import interview_style as style
from app.ai.interview_speaker import (DEEPEN_UNKNOWN, HARDSHIP, INFER, OTHER, _norm, _simp, check_ask, elder_signal,
                                      signal_scope, scope_bigrams, SCOPE_PARTICLE, _scope_generic)

MAX_TURNS = 6  # elder messages per question (the simulator's hard cap)


def simp_text(text):
    return _simp(text)


# --------------------------------------------------------------------------- v5 story deepening
DEEPEN_DIMS = ('场景', '人物', '细节', '感受')
# rough literal markers of the four kinds in the elder's own words; only used for the "already told in full" gate
DIM_MARKERS = {
    '场景': re.compile(r'\d+\s*年|[一二三四五六七八九十几]+岁|\d+岁|民国|那年|那时|当时|那会|时候|年代|春天|夏天|秋天|冬天|过年|早上|晚上|夜里|白天|'
                     r'村|镇|县|城|街|厂|学校|屋|院子|河|山|庙|车站|部队|公司|医院|农场|乡下|老家|家里|那里|那儿'),
    '人物': re.compile(OTHER + r'|(?:说|讲|告诉|叫|问)(?:我|他|她|：|:|，|“)'),
    '细节': re.compile(r'\d+|[一两二三四五六七八九十几半]+(?:个|块|斤|张|件|碗|间|只|条|把|毛|元|分|根|双|辆|袋|口|床|套|台|本|封)|'
                     r'衣服|被子|房子|桌子|床|车|饭|馒头|米|面|钱|信|照片|书|手|脚|眼泪|哭|笑|跑|抱|拉着|背着|扛'),
    '感受': re.compile(r'觉得|感觉|心里|想着|以为|高兴|开心|难过|伤心|害怕|怕|舒服|难受|委屈|感动|感激|感谢|后悔|遗憾|喜欢|想念|骄傲|自豪|欣慰|'
                     r'满意|生气|着急|担心|紧张|佩服|心疼|舍不得|忘不了|不甘心'),
}
DEEPEN_BANNED = re.compile(r'细节|回忆录')
# one question mark can still carry two asks ("在什么地方，周围是什么样子的？"): count clauses with an interrogative
ASK_WORD = re.compile(r'什么|哪(?!怕)|怎么|怎样|谁|多大|几岁|[吗呢][？?]?$')
# v5c1 praise words clean_ack's list does not have (deepen only)
DEEPEN_ACK_EVAL = re.compile(r'有意思|有趣|真好|难得|感人|了不起')


def deepen_ack(ack, question):
    """An ack that only says again what the question names right after is dropped (v5c). Returns (ack, [repairs])."""
    a = style.bigrams(ack)
    if ack and (not a or a <= style.bigrams(question)):
        return '', ['ack_echo']
    return ack, []


def story_dims(text):
    return [d for d in DEEPEN_DIMS if DIM_MARKERS[d].search(text or '')]


def new_deepen(rt, qid):
    """The per-question deepening record (simulator ``dz``), saved in the question's own state."""
    item = rt.story[qid]
    cfg = rt.speaker_config['deepen']
    return {'story': True, 'sensitive': bool(item.get('sensitive')), 'direction': item['deepen_direction'],
            'cap': cfg['max_per_sensitive'] if item.get('sensitive') else cfg['max_per_question'],
            'asked': 0, 'dims': [], 'log': []}


def deepen_gate(policy, reason, text, elder_words, dz, k):
    """Whether to ask one more detail question now (interview.deepen_gate). Returns (ok, reason, info)."""
    cfg = policy['deepen']
    info = {'last_chars': len(_norm(text)), 'chars': len(_norm(elder_words)), 'dims_told': story_dims(elder_words)}
    if reason != 'done' and not (reason == 'unknown_partial' and policy.get('signal_scope')):
        return False, ('answer_' if dz['asked'] else 'not_done_') + reason, info
    if dz['asked'] >= dz['cap']:
        return False, 'cap', info
    if k >= MAX_TURNS:
        return False, 'max_turns', info
    # v5e short_chars_first: before any deepen a brief answer that still names someone or something may be asked
    # about once; after a deepen question a brief answer keeps stopping (short_chars)
    short = cfg['short_chars'] if dz['asked'] or 'short_chars_first' not in cfg else cfg['short_chars_first']
    if info['last_chars'] <= short:
        return False, 'short', info
    sig = elder_signal(text)
    extra = bool(cfg.get('extra_guards') and DEEPEN_UNKNOWN.search(text))
    if policy.get('signal_scope'):
        dz['partial'] = None
    if policy.get('signal_scope') and (sig == 'unknown' or (extra and not sig)):
        # v5d: "can't remember that, but ..." -> not pressed on that point; what he went on to tell may be followed
        scope = signal_scope(text, dz.get('asked_text', ''), dz.get('before', ''), policy.get('scope_min_chars', 15), extra=True)
        info['scope'] = scope[0]
        if scope[0] == 'partial':
            dz['partial'] = {'signal': scope[2], 'new': scope[1]}
            info['partial'] = dz['partial']
            sig, extra = None, False
    if sig:
        return False, 'signal_' + sig, info
    if extra:
        return False, 'signal_unknown_extra', info
    if info['chars'] >= cfg['detailed_chars'] and len(info['dims_told']) >= cfg['detailed_dims']:
        return False, 'detailed', info
    return True, 'asked', info


def deepen_user(rt, qid, dialogue, dz):
    item = rt.story[qid]
    lines = [f'当前话题：{rt.questions[qid]["main_question"]}', f'深挖方向：{item["deepen_direction"]}']
    if item.get('sensitive'):
        lines.append('敏感：是（只轻轻问一句，老人不愿细说就不再问）')
    lines.append('对话：')
    for role, text in dialogue:
        lines.append(('问：' if role == 'system' else '答：') + text)
    lines.append('已经深挖过：' + ('、'.join(dz['dims']) if dz['dims'] else '（无）'))
    if dz.get('partial'):  # v5d signal scope
        lines.append(f'老人刚说记不清的：{dz["partial"]["signal"]}（这一点不再问）')
        lines.append(f'他接着讲的：{dz["partial"]["new"]}')
    lines.append('任务：deepen')
    return '\n'.join(lines)


def parse_deepen(row):
    out = row.get('output') if isinstance(row.get('output'), dict) else {}
    get = lambda k: out.get(k).strip() if isinstance(out.get(k), str) else ''  # noqa: E731
    return get('dimension'), get('ack'), get('question')


# v5f deepen checks (deepen.no_yes_no, deepen.no_repeat_last)
YES_NO = re.compile(r'[吗嘛][？?]\s*$')
# a question about what came next, about who, or about what someone said asks for something new even when it names
# what he just told
NEXT_ASK = re.compile(r'后来|以后|之后|后面|接下来|结果|最后|怎么样|怎样了|谁|怎么(?:跟|对|和)?您?说|说了什么|说过什么')
REPEAT_GENERIC = None


def repeats_last(question, last, before):
    """After the elder answered a deepen question: whether the next one only asks him to tell again what that answer
    told (interview.repeats_last)."""
    global REPEAT_GENERIC
    if REPEAT_GENERIC is None:
        REPEAT_GENERIC = _scope_generic() | scope_bigrams('回想想起起来心里感觉滋味怎么什么那天那回那次这回这次当时那年时候'
                                                          '情形样子印象具体当时最后一回哪一回')
    if NEXT_ASK.search(question or ''):
        return False
    q = {b for b in scope_bigrams(question) if not SCOPE_PARTICLE.search(b)} - REPEAT_GENERIC
    shared = q & scope_bigrams(last)
    return bool(shared - scope_bigrams(before)) or len(shared) >= 2


def check_deepen(dim, ack, question, prior, dz, cfg=None):
    errs = check_ask(ack, question, prior)
    cfg = cfg or {}
    if cfg.get('no_yes_no') and YES_NO.search(question):  # v5f: a yes/no question is not asked
        errs.append('yes_no')
    if cfg.get('no_repeat_last') and dz['asked'] and repeats_last(question, dz.get('last', ''), dz.get('before', '')):
        errs.append('repeat_last')
    if INFER.search(question):
        errs.append('inference_in_question')
    if DEEPEN_BANNED.search(ack + question):
        errs.append('meta_words')
    if re.search(r'还是', question):
        errs.append('choice_question')
    if sum(1 for c in re.split(r'[，,；;]', question) if ASK_WORD.search(c.strip())) >= 2:
        errs.append('multi_part')
    if dim not in DEEPEN_DIMS:
        errs.append('bad_dimension')
    elif dim in dz['dims']:
        errs.append('repeat_dimension')
    return errs


def compose_deepen(rt, row, dz, prior, elder_words):
    """The simulator's handling of one deepen reply: ack cleaning and guards, checks; an invalid ack alone is dropped.
    Returns (dimension, ack, question, errors, repairs); errors empty = ask it."""
    policy = rt.speaker_config
    cfg = policy['deepen']
    dim, ack, question = parse_deepen(row)
    ack, ack_fix = speaker.clean_ack(rt, ack, elder_words)
    if cfg.get('drop_echo_ack'):
        ack, echo = deepen_ack(ack, question)
        ack_fix += echo
    if policy.get('echo_guard') and restates(ack, elder_words, policy.get('echo_names')):  # v5d
        ack, ack_fix = '', ack_fix + ['restate_dropped']
    if cfg.get('extra_guards') and DEEPEN_ACK_EVAL.search(ack):
        ack, ack_fix = '', ack_fix + ['ack_eval']
    errs = []
    if not row.get('ok') or not isinstance(row.get('output'), dict):
        errs = ['call_failed']
    elif not question and not dim:
        errs = ['model_skip']
    else:
        errs = check_deepen(dim, ack, question, prior, dz, cfg)
        if errs and ack and not check_deepen(dim, '', question, prior, dz, cfg):
            ack_fix.append('ack_dropped:' + ','.join(errs))
            ack, errs = '', []
    return dim, ack, question, errs, ack_fix


def deepen_close(text, result, extra=False, scope=None):
    """After the elder answers a deepen question (no new judgment): how this question ends. Returns (action, reason).
    ``scope`` (v5d signal_scope): (question, earlier words, min_chars); a partial "can't remember" -> 'unknown_partial'
    (the deepen gate may then ask once more about what he went on to tell)."""
    if (result or {}).get('decision') == 'paused':
        return 'rest', None
    sig = elder_signal(text)
    if sig == 'rest':
        return 'rest', None
    if sig == 'declined':
        return 'close', 'declined_partial'
    if sig == 'unknown' or (extra and DEEPEN_UNKNOWN.search(text or '')):
        if scope and signal_scope(text, scope[0], scope[1], scope[2], extra=extra)[0] == 'partial':
            return 'close', 'unknown_partial'
        return 'close', 'unknown'
    return 'close', 'done'


# --------------------------------------------------------------------------- v5d-v5f wording guards
# policy "echo_guard": an acknowledgement that mainly restates what the elder said in this question is dropped
# (style.is_restate, the definition of the 复述率 metric, here against all his words of the question; a short sympathy
# in the elder's own words about a hardship he told is kept). policy "template_guard": a stock move-on clause before
# the next entry is dropped ("repeat", v5f: only when an earlier close of the session used it). Both only remove
# words; the question itself is never rewritten.
def restates(ack, elder_said, names=False):
    if names and len(style.cjk(ack)) <= NAME_ACK_CHARS:  # v5f: a short reaction naming a person or place is pointing
        ack, elder_said = mask_names(ack), mask_names(elder_said)
    if not ack or not style.is_restate(ack, elder_said)[0]:
        return False
    return not (len(style.cjk(ack)) <= 10 and HARDSHIP.search(simp_text(ack)) and HARDSHIP.search(simp_text(elder_said)))


# v5f echo_names: names of people (one to three characters before a title: 蒋经国先生, 王老师) and proper place names (two
# to four characters before a place word: 黄浦江, 民本电台) are masked on both sides before the restate test, so that
# "噢，还见过蒋经国先生。" is a reaction that names someone, not a restatement. Kin words and generic places (哥哥, 学校,
# 糖厂) are not masked. General wording, no list of real names.
NAME_TITLE = r'(?:先生|太太|老师|师傅|同志|女士|小姐|校长|主任|经理|老板|司令|将军|主席|总统|委员长)'
NAME_PLACE = r'(?:江|河|湖|海|山|岛|村|镇|县|市|省|街|港|码头|车站|电台|饭店|夜总会|中学|小学|大学|医院|大队)'
NAMES = re.compile(rf'[一-鿿]{{1,3}}{NAME_TITLE}|[一-鿿]{{2,4}}{NAME_PLACE}')
NAME_ACK_CHARS = 12  # only a short reaction (at most this many Chinese characters) is read with names masked


def mask_names(text):
    return NAMES.sub('□', simp_text(text or ''))


# a reaction that only makes sense after the clause before it (是可怕 / 也是 / 真是 …)
ACK_DEPENDENT = re.compile(r'^(?:是|也是|就是|真是|都是|还是|确实|可不)')
# v5f echo_fragment_bare: what is left is only an interjection ("噢，") or a scrap of at most one character
ACK_BARE = re.compile(r'^(?:噢|哦|喔|嗯|啊|唉|哎|呀|哟|好|好的|对|是|行|那|原来|还|也|就)*$')


def bare_fragment(text):
    t = style.cjk(text)
    return len(t) <= 1 or bool(ACK_BARE.match(t))


def align_entry(text, next_entry):
    """v5f: a lead-in glued to a reworded-punctuation entry ("那咱们再聊聊青年时，有没有……？" for "青年时有没有……？") is
    split where the entry starts, and the entry follows as written after a comma."""
    if not next_entry or not _norm(text).endswith(_norm(next_entry)) or text.rfind(next_entry.rstrip('？?')) >= 0:
        return text
    n, p = len(_norm(next_entry)), len(text)
    while p > 0 and len(_norm(text[p - 1:])) <= n:
        p -= 1
    pre = text[:p].rstrip()
    return pre + ('' if not pre or re.search(r'[。！？!?，,]$', pre) else '，') + next_entry


def guard_close(text, next_entry, elder_said, echo=True, template=True, echo_fragment=None, v5f=None):
    """Close text with a restating acknowledgement and stock move-on clauses taken out (interview.guard_close).
    Returns (text, [repairs])."""
    names = bool((v5f or {}).get('names'))
    bare = bool((v5f or {}).get('bare'))
    seen = (v5f or {}).get('seen') or ()
    if v5f is not None:
        text = align_entry(text, next_entry)
    clauses, core = style.split_turn(text, next_entry)
    notes = []
    ack = ''.join(c for k, c in clauses if k == 'ack')
    if echo == 'clause':
        # v5e: only the clauses that restate on their own go ("上大夜班回来还得走路，是辛苦。" keeps "是辛苦。");
        # when only together they restate, the whole acknowledgement goes
        kept = [(k, c) for k, c in clauses if not (k == 'ack' and restates(c, elder_said, names))]
        if len(kept) == len(clauses) and restates(ack, elder_said, names):
            # v5f: a clause that restates once names are read as words goes alone before the whole goes
            alone = [(k, c) for k, c in clauses if not (k == 'ack' and restates(c, elder_said))] if names else kept
            kept = alone if len(alone) < len(clauses) else [(k, c) for k, c in clauses if k != 'ack']
        left = ''.join(c for k, c in kept if k == 'ack').strip()
        # v5f: an interjection the turn split reads as a move-on clause ("噢，") counts with what is left
        lone = ''.join(c for k, c in kept if k == 'transit' and style.INTERJ.match(re.sub(r'[，,。！!；;\s]', '', c)))
        if echo_fragment is not None and (left or lone) and (left and ACK_DEPENDENT.match(left) or (
                bare and len(kept) < len(clauses) and bare_fragment(left + lone))):
            # v5e1: what is left leans on the clause that went ("那时候兵荒马乱的，是可怕。" -> "是可怕。"): a short
            # reaction (<= echo_fragment characters) is kept whole, a longer one goes whole
            if len(style.cjk(ack)) <= echo_fragment:
                kept = clauses
            else:  # (v5f: with the lone interjection)
                kept = [(k, c) for k, c in clauses if k != 'ack' and not (
                    bare and k == 'transit' and style.INTERJ.match(re.sub(r'[，,。！!；;\s]', '', c)))]
        if len(kept) < len(clauses):
            notes.append('restate_dropped')
        clauses = kept
    elif echo and restates(ack, elder_said, names):
        clauses = [(k, c) for k, c in clauses if k != 'ack']
        notes.append('restate_dropped')
    if template == 'repeat' and next_entry:
        # v5f: natural move-on phrases are allowed; the same one twice in a session is not
        used = [_norm(x) for x in seen if x]
        kept = [(k, c) for k, c in clauses if not (k in ('transit', 'pointer') and style.TEMPLATE.search(c)
                                                    and any(_norm(style.TEMPLATE.search(c).group(0)) in u for u in used))]
        if len(kept) < len(clauses):
            notes.append('template_repeat_dropped')
        clauses = kept
    elif template and next_entry:
        kept = [(k, c) for k, c in clauses if not (k in ('transit', 'pointer') and style.TEMPLATE.search(c))]
        if len(kept) < len(clauses):
            notes.append('template_dropped')
        clauses = kept
    if not notes:
        return text, []
    lead = ''.join(c for _, c in clauses).strip()
    lead = re.sub(r'^[，,。；;]+', '', lead)
    if not style.cjk(lead):
        lead = ''
    if next_entry:
        core = core or next_entry
        if lead and not re.search(r'[。！？!?，,]$', lead):
            # v5f: a move-on clause or pointer kept from inside the entry's sentence stays joined to it
            inside = v5f is not None and clauses and clauses[-1][0] in ('transit', 'pointer') and \
                not re.search(r'[。！？!?]', text[:max(0, text.rfind(core))].rstrip()[-1:] or '。')
            lead += '，' if inside else '。'
        if lead.endswith(('，', ',')) and not style.cjk(lead.rstrip('，,')[-1:]):
            lead = lead.rstrip('，,') + '。'
        out = (lead + core) if lead else core
        out = re.sub(r'^那[，,]\s*', '那', out)
        if v5f is not None:  # "……报考，那，青年时……" -> "……报考，那青年时……"
            out = re.sub(r'([，,。！!])那[，,。]\s*', r'\1那', out)
        return out, notes
    lead = re.sub(r'[，,；;]$', '。', lead)
    return lead or text, notes


# --------------------------------------------------------------------------- the simulator's close, as one step


def guarded(rt, text, next_entry, elder_words, seen=()):
    """A composed close through the policy's guards, exactly as the simulator applies them after compose_close.
    Returns (text, notes); text None = nothing usable is left (the caller's fallback follows)."""
    policy = rt.speaker_config
    if not (policy.get('echo_guard') or policy.get('template_guard')):
        return text, []
    echo, tg = policy.get('echo_guard'), policy.get('template_guard')
    v5f = {'names': policy.get('echo_names'), 'bare': policy.get('echo_fragment_bare'),
           'seen': list(seen or ())} if tg == 'repeat' else None
    out, why = guard_close(text, next_entry, elder_words, 'clause' if echo == 'clause' else bool(echo),
                           tg if tg == 'repeat' else bool(tg), policy.get('echo_fragment_chars'), v5f)
    return (out or None), why


def close_reply(rt, reply, next_entry, elder_words, seen=()):
    """compose_close + guards (the simulator's close). Returns (text, ack, notes, ok)."""
    text, ack, notes, ok = speaker.compose_close(rt, reply, next_entry, elder_words)
    if ok:
        text, why = guarded(rt, text, next_entry, elder_words, seen)
        notes = notes + why
        if not text:
            ok = False
    return text, ack, notes, ok


def lead_part(text, next_entry):
    """What a guarded close says before the next entry (the acknowledgement and any kept lead-in)."""
    if not text:
        return ''
    if next_entry and _norm(text).endswith(_norm(next_entry)):
        clauses, core = style.split_turn(text, next_entry)
        pos = text.rfind(core) if core else -1
        return text[:pos].strip() if pos > 0 else ''
    return text


def draft_ack(rt, reply, next_entry, elder_words, seen=()):
    """The acknowledgement of a guarded close, for a step where the backend's own fixed text follows instead of the
    next question (draft sentence, module menu): the simulator's close (compose_close + guards) without the next entry,
    move-on clauses removed as speaker.lead_ack does. Returns '' when nothing usable remains."""
    text, _, _, ok = close_reply(rt, reply, next_entry, elder_words, seen)
    ack = lead_part(text, next_entry) if ok else ''
    kept = []
    for p in [p for p in re.findall(r'[^，,。！!；;]*[，,。！!；;]?', ack) if p.strip()]:
        if speaker.TRANSITION.search(p) or style.TEMPLATE.search(p) or re.fullmatch(r'\s*那[，,。]?\s*', p):
            if kept and re.search(r'[。！!；;]$', p):
                kept[-1] = re.sub(r'[，,]$', '。', kept[-1])
            continue
        kept.append(p)
    ack = re.sub(r'[，,；;]$', '。', ''.join(kept).strip())
    if not style.cjk(ack) or speaker.check_close(ack):
        return ''
    return ack


def earlier_closes(records):
    """Close texts already shown (template_guard "repeat"): the speaking-layer closes kept in question audits."""
    out = []
    for record in records:
        spoken = record.get('speaker') or {}
        if spoken.get('task') == 'close' and spoken.get('text'):
            out.append(spoken['text'])
    return out
