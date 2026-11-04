#!/usr/bin/env python3
"""BRIEF12 (interview V6.2) metrics of run_full.py / v6flow.py runs -- code first, 0 token, recomputable.

  python3 tools/interview_eval/simulate/v62_metrics.py convert RUN [RUN ...]
        v4-style sessions in RUNS/<RUN>__v4/sessions, so style.py / material.py / score.py / export_html.py read them
  python3 tools/interview_eval/simulate/v62_metrics.py table A=RUN B=RUN ... [--json OUT] [--md OUT]
        per run (and per person x module chain): the elder's words, what is new after retellings are taken out,
        cross-question retellings, deepening, judgements of the elder, questions beyond what he lived through,
        DeepSeek tokens; RUN may be RUN1+RUN2 (pooled)
  python3 tools/interview_eval/simulate/v62_metrics.py score RUN [--offline]
        the unchanged rubric (docs/prototypes/full-interview-v4/scorer-prompt.txt, Haiku scorer queue, one request per
        question) -> RUNS/<RUN>/scores.json (score.metrics summary + per-question scores)
  python3 tools/interview_eval/simulate/v62_metrics.py firsts --people NID[,NID] --sim-config A.json [--sim-config B.json]
        [--offline] [--json OUT]
        simulator sensitivity: the elder's FIRST answer to every module question (he sees only the fixed entry
        question, so the interviewer cannot cause any retelling there) under each persona setting; how much of it
        retells an earlier question

Definitions (the same for every run and version):
- sentence: text up to 。！？；… ; Chinese characters only are counted.
- new material (去复述后的新素材): a sentence whose 4-grams are less than half covered by everything the elder said
  before it in this interview (the run's memory seed -- earlier modules of the reference run -- first, then the
  run's own questions in plan order); a short (<= 20 characters) closer such as "没有了，就这些" is not material.
  The same definition as the memoir side's novel_chars (tools/memoir_eval/book.py), in interview order.
- cross-question retelling (跨题重讲): a sentence of at least 8 characters whose 4-grams are at least half covered by
  ONE earlier question's words (another question than its own, seed included); counted per sentence and per
  question that has one.
- judgement of the elder (替老人下评价): an interviewer turn whose acknowledgement part contains a word of the backend's
  EVAL / EVAL_V62 lists that the elder's own words in this question lack (both lists for every version).
- beyond his experience (超出亲历): a follow-up or detail question that asks how someone else talked to a third person
  (interview_story.third_party).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import v6flow  # noqa: E402

SENT = re.compile(r'[^。！？!?；;…\n]+[。！？!?；;…]*')
FILLER = re.compile(r'(想不起来了|没什么要补充|没有要补充|没有了[，。]|就是这些|就这些了|都跟您讲了|都讲了|没别的了|别的也没什么|也没什么了|没有别的|别的就没|'
                    r'说不上来了|讲不出什么|不乱讲|不敢乱说|不好乱说|记不清了|没什么印象)')
KIND_OF_PROMPT = {'entry': 'entry', 'followup': 'followup', 'deepen': 'deepen', 'draft': 'draft', 'supplement': 'supplement',
                  'resume': 'resume', 'review': 'review', 'transition': 'transition', 'pause': 'pause'}
_BACKEND = None


def backend():
    global _BACKEND
    if _BACKEND is None:
        _, speaker, story = v6flow.load_backend()
        _BACKEND = SimpleNamespace(speaker=speaker, story=story)
    return _BACKEND


def han(text):
    return re.sub(r'[^一-鿿]', '', backend().speaker._simp(text or ''))


def grams(text, n=4):
    t = han(text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def load_run(name):
    sessions = []
    for part in name.split('+'):
        d = common.RUNS / part
        plan = common.load(d / 'plan.json')
        for f in sorted((d / 'sessions').glob('*.json')):
            s = common.load(f)
            s['_run'], s['_plan'] = part, plan
            sessions.append(s)
    return sessions


def seed_text(plan, nid, module):
    """The reference run's earlier modules (run_full.py --memory-seed), as the elder told them."""
    seed = plan.get('memory_seed')
    if not seed:
        return []
    path = common.RUNS / seed / 'sessions' / f'{nid}.json'
    if not path.exists():
        return []
    names = list(v6flow.MODULE_NAMES)
    keep = names[:names.index(module)]
    out = []
    for r in common.load(path)['questions']:
        if r.get('module') in keep:
            out.append((r['qid'], ''.join(m['text'] for m in r['messages'] if m['role'] == 'elder' and not m.get('scripted'))))
    return out


