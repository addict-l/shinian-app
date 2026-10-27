#!/usr/bin/env python3
"""0-token alignment checks of the V6 production-flow simulator (v6flow.py).

  python3 tools/interview_eval/simulate/v6_replay.py st7 [RUN]     # default RUN st7-b5f-it
  python3 tools/interview_eval/simulate/v6_replay.py self RUN      # a run_full.py run, replayed from its caches
  python3 tools/interview_eval/simulate/v6_replay.py cause         # V6 literal_cause_span: pipelines/v3j.py port vs backend
  python3 tools/interview_eval/simulate/v6_replay.py cache RUN [--keys OUT.json]   # 0-token check of a (partial) run

st7: the st7-b5f-it simulated interviews (the old simulator, v5f bundle) were replayed through the backend flow with 0
differences (backend tests/test_interview_v5f_sim_replay.py). Here the same recorded elder answers are fed to
v6flow configured with that v5f bundle, the next entry, the "last close" and the earlier closes patched in as
that test does. Every DeepSeek request v6flow builds must be a cache hit (= the same system, user and parameters
as recorded), and per answer the judgment, the ending-rule action, the follow-up / detail-question / transition
texts and the deepen log must equal the recorded ones. The draft step (v6flow keeps it, the old simulator moved on
to the next entry) is compared by its speaking-layer input, and its text is listed as a designed difference, as in
the backend test.

self: a finished run_full.py run is run again from the relay and Haiku caches with the recorded answers; every
request must be a cache hit and every question record must come out the same (determinism of the run).

cache: a run_full.py run -- finished or stopped part-way -- driven again exactly as run_full.py drives it (same plan,
sim config and chains from its plan.json), with the elder answered only from the persona cache and DeepSeek only
from the relay cache; network access is blocked for the whole check. Every question the run saved must come out
identical with 0 cache misses (DeepSeek and elder); for the unfinished ones it reports how far the caches carry
them (the next request is what a resumed run sends first). --keys writes the cache keys used (for packaging).

cause: the backend's literal-cause unit cases (tests/test_interview_causal_evidence.py) through the eval pipeline
pipelines/v3j.py with ctx.literal_cause_span (and off), against the backend V3jPipeline on the V6 bundle.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import v6flow  # noqa: E402

V5F_BUNDLE = v6flow.BACKEND / 'app/ai/interview_runtime_v3j_v5f'


def cached_row(call):
    path = common.CACHE / (common.Relay.key(call) + '.json')
    if path.exists():
        return {**common.load(path), 'cached': True}, True
    return {'id': call['id'], 'ok': False, 'error': 'offline_cache_miss'}, False


def drive(gen, answers, chain_value, misses, extra_answer='没有了'):
    """Run one question generator synchronously: persona calls get the recorded answers in order (then
    ``extra_answer``), DeepSeek calls the cache, chain requests ``chain_value``."""
    fed = 0
    value = None
    while True:
        try:
            calls = gen.send(value)
        except StopIteration as stop:
            return stop.value, fed
        route = calls[0].get('route', 'ds')
        if route == 'chain':
            value = [{'id': c['id'], 'value': chain_value} for c in calls]
        elif route == 'persona':
            text = answers[fed] if fed < len(answers) else extra_answer
            fed += 1
            value = [{'id': c['id'], 'ok': True, 'output': {'reply': text}, 'content': json.dumps({'reply': text}, ensure_ascii=False)}
                     for c in calls]
        else:
            rows = []
            for c in calls:
                row, hit = cached_row(c)
                if not hit and fed <= len(answers):
                    misses.append({'id': c['id'], 'system': c['system'][:40], 'user': c['user'][-300:]})
                rows.append(row)
            value = rows


def summary(S, result):
    """The old simulator's judge_summary of a result (as backend tests/test_interview_v5f_sim_replay.summary)."""
    return {'decision': result.get('decision'), 'target': result.get('target'), 'question': result.get('question'),
            'effective': {k: v for k, v in (result.get('effective') or {}).items() if S.rt.F[k]['requirement'] != 'optional'},
            'active': result.get('active'), 'fields': S.speaker.recorded_fields(S.rt, result), 'errors': result.get('errors')}


def comparable(log):
    return [(e.get('k'), e['decision'], e['reason'], e.get('question') or '', tuple(e.get('errors') or ()))
            for e in log if not str(e['reason']).startswith(('not_done_declined', 'not_done_deferred', 'not_done_rest'))
            and e['reason'] not in ('answer_skip_control',)]


