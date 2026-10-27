"""Shared plumbing for the memoir (book layer) prototype.

- Paths: the eval home (.runtime/interview-eval) lives in the main checkout; a worktree points
  SHINIAN_EVAL_HOME at it (defaulted here when the worktree has no .runtime of its own).
- Catalog: the frozen 83-question bank (module from the ID prefix) + depth tags (story/fact/reflection).
- Text helpers: traditional -> simplified (the runtime's OpenCC char map), source units, time clues,
  number / place / person token extraction used by the code fact check.
- Relay: DeepSeek calls go through tools/interview_eval/common.Relay (staged job files + content cache).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_MAIN_EVAL = Path('/home/claude/addict-l/shinian-app/.runtime/interview-eval')
if not (ROOT / '.runtime/interview-eval').exists() and _MAIN_EVAL.exists():
    os.environ.setdefault('SHINIAN_EVAL_HOME', str(_MAIN_EVAL))
sys.path.insert(0, str(ROOT / 'tools/interview_eval'))
import common  # noqa: E402  (interview_eval.common: Relay, load/save, RUNS, TESTSET_DIR)

DOCS = ROOT / 'docs/prototypes/memoir-v1'
PROMPTS = Path(__file__).resolve().with_name('prompts')
BACKEND_AI = ROOT / 'cloud-deployment/backend/app/ai'
RUNS = common.RUNS
TESTSET = common.TESTSET_DIR
load, save, sha = common.load, common.save, common.sha

MODULES = [  # chapter order of the book; the skeleton is the prologue
    ('skeleton', 'SK', '开篇'),
    ('childhood', 'CH', '家乡与童年'),
    ('growth', 'GR', '求学与成长'),
    ('work', 'WK', '工作与劳动'),
    ('family', 'FM', '家庭生活'),
    ('later_life', 'LT', '后来的生活'),
    ('reflection', 'RV', '人生回望'),
]
MODULE_NAME = {m: n for m, _, n in MODULES}
PREFIX_MODULE = {p: m for m, p, _ in MODULES}
# Share of the standard book per chapter (decision 2026-10-26).
SHARE = {'skeleton': .05, 'childhood': .15, 'growth': .15, 'work': .22, 'family': .17, 'later_life': .11, 'reflection': .13}
# Edition: ratio of written chars to the elder's own chars, and the book cap.
# standard was 0.8 in rounds 1-2 (pass --ratio 0.8 to reproduce them); 0.7 from round 3 on.
EDITIONS = {'brief': (0.5, 20000), 'standard': (0.7, 50000), 'full': (1.0, 90000)}
MERGE_BELOW = 1500  # a chapter whose material (elder chars) is below this merges into a neighbour (the prologue never merges)


def module_of(qid):
    return PREFIX_MODULE[qid[:2]]


def catalog():
    contracts = load(BACKEND_AI / 'interview_runtime/contracts.json')
    depth = {q['id']: q for q in load(DOCS / 'question-depth.json')['questions']}
    out = {}
    for q in contracts['questions']:
        d = depth[q['id']]
        out[q['id']] = {'id': q['id'], 'module': module_of(q['id']), 'title': q['title'],
                        'main_question': q['main_question'], 'depth': d['depth'],
                        'sensitive': bool(d.get('sensitive'))}
    return out


def grounded_draft_prompt():
    """The production GROUNDED_DRAFT_PROMPT, read from app/ai/prompts.py without importing the app."""
    import ast
    tree = ast.parse((BACKEND_AI / 'prompts.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == 'GROUNDED_DRAFT_PROMPT':
            return ast.literal_eval(node.value).strip()
    raise KeyError('GROUNDED_DRAFT_PROMPT')


def prompt(name):
    return (PROMPTS / name).read_text(encoding='utf-8').strip()


# --------------------------------------------------------------------------- text
_T2S = None


def t2s(text):
    global _T2S
    if _T2S is None:
        _T2S = load(BACKEND_AI / 'interview_runtime/opencc-ts-char-map.json')
    return ''.join(_T2S.get(ch, ch) for ch in text or '')


def clean(text):
    text = t2s(text or '').replace('　', ' ')
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


SENT_END = re.compile(r'(?<=[。！？!?；])')


def sentences(text):
    return [s for s in (p.strip() for p in SENT_END.split(text)) if s]


CN_DIGIT = {'零': 0, '〇': 0, '○': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
CN_UNIT = {'十': 10, '百': 100, '千': 1000, '万': 10000}
CN_NUM = re.compile(r'[零〇○一二两三四五六七八九十百千万]+')
AR_NUM = re.compile(r'\d+(?:\.\d+)?')
# Chinese words that contain numeral characters but are not quantities.
NUM_WORDS = ('一直', '一起', '一样', '一定', '一下', '一些', '一切', '一点', '一般', '一边', '一面', '一生', '一辈子', '一路',
             '一向', '一旦', '一共', '一齐', '一再', '一心', '一口气', '一阵', '一片', '一手', '一时', '一同', '一致', '统一',
             '唯一', '万一', '一会', '一遍', '一次次', '一个个', '一天天', '一年年', '一步步', '一声', '一眼', '一回',
             '十分', '万分', '千万', '万万', '三番五次', '七八糟', '乱七八糟', '四处', '四周', '四面', '一五一十', '五花八门',
             '一模一样', '三心二意', '万事', '百姓', '老百姓', '千辛万苦', '十足', '十全十美', '一刀两断', '两样', '两边',
             '不三不四', '星期一', '一家人', '一家子', '第一', '一把', '一些', '二话', '一无所有', '万里', '三三两两',
             '一阵子', '一下子', '一辈', '一层', '一半', '万般', '百般', '千百', '几十', '一九', '六一')


def _cn_value(token):
    """Value(s) of a Chinese numeral token. '一九七一' -> 1971 (digit style); '三四十' -> {30,40}; '二十六' -> 26."""
    if all(ch in CN_DIGIT for ch in token):
        if len(token) == 1:
            return {CN_DIGIT[token]}
        if len(token) == 2 and token[0] != token[1] and abs(CN_DIGIT[token[0]] - CN_DIGIT[token[1]]) == 1 \
                and CN_DIGIT[token[0]] < CN_DIGIT[token[1]]:
            return {CN_DIGIT[token[0]], CN_DIGIT[token[1]]}  # '三四' (个) = 3 or 4
        return {int(''.join(str(CN_DIGIT[c]) for c in token))}
    # trailing range after a unit: 十六七 (岁) = 16 or 17, 二十三四 = 23 or 24
    m = re.fullmatch(r'(.*[十百千万])([一二三四五六七八九])([一二三四五六七八九])', token)
    if m and CN_DIGIT[m.group(3)] - CN_DIGIT[m.group(2)] == 1:
        base = _cn_value(m.group(1) + '零')
        return {b + CN_DIGIT[m.group(2)] for b in base} | {b + CN_DIGIT[m.group(3)] for b in base}
    # positional: allow a leading range pair like 三四十 / 五六百
    m = re.fullmatch(r'([一二三四五六七八九])([一二三四五六七八九])([十百千万])(.*)', token)
    if m and CN_DIGIT[m.group(2)] - CN_DIGIT[m.group(1)] == 1:
        unit = CN_UNIT[m.group(3)]
        return {CN_DIGIT[m.group(1)] * unit, CN_DIGIT[m.group(2)] * unit}
    total, section, num = 0, 0, 0
    for ch in token:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            unit = CN_UNIT[ch]
            if unit == 10000:
                section = (section + num) * unit
                total += section
                section = 0
            else:
                section += (num or 1) * unit
            num = 0
    return {total + section + num}


def numbers(text):
    """Set of numeric values mentioned in text (arabic + Chinese numerals), ignoring idiomatic 一/两."""
    text = t2s(text)
    for w in sorted(NUM_WORDS, key=len, reverse=True):
        text = text.replace(w, '　' if w not in ('一九', '六一') else w)
    vals = set()
    for m in AR_NUM.finditer(text):
        v = float(m.group())
        vals.add(int(v) if v.is_integer() else v)
    for m in CN_NUM.finditer(text):
        tok = m.group()
        if tok in ('一', '两', '二', '十', '万', '千', '百'):
            continue  # bare articles / '十几' style vagueness carry no checkable quantity
        try:
            vals |= _cn_value(tok)
        except (KeyError, ValueError):
            continue
    # two-digit year shorthands ('八五年', '85年') also match the full year and vice versa
    extra = set()
    for v in vals:
        if isinstance(v, int) and 1900 <= v <= 2099:
            extra.add(v % 100)
    return vals | extra


PLACE_SUFFIX = '省市县乡镇村区州街路巷山河江湖岛港屯庄寨沟岭湾营堡'
PLACE = re.compile(r'([一-鿿]{1,5}?)([%s])' % PLACE_SUFFIX)
GENERIC_PLACE = {'家乡', '老家', '农村', '乡村', '山区', '城市', '县城', '城里', '村里', '乡里', '山里', '山上', '河边',
                 '江边', '湖边', '街上', '路上', '马路', '大街', '小路', '公路', '铁路', '道路', '山路', '村子', '城区',
                 '社区', '市区', '郊区', '地区', '小区', '学区', '下乡', '回乡', '异乡', '他乡', '故乡', '本村', '全村',
                 '全县', '外省', '本省', '同乡', '乡亲', '邻村', '隔壁村', '一路', '半路', '走路', '出路', '思路', '门路',
                 '心里', '这里', '那里', '哪里', '家里', '夜里', '屋里', '手里', '嘴里', '眼里', '梦里', '心里头', '逛街', '上街', '大山',
                 '深山', '高山', '下山', '上山', '爬山', '江山', '河山', '山村', '渔村', '各乡', '城乡', '老乡', '同村'}
TITLE_WORDS = '(?:老师|师傅|先生|同学|主任|书记|校长|队长|厂长|医生|大夫|阿姨|叔叔|伯伯|婶婶|大姐|大哥)'
TITLE = re.compile(r'(?:老|小|阿)[\u4e00-\u9fff]|[\u4e00-\u9fff]{1,2}' + TITLE_WORDS)
GENERIC_PERSON = {'老师', '老人', '老家', '老伴', '老板', '老婆', '老公', '老乡', '老大', '老二', '老三', '老小', '老实', '老是',
                  '老了', '老去', '小孩', '小学', '小时', '小的', '小心', '小事', '小姐', '小伙', '小子', '阿姨', '老百', '小小',
                  '老太', '老头', '老年', '老天', '老式', '老屋', '老房', '老街', '老路', '小路', '小河', '小镇', '小村', '老早',
                  '老样', '小声', '小菜', '小店', '小饭', '小吃', '老兵', '小兵', '老一', '小一', '小姑', '老爷', '老总'}


def places(text):
    """Place-like tokens, reduced to the char before the suffix + the suffix ('跟着苏州' -> '苏州', '浦城县' -> '城县'):
    the lazy regex starts at the earliest position, so the raw match carries unrelated leading words."""
    out = set()
    for m in PLACE.finditer(t2s(text)):
        tok = m.group(0)[-2:]
        if len(tok) < 2 or tok[0] in '的了着在到和与是从往去来个条' or tok in GENERIC_PLACE \
                or any(g in m.group(0)[-3:] for g in ('心里', '这里', '那里', '家里')):
            continue
        out.add(tok)
    return out


def persons(text):
    out = set()
    t = t2s(text)
    for m in TITLE.finditer(t):
        tok = m.group(0)
        if tok[0] in '老小' and m.start() > 0 and t[m.start() - 1] in '从很最太多大不好变显':
            continue  # 从小想 / 很老 / 变小 are not names
        if tok not in GENERIC_PERSON and tok[:2] not in GENERIC_PERSON:
            out.add(tok)
    return out


def unsupported(sentence, source_text):
    """Code fact check of one written sentence against source text: numbers, place and person tokens."""
    src = t2s(source_text)
    src_nums = numbers(src)
    bad = []
    for v in sorted(numbers(sentence) - src_nums, key=str):
        bad.append(('number', str(v)))
    # vague magnitudes (几百年, 上千, 数十) carry no value but still state a scale: they must be in the sources too
    for tok in sorted(set(re.findall(r'[几数上好][十百千万]', t2s(sentence)))):
        if tok not in src and not (tok[0] == '几' and '几' + tok[1] in src):
            bad.append(('number', tok))
    for tok in sorted(places(sentence)):
        # tokens are the shortest match (one char + suffix), so '浦城县' is checked as '城县'
        if tok not in src:
            bad.append(('place', tok))
    for tok in sorted(persons(sentence)):
        m = re.match('(.*?)(' + TITLE_WORDS + ')$', tok)
        if m:
            name, title = m.group(1), m.group(2)
            forms = [name[-1:] + title, name[-2:] + title] + ([name[-2:]] if len(name) >= 2 else [])
            if not any(f in src for f in forms):
                bad.append(('person', name[-1:] + title))
        elif tok not in src:
            bad.append(('person', tok))
    return bad


TIME = re.compile(r'(?:19|20)\d\d年?(?:代)?|\d{2}年代|民国\s?\d+\s?年|[一二三四五六七八九十]{2,4}年代|'
                  r'[一二三四五六七八九〇零]{4}年|\d{1,3}岁|[一二三四五六七八九十]{1,3}岁|小时候|年轻时|上学时|那年|那时候|'
                  r'后来|退休|结婚|解放|抗战|文革|改革开放|恢复高考')


def time_clues(text):
    return sorted(set(m.group(0) for m in TIME.finditer(t2s(text))), key=lambda s: t2s(text).find(s))


UNKNOWN = re.compile(r'记不(?:太)?清|不(?:太)?记得|记不到|忘(?:记)?了|模糊|说不清|不知道|想不起')
DECLINE = re.compile(r'不想(?:多)?(?:讲|说|谈|提)|不愿(?:意)?(?:讲|说|谈|提)|不多(?:讲|说|谈)了?|别问|不提(?:也)?罢|不提还好')
KIN = ('我爸', '爸爸', '我爹', '爹', '父亲', '老爸', '阿爸', '我妈', '妈妈', '我娘', '娘', '母亲', '老妈', '阿妈',
       '爷爷', '祖父', '奶奶', '祖母', '外公', '姥爷', '外婆', '姥姥', '老伴', '爱人', '太太', '先生', '丈夫', '老公',
       '妻子', '老婆', '媳妇', '儿子', '女儿', '闺女', '孩子', '孙子', '孙女', '外孙', '哥哥', '我哥', '大哥', '姐姐',
       '我姐', '大姐', '弟弟', '妹妹', '兄弟姊妹', '兄弟姐妹')


def voice_profile(texts):
    """Kinship terms and self reference the elder actually uses (code-extracted), most frequent first."""
    joined = '\n'.join(t2s(t) for t in texts)
    kin = {}
    for term in sorted(KIN, key=len, reverse=True):
        n = joined.count(term)
        if n:
            kin[term] = n
    # drop short terms only counted inside longer ones (爸爸 inside 我爸爸 is still 爸爸)
    self_ref = {w: joined.count(w) for w in ('俺', '咱', '我们家', '咱家', '俺家') if joined.count(w)}
    return {'kin_terms': dict(sorted(kin.items(), key=lambda kv: -kv[1])[:14]), 'self_reference': self_ref}


def han_len(text):
    return len(re.findall(r'[一-鿿]', text or ''))


_EXTRA_T2S = {'邉': '边', '裏': '里', '衆': '众', '綫': '线', '着': '着'}


def simplify(text):
    """t2s plus fixes the char map leaves out: 著 used as the aspect particle (跟著/带著) -> 着, except 著名/著作/著称."""
    text = ''.join(_EXTRA_T2S.get(ch, ch) for ch in t2s(text))
    return re.sub(r'著(?![名作称述书])', '着', text)


_COPY_NORM = re.compile(r'[^一-鿿0-9A-Za-z]')


def copy_ratio(sentences_, source_text):
    """Share of written (non-added) chars in sentences that are near-verbatim copies of the sources: a sentence counts
    as copied when one common substring with the sources covers >= 80% of it (punctuation ignored)."""
    import difflib
    src = _COPY_NORM.sub('', t2s(source_text))
    total = copied = 0
    for s in sentences_:
        t = _COPY_NORM.sub('', t2s(s))
        if not t:
            continue
        m = difflib.SequenceMatcher(None, t, src, autojunk=False).find_longest_match(0, len(t), 0, len(src))
        total += len(t)
        copied += len(t) if m.size >= 0.8 * len(t) else 0
    return round(copied / total, 3) if total else None


def premerge(module_chars, max_modules=2):
    """Chapter groups before planning. A module whose material (elder chars) is below MERGE_BELOW merges with ONE
    adjacent module (the smaller one; the previous one on ties) that is not merged yet, so a chapter holds at most
    max_modules modules and the six-module structure stays visible; a thin module with no free neighbour stays a
    short chapter. The prologue never merges. module_chars: {module: elder chars}; returns [[module, ...], ...]."""
    groups = [[m] for m, _, _ in MODULES if module_chars.get(m)]
    size = lambda g: sum(module_chars[m] for m in g)
    tried = set()
    while True:
        body = [g for g in groups if g[0] != 'skeleton']
        thin = [g for g in body if size(g) < MERGE_BELOW and len(g) < max_modules and g[0] not in tried]
        if not thin:
            return groups
        g = min(thin, key=size)
        tried.add(g[0])
        i = body.index(g)
        prev = body[i - 1] if i > 0 else None
        nxt = body[i + 1] if i + 1 < len(body) else None
        free = [x for x in (prev, nxt) if x and len(x) + len(g) <= max_modules]
        if not free:
            continue
        into = min(free, key=lambda x: (size(x), 0 if x is prev else 1))
        a, b = (into, g) if groups.index(into) < groups.index(g) else (g, into)
        groups[groups.index(a)] = a + b
        groups.remove(b)


def ingest_staged(relay, job_name, calls):
    """Cache the answers of an already-sent relay job whose runner died before reading them (no resend).
    A call is taken only when the request file holds the same user text and params under the same id."""
    req = load(common.OUT_JOBS / (job_name + '.request.json'))
    sent = {c['id']: c for c in req['calls']}
    resp = next(common.IN_ROOT.rglob(job_name + '.response.jsonl'))
    rows = {}
    for line in resp.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rows[row.get('id')] = row
    n = 0
    for call in calls:
        s, row = sent.get(call['id']), rows.get(call['id'])
        if not s or not row or not row.get('ok') or s['user'] != call['user'] or s['params'] != call['params'] \
                or req['prompts'].get(s['system_ref']) != call['system']:
            continue
        try:
            row['output'], row['parse_error'] = json.loads(row.get('content') or ''), None
        except ValueError:
            row['output'], row['parse_error'] = None, 'JSONDecodeError'
        save(common.CACHE / (relay.key(call) + '.json'), row)
        n += 1
    return n