def elder_answers(rec):
    """[(prompt kind, text)] of the elder's own answers (scripted "继续" taps left out)."""
    out, last = [], 'entry'
    for m in rec['messages']:
        if m['role'] == 'system':
            last = KIND_OF_PROMPT.get(m.get('kind'), m.get('kind'))
        elif not m.get('scripted'):
            out.append((last, m['text']))
    return out


def eval_words():
    sp = backend().speaker
    return tuple(dict.fromkeys(sp.EVAL + sp.EVAL_V62))


def turn_ack(m):
    """The interviewer's own words of a turn before its fixed part / question part."""
    text = m['text']
    for tail in (m.get('question_part'), v6flow.DRAFT_TEXT, v6flow.SUPPLEMENT_TEXT, v6flow.REVIEW_TEXT):
        if tail and text.endswith(tail):
            return text[:-len(tail)]
    if m.get('kind') == 'transition':
        return re.split(r'[。！!]', text)[0] if '。' in text else ''
    return text


# --------------------------------------------------------------------------- wording (V6.1 cloud evidence problems)
FIXED_TAILS = None


def fixed_tails():
    global FIXED_TAILS
    if FIXED_TAILS is None:
        S = setup()
        FIXED_TAILS = [v6flow.DRAFT_TEXT, v6flow.SUPPLEMENT_TEXT, v6flow.REVIEW_TEXT, v6flow.LIFE_REVIEW_TEXT] + \
            sorted({q['main_question'] for q in S.rt.questions.values()}, key=len, reverse=True)
    return FIXED_TAILS


def phrase_family(lead):
    """The move-on phrase right before the next entry, reduced to its family (那咱们/那我们再来聊聊 -> 再聊聊)."""
    st = backend().story
    t = backend().speaker._norm(lead)
    for p in st.WARM_TRANSITIONS_V62 + st.WARM_TRANSITIONS:
        if t.endswith(backend().speaker._norm(p)):
            return re.sub(r'[那我们咱来就]', '', p)
    m = re.search(r'(?:接着|再|来|接下来)?(?:聊聊|说说|谈谈|讲讲|问问|打听)[^。！？]*$', t)
    return re.sub(r'[那我们咱来就]', '', m.group(0)) if m else ''


def close_parts(text):
    """(own words before the fixed tail, tail) of a close; tail '' when none is recognised."""
    for tail in fixed_tails():
        if text.endswith(tail):
            return text[:-len(tail)], tail
    return text, ''


def wording(text, elder_words, kind):
    """Features of one interviewer turn: ack (his own reaction part), echo, family of the move-on phrase, pattern."""
    st, sp = backend().story, backend().speaker
    fam = ''
    if kind == 'close':
        own, tail = close_parts(text)
        fam = phrase_family(own)
        clauses = re.findall(r'[^，,。！!]+[，,。！!]?', own.strip())
        while clauses and (fam and sp._norm(clauses[-1]) and fam[-2:] in sp._norm(clauses[-1]) or
                           sp._norm(clauses[-1]) in ('那', '好', '嗯', '好那')):
            clauses.pop()
        ack = ''.join(clauses)
    else:
        q = re.findall(r'[^。！!？?]*[？?]$', text)
        ack = text[:-len(q[0])] if q else ''
    if sp.BARE_ACK.fullmatch(sp._norm(ack)):
        ack = ''
    ack = ack.strip()
    echo = bool(ack) and st.fragment_echo(ack, elder_words)
    ack_kind = 'none' if not backend().speaker._norm(ack) else ('echo' if echo else 'reaction')
    return {'ack': ack, 'echo': echo, 'family': fam, 'pattern': (ack_kind, fam or ('light' if kind == 'close' else '')),
            'ack_kind': ack_kind}


