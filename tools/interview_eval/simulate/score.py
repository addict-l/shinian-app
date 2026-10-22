"""Scoring of simulated interviews: one cheap-model rubric call per question episode + code metrics.

The rubric (docs/prototypes/full-interview-v4/scorer-prompt.txt) is blind to the policy that produced the
dialogue. Code metrics are computed from the saved session records only.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from interview import V4, CONTROLS  # noqa: F401
from persona import bigrams

# Rubric scorer = Claude Haiku sub-agent via the scorer file queue (queue_worker.py). The deepseek-flash scorer used
# by the void B0 run was {'model': 'deepseek-flash', 'thinking': 'disabled', 'max_tokens': 900, 'temperature': 0}.
SCORER_PARAMS = {'model': 'claude-haiku-subagent', 'via': 'file queue <runs>/scorer-queue'}
DIMS = ('natural', 'grounded', 'timing', 'single', 'tone')
DIM_ZH = {'natural': '自然不生硬', 'grounded': '追问/回应贴合', 'timing': '时机（结束自然）', 'single': '单一不预设', 'tone': '语气'}
VIOLATIONS = ('multi_question', 'presupposition', 'repeat_ask', 'should_have_stopped')
GENERIC = bigrams('时候以后后来那时当时现在事情经历印象记得觉得一下一点一件这件那件这段那段日子生活家里')


def label_messages(episode):
    """[(label, message)] with S0.. for the interviewer and E1.. for the elder."""
    out, s, e = [], 0, 0
    for m in episode['messages']:
        if m['role'] == 'system':
            out.append(('S%d' % s, m))
            s += 1
        else:
            e += 1
            out.append(('E%d' % e, m))
    return out


def scorer_call(S, sess, ei, prompt):
    ep = sess['episodes'][ei]
    nid, qid = sess['narrator_id'], ep['qid']
    lines = ['老人资料：', S.personas.render(S.personas.material(nid, qid)), '', f'话题入口：{ep["entry"]}', '对话：']
    scored = []
    next_entry = sess['episodes'][ei + 1]['entry'] if ei + 1 < len(sess['episodes']) else None
    marked = False
    for label, m in label_messages(ep):
        text = m['text'].replace('\n', ' ')
        if m.get('scripted'):
            text += '（老人点了“继续”）'
        entry = m.get('entry_part') or (next_entry if m.get('kind') == 'close' else None)
        if m['role'] == 'system' and entry and text.endswith(entry):
            # the next topic's entry question is a fixed question-bank sentence, like S0: shown, not judged itself
            text = text[:-len(entry)].rstrip() + f'〔下一题入口，题库固定原句：{entry}〕'
            marked = True
        lines.append(f'{label}：{text}')
        if m['role'] == 'system' and label != 'S0':
            scored.append(label)
    lines.append('系统记下的内容：')
    rec = []
    for fid, f in ((ep.get('final') or {}).get('fields') or {}).items():
        label = S.F[fid]['label']
        if f['state'] == 'known':
            rec.append(f'- {label}：「{f.get("value")}」')
        else:
            rec.append(f'- {label}：（{ {"none": "明确没有", "unknown": "记不清", "declined": "不愿讲", "deferred": "以后再讲", "ambiguous": "说有但没说清"}.get(f["state"], f["state"]) }）')
    lines += rec or ['（无）']
    if marked:
        lines.append('注：〔〕里是题库固定的下一题入口原句，和 S0 一样不评它本身的内容（问什么不由采访者决定）；只评〔〕前面采访者自己说的话，以及转到下一题转得是否自然。')
    lines.append('需要打分的采访者发言：' + '、'.join(scored))
    note = ('只输出一个 JSON 对象，格式见指令末尾的“输出格式”。turns 里必须正好包含这些编号：' + '、'.join(scored)
            + '；每个编号给 natural/grounded/timing/single/tone 五个 1–5 的整数和 violations 列表；fabrication、record_errors 没有就给 []；note 一句话。')
    return {'id': f'score-{sess["session"]}-{ei}', 'route': 'scorer', 'system': prompt, 'user': '\n'.join(lines), 'params': SCORER_PARAMS,
            'output_note': note, 'validate': {'type': 'scorer', 'labels': scored}}, scored


def parse_scores(row, scored):
    out = row.get('output') if isinstance(row.get('output'), dict) else {}
    turns = out.get('turns') if isinstance(out.get('turns'), dict) else {}
    clean = {}
    for label in scored:
        t = turns.get(label) if isinstance(turns.get(label), dict) else None
        if not t:
            continue
        c = {}
        for d in DIMS:
            try:
                v = int(t.get(d))
                if 1 <= v <= 5:
                    c[d] = v
            except (TypeError, ValueError):
                pass
        vio = t.get('violations') if isinstance(t.get('violations'), list) else []
        c['violations'] = [v for v in vio if v in VIOLATIONS]
        clean[label] = c
    fab = [x for x in (out.get('fabrication') or []) if isinstance(x, dict)]
    rec = [x for x in (out.get('record_errors') or []) if isinstance(x, dict)]
    return {'turns': clean, 'fabrication': fab, 'record_errors': rec, 'note': out.get('note'), 'ok': bool(row.get('ok')) and bool(clean)}


# --------------------------------------------------------------------------- code metrics
def grounded_words(question, episode, upto_index):
    """Content bigrams of the follow-up that come from the elder's words in this question (not from the
    entry question, the reference question or generic vocabulary)."""
    elder = ''.join(m['text'] for m in episode['messages'][:upto_index] if m['role'] == 'elder' and not m.get('scripted'))
    ref = episode['entry'] + (episode['messages'][upto_index].get('engine_question') or '')
    words = bigrams(question) & bigrams(elder)
    return sorted(words - bigrams(ref) - GENERIC)


def sys_turn_cost(m):
    calls = [c for c in m.get('calls') or [] if c.get('kind') in ('judge', 'verify', 'speak')]
    secs = sum(c.get('seconds') or 0 for c in calls)
    toks = sum((c.get('usage') or {}).get('total_tokens', 0) for c in calls)
    return secs, toks, calls


def metrics(sessions, scores=None):
    scores = scores or {}
    eps = [(s, i, ep) for s in sessions for i, ep in enumerate(s['episodes'])]
    agg = defaultdict(list)
    per_turn = []
    fallback = Counter()
    for s, i, ep in eps:
        msgs = ep['messages']
        elder_n = sum(1 for m in msgs if m['role'] == 'elder' and not m.get('scripted'))
        fus = [(j, m) for j, m in enumerate(msgs) if m['role'] == 'system' and m.get('kind') == 'followup']
        agg['elder_turns'].append(elder_n)
        agg['followups'].append(len(fus))
        agg['supplements'].append(sum(1 for m in msgs if m.get('kind') == 'supplement'))
        targets = Counter(m.get('target') for _, m in fus)
        texts = Counter(m.get('question_part') for _, m in fus)
        agg['repeat_target'].append(sum(c - 1 for c in targets.values() if c > 1))
        agg['repeat_text'].append(sum(c - 1 for c in texts.values() if c > 1))
        agg['complete'].append(1 if ep.get('final_decision') == 'ready' else 0)
        agg['limited'].append(1 if ep.get('final_decision') == 'limited' else 0)
        for j, m in fus:
            agg['verbatim'].append(1 if (m.get('question_part') or '').strip() == (m.get('engine_question') or '').strip() else 0)
            agg['grounded_proxy'].append(1 if grounded_words(m.get('question_part') or '', ep, j) else 0)
            if m.get('speaker'):
                fallback['followup'] += 1 if m['speaker'].get('fallback') else 0
                fallback['followup_n'] += 1
        sc = (scores.get(s['session']) or {}).get(str(i)) or {}
        labels = dict((id(m), lab) for lab, m in label_messages(ep))
        for j, m in enumerate(msgs):
            if m['role'] != 'system' or m.get('kind') == 'entry':
                continue
            secs, toks, calls = sys_turn_cost(m)
            row = {'session': s['session'], 'episode': i, 'kind': m.get('kind'), 'len': len(m['text']), 'seconds': secs,
                   'tokens': toks, 'has_model_call': bool(calls)}
            if m.get('kind') == 'close' and m.get('speaker') and not m['speaker'].get('fixed'):
                fallback['close'] += 1 if m['speaker'].get('fallback') else 0
                fallback['close_n'] += 1
            t = (sc.get('turns') or {}).get(labels[id(m)])
            if t:
                row.update({d: t.get(d) for d in DIMS})
                row['violations'] = t.get('violations') or []
            per_turn.append(row)
        if sc:
            agg['fabrication'].append(len(sc.get('fabrication') or []))
            agg['record_errors'].append(len(sc.get('record_errors') or []))

    def mean(xs):
        return round(statistics.mean(xs), 3) if xs else None

    out = {'episodes': len(eps), 'sessions': len(sessions)}
    for k in ('elder_turns', 'followups', 'supplements', 'repeat_target', 'repeat_text', 'complete', 'limited',
              'verbatim', 'grounded_proxy', 'fabrication', 'record_errors'):
        out[k] = mean(agg[k])
    out['followups_total'] = sum(agg['followups'])
    out['fabrication_total'] = sum(agg['fabrication'])
    out['record_errors_total'] = sum(agg['record_errors'])
    out['episodes_scored'] = len(agg['fabrication'])
    sys_turns = [r for r in per_turn]
    model_turns = [r for r in per_turn if r['has_model_call']]
    out['system_turns'] = len(sys_turns)
    out['reply_len_mean'] = mean([r['len'] for r in sys_turns])
    out['latency_mean_s'] = mean([r['seconds'] for r in model_turns])
    out['latency_p90_s'] = round(sorted(r['seconds'] for r in model_turns)[int(0.9 * (len(model_turns) - 1))], 2) if model_turns else None
    out['tokens_per_model_turn'] = mean([r['tokens'] for r in model_turns])
    scored = [r for r in per_turn if r.get('natural') is not None]
    out['scored_turns'] = len(scored)
    for d in DIMS:
        vals = [r[d] for r in scored if r.get(d) is not None]
        out['score_' + d] = mean(vals)
        out['ge4_' + d] = round(sum(v >= 4 for v in vals) / len(vals), 3) if vals else None
    vio = Counter(v for r in scored for v in r.get('violations') or [])
    out['violations'] = dict(vio)
    out['violation_turns'] = sum(1 for r in scored if r.get('violations'))
    out['violation_rate'] = round(out['violation_turns'] / len(scored), 4) if scored else None
    by_kind = defaultdict(list)
    for r in scored:
        by_kind[r['kind']].append(r)
    out['by_kind'] = {k: {'n': len(v), **{d: mean([r[d] for r in v if r.get(d) is not None]) for d in DIMS},
                          'violation_turns': sum(1 for r in v if r.get('violations'))} for k, v in by_kind.items()}
    if fallback['followup_n'] or fallback['close_n']:
        out['speaker_fallback'] = {'followup': f"{fallback['followup']}/{fallback['followup_n']}", 'close': f"{fallback['close']}/{fallback['close_n']}"}
    out['close_reasons'] = dict(Counter(ep['close_reason'] for _, _, ep in eps))
    # transition variety: a close's lead-in (the clause right before the next entry) reused earlier in the same session
    rep = tot = 0
    for s in sessions:
        seen = set()
        for i, ep in enumerate(s['episodes']):
            nxt = s['episodes'][i + 1]['entry'] if i + 1 < len(s['episodes']) else None
            for m in ep['messages']:
                if m['role'] != 'system' or m.get('kind') != 'close' or not nxt or not m['text'].endswith(nxt):
                    continue
                lead = m['text'][:-len(nxt)]
                clause = re.split(r'[。！!，,；;]', lead.rstrip('。！!，,；; '))[-1].strip() if lead.strip() else ''
                key = re.sub(r'[^一-鿿]', '', clause)[:6]
                if not key:
                    continue
                tot += 1
                rep += key in seen
                seen.add(key)
    out['transition_repeat'] = round(rep / tot, 3) if tot else None
    return out, per_turn


def violation_list(sessions, scores):
    rows = []
    for s in sessions:
        for i, ep in enumerate(s['episodes']):
            sc = (scores.get(s['session']) or {}).get(str(i)) or {}
            for label, m in label_messages(ep):
                t = (sc.get('turns') or {}).get(label)
                if t and t.get('violations'):
                    rows.append({'session': s['session'], 'name': s['name'], 'qid': ep['qid'], 'turn': label,
                                 'violations': t['violations'], 'text': m['text']})
            for f in sc.get('fabrication') or []:
                rows.append({'session': s['session'], 'name': s['name'], 'qid': ep['qid'], 'turn': f.get('turn'),
                             'violations': ['elder_fabrication'], 'text': f.get('claim')})
            for f in sc.get('record_errors') or []:
                rows.append({'session': s['session'], 'name': s['name'], 'qid': ep['qid'], 'turn': '记录',
                             'violations': ['record_error'], 'text': f'{f.get("item")}：{f.get("why")}'})
    return rows


def report_lines(name, mode, m, usage, sent, cached, wall):
    L = [f'# {name}（{mode}）', '',
         f"会话 {m['sessions']}，话题 {m['episodes']}，采访者发言 {m['system_turns']}（打分 {m['scored_turns']}）",
         f"每题老人回答轮数 {m['elder_turns']}；每题追问 {m['followups']}（共 {m['followups_total']}）；每题补充邀请 {m['supplements']}",
         f"重复追问（同一目标）每题 {m['repeat_target']}；重复问句 {m['repeat_text']}；题目完成（ready）{m['complete']}，信息有限 {m['limited']}",
         f"追问与合同固定问句逐字相同 {m['verbatim']}；追问引用老人本题原话词语 {m['grounded_proxy']}",
         f"采访者发言平均字数 {m['reply_len_mean']}；有模型调用的轮次延迟均值 {m['latency_mean_s']}s，P90 {m['latency_p90_s']}s；每轮 token {m['tokens_per_model_turn']}",
         '量表均分：' + '，'.join(f"{DIM_ZH[d]} {m['score_' + d]}（≥4 占 {m['ge4_' + d]}）" for d in DIMS),
         f"硬性违规轮次 {m['violation_turns']}/{m['scored_turns']} = {m['violation_rate']}；明细 {m['violations']}",
         f"模拟老人编造 {m['fabrication_total']} 处（{m['episodes_scored']} 个话题）；记录错误 {m['record_errors_total']} 处",
         f"收尾原因 {m['close_reasons']}" + (f"；说话层回退 {m.get('speaker_fallback')}" if m.get('speaker_fallback') else ''),
         '分类型：' + '；'.join(f"{k} n={v['n']} " + ' '.join(f"{d[:3]}={v[d]}" for d in DIMS) + f" 违规={v['violation_turns']}" for k, v in m['by_kind'].items()),
         f"模型调用 新发 {sent} / 缓存 {cached}；用时 {wall}s",
         f"DS token（仅新发）：总 {usage.get('total_tokens', 0)}，输入 {usage.get('prompt_tokens', 0)}（缓存命中 {usage.get('prompt_cache_hit_tokens', 0)}），输出 {usage.get('completion_tokens', 0)}"]
    return L