def st7(run='st7-b5f-it'):
    S = v6flow.Setup(bundle=V5F_BUNDLE, pin=sha256((V5F_BUNDLE / 'manifest.json').read_bytes()).hexdigest())
    stats = dict.fromkeys(('episodes', 'answers', 'judged', 'judge_equal', 'action_equal', 'deepen_answers', 'deepens',
                           'deepen_equal', 'deepen_input_equal', 'followups', 'followup_equal', 'speaker_input_equal',
                           'speaker_inputs', 'transitions', 'transition_equal', 'draft', 'draft_input_equal', 'rest',
                           'logs_equal'), 0)
    failures, misses, drafts = [], [], []
    for path in sorted((common.RUNS / run / 'sessions').glob('*.json')):
        sess = common.load(path)
        plan = sess['questions']
        prev_close, seen = None, []
        for ei, ep in enumerate(sess['episodes']):
            qid = ep['qid']
            stats['episodes'] += 1
            nxt = S.rt.questions[plan[ei + 1]]['main_question'] if ei + 1 < len(plan) else None
            life = qid.startswith('SK')
            override = {'next': nxt if life else (nxt, False), 'seen': list(seen), 'keep': True}
            elders = [m for m in ep['messages'] if m['role'] == 'elder' and not m.get('scripted')]
            gen = (v6flow.life_question if life else v6flow.guided_question)(S, sess['narrator_id'], qid, override)
            (record, _), _ = drive(gen, [m['text'] for m in elders], prev_close, misses)
            mine_elders = [m for m in record['messages'] if m['role'] == 'elder' and not m.get('scripted')]
            steps = {s['answer']: s for s in record['steps'] if 'answer' in s}
            msgs = ep['messages']
            for j, m in enumerate(msgs):
                if m['role'] != 'elder' or m.get('scripted'):
                    continue
                i = elders.index(m)
                where = f'{sess["name"]} {qid} #{j}'
                stats['answers'] += 1
                reply_sim = next(x for x in msgs[j + 1:] if x['role'] == 'system')
                step = steps[mine_elders[i]['id']]
                mine_k = record['messages'].index(mine_elders[i])
                mine_reply = next(x for x in record['messages'][mine_k + 1:] if x['role'] == 'system')
                if m.get('deepen_answer'):
                    stats['deepen_answers'] += 1
                    if not step.get('deepen_answer'):
                        failures.append(where + ' a deepen answer was judged')
                elif m.get('judge') is not None:
                    stats['judged'] += 1
                    same = summary(S, step['result']) == m['judge']
                    stats['judge_equal'] += same
                    if not same:
                        failures.append(where + ' judge differs')
                    act = [step['rule']['action'], step['rule']['reason']]
                    stats['action_equal'] += act == m['v4_action']
                    if act != m['v4_action']:
                        failures.append(where + f' action {act} vs {m["v4_action"]}')
                kind = reply_sim['kind']
                sim_in = (reply_sim.get('speaker') or {}).get('input')
                if kind == 'followup':
                    stats['followups'] += 1
                    stats['followup_equal'] += mine_reply['text'] == reply_sim['text']
                    if mine_reply['text'] != reply_sim['text']:
                        failures.append(where + f' follow-up {mine_reply["text"]!r} vs {reply_sim["text"]!r}')
                    stats['speaker_inputs'] += 1
                    stats['speaker_input_equal'] += (step.get('spoken') or {}).get('input') == sim_in
                elif kind == 'deepen':
                    stats['deepens'] += 1
                    stats['deepen_equal'] += mine_reply['text'] == reply_sim['text']
                    stats['deepen_input_equal'] += (step.get('deepen') or {}).get('input') == sim_in
                    if mine_reply['text'] != reply_sim['text']:
                        failures.append(where + f' deepen {mine_reply["text"]!r} vs {reply_sim["text"]!r}')
                elif kind == 'close' and reply_sim.get('reason') in ('declined', 'deferred'):
                    stats['transitions'] += 1
                    stats['transition_equal'] += mine_reply['text'] == reply_sim['text']
                    if mine_reply['text'] != reply_sim['text']:
                        failures.append(where + f' transition {mine_reply["text"]!r} vs {reply_sim["text"]!r}')
                elif kind == 'close' and reply_sim.get('reason') != 'rest':
                    if life:  # the skeleton has no draft step: the close is compared as text
                        stats['transitions'] += 1
                        stats['transition_equal'] += mine_reply['text'] == reply_sim['text']
                        if mine_reply['text'] != reply_sim['text']:
                            failures.append(where + f' skeleton close {mine_reply["text"]!r} vs {reply_sim["text"]!r}')
                    else:
                        stats['draft'] += 1
                        same = (step.get('spoken') or {}).get('input') == sim_in
                        stats['draft_input_equal'] += same
                        if not same:
                            failures.append(where + ' draft-step speaker input differs')
                        if not mine_reply['text'].endswith(v6flow.DRAFT_TEXT):
                            failures.append(where + ' draft step lost')
                        drafts.append(f'{where} [{reply_sim.get("reason")}] 模拟：{reply_sim["text"]}\n    V6流程（v5f包）：{mine_reply["text"]}')
                else:
                    stats['rest'] += 1
                if kind in ('close', 'pause'):
                    break
            same_log = comparable((ep.get('deepen') or {}).get('log') or []) == comparable((record.get('deepen') or {}).get('log') or [])
            stats['logs_equal'] += same_log
            if not same_log:
                failures.append(f'{sess["name"]} {qid} deepen log differs')
            close = next((x for x in reversed(ep['messages']) if x['role'] == 'system' and x.get('kind') == 'close'), None)
            if close and not (close.get('speaker') or {}).get('fixed'):
                prev_close = close['text']
                seen.append(close['text'])
    out = {'run': run, 'stats': stats, 'cache_misses': len(misses), 'failures': failures, 'designed_draft_differences': drafts}
    print(json.dumps({k: v for k, v in out.items() if k != 'designed_draft_differences'}, ensure_ascii=False, indent=1))
    print('\n'.join(drafts[:6]))
    if misses:
        print(json.dumps(misses[:5], ensure_ascii=False, indent=1))
    return out