def wording_summary(turns):
    """turns: [(session key, kind, text, elder words)] in order. Counts of the three V6.1 problems' code metrics."""
    sp, st = backend().speaker, backend().story
    words = eval_words()
    out = Counter()
    last = {}
    for key, kind, text, elder in turns:
        w = wording(text, elder, kind)
        out['turns'] += 1
        out['turns_' + kind] += 1
        if w['ack_kind'] != 'none':
            out['with_ack'] += 1
        if w['echo']:
            out['fragment_echo'] += 1
        if kind == 'close':
            out['closes'] += 1
            if w['family']:
                out['phrase_closes'] += 1
            prev = last.get(key)
            if prev is not None:
                out['close_pairs'] += 1
                out['same_pattern_pairs'] += w['pattern'] == prev['pattern']
                out['same_family_pairs'] += bool(w['family']) and w['family'] == prev['family']
            last[key] = w
        bad = [x for x in words if x in w['ack'] and x not in sp._simp(elder)] or \
            ([st.WARM_SUBJECTIVE.search(w['ack']).group(0)] if st.WARM_SUBJECTIVE.search(w['ack']) else [])
        if bad:
            out['subjective'] += 1
        if kind in ('followup', 'deepen') and st.third_party(text):
            out['third_party'] += 1
    return out


def wording_row(c):
    return {'turns': c['turns'], 'fragment_echo_rate': ratio(c['fragment_echo'], c['turns']),
            'ack_share': ratio(c['with_ack'], c['turns']), 'phrase_share_of_closes': ratio(c['phrase_closes'], c['closes']),
            'same_pattern_rate': ratio(c['same_pattern_pairs'], c['close_pairs']),
            'same_family_rate': ratio(c['same_family_pairs'], c['close_pairs']),
            'subjective': c['subjective'], 'third_party': c['third_party']}


def run_turns(name):
    """Interviewer turns of a run in the wording_summary format (closes = draft/supplement/transition/review+ack)."""
    turns = []
    for s in load_run(name):
        chains = defaultdict(list)
        S = setup()
        for rec in s['questions']:
            chains[S.module_of(rec['qid'])].append(rec)
        for module, recs in chains.items():
            key = f"{s['_run']}:{s['narrator_id']}:{module}"
            for rec in recs:
                elder = ''
                for m in rec['messages']:
                    if m['role'] == 'elder':
                        if not m.get('scripted'):
                            elder += m['text']
                        continue
                    k = m.get('kind')
                    if k in ('draft', 'supplement', 'transition') or (k == 'review' and m['text'] != v6flow.REVIEW_TEXT):
                        turns.append((key, 'close', m['text'], elder))
                    elif k in ('followup', 'deepen'):
                        turns.append((key, k, m['text'], elder))
    return turns


