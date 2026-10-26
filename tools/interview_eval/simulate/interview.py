"""Full simulated interviews: elder simulator <-> v3j judgment layer <-> a speaking policy.

A session = one person, the questions of their plan in frozen bank order. Each question:
  entry question -> elder answer -> v3j judgment (unchanged pipeline, same multi-turn state as production:
  previous_fields / ask_counts / focus) -> speaking policy reply (follow-up, or close + move to the next entry)
  -> ... until the question closes; MAX_TURNS caps every question. Switching questions clears all
  question state (independent questions).

Speaking policies
  baseline : the production backend's fixed texts (contract_guided_interview.turn): follow-up = the engine's
             contract question; complete = "这段可以先整理成草稿了。您还有什么想补充的吗？"; skip = SKIP_ACK +
             next entry; pause = fixed text. After the supplement invitation a short "nothing more" reply is
             treated as the user confirming the draft (the App shows a button for it).
  v4       : speaking layer (speaker-prompt.txt, deepseek-v4-pro, thinking disabled) + natural ending rules.

Everything the elder simulator sees: its own material (persona.py), the dialogue of the current question and
the system's last message. It never sees gold, judgments, targets or any other internal state. For the first
answer of each question it sees only the entry question, so that first answers (and their judgments) are
shared through the content cache by every policy run on the same person.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
from persona import Personas  # noqa: E402

V4 = common.ROOT / 'docs/prototypes/full-interview-v4'
MAX_TURNS = 6  # elder messages per question (hard cap against loops)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V3J = _load(common.ROOT / 'tools/interview_eval/pipelines/v3j.py', 'pipeline_v3j_sim')
CONTROLS = _load(common.ROOT / 'cloud-deployment/backend/app/services/interview_controls.py', 'interview_controls_sim')
PAUSE_RE = re.compile(r'(?:先休息|先暂停|暂停|今天先不聊|暂时不想讲)[。！!\s]*')
RESUME_TEXT = '继续'
BASE_DONE = '这段可以先整理成草稿了。您还有什么想补充的吗？'
BASE_REVIEW = '好，先核对这段草稿，您确认后再保存。'
BASE_PAUSE = '好，先休息。您的讲述和采访位置都已保留。'
NO_MORE = re.compile(r'没有|没了|就这些|差不多|不用了|没什么|没啥')


class Setup:
    def __init__(self, speaker_prompt=None, policy=None):
        self.personas = Personas()
        self.ctx = V3J.setup()
        self.sim_prompt = (V4 / 'simulator-prompt.txt').read_text(encoding='utf-8')
        self.sim_cfg = json.loads((V4 / 'sim-config.json').read_text(encoding='utf-8'))
        self.speaker_prompt = Path(speaker_prompt or V4 / 'speaker-prompt.txt').read_text(encoding='utf-8')
        self.policy = json.loads(Path(policy or V4 / 'speaker-config.json').read_text(encoding='utf-8'))
        self.Q = self.personas.Q
        self.F = self.ctx.F
        # v5 story deepening: only when the policy carries an enabled "deepen" block (v4d policies have none)
        dz = self.policy.get('deepen') or {}
        self.deepen = dz if dz.get('enabled') else None
        if self.deepen:
            bank = json.loads((common.ROOT / dz['questions']).read_text(encoding='utf-8'))
            for q in bank['questions']:  # the labels sit beside the frozen bank: same ids, same entry questions
                if self.Q[q['id']]['main_question'] != q['main_question']:
                    raise ValueError('story-questions.json does not match the frozen bank at ' + q['id'])
            if len(bank['questions']) != len(self.Q):
                raise ValueError('story-questions.json must label every question of the frozen bank')
            self.story = {q['id']: q for q in bank['questions'] if q['depth'] == 'story'}
            self.deepen_prompt = (common.ROOT / dz['prompt']).read_text(encoding='utf-8')


# --------------------------------------------------------------------------- elder simulator
def behaviour(S, nid, qid, k):
    rng = random.Random(int(hashlib.sha256(f'{nid}|{qid}|{k}'.encode()).hexdigest()[:15], 16))
    probs = S.sim_cfg['probabilities']['first_answer' if k == 0 else 'later_answer']
    x, acc, pick = rng.random(), 0.0, 'normal'
    for name, p in probs.items():
        acc += p
        if x < acc:
            pick = name
            break
    asr = rng.random() < S.sim_cfg['probabilities']['asr_typos']
    return pick, asr


def elder_call(S, nid, qid, k, dialogue, prompt_text):
    beh, asr = behaviour(S, nid, qid, k)
    material = S.personas.render(S.personas.material(nid, qid))
    lines = [f'你是{S.personas.names[nid]}。', '你的资料（你本人以前讲过的话）：', material, '', '这个话题里刚才的对话：' if dialogue else '采访者刚开始问这个话题。']
    for role, text in dialogue:
        lines.append(('采访者：' if role == 'system' else '你：') + text)
    lines.append('采访者（请回答这一句）：' + prompt_text)
    lines.append('本轮表现：' + S.sim_cfg['behaviors'][beh] + (S.sim_cfg['asr_note'] if asr and beh not in ('rest', 'reluctant') else ''))
    call = {'id': f'{qid}-e{k}-sim', 'route': 'persona', 'system': S.sim_prompt, 'user': '\n'.join(lines), 'params': S.sim_cfg['model'],
            'output_note': PERSONA_NOTE, 'validate': {'type': 'persona', 'max_chars': 400}}
    return call, beh, asr


PERSONA_NOTE = '只输出一个 JSON 对象：{"reply": "你说的话"}（不加解释，不加代码块，不加别的字段）。'


def elder_text(row):
    out = row.get('output') if isinstance(row.get('output'), dict) else None
    text = (out or {}).get('reply') if out else None
    if not isinstance(text, str) or not text.strip():
        text = (row.get('content') or '').strip()
        m = re.search(r'"reply"\s*:\s*"([^"]*)"', text)
        text = m.group(1) if m else text
    return text.strip() or '嗯。'


# --------------------------------------------------------------------------- helpers
def call_info(row):
    return {'id': row.get('id'), 'ok': row.get('ok'), 'cached': bool(row.get('cached')), 'seconds': row.get('seconds'),
            'usage': {k: v for k, v in (row.get('usage') or {}).items() if isinstance(v, (int, float))},
            'model': row.get('model_requested') or row.get('response_model')}


def tracked(gen, prefix, log):
    """Run a pipeline generator, prefixing call ids and logging every response row."""
    try:
        calls = next(gen)
        while True:
            kinds = [c['id'] for c in calls]
            resp = yield [{**c, 'id': prefix + c['id']} for c in calls]
            for kind, r in zip(kinds, resp):
                log.append({**call_info(r), 'kind': kind.split('-')[-1]})
            calls = gen.send(resp)
    except StopIteration as stop:
        return stop.value


def judge_summary(S, result, qid):
    fields = {}
    for fid, f in (result.get('fields') or {}).items():
        if S.F[fid]['requirement'] == 'optional':
            continue
        st = f.get('state')
        if st and st != 'missing':
            v = f.get('value')
            v = '；'.join(x for x in v if isinstance(x, str)) if isinstance(v, list) else v
            fields[fid] = {'state': st, 'value': v}
    return {'decision': result.get('decision'), 'target': result.get('target'), 'question': result.get('question'),
            'effective': {k: v for k, v in (result.get('effective') or {}).items() if S.F[k]['requirement'] != 'optional'},
            'active': result.get('active'), 'fields': fields, 'errors': result.get('errors')}


def recorded_lines(S, fields, limit=4, width=40):
    out = []
    names = {'known': None, 'none': '明确说没有', 'unknown': '说记不清', 'declined': '不愿讲', 'deferred': '以后再讲', 'ambiguous': '说有但没说清'}
    for fid, f in fields.items():
        label = S.F[fid]['label']
        if f['state'] == 'known' and f.get('value'):
            v = f['value'] if len(f['value']) <= width else f['value'][:width] + '…'
            out.append(f'{label}：「{v}」')
        elif names.get(f['state']):
            out.append(f'{label}：{names[f["state"]]}')
    return out[:limit]


# --------------------------------------------------------------------------- v4 speaking layer
BANNED = re.compile(r'保存|整理|草稿|记录下|记下来|已记下|系统|App|APP|采访者|题目|下一题|要素|资料')
PRAISE = re.compile(r'太棒|真棒|了不起|非常精彩|谢谢您的分享|感谢您的分享|感谢分享|太感人|非常感人')
FALLBACK_CLOSE = {'done': '好的。', 'limited': '好的。', 'unknown': '没关系，记不清就不勉强。', 'declined': '好，这个咱们就不多聊了。',
                  'declined_partial': '好，这个咱们就不多聊了。',
                  'deferred': '好，这个以后想聊再说。', 'cap': '好的。', 'asked_once': '好的。', 'error': '好的。', 'rest': '好，您先歇会儿。',
                  'rest_resume': '好，咱们接着聊。'}
# 'declined_partial' (C02) tells the speaking layer the same as a refusal; only what follows differs.
CLOSE_REASON = {'done': '这个话题已经聊完', 'limited': '这个话题聊到这里就够了', 'unknown': '老人说记不清了', 'declined': '老人不想多说',
                'declined_partial': '老人不想多说',
                'deferred': '老人想以后再讲', 'cap': '这个话题已经追问过几次，不再追问', 'asked_once': '这一点刚才问过了，老人没接着讲，不再追问',
                'error': '这个话题聊到这里就够了', 'rest': '老人累了想歇一会儿',
                'rest_resume': '老人刚才说累了，歇了一会儿，刚点了“继续”；这个话题不再追问，接着聊下一题'}


def speaker_user(S, qid, dialogue, fields, task, target=None, engine_question=None, reason=None, next_entry=None, prev_close=None):
    q = S.Q[qid]
    lines = [f'当前话题：{q["main_question"]}', '对话：']
    for role, text in dialogue:
        lines.append(('问：' if role == 'system' else '答：') + text)
    rec = recorded_lines(S, fields)
    lines.append('已记下：' + ('；'.join(rec) if rec else '（暂无）'))
    if task == 'ask':
        f = S.F[target]
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


def clean_ack(text, elder_text=''):
    """Drop ack clauses that infer, evaluate beyond the elder's own words, or ask a question of their own; keep the
    rest in order. Returns (text, [reasons])."""
    elder = simp_text(elder_text)
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


def simp_text(text):
    from persona import simp
    return simp(text or '')


def drop_inference(text, elder_text=''):
    out, why = clean_ack(text, elder_text)
    return out, bool(why)


def compose_close(reply, next_entry, elder_text=''):
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
    ack, why = clean_ack(ack, elder_text)
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


def has_content(result):
    """Whether this question already has a real answer (C02): an active field known or explicitly none (optional
    fields are not counted, so the backend and the simulator's judge summary read the same)."""
    eff = result.get('effective') or {}
    return any(eff.get(a) in ('known', 'none') for a in result.get('active') or [])


def v4_decide(S, result, st, text=''):
    """Natural-ending rules on top of the engine decision. Returns (action, reason_or_target).

    'declined_partial' (C02, decision of 2026-10-23): the elder has answered and then says he does not want to
    go into it further (his own words, or the engine's limited with a declined field next to an answered one); the
    question closes as answered, the speaking layer is told '老人不想多说'. A decline
    before any real answer stays a refusal ('declined'). Same rules as the backend (interview_speaker.decide)."""
    cfg = S.policy
    d = result.get('decision')
    eff = result.get('effective') or {}
    active = result.get('active') or []
    sig = elder_signal(text) if cfg.get('signal_close') else None
    st['signal'] = sig
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
        return 'close', 'unknown' if 'unknown' in [eff.get(a) for a in active] else 'limited'
    target = result.get('target')
    if sig == 'declined':
        return 'close', 'declined_partial' if has_content(result) else 'declined'
    if sig == 'unknown':
        return 'close', sig
    if st['followups'] >= cfg['followup_cap']:
        return 'close', 'cap'
    if st['ask_counts'].get(target, 0) >= cfg['same_target_cap']:
        return 'close', 'asked_once'
    newly = [a for a in active if eff.get(a) in ('unknown', 'declined') and st['prev_eff'].get(a) not in ('unknown', 'declined')]
    if newly and st['followups'] >= cfg.get('stop_after_unknown_once_asked', 1):
        return 'close', 'unknown'
    return 'ask', target


# --------------------------------------------------------------------------- v5 story deepening
# On a story question, after the ending rules say 'done' and before the close, the interviewer may ask up to N
# detail questions (one of scene / people / detail / feeling) drawn from what the elder just told. A separate
# speaker call writes them (deepen-prompt.txt); the v4d speaker prompt and every other step are unchanged.
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


# v5c1 guards (deepen only; the shared elder_signal / clean_ack of v4d and the backend stay as they are):
# "can't think of one" wordings elder_signal does not cover, and praise words clean_ack's list does not have
DEEPEN_UNKNOWN = re.compile(r'想不出|说不出|没(?:有)?(?:什么|啥)特别')
DEEPEN_ACK_EVAL = re.compile(r'有意思|有趣|真好|难得|感人|了不起')


def deepen_ack(ack, question):
    """An ack that only says again what the question names right after ("变身的把戏。那会儿……把戏……？") is dropped
    (v5c). Returns (ack, [repairs])."""
    from persona import bigrams
    a = bigrams(ack)
    if ack and (not a or a <= bigrams(question)):
        return '', ['ack_echo']
    return ack, []


def story_dims(text):
    return [d for d in DEEPEN_DIMS if DIM_MARKERS[d].search(text or '')]


def deepen_gate(S, qid, reason, text, elder_words, dz, k):
    """Whether to ask one more detail question now. Returns (ok, reason, info)."""
    cfg = S.deepen
    info = {'last_chars': len(_norm(text)), 'chars': len(_norm(elder_words)), 'dims_told': story_dims(elder_words)}
    if reason != 'done':
        return False, ('answer_' if dz['asked'] else 'not_done_') + reason, info
    if dz['asked'] >= dz['cap']:
        return False, 'cap', info
    if k >= MAX_TURNS:
        return False, 'max_turns', info
    if info['last_chars'] <= cfg['short_chars']:
        return False, 'short', info
    sig = elder_signal(text)
    if sig:
        return False, 'signal_' + sig, info
    if cfg.get('extra_guards') and DEEPEN_UNKNOWN.search(text):
        return False, 'signal_unknown_extra', info
    if info['chars'] >= cfg['detailed_chars'] and len(info['dims_told']) >= cfg['detailed_dims']:
        return False, 'detailed', info
    return True, 'asked', info


def deepen_user(S, qid, dialogue, dz):
    item = S.story[qid]
    lines = [f'当前话题：{S.Q[qid]["main_question"]}', f'深挖方向：{item["deepen_direction"]}']
    if item.get('sensitive'):
        lines.append('敏感：是（只轻轻问一句，老人不愿细说就不再问）')
    lines.append('对话：')
    for role, text in dialogue:
        lines.append(('问：' if role == 'system' else '答：') + text)
    lines.append('已经深挖过：' + ('、'.join(dz['dims']) if dz['dims'] else '（无）'))
    lines.append('任务：deepen')
    return '\n'.join(lines)


def parse_deepen(row):
    out = row.get('output') if isinstance(row.get('output'), dict) else {}
    get = lambda k: out.get(k).strip() if isinstance(out.get(k), str) else ''
    return get('dimension'), get('ack'), get('question')


def check_deepen(dim, ack, question, prior, dz):
    errs = check_ask(ack, question, prior)
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


def deepen_close(text, result, extra=False):
    """After the elder answers a deepen question (no new judgment): how this question ends. Returns (action, reason)."""
    if (result or {}).get('decision') == 'paused':
        return 'rest', None
    sig = elder_signal(text)
    if sig == 'rest':
        return 'rest', None
    if sig == 'declined':
        return 'close', 'declined_partial'
    if sig == 'unknown' or (extra and DEEPEN_UNKNOWN.search(text or '')):
        return 'close', 'unknown'
    return 'close', 'done'


# --------------------------------------------------------------------------- session
ERROR_TEXT = '抱歉，刚才这段没处理好，咱们先往下聊。'


def session(S, sid, nid, questions, mode):
    """Generator: yields call lists, receives response lists; returns the session record."""
    episodes = []
    entry_already_shown = False  # the previous close message already carried this question's entry
    prev_close = None            # the previous transition (the speaker is asked not to reuse its wording)
    for qi, qid in enumerate(questions):
        entry = S.Q[qid]['main_question']
        next_entry = S.Q[questions[qi + 1]]['main_question'] if qi + 1 < len(questions) else None
        msgs = [{'role': 'system', 'text': entry, 'kind': 'entry', 'question_part': entry, 'calls': [],
                 'shown_in_previous': entry_already_shown}]
        dialogue_sim = []          # what the simulator has seen in this question
        sources, previous, ask_counts, last_target = [], {}, {}, None
        st = {'followups': 0, 'ask_counts': ask_counts, 'prev_eff': {}, 'supplements': 0, 'pending': None}
        prompt_for_sim, asked_part = entry, entry
        phase, k, close, final = 'exploring', 0, None, None
        deepening = bool(S.deepen) and mode != 'baseline' and qid in S.story
        if deepening:
            item = S.story[qid]
            dz = {'story': True, 'sensitive': bool(item.get('sensitive')), 'direction': item['deepen_direction'],
                  'cap': S.deepen['max_per_sensitive'] if item.get('sensitive') else S.deepen['max_per_question'],
                  'asked': 0, 'dims': [], 'log': []}
            deepen_sources = []
        while True:
            if k >= MAX_TURNS:
                close = {'reason': 'max_turns'}
                break
            # ---------------- elder answers
            call, beh, asr = elder_call(S, nid, qid, k, dialogue_sim, prompt_for_sim)
            [row] = yield [call]
            text = elder_text(row)
            elder = {'role': 'elder', 'text': text, 'behavior': beh, 'asr': asr, 'k': k, 'calls': [{**call_info(row), 'kind': 'sim'}],
                     'sim_input': call['user']}
            msgs.append(elder)
            dialogue_sim += [('system', prompt_for_sim), ('elder', text)]
            k += 1
            sys_calls = []
            # ---------------- explicit controls (both policies, no model call)
            if CONTROLS.skips_question(text):
                if phase == 'deepen':  # the question was already answered before the detail question
                    dz['log'].append({'k': k, 'decision': 'stop', 'reason': 'answer_skip_control'})
                    close = {'reason': 'declined_partial', 'control': 'skip'}
                    break
                close = {'reason': 'declined', 'control': 'skip'}
                break
            if PAUSE_RE.fullmatch(text.strip()):
                result = {'decision': 'paused', 'effective': {}, 'active': [], 'control': 'pause_regex'}
            elif mode == 'baseline' and phase == 'supplement' and len(text) <= 20 and NO_MORE.search(text):
                close = {'reason': 'done', 'control': 'confirm_draft'}
                break
            elif phase == 'deepen':
                # answer to a detail question: not judged again (the elements were complete); kept verbatim as a
                # source of this question for the draft
                deepen_sources.append({'id': f'{qid}-a{k}', 'text': text, 'question': asked_part, 'dimension': dz['dims'][-1]})
                elder['deepen_answer'] = True
                result = None
            else:
                # ---------------- v3j judgment (unchanged pipeline, production multi-turn state)
                source = {'id': f'{qid}-a{k}', 'text': text, 'question': asked_part}
                sources.append({'source': source, 'focus': {'field_id': last_target} if last_target else None})
                case = {'question_id': qid, 'turns': sources}
                payload = S.ctx.engine.payload_for(case, len(sources) - 1, previous, ask_counts)
                try:
                    result, trace = yield from tracked(V3J.run_checkpoint(payload, S.ctx), f'{qid}-a{k}-', sys_calls)
                except V3J.CallFailed as exc:
                    result = {'decision': 'invalid', 'errors': ['call_failed:' + str(exc)[:200]], 'effective': {}, 'active': []}
                elder['judge'] = judge_summary(S, result, qid)
                final = result
            elder['calls_system'] = sys_calls
            decision = (result or {}).get('decision')
            # ---------------- baseline: production fixed texts
            if mode == 'baseline':
                if decision == 'paused':
                    if result.get('control') != 'pause_regex':
                        st['pending'] = None  # production clears the pending question before a model-detected pause
                    resume = st['pending'] or entry
                    msgs.append({'role': 'system', 'text': BASE_PAUSE, 'kind': 'pause', 'calls': sys_calls})
                    msgs.append({'role': 'elder', 'text': RESUME_TEXT, 'scripted': True, 'calls': []})
                    msgs.append({'role': 'system', 'text': resume, 'kind': 'resume', 'question_part': resume, 'calls': []})
                    dialogue_sim += [('system', BASE_PAUSE), ('elder', RESUME_TEXT)]
                    prompt_for_sim, asked_part = resume, resume
                    continue
                if decision in ('ask', 'ask_defer'):
                    q, t = result.get('question') or '', result.get('target')
                    st['followups'] += 1
                    st['pending'] = q
                    ask_counts[t] = ask_counts.get(t, 0) + 1
                    msgs.append({'role': 'system', 'text': q, 'kind': 'followup', 'target': t, 'question_part': q,
                                 'engine_question': q, 'decision': decision, 'calls': sys_calls})
                    previous, last_target = result.get('fields', {}), t
                    prompt_for_sim, asked_part = q, q
                    continue
                if decision in ('skipped', 'deferred') or (decision == 'limited' and 'declined' in (result.get('effective') or {}).values()):
                    close = {'reason': 'declined', 'calls': sys_calls}
                    break
                if decision == 'invalid':
                    close = {'reason': 'error', 'calls': sys_calls}
                    break
                # ready / limited -> the fixed supplement invitation (repeated while the elder keeps adding)
                st['supplements'] += 1
                st['pending'] = None
                previous, last_target = result.get('fields', {}), None
                if st['supplements'] > S.policy.get('baseline_supplement_cap', 2):
                    close = {'reason': 'done', 'control': 'supplement_cap', 'calls': sys_calls}
                    break
                phase = 'supplement'
                msgs.append({'role': 'system', 'text': BASE_DONE, 'kind': 'supplement', 'question_part': BASE_DONE,
                             'decision': decision, 'calls': sys_calls})
                prompt_for_sim, asked_part = BASE_DONE, BASE_DONE
                continue
            # ---------------- v4: speaking layer + natural ending rules
            if phase == 'deepen':
                action, arg = deepen_close(text, result, S.deepen.get('extra_guards'))
                elder['signal'] = elder_signal(text)
            else:
                action, arg = v4_decide(S, result, st, text)
                st['prev_eff'] = dict(result.get('effective') or {})
                elder['signal'] = st.get('signal')
            elder['v4_action'] = [action, arg]
            if deepening and action != 'ask':
                # ---------------- v5: one more detail question before the close (story questions only)
                elder_words = ''.join(m['text'] for m in msgs if m['role'] == 'elder' and not m.get('scripted'))
                ok, why, info = deepen_gate(S, qid, arg if action == 'close' else action, text, elder_words, dz, k)
                entry_log = {'k': k, 'decision': 'skip' if not ok else 'asked', 'reason': why, **info}
                if ok:
                    dialogue = [(m['role'], m['text']) for m in msgs if not m.get('scripted')]
                    prior = [m.get('question_part') for m in msgs if m['role'] == 'system']
                    call = {'id': f'{qid}-d{dz["asked"] + 1}-deepen', 'system': S.deepen_prompt, 'params': S.deepen['model'],
                            'user': deepen_user(S, qid, dialogue, dz)}
                    [row] = yield [call]
                    sys_calls.append({**call_info(row), 'kind': 'deepen'})
                    dim, ack, question = parse_deepen(row)
                    ack, ack_fix = clean_ack(ack, elder_words)
                    if S.deepen.get('drop_echo_ack'):
                        ack, echo = deepen_ack(ack, question)
                        ack_fix += echo
                    if S.deepen.get('extra_guards') and DEEPEN_ACK_EVAL.search(ack):
                        ack, ack_fix = '', ack_fix + ['ack_eval']
                    errs = []
                    if not row.get('ok') or not isinstance(row.get('output'), dict):
                        errs = ['call_failed']
                    elif not question and not dim:
                        errs = ['model_skip']
                    else:
                        errs = check_deepen(dim, ack, question, prior, dz)
                        if errs and ack and not check_deepen(dim, '', question, prior, dz):
                            ack_fix.append('ack_dropped:' + ','.join(errs))
                            ack, errs = '', []
                    entry_log.update({'dimension': dim, 'ack': ack, 'question': question, 'errors': errs, 'repairs': ack_fix,
                                      'raw': row.get('content')})
                    if not errs:
                        dz['asked'] += 1
                        dz['dims'].append(dim)
                        dz['log'].append(entry_log)
                        text_out = join(ack, question)
                        elder['deepen'] = 'asked'
                        msgs.append({'role': 'system', 'text': text_out, 'kind': 'deepen', 'dimension': dim, 'question_part': question,
                                     'deepen_n': dz['asked'],
                                     'speaker': {'ack': ack, 'question': question, 'errors': [], 'repairs': ack_fix,
                                                 'raw': row.get('content'), 'input': call['user']},
                                     'calls': sys_calls})
                        phase = 'deepen'
                        prompt_for_sim, asked_part = text_out, question
                        continue
                    # failed or invalid: no deepen, the question closes as it would have (never a fixed question)
                    entry_log['decision'] = 'skip'
                    entry_log['reason'] = 'invalid' if errs[0] not in ('call_failed', 'model_skip') else errs[0]
                elder['deepen'] = entry_log['reason']
                dz['log'].append(entry_log)
            if action == 'ask':
                dialogue = [(m['role'], m['text']) for m in msgs if not m.get('scripted')]
                prior = [m.get('question_part') for m in msgs if m['role'] == 'system']
                fields = (elder.get('judge') or {}).get('fields') or {}
                call = {'id': f'{qid}-a{k}-speak', 'system': S.speaker_prompt, 'params': S.policy['model'],
                        'user': speaker_user(S, qid, dialogue, fields, 'ask', arg, result.get('question'))}
                [row] = yield [call]
                sys_calls.append({**call_info(row), 'kind': 'speak'})
                ack, question = parse_speaker(row)
                elder_words = ''.join(m['text'] for m in msgs if m['role'] == 'elder' and not m.get('scripted'))
                ack, ack_fix = clean_ack(ack, elder_words)
                errs = check_ask(ack, question, prior)
                if INFER.search(question):
                    errs.append('inference_in_question')
                if errs:
                    question = result.get('question') or S.F[arg]['question']
                    if check_close(ack):
                        ack = ''
                text_out = join(ack, question)
                st['followups'] += 1
                ask_counts[arg] = ask_counts.get(arg, 0) + 1
                msgs.append({'role': 'system', 'text': text_out, 'kind': 'followup', 'target': arg, 'question_part': question,
                             'engine_question': result.get('question'), 'decision': result.get('decision'),
                             'speaker': {'ack': ack, 'question': question, 'errors': errs, 'fallback': bool(errs), 'repairs': ack_fix, 'raw': row.get('content'),
                                         'input': call['user']},
                             'calls': sys_calls})
                previous, last_target = result.get('fields', {}), arg
                prompt_for_sim, asked_part = text_out, question
                continue
            if action == 'rest':
                if next_entry:  # pause, the elder taps "continue", then the next question
                    msgs.append({'role': 'system', 'text': '好，您先歇会儿，想接着聊了跟我说一声。', 'kind': 'pause', 'calls': sys_calls})
                    msgs.append({'role': 'elder', 'text': RESUME_TEXT, 'scripted': True, 'calls': []})
                    close = {'reason': 'rest', 'calls': []}
                else:  # tired at the last question of the session: end the session here
                    close = {'reason': 'rest', 'calls': sys_calls, 'end_session': True}
                break
            close = {'reason': arg, 'calls': sys_calls}
            break
        # ---------------- close the question (and, in v4, move on to the next entry in the same message)
        reason, calls = close['reason'], close.get('calls') or []
        entry_already_shown = False
        if mode == 'baseline':
            if reason == 'declined':
                text_out = CONTROLS.SKIP_ACK + ('\n' + next_entry if next_entry else '')
                entry_already_shown = bool(next_entry)
            elif reason == 'error':
                text_out = ERROR_TEXT
            else:  # done / max_turns: the user confirms the draft, then the next entry follows as its own message
                text_out = BASE_REVIEW
            msgs.append({'role': 'system', 'text': text_out, 'kind': 'close', 'reason': reason, 'control': close.get('control'), 'calls': calls,
                         'entry_part': next_entry if entry_already_shown else None})
        elif reason == 'rest' and not next_entry:  # tired at the session's last question: end here (fixed text)
            text_out = '好，您先歇着，今天就先聊到这儿，辛苦您了。'
            msgs.append({'role': 'system', 'text': text_out, 'kind': 'close', 'reason': reason, 'calls': calls, 'speaker': {'fixed': True},
                         'entry_part': None})
            entry_already_shown = False
        elif reason == 'rest' and not S.policy.get('rest_resume_by_speaker'):  # v4d: fixed resume line + next entry
            text_out = join(FALLBACK_CLOSE['rest_resume'], next_entry)
            msgs.append({'role': 'system', 'text': text_out, 'kind': 'close', 'reason': reason, 'calls': calls, 'speaker': {'fixed': True},
                         'entry_part': next_entry})
            entry_already_shown = True
        else:
            reason_for_speaker = {'max_turns': 'cap', 'rest': 'rest_resume'}.get(reason, reason)
            dialogue = [(m['role'], m['text']) for m in msgs if not m.get('scripted')]
            fields = judge_summary(S, final, qid)['fields'] if final else {}
            call = {'id': f'{qid}-close-speak', 'system': S.speaker_prompt, 'params': S.policy['model'],
                    'user': speaker_user(S, qid, dialogue, fields, 'close', reason=reason_for_speaker, next_entry=next_entry,
                                         prev_close=prev_close)}
            [row] = yield [call]
            calls = calls + [{**call_info(row), 'kind': 'speak'}]
            reply, _ = parse_speaker(row)
            elder_words = ''.join(m['text'] for m in msgs if m['role'] == 'elder' and not m.get('scripted'))
            text_out, ack, notes, ok = compose_close(reply, next_entry, elder_words)
            if not ok:
                ack = FALLBACK_CLOSE.get(reason_for_speaker, '好的。') if next_entry else '好的，今天就先聊到这儿，您辛苦了。'
                text_out = join(ack, next_entry) if next_entry else ack
            msgs.append({'role': 'system', 'text': text_out, 'kind': 'close', 'reason': reason, 'control': close.get('control'), 'calls': calls,
                         'entry_part': next_entry,
                         'speaker': {'ack': ack, 'errors': [] if ok else notes, 'repairs': notes if ok else [], 'fallback': not ok,
                                     'raw': row.get('content'), 'input': call['user']}})
            entry_already_shown = bool(next_entry)
            prev_close = text_out
        record = {'qid': qid, 'entry': entry, 'messages': msgs, 'close_reason': reason,
                  'final_decision': (final or {}).get('decision'),
                  'final': judge_summary(S, final, qid) if final else None,
                  'material_ids': [e['id'] for e in S.personas.material(nid, qid)]}
        if deepening:
            record['deepen'] = dz
            record['deepen_sources'] = deepen_sources
        episodes.append(record)
    return {'session': sid, 'narrator_id': nid, 'name': S.personas.names[nid], 'mode': mode, 'questions': questions,
            'episodes': episodes}
