#!/usr/bin/env python3
"""Run simulated full interviews: elder simulator (Claude Haiku via file queue) <-> v3j + speaking layer (DeepSeek
via the relay), then score every question with the rubric (Claude Haiku via file queue).

  python3 tools/interview_eval/simulate/run_sim.py --mode baseline --group iteration_run --name sim-hb1
  python3 tools/interview_eval/simulate/run_sim.py --mode v4 --group iteration_run --name sim-hv4a
  options: --people N (first N of the group) --only NID,NID --questions K (first K of each plan)
           --offline (caches only) --dry (plumbing, nothing sent) --no-score
           --speaker-prompt PATH --policy PATH (speaker-config.json variants)
           --rescore RUN (score the sessions of an earlier run again, no interview calls)

Scheduling: every session advances on its own. Elder requests go to <runs>/persona-queue as
soon as a session needs one (Haiku workers answer them, see WORKER.md); DeepSeek calls of all sessions are
pooled and sent as ONE relay job at a time (flushed when every live session is waiting on DeepSeek, or after
--batch-wait seconds). A finished session's questions go to the scorer queue right away. A relay job with no
answer for --ds-timeout seconds (default 900 = 15 min) stops the run.
Results: RUNS/<name>/sessions/*.json, scores.json, report.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import interview  # noqa: E402
import queue_worker as qw  # noqa: E402
import score as scoring  # noqa: E402


def dry_response(call):
    cid = call['id']
    if cid.endswith('-sim'):
        return json.dumps({'reply': '我记不清了，那时候家里挺苦的。'}, ensure_ascii=False)
    if cid.endswith('-judge'):
        return interview.V3J.DRY_RESPONSE(call)
    if cid.endswith('-speak'):
        return json.dumps({'ack': '嗯，那时候不容易。', 'question': '那后来呢？'}, ensure_ascii=False)
    return '{}'


def dry_row(call):
    content = dry_response(call)
    return {'id': call['id'], 'ok': True, 'content': content, 'output': json.loads(content), 'dry': True}


class Scheduler:
    def __init__(self, relay, persona, name, batch_wait=12.0, offline=False, dry=False, on_done=None):
        self.relay, self.persona, self.name = relay, persona, name
        self.batch_wait, self.offline, self.dry = batch_wait, offline, dry
        self.on_done = on_done
        self.jobs = 0
        self.ds_thread = None
        self.ds_result = None
        self.ds_batch = None
        self.ds_error = None

    def _ds_cached(self, call):
        return (common.CACHE / (self.relay.key(call) + '.json')).exists()

    def _ds_worker(self, job, batch):
        try:
            self.ds_result = self.relay.run_batch(job, batch)
        except Exception as exc:  # RelayError (timeout) or anything else: stop the run
            self.ds_error = exc

    def run(self, gens):
        results = {}
        ready = {}          # sid -> responses to send
        p_wait = {}         # sid -> [(call, rid, row_or_None)]
        d_wait = {}         # sid -> calls
        d_since = {}
        inflight = {}       # sid -> calls in the running relay job

        def dispatch(sid, calls):
            if all(c.get('route') == 'persona' for c in calls):
                items = []
                for c in calls:
                    if self.dry:
                        items.append((c, None, dry_row(c)))
                        continue
                    rid, row = self.persona.submit(c['system'], c['user'], c['output_note'], c['validate'],
                                                   {'run': self.name, 'session': sid, 'call': c['id']})
                    if row is None and self.offline:
                        row = {'id': rid, 'ok': False, 'error': 'offline_haiku_cache_miss'}
                    items.append((c, rid, row))
                if all(r is not None for _, _, r in items):
                    ready[sid] = [{**r, 'id': c['id']} for c, _, r in items]
                else:
                    p_wait[sid] = items
                return
            if any(c.get('route') == 'persona' for c in calls):
                raise RuntimeError('mixed persona / DeepSeek call list')
            if self.dry:
                ready[sid] = [dry_row(c) for c in calls]
            elif self.offline or all(self._ds_cached(c) for c in calls):
                resp = self.relay.run_batch(f'{self.name}-cache', [{**c, 'id': f'{sid}::{c["id"]}'} for c in calls])
                ready[sid] = [resp[f'{sid}::{c["id"]}'] for c in calls]
            else:
                d_wait[sid] = calls
                d_since[sid] = time.time()

        def step(sid, value):
            try:
                calls = gens[sid].send(value)
            except StopIteration as stop:
                results[sid] = stop.value
                del gens[sid]
                if self.on_done:
                    self.on_done(stop.value)
                return
            except Exception:
                traceback.print_exc()
                results[sid] = {'session': sid, 'error': traceback.format_exc()[-2000:], 'episodes': []}
                del gens[sid]
                return
            dispatch(sid, calls)

        for sid in list(gens):
            step(sid, None)
        t0, last_status = time.time(), 0.0
        while gens:
            progressed = False
            for sid in list(ready):
                value = ready.pop(sid)
                step(sid, value)
                progressed = True
            for sid in list(p_wait):
                items = p_wait[sid]
                new = []
                for c, rid, row in items:
                    if row is None:
                        row = self.persona.poll(rid)
                    new.append((c, rid, row))
                p_wait[sid] = new
                if all(r is not None for _, _, r in new):
                    del p_wait[sid]
                    ready[sid] = [{**r, 'id': c['id']} for c, _, r in new]
                    progressed = True
            if self.ds_thread is not None and not self.ds_thread.is_alive():
                self.ds_thread = None
                if self.ds_error is not None:
                    raise self.ds_error
                for sid, calls in inflight.items():
                    ready[sid] = [self.ds_result[f'{sid}::{c["id"]}'] for c in calls]
                inflight = {}
                print(json.dumps({'ds_job_done': self.jobs, 'sent': self.relay.calls_sent, 'cached': self.relay.calls_cached,
                                  'tokens_sent': self.relay.usage.get('total_tokens', 0), 'elapsed': round(time.time() - t0, 1)}), flush=True)
                progressed = True
            if self.ds_thread is None and d_wait and not ready:
                oldest = min(d_since.values())
                blocked_on_ds = all(sid in d_wait for sid in gens)
                if blocked_on_ds or time.time() - oldest >= self.batch_wait:
                    self.jobs += 1
                    inflight = dict(d_wait)
                    d_wait.clear()
                    d_since.clear()
                    batch = [{**c, 'id': f'{sid}::{c["id"]}'} for sid, calls in inflight.items() for c in calls]
                    self.ds_error = None
                    self.ds_thread = threading.Thread(target=self._ds_worker, args=(f'{self.name}-p{self.jobs:02d}', batch), daemon=True)
                    self.ds_thread.start()
                    progressed = True
            if time.time() - last_status >= 60:
                last_status = time.time()
                print(json.dumps({'t': round(time.time() - t0), 'alive': len(gens), 'done': len(results),
                                  'persona_waiting': len(p_wait), 'persona_queue': self.persona.waiting() if not self.dry else 0,
                                  'ds_waiting': len(d_wait), 'ds_inflight': len(inflight), 'ds_jobs': self.jobs,
                                  'haiku_answered': self.persona.sent, 'haiku_cached': self.persona.cached}), flush=True)
            if not progressed:
                time.sleep(0.5)
        return results


class Scorer:
    """Rubric calls (Haiku scorer queue), submitted as soon as a session finishes."""

    def __init__(self, S, prompt, offline=False, dry=False):
        self.S, self.prompt, self.offline, self.dry = S, prompt, offline, dry
        self.q = qw.HaikuQueue('scorer')
        self.items = {}  # call id -> (sid, i, scored, rid, row)

    def add(self, sess):
        for i, _ in enumerate(sess.get('episodes') or []):
            call, scored = scoring.scorer_call(self.S, sess, i, self.prompt)
            if not scored:
                continue
            if self.dry:
                row = {'ok': True, 'output': {'turns': {l: {d: 3 for d in scoring.DIMS} | {'violations': []} for l in scored},
                                              'fabrication': [], 'record_errors': []}}
                rid = None
            else:
                rid, row = self.q.submit(call['system'], call['user'], call['output_note'], call['validate'],
                                         {'session': sess['session'], 'episode': i})
                if row is None and self.offline:
                    row = {'ok': False, 'error': 'offline_haiku_cache_miss'}
            self.items[call['id']] = [sess['session'], i, scored, rid, row]

    def wait(self):
        t0, last = time.time(), 0
        while True:
            missing = 0
            for item in self.items.values():
                if item[4] is None:
                    item[4] = self.q.poll(item[3])
                    missing += item[4] is None
            if not missing:
                break
            if time.time() - last >= 60:
                last = time.time()
                print(json.dumps({'scorer_waiting': missing, 't': round(time.time() - t0)}), flush=True)
            time.sleep(1)
        scores = {}
        for sid, i, scored, rid, row in self.items.values():
            scores.setdefault(sid, {})[str(i)] = {**scoring.parse_scores(row, scored), 'cached': row.get('cached'),
                                                 'seconds': row.get('seconds')}
        return scores


def finish(run_dir, name, mode, S, sessions, scores, relay, persona, scorer_q, wall):
    m, per_turn = scoring.metrics(sessions, scores)
    usage = relay.usage
    vl = scoring.violation_list(sessions, scores)
    common.save(run_dir / 'scores.json', {'run': name, 'mode': mode, 'metrics': m, 'scores': scores, 'per_turn': per_turn,
                                         'relay': {'sent': relay.calls_sent, 'cached': relay.calls_cached, 'usage': usage},
                                         'haiku': {'persona_answered': persona.sent, 'persona_cached': persona.cached,
                                                   'scorer_answered': scorer_q.sent, 'scorer_cached': scorer_q.cached},
                                         'violations': vl})
    lines = scoring.report_lines(name, mode, m, usage, relay.calls_sent, relay.calls_cached, wall)
    lines.append(f"Haiku（子代理队列）：模拟老人 新答 {persona.sent} / 缓存 {persona.cached}；打分 新答 {scorer_q.sent} / 缓存 {scorer_q.cached}")
    if vl:
        lines += ['', '## 硬性违规 / 编造 / 记录错误']
        lines += [f"- {v['name']} {v['qid']} {v['turn']} {','.join(v['violations'])}：{v['text']}" for v in vl]
    errs = [s for s in sessions if s.get('error')]
    if errs:
        lines += ['', '## 会话错误'] + [f"- {s['session']}: {s['error'][-300:]}" for s in errs]
    (run_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('baseline', 'v4'))
    p.add_argument('--group', default='iteration_run')
    p.add_argument('--people', type=int)
    p.add_argument('--only', default='')
    p.add_argument('--questions', type=int)
    p.add_argument('--name', required=True)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--dry', action='store_true')
    p.add_argument('--no-score', action='store_true')
    p.add_argument('--speaker-prompt')
    p.add_argument('--policy')
    p.add_argument('--rescore')
    p.add_argument('--batch-wait', type=float, default=12.0)
    p.add_argument('--ds-timeout', type=float, default=900.0)
    a = p.parse_args()

    run_dir = common.RUNS / a.name
    run_dir.mkdir(parents=True, exist_ok=False)
    S = interview.Setup(a.speaker_prompt, a.policy)
    relay = common.Relay(run_dir, offline=a.offline, wait_seconds=a.ds_timeout,
                         dry=dry_response if a.dry else None)
    persona = qw.HaikuQueue('persona')
    prompt = (interview.V4 / 'scorer-prompt.txt').read_text(encoding='utf-8')
    scorer = Scorer(S, prompt, offline=a.offline, dry=a.dry)
    t0 = time.time()
    if a.rescore:
        src = common.RUNS / a.rescore
        sessions = [common.load(f) for f in sorted((src / 'sessions').glob('*.json'))]
        mode = sessions[0]['mode'] if sessions else a.mode
        common.save(run_dir / 'plan.json', {'rescore_of': a.rescore, 'argv': sys.argv})
        for s in sessions:
            common.save(run_dir / 'sessions' / (s['session'] + '.json'), s)
            scorer.add(s)
        scores = scorer.wait()
        finish(run_dir, a.name, mode, S, sessions, scores, relay, persona, scorer.q, round(time.time() - t0, 1))
        S.ctx.engine.close()
        return
    if not a.mode:
        p.error('--mode is required')
    split = common.load(interview.V4 / 'split.json')
    people = [x for x in a.only.split(',') if x] or split[a.group]
    if a.people:
        people = people[:a.people]
    plans = {nid: split['plans'][nid]['questions'][:a.questions or None] for nid in people}
    common.save(run_dir / 'plan.json', {'mode': a.mode, 'group': a.group, 'people': people, 'plans': plans,
                                        'speaker_prompt': a.speaker_prompt, 'policy': S.policy, 'argv': sys.argv,
                                        'simulator': S.sim_cfg['model'], 'scorer': scoring.SCORER_PARAMS})
    print(json.dumps({'run': str(run_dir), 'mode': a.mode, 'people': [(n, S.personas.names[n]) for n in people]},
                     ensure_ascii=False), flush=True)

    def on_done(sess):
        common.save(run_dir / 'sessions' / (sess['session'] + '.json'), sess)
        if not a.no_score and not sess.get('error'):
            scorer.add(sess)
        print(json.dumps({'session_done': sess['session'], 'error': bool(sess.get('error'))}), flush=True)

    gens = {f's{k:02d}-{nid}': interview.session(S, f's{k:02d}-{nid}', nid, plans[nid], a.mode) for k, nid in enumerate(people)}
    sched = Scheduler(relay, persona, a.name, batch_wait=a.batch_wait, offline=a.offline, dry=a.dry, on_done=on_done)
    try:
        results = sched.run(gens)
    except common.RelayError as exc:
        print(json.dumps({'stopped': 'relay_no_progress', 'error': str(exc), 'tokens_sent': relay.usage.get('total_tokens', 0)}), flush=True)
        S.ctx.engine.close()
        sys.exit(3)
    sessions = [results[sid] for sid in sorted(results)]
    for s in sessions:
        common.save(run_dir / 'sessions' / (s['session'] + '.json'), s)
    print(json.dumps({'interviews_done': len(sessions), 'elapsed': round(time.time() - t0, 1),
                      'tokens_sent': relay.usage.get('total_tokens', 0)}), flush=True)
    scores = {} if a.no_score else scorer.wait()
    finish(run_dir, a.name, a.mode, S, sessions, scores, relay, persona, scorer.q, round(time.time() - t0, 1))
    S.ctx.engine.close()


if __name__ == '__main__':
    main()