def evidence_turns(path):
    """Interviewer turns of a Codex cloud export (原样问答.json): each turn after an elder answer."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    turns = []
    for case in data['cases']:
        elder, prev_role = '', None
        events = case.get('events') or []
        for k, e in enumerate(events):
            if e['role'] == 'respondent':
                if e['text'].strip() not in ('继续', '暂停', '跳过'):
                    elder += e['text']
                prev_role = 'respondent'
                continue
            text = e['text']
            if prev_role != 'respondent' or text in (v6flow.PAUSE_TEXT, v6flow.LIFE_PAUSE_TEXT) or \
                    events[k - 1]['text'].strip() in ('继续',):
                prev_role = 'interviewer'
                continue
            own, tail = close_parts(text)
            kind = 'close' if tail else ('followup' if re.search(r'[？?]$', text) else 'close')
            turns.append((case['case'], kind, text, elder))
            if tail and tail not in (v6flow.DRAFT_TEXT, v6flow.SUPPLEMENT_TEXT, v6flow.REVIEW_TEXT):
                elder = ''  # the next question starts
            prev_role = 'interviewer'
    return turns


def evidence_v62_turns(path):
    """0 token counterfactual: the V6.2 code guards applied to the very texts the V6.1 cloud candidate showed, read as
    the model's reply (no new model call, so the V6.2 prompt changes are NOT in it): closes into the next question
    through close_reply, draft/supplement acknowledgements through draft_ack, follow-ups lose a fragment echo."""
    S = v6flow.Setup(version='v6.2')
    st, sp, rt = S.story, S.speaker, S.rt
    out, shown = [], {}
    for key, kind, text, elder in evidence_turns(path):
        seen = shown.setdefault(key, [])
        own, tail = close_parts(text)
        if kind == 'close' and tail == v6flow.LIFE_REVIEW_TEXT or text == v6flow.LIFE_REVIEW_TEXT:
            new = text  # the fixed skeleton review text
        elif kind == 'close' and tail in (v6flow.DRAFT_TEXT, v6flow.SUPPLEMENT_TEXT, v6flow.REVIEW_TEXT):
            ack = st.draft_ack(rt, own, None, elder, seen)
            ack, _ = sp.listening_ack(rt, ack, elder)
            new = sp.join(ack, tail) if ack else tail
        elif kind == 'close' and tail:
            reason = 'declined' if re.search(r'不想说|不想多讲|不多说', elder[-12:]) else None
            new = st.close_reply(rt, text, tail, elder, seen, reason)[0] or text
        else:
            q = re.findall(r'[^。！!？?]*[？?]$', text)
            ack = text[:-len(q[0])] if q else ''
            ack, _ = sp.clean_ack(rt, ack, elder)
            ack, _ = st.drop_fragment_echo(rt, ack, elder)
            question = q[0] if q else text
            if st.third_party(question):  # V6.2 refuses it; the judgment layer's own question is asked instead
                question = '〔判定层原问法〕'
            new = sp.join(ack, question)
        seen.append(new)
        out.append((key, kind, new, elder))
    return out


def wording_cmd(args):
    """python3 v62_metrics.py wording LABEL=RUN ... [--evidence LABEL=原样问答.json] [--json OUT]"""
    out_json = args[args.index('--json') + 1] if '--json' in args else None
    res = {}
    for i, a in enumerate(args):
        if a == '--evidence':
            label, path = args[i + 1].split('=', 1)
            res[label] = wording_row(wording_summary(evidence_turns(path)))
        if a == '--evidence-v62':
            label, path = args[i + 1].split('=', 1)
            turns = evidence_v62_turns(path)
            res[label] = wording_row(wording_summary(turns))
            if '--show' in args:
                for _, kind, text, _ in turns:
                    print(kind, text)
    for a in args:
        if '=' in a and not a.startswith('--') and a not in [args[i + 1] for i, x in enumerate(args) if x in ('--evidence', '--evidence-v62')]:
            label, name = a.split('=', 1)
            res[label] = wording_row(wording_summary(run_turns(name)))
    keys = ['turns', 'fragment_echo_rate', 'ack_share', 'phrase_share_of_closes', 'same_pattern_rate', 'same_family_rate',
            'subjective', 'third_party']
    names = {'turns': '采访者发言数', 'fragment_echo_rate': '碎片式复述承接占比', 'ack_share': '带承接的发言占比',
             'phrase_share_of_closes': '收尾用过渡短语占比', 'same_pattern_rate': '相邻收尾同一句式占比',
             'same_family_rate': '相邻收尾同一过渡短语族占比', 'subjective': '主观评价（老人没说过）', 'third_party': '第三方亲历追问'}
    print('| 指标 | ' + ' | '.join(res) + ' |')
    print('|---|' + '---|' * len(res))
    for k in keys:
        print(f'| {names[k]} | ' + ' | '.join(str(r[k]) for r in res.values()) + ' |')
    if out_json:
        common.save(Path(out_json), res)


def chain_metrics(recs, seed, depth):
    """Metrics of one person's module chain (records in plan order), ``seed``: [(qid, text)] told before it."""
    sp, st = backend().speaker, backend().story
    seen = set()
    by_q = []  # (qid, grams) of earlier questions
    for qid, text in seed:
        g = grams(text)
        seen |= g
        by_q.append((qid, g))
    words = eval_words()
    out = Counter()
    kinds = defaultdict(Counter)
    retell_q = 0
    examples = {'retell': [], 'judgement': [], 'third_party': [], 'told_redirect': []}
    for rec in recs:
        qid = rec['qid']
        qg = set()
        had_retell = False
        for kind, text in elder_answers(rec):
            for sent in SENT.findall(text):
                g, n = grams(sent), len(han(sent))
                if not n:
                    continue
                out['elder_chars'] += n
                kinds[kind]['all'] += n
                if depth.get(qid) == 'story':
                    out['story_elder_chars'] += n
                new = g and len(g & seen) / len(g) < 0.5 and not (n <= 20 and FILLER.search(sent))
                if new:
                    out['novel_chars'] += n
                    kinds[kind]['new'] += n
                    if depth.get(qid) == 'story':
                        out['story_novel_chars'] += n
                if n >= 8 and g:
                    best = max((len(g & og) / len(g), oq) for oq, og in by_q) if by_q else (0, None)
                    if best[0] >= 0.5:
                        out['cross_retell_sents'] += 1
                        out['cross_retell_chars'] += n
                        had_retell = True
                        if len(examples['retell']) < 6:
                            examples['retell'].append(f'{qid}←{best[1]}：{sent.strip()[:40]}')
                seen |= g
                qg |= g
        retell_q += had_retell
        by_q.append((qid, qg))
        # interviewer turns
        elder_so_far = ''
        prev_deepen = False
        for m in rec['messages']:
            if m['role'] == 'elder':
                if not m.get('scripted'):
                    elder_so_far += m['text']
                    if prev_deepen:
                        out['deepen_answer_chars'] += len(han(m['text']))
                prev_deepen = False
                continue
            kind = m.get('kind')
            prev_deepen = kind == 'deepen'
            if kind not in ('followup', 'deepen', 'draft', 'supplement', 'transition', 'review'):
                continue
            ack = turn_ack(m)
            if ack and kind != 'review' or (kind == 'review' and m['text'] != v6flow.REVIEW_TEXT):
                elder = sp._simp(elder_so_far)
                bad = [w for w in words if w in ack and w not in elder]
                if bad:
                    out['judgement_turns'] += 1
                    if len(examples['judgement']) < 8:
                        examples['judgement'].append(f'{qid}：{m["text"][:50]}（{"、".join(bad)}）')
            if kind in ('followup', 'deepen'):
                q = m.get('question_part') or m['text']
                if st.third_party(q):
                    out['third_party'] += 1
                    if len(examples['third_party']) < 6:
                        examples['third_party'].append(f'{qid}：{q}')
            if kind == 'deepen':
                out['deepen_turns'] += 1
            if kind == 'transition':
                out['transitions'] += 1
        dz = rec.get('deepen') or {}
        asked = [e for e in dz.get('log') or [] if e.get('decision') == 'asked']
        if dz.get('redirect'):
            out['redirects'] += len(asked)
        elif asked:
            out['story_deepened'] += 1
        out['told_aware_deepens'] += sum(1 for e in asked if e.get('told_items'))
        for e in asked:
            if e.get('told_items') and len(examples['told_redirect']) < 6:
                examples['told_redirect'].append(f'{qid}：{e.get("question")}')
        if depth.get(qid) == 'story':
            out['story_questions'] += 1
        out['questions'] += 1
        out['completed'] += rec.get('status') in ('saved', 'skipped')
        for c in rec.get('calls') or []:
            u = (c.get('usage') or {}).get('total_tokens', 0)
            out['ds_calls'] += 1
            out['ds_tokens'] += u
            if not c.get('cached'):
                out['ds_tokens_new'] += u
        out['elder_answers'] += len(elder_answers(rec))
    out['questions_with_cross_retell'] = retell_q
    for key in KEYS:
        out[key] += 0
    return out, kinds, examples