def self_replay(run):
    """A run_full.py run again from the caches with its recorded answers: same requests (cache hits), same records."""
    S = v6flow.Setup(common.load(common.RUNS / run / 'plan.json').get('sim_config') if False else None)
    failures, misses, n = [], [], 0
    for path in sorted((common.RUNS / run / 'sessions').glob('*.json')):
        sess = common.load(path)
        for rec in sess['questions']:
            if rec.get('error'):
                continue
            n += 1
            answers = [m['text'] for m in rec['messages'] if m['role'] == 'elder' and not m.get('scripted')]
            gen = (v6flow.life_question if rec['qid'].startswith('SK') else v6flow.guided_question)(S, sess['narrator_id'], rec['qid'])
            (mine, _), fed = drive(gen, answers, rec.get('chain_in'), misses, extra_answer=None)
            strip = lambda r: json.dumps([(m['role'], m['text'], m.get('kind')) for m in r['messages']], ensure_ascii=False)  # noqa: E731
            if strip(mine) != strip(rec) or mine['status'] != rec['status'] or fed != len(answers):
                failures.append(rec['qid'])
    out = {'run': run, 'questions': n, 'cache_misses': len(misses), 'differences': failures}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def _no_network():
    import socket

    def refuse(*args, **kwargs):
        raise OSError('network access is blocked during the 0-token cache check')
    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    socket.getaddrinfo = refuse


def _norm(obj):
    """A record without the per-run bookkeeping (cache flags, timings, token usage: a request sent twice keeps the
    content of its answer but the cache keeps the usage of the last sending)."""
    if isinstance(obj, dict):
        return {k: _norm(v) for k, v in obj.items() if k not in ('cached', 'seconds', 'usage')}
    if isinstance(obj, list):
        return [_norm(v) for v in obj]
    return obj