KEYS = ('elder_chars', 'novel_chars', 'story_elder_chars', 'story_novel_chars', 'cross_retell_sents', 'cross_retell_chars',
        'deepen_answer_chars', 'judgement_turns', 'third_party', 'deepen_turns', 'transitions', 'redirects', 'story_deepened',
        'told_aware_deepens', 'story_questions', 'questions', 'completed', 'ds_calls', 'ds_tokens', 'ds_tokens_new',
        'elder_answers', 'questions_with_cross_retell')


def run_table(name):
    S = setup()
    rows, pooled, pooled_kinds, ex = [], Counter(), defaultdict(Counter), defaultdict(list)
    for s in load_run(name):
        chains = defaultdict(list)
        for rec in s['questions']:
            chains[S.module_of(rec['qid'])].append(rec)
        for module, recs in chains.items():
            m, kinds, examples = chain_metrics(recs, seed_text(s['_plan'], s['narrator_id'], module), S.depth)
            rows.append(Counter({'person': s['name'], 'nid': s['narrator_id'], 'module': module, **m}))
            pooled.update(m)
            for k, v in kinds.items():
                pooled_kinds[k].update(v)
            for k, v in examples.items():
                ex[k] += v
    return rows, pooled, pooled_kinds, ex


def setup():
    if not hasattr(setup, 'S'):
        setup.S = v6flow.Setup(version='v6.1')
    return setup.S


def ratio(a, b):
    return round(a / b, 3) if b else None


ROWS = [('题数（完成）', lambda p: f"{p['questions']}（{p['completed']}）"),
        ('老人原话字数', lambda p: p['elder_chars']),
        ('去复述后新素材字数', lambda p: p['novel_chars']),
        ('新素材比例', lambda p: ratio(p['novel_chars'], p['elder_chars'])),
        ('故事题原话 / 新素材', lambda p: f"{p['story_elder_chars']} / {p['story_novel_chars']}"),
        ('跨题重讲句数（字数）', lambda p: f"{p['cross_retell_sents']}（{p['cross_retell_chars']}）"),
        ('有跨题重讲的题数', lambda p: p['questions_with_cross_retell']),
        ('故事题被深挖题数 / 故事题数', lambda p: f"{p['story_deepened']} / {p['story_questions']}"),
        ('深挖问句数（含事实题转向问）', lambda p: f"{p['deepen_turns']}（转向 {p['redirects']}）"),
        ('深挖回答字数', lambda p: p['deepen_answer_chars']),
        ('知道“已讲过”的深挖/转向', lambda p: p['told_aware_deepens']),
        ('替老人下评价的发言', lambda p: p['judgement_turns']),
        ('超出亲历的追问/深挖', lambda p: p['third_party']),
        ('老人回答次数', lambda p: p['elder_answers']),
        ('DeepSeek 调用 / token（其中新发）', lambda p: f"{p['ds_calls']} / {p['ds_tokens']}（{p['ds_tokens_new']}）")]


def table(args):
    out_json = args[args.index('--json') + 1] if '--json' in args else None
    out_md = args[args.index('--md') + 1] if '--md' in args else None
    runs = [a for a in args if not a.startswith('--') and a not in (out_json, out_md)]
    runs = [tuple(x.split('=', 1)) if '=' in x else (x, x) for x in runs]
    res = {label: run_table(name) for label, name in runs}
    lines = ['| 指标 | ' + ' | '.join(label for label, _ in runs) + ' |', '|---|' + '---|' * len(runs)]
    for title, fn in ROWS:
        lines.append(f'| {title} | ' + ' | '.join(str(fn(res[label][1])) for label, _ in runs) + ' |')
    lines += ['', '按“上一句采访者的话”分的老人原话（字数 / 新素材比例）：', '',
              '| 回答的是 | ' + ' | '.join(label for label, _ in runs) + ' |', '|---|' + '---|' * len(runs)]
    for kind in ('entry', 'followup', 'deepen', 'draft', 'supplement', 'resume'):
        cells = []
        for label, _ in runs:
            k = res[label][2].get(kind) or Counter()
            cells.append(f"{k['all']} / {ratio(k['new'], k['all'])}" if k['all'] else '')
        name = {'entry': '入口题（首答）', 'followup': '追问', 'deepen': '深挖/转向问', 'draft': '草稿入口“还有什么想补充”',
                'supplement': '补充“还有别的想补充”', 'resume': '休息后继续'}[kind]
        lines.append(f'| {name} | ' + ' | '.join(cells) + ' |')
    lines += ['', '按人物 × 模块链：', '', '| 版本 | 人物 | 模块 | 原话 | 新素材 | 比例 | 跨题重讲句 | 深挖问 | 深挖答字数 | 评价 | 超亲历 |',
              '|---|---|---|---|---|---|---|---|---|---|---|']
    for label, _ in runs:
        for r in res[label][0]:
            lines.append(f"| {label} | {r['person']} | {v6flow.MODULE_NAMES.get(r['module'], r['module'])} | {r['elder_chars']} | "
                         f"{r['novel_chars']} | {ratio(r['novel_chars'], r['elder_chars'])} | {r['cross_retell_sents']} | "
                         f"{r['deepen_turns']} | {r['deepen_answer_chars']} | {r['judgement_turns']} | {r['third_party']} |")
    for label, _ in runs:
        ex = res[label][3]
        lines += ['', f'{label} 例子：']
        for k, title in (('retell', '跨题重讲'), ('judgement', '替老人评价'), ('third_party', '超出亲历'), ('told_redirect', '知道已讲过的深挖')):
            if ex[k]:
                lines.append(f'- {title}：' + '；'.join(ex[k][:6]))
    text = '\n'.join(lines)
    print(text)
    if out_md:
        Path(out_md).write_text(text + '\n', encoding='utf-8')
    if out_json:
        common.save(Path(out_json), {label: {'pooled': dict(r[1]), 'kinds': {k: dict(v) for k, v in r[2].items()},
                                             'rows': r[0], 'examples': r[3]} for label, r in res.items()})