def cache_replay(run, keys_out=None):
    """0-token replay of a (partial) run_full.py run from the DeepSeek and persona caches (see the module doc)."""
    import queue_worker as qw
    _no_network()
    run_dir = common.RUNS / run
    plan = common.load(run_dir / 'plan.json')
    sim = plan.get('sim_config')
    sim = str(common.ROOT / sim) if sim and not Path(sim).is_absolute() else sim
    S = v6flow.Setup(sim)
    if plan.get('pin') != v6flow.V6_PIN or plan.get('speaker_config') != S.rt.speaker_config.get('version'):
        raise SystemExit('the run was made with another bundle / speaker config')
    persona_cache = qw.HAIKU_CACHE / 'persona'
    used = {'deepseek': set(), 'persona': set()}
    out = {'run': run, 'questions_planned': 0, 'saved_records': 0, 'replayed_equal': 0, 'cache_misses_in_saved': 0,
           'differences': [], 'stale_saved': {}, 'complete_not_saved': [], 'frontier': {}, 'hits': {'deepseek': 0, 'persona': 0},
           'params': {}, 'persona_models': {}}
    for nid in plan['people']:
        chain_out, last = {}, {'life': None, 'guided': None}
        for qid in plan['plan']:
            out['questions_planned'] += 1
            sid = f'{nid}:{qid}'
            life = qid.startswith('SK')
            chain = 'life' if life else ('guided' if plan.get('chains', 'interview') == 'interview' else S.module_of(qid))
            pred, last[chain] = last.get(chain), sid
            path = run_dir / 'questions' / (sid.replace(':', '__') + '.json')
            rec = common.load(path) if path.exists() else None
            if rec is not None:
                out['saved_records'] += 1
            gen = (v6flow.life_question if life else v6flow.guided_question)(S, nid, qid)
            value, stop, result, chain_seen = None, None, None, False
            n_elder = n_ds = 0
            while stop is None:
                try:
                    calls = gen.send(value)
                except StopIteration as fin:
                    result = fin.value
                    break
                route = calls[0].get('route', 'ds')
                rows = []
                for c in calls:
                    if route == 'chain':
                        if pred is not None and pred not in chain_out:
                            stop = 'waits for the last close of ' + pred
                            break
                        rows.append({'id': c['id'], 'value': chain_out.get(pred) if pred else None})
                        chain_seen = True
                    elif route == 'persona':
                        key = qw.request_key('persona', c['system'], c['user'], {'note': c['output_note'], 'validate': c['validate']})
                        hit = persona_cache / f'{key}.json'
                        if not hit.exists():
                            stop = 'elder answer %d (persona request p-%s)' % (n_elder + 1, key[:16])
                            break
                        row = {**common.load(hit), 'cached': True}
                        used['persona'].add(key)
                        out['hits']['persona'] += 1
                        model = row.get('model_requested') or qw.MODEL_TAG
                        out['persona_models'][model] = out['persona_models'].get(model, 0) + 1
                        n_elder += 1
                        rows.append({**row, 'id': c['id']})
                    else:
                        key = common.Relay.key(c)
                        hit = common.CACHE / f'{key}.json'
                        if not hit.exists():
                            stop = 'DeepSeek call %d (%s)' % (n_ds + 1, c['id'])
                            break
                        used['deepseek'].add(key)
                        out['hits']['deepseek'] += 1
                        p = c['params']
                        tag = '%s/thinking=%s' % (p.get('model'), p.get('thinking'))
                        out['params'][tag] = out['params'].get(tag, 0) + 1
                        n_ds += 1
                        rows.append({**common.load(hit), 'cached': True, 'id': f'{sid}::{c["id"]}'})  # as run_full's batches
                value = rows
            # a saved record whose "last close" input is not what its predecessor now hands on was made in an earlier
            # start of the run under another chain layout (--chains): a resumed run redoes it (only the calls after
            # the changed input are new) and overwrites the file
            now_in = chain_out.get(pred) if pred else None
            stale = rec is not None and (pred is not None and pred not in chain_out or rec.get('chain_in') != now_in)
            if result is not None:
                record, chain_value = result
                chain_out[sid] = chain_value
                if rec is None:
                    out['complete_not_saved'].append(qid)
                elif _norm(record) == _norm(rec):
                    out['replayed_equal'] += 1
                elif stale:
                    out['stale_saved'][qid] = 'chain_in %r, predecessor now hands on %r' % (rec.get('chain_in'), now_in)
                else:
                    out['differences'].append(qid)
            else:
                if rec is not None and stale:
                    out['stale_saved'][qid] = 'chain_in %r, predecessor now hands on %r; stops at %s' % (
                        rec.get('chain_in'), now_in if pred in chain_out or pred is None else '(unfinished)', stop)
                elif rec is not None:
                    out['cache_misses_in_saved'] += 1
                    out['differences'].append(qid + ' (' + stop + ')')
                if rec is None or stale:
                    out['frontier'][qid] = {'elder_answers_cached': n_elder, 'deepseek_cached': n_ds, 'next': stop}
    out['finished_now'] = out['replayed_equal']
    out['ok'] = out['cache_misses_in_saved'] == 0 and not out['differences'] and \
        out['replayed_equal'] + len(out['stale_saved']) == out['saved_records']
    out['keys'] = {k: len(v) for k, v in used.items()}
    if keys_out:
        common.save(keys_out, {k: sorted(v) for k, v in used.items()})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


CAUSE_OK = [('因家穷才去粮站搬货。', '家穷'), ('因为家里穷，所以我去粮站搬货。', '家里穷'), ('我当时因为家里穷才去粮站搬货。', '家里穷'),
            ('当时我因为家穷才去粮站搬货。', '家穷'), ('因为家里穷，所以我去了粮站搬货。', '家里穷'), ('由于家里穷，我只好去粮站搬货。', '家里穷'),
            ('我去粮站搬货，是因为家里穷。', '家里穷'), ('我最初去粮站搬货是因为家穷。', '家穷'), ('因父亲生病才去粮站搬货。', '父亲生病'),
            ('因家里没钱才去粮站搬货。', '家里没钱'), ('因家窮才去糧站搬貨。', '家窮')]