# --------------------------------------------------------------------------- v4-style view for the older tools
def to_v4(s, S):
    eps = []
    for rec in s['questions']:
        msgs, steps = [], {st.get('answer'): st for st in rec.get('steps') or [] if st.get('answer')}
        last_answer = None
        for m in rec['messages']:
            x = {k: v for k, v in m.items() if k not in ('calls',)}
            if m['role'] == 'elder':
                last_answer = m['id']
                stp = steps.get(m['id']) or {}
                if stp.get('judge') is not None:
                    x['judge'] = stp['judge']
                if stp.get('rule'):
                    x['v4_action'] = [stp['rule'].get('action'), stp['rule'].get('reason')]
                if stp.get('deepen_answer'):
                    x['deepen_answer'] = True
                msgs.append(x)
                continue
            kind = m.get('kind')
            stp = steps.get(last_answer) or {}
            spoken = stp.get('spoken') or {}
            if kind in ('draft', 'supplement', 'transition') or (kind == 'review' and m['text'] != v6flow.REVIEW_TEXT):
                x['kind'] = 'close'
                x['v6_kind'] = kind
                x['reason'] = spoken.get('close_reason')
                tail = spoken.get('next_entry') if kind == 'transition' else \
                    {'draft': v6flow.DRAFT_TEXT, 'supplement': v6flow.SUPPLEMENT_TEXT, 'review': v6flow.REVIEW_TEXT}[kind]
                if tail and m['text'].endswith(tail):
                    x['entry_part'] = tail
                x['speaker'] = {'raw': spoken.get('raw'), 'input': spoken.get('input'), 'fallback': 'ack_fallback' in (spoken.get('notes') or [])}
            elif kind == 'followup':
                x['speaker'] = {'raw': spoken.get('raw'), 'input': spoken.get('input'), 'fallback': bool(spoken.get('fallback'))}
                x['engine_question'] = ((stp.get('judge') or {}).get('question'))
            elif kind == 'deepen':
                d = stp.get('deepen') or {}
                x['speaker'] = {'raw': d.get('raw'), 'input': d.get('input')}
            msgs.append(x)
        final = rec.get('final') or {}
        eps.append({'qid': rec['qid'], 'entry': rec['entry'], 'messages': msgs, 'close_reason': rec.get('close_reason'),
                    'final_decision': final.get('decision'), 'final': final, 'material_ids': rec.get('material_ids'),
                    'deepen': rec.get('deepen'), 'deepen_sources': rec.get('deepen_sources'), 'status': rec.get('status')})
    return {'session': f"{s['_run']}-{s['narrator_id']}", 'narrator_id': s['narrator_id'], 'name': s['name'], 'mode': 'v6',
            'questions': [r['qid'] for r in s['questions']], 'episodes': eps}


def convert(args):
    S = setup()
    for name in args:
        out = common.RUNS / (name + '__v4') / 'sessions'
        out.mkdir(parents=True, exist_ok=True)
        for s in load_run(name):
            common.save(out / f"{s['narrator_id']}.json", to_v4(s, S))
        common.save(out.parent / 'plan.json', {**common.load(common.RUNS / name / 'plan.json'), 'view_of': name})
        print('converted', name, '->', out)


# --------------------------------------------------------------------------- rubric
def score(args):
    import queue_worker as qw
    import score as scoring
    from persona import Personas
    name = args[0]
    offline = '--offline' in args
    convert([name])
    S = setup()
    prompt = (common.ROOT / 'docs/prototypes/full-interview-v4/scorer-prompt.txt').read_text(encoding='utf-8')
    SS = SimpleNamespace(personas=Personas(), F=S.rt.F)
    q = qw.HaikuQueue('scorer')
    sessions = [common.load(f) for f in sorted((common.RUNS / (name + '__v4') / 'sessions').glob('*.json'))]
    items = []
    for sess in sessions:
        for i, _ in enumerate(sess['episodes']):
            call, scored = scoring.scorer_call(SS, sess, i, prompt)
            if not scored:
                continue
            rid, row = q.submit(call['system'], call['user'], call['output_note'], call['validate'],
                                {'session': sess['session'], 'episode': i})
            if row is None and offline:
                row = {'ok': False, 'error': 'offline_haiku_cache_miss'}
            items.append([sess['session'], i, scored, rid, row])
    t0, last = time.time(), 0
    while True:
        missing = 0
        for it in items:
            if it[4] is None:
                it[4] = q.poll(it[3])
                missing += it[4] is None
        if not missing:
            break
        if time.time() - last >= 120:
            last = time.time()
            print(json.dumps({'scorer_waiting': missing, 't': round(time.time() - t0)}), flush=True)
        time.sleep(2)
    scores = {}
    for sid, i, scored, rid, row in items:
        scores.setdefault(sid, {})[str(i)] = {**scoring.parse_scores(row, scored), 'cached': row.get('cached')}
    m, _ = scoring.metrics(sessions, scores)
    common.save(common.RUNS / name / 'scores.json', {'run': name, 'metrics': m, 'scores': scores,
                                                     'violations': scoring.violation_list(sessions, scores),
                                                     'haiku': {'answered': q.sent, 'cached': q.cached}})
    print(json.dumps({k: m.get(k) for k in ('episodes_scored', 'scored_turns', 'ge4_natural', 'ge4_grounded', 'ge4_timing',
                                            'score_natural', 'score_grounded', 'score_timing', 'violation_turns', 'violation_rate',
                                            'violations', 'fabrication_total')}, ensure_ascii=False))


# --------------------------------------------------------------------------- simulator sensitivity (first answers)
def firsts(args):
    import interview
    import persona_backend
    people = args[args.index('--people') + 1].split(',')
    configs = [args[i + 1] for i, a in enumerate(args) if a == '--sim-config']
    offline = '--offline' in args
    out_json = args[args.index('--json') + 1] if '--json' in args else None
    pb = persona_backend.make(None)
    res = {}
    for cfgpath in configs:
        S = v6flow.Setup(cfgpath, version='v6.1')
        plan = [q for m in v6flow.MODULE_NAMES for q in S.modules[m]]
        for nid in people:
            items = []
            for qid in plan:
                call, beh, asr = interview.elder_call(S, nid, qid, 0, [], S.rt.questions[qid]['main_question'])
                rid, row = pb.submit(call['system'], call['user'], call['output_note'], call['validate'],
                                     {'run': 'st8-firsts', 'session': nid, 'call': call['id']})
                if row is None and offline:
                    row = {'ok': False}
                items.append([qid, beh, rid, row])
            while any(it[3] is None for it in items):
                for it in items:
                    if it[3] is None:
                        it[3] = pb.poll(it[2])
                time.sleep(2)
            recs = [{'qid': qid, 'status': 'saved', 'messages': [{'role': 'system', 'kind': 'entry', 'text': ''},
                                                               {'role': 'elder', 'text': interview.elder_text(row)}]}
                    for qid, beh, rid, row in items if row.get('ok') is not False]
            m, _, ex = chain_metrics(recs, [], S.depth)
            res[f'{Path(cfgpath).name}:{nid}'] = {'answers': len(recs), 'chars': m['elder_chars'], 'novel': m['novel_chars'],
                                                  'novel_share': ratio(m['novel_chars'], m['elder_chars']),
                                                  'cross_retell_sents': m['cross_retell_sents'],
                                                  'questions_with_cross_retell': m['questions_with_cross_retell'],
                                                  'examples': ex['retell'][:4], 'haiku_new': pb.sent, 'haiku_cached': pb.cached}
            print(json.dumps({f'{Path(cfgpath).name}:{nid}': res[f'{Path(cfgpath).name}:{nid}']}, ensure_ascii=False), flush=True)
    if out_json:
        common.save(Path(out_json), res)


if __name__ == '__main__':
    cmd, rest = sys.argv[1], sys.argv[2:]
    {'convert': convert, 'table': table, 'score': score, 'firsts': firsts, 'wording': wording_cmd}[cmd](rest)