CAUSE_NO = ['我去粮站搬货。', '家里穷，我去粮站搬货。', '后来因厂里倒闭才去粮站搬货。', '不是因为家穷才去粮站搬货。', '因家穷才没去粮站搬货。',
            '因家穷才去纺织厂。', '因为家里穷，所以他去粮站搬货。', '我后来去粮站搬货，是因为家里穷。', '我没有去粮站搬货，是因为家里穷。',
            '因家穷才想去粮站搬货。', '因为不是家穷才去粮站搬货。', '因什么原因才去粮站搬货。', '因家里穷才让弟弟去粮站搬货。',
            '因为家里穷，所以老李去粮站搬货。', '因家里穷才我让弟弟去粮站搬货。', '因家里穷才去看弟弟在粮站搬货。', '老李去粮站搬货是因为家里穷。']


def cause():
    """The backend unit cases of S01 through both implementations (no provider call: the judge output is a fixture)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('v3j_cause', common.ROOT / 'tools/interview_eval/pipelines/v3j.py')
    V3J = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V3J)
    S = v6flow.Setup()
    ctx = V3J.setup()
    rows = []

    def fixture(word, subject='self'):
        targets = {fid: {'best': 'S1.1', 'core': ['S1.1'], 'units': ['S1.1'], 'kind': 'content', 'concept': 'same', 'subject': subject}
                   for fid in ('WK01-E1', 'WK01-E2')}
        targets['WK01-E2']['link_word'] = word
        return {'control': {'action': 'continue', 'units': []}, 'targets': targets}

    def backend(text, word):
        pipe = S.cij.V3jPipeline(S.rt, None)
        out = fixture(word)
        pipe._call = lambda system, user, params, timeout: {'ok': True, 'output': {'checks': {}}} if system == S.rt.verify_prompt \
            else {'ok': True, 'output': deepcopy(out)}
        src = [{'id': 'S1', 'text': text, 'speaker': 'narrator', 'question_id': 'WK01', 'question': '您最初做的是什么工作？'}]
        return pipe.run('WK01', src, {'previous_fields': {}, 'ask_counts': {}})['result']

    def evalpipe(text, word, enabled):
        ctx.literal_cause_span = enabled
        case = {'question_id': 'WK01', 'turns': [{'source': {'id': 'S1', 'text': text, 'question': '您最初做的是什么工作？'}}]}
        payload = ctx.engine.payload_for(case, 0, {}, {})
        gen = V3J.run_checkpoint(payload, ctx)
        calls = next(gen)
        try:
            while True:
                c = calls[0]
                out = {'checks': {}} if c['system'] == ctx.verify_prompt else fixture(word)
                calls = gen.send([{'ok': True, 'output': deepcopy(out), 'content': json.dumps(out)}])
        except StopIteration as stop:
            return stop.value[0]

    for text, expected in CAUSE_OK + [(t, None) for t in CAUSE_NO]:
        word = '糧站搬貨' if '糧' in text else '粮站搬货'
        b = backend(text, word)
        e = evalpipe(text, word, True)
        off = evalpipe(text, word, False)
        bv = (b['effective'].get('WK01-E2'), (b['fields'].get('WK01-E2') or {}).get('value'))
        ev = (e['effective'].get('WK01-E2'), (e['fields'].get('WK01-E2') or {}).get('value'))
        rows.append({'text': text, 'backend': bv, 'eval': ev, 'eval_off': off['effective'].get('WK01-E2'),
                     'expected': expected, 'same': bv == ev})
    ctx.engine.close()
    bad = [r for r in rows if not r['same'] or (r['expected'] and r['backend'] != ('known', r['expected']))
           or (not r['expected'] and r['backend'][0] == 'known')]
    print(json.dumps({'cases': len(rows), 'equal': sum(r['same'] for r in rows), 'unexpected': bad,
                      'off_known': sum(r['eval_off'] == 'known' for r in rows)}, ensure_ascii=False, indent=1))
    return rows


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'st7'
    if what == 'st7':
        st7(*sys.argv[2:3])
    elif what == 'self':
        self_replay(sys.argv[2])
    elif what == 'cause':
        cause()
    elif what == 'cache':
        args = sys.argv[3:]
        res = cache_replay(sys.argv[2], args[args.index('--keys') + 1] if '--keys' in args else None)
        sys.exit(0 if res['ok'] else 1)
