#!/usr/bin/env python3
"""Run complete simulated interviews (skeleton + all 72 module questions) in the production V6 flow (v6flow.py).

  python3 tools/interview_eval/simulate/run_full.py --people N-6733a23cd1 --name mb2-full84
  options: --questions SK01,CH01 (only these) --limit K (first K of the plan) --sim-config PATH (persona behaviour
           variant) --offline (caches only) --dry (plumbing, nothing sent) --batch-wait S --ds-timeout S
           --persona queue|openai (who plays the elder; never DeepSeek; see persona_backend.py)

DeepSeek goes through the relay by default; SHINIAN_DS_MODE=direct sends the same requests straight to the API
(common.Relay). Either way every answer is content-cached, so --resume replays all finished work at 0 tokens.

Every question of every person is its own generator (questions are independent in production); elder requests go
to the Haiku persona queue as soon as a question needs one, DeepSeek requests of all questions are pooled into one
relay job at a time, and the speaking layer's "last close" is handed from question to question along the
production order (one chain per person over the skeleton, one over the guided interview).
Results: RUNS/<name>/sessions/<person>.json (questions in plan order), summary.json, report.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import persona_backend  # noqa: E402
import v6flow  # noqa: E402


def dry_content(S, call):
    if call.get('route') == 'persona':
        return json.dumps({'reply': '我记不清了，那时候家里挺苦的。'}, ensure_ascii=False)
    if call['system'] == S.rt.judge_prompt:
        return json.dumps({'control': {'action': 'continue', 'units': []}, 'targets': {}})
    if call['system'] == S.rt.deepen_prompt:
        return json.dumps({'dimension': '场景', 'ack': '', 'question': '那地方当时是什么样子的？'}, ensure_ascii=False)
    if call['system'] == S.rt.speaker_prompt:
        return json.dumps({'ack': '嗯，那时候不容易。', 'question': '那后来呢？'}, ensure_ascii=False)
    return '{}'


class Scheduler:
    def __init__(self, S, relay, persona, name, batch_wait=12.0, offline=False, dry=False):
        self.S, self.relay, self.persona, self.name = S, relay, persona, name
        self.batch_wait, self.offline, self.dry = batch_wait, offline, dry
        self.jobs = 0
        self.ds_thread = self.ds_result = self.ds_error = None

    def _ds_worker(self, job, batch):
        try:
            self.ds_result = self.relay.run_batch(job, batch)
        except Exception as exc:
            self.ds_error = exc

    def run(self, gens, preds, on_done=None):
        """gens: {sid: generator}; preds: {sid: sid of the previous question on its chain, or None}."""
        results, chain_out = {}, {}
        ready, p_wait, d_wait, c_wait, d_since, inflight = {}, {}, {}, {}, {}, {}

        def row_of(c, content):
            try:
                out = json.loads(content)
            except ValueError:
                out = None
            return {'id': c['id'], 'ok': True, 'content': content, 'output': out, 'dry': True}

        def dispatch(sid, calls):
            routes = {c.get('route', 'ds') for c in calls}
            if len(routes) != 1:
                raise RuntimeError('mixed call list')
            route = routes.pop()
            if route == 'chain':
                c_wait[sid] = calls
                return
            if route == 'persona':
                items = []
                for c in calls:
                    if self.dry:
                        items.append((c, None, row_of(c, dry_content(self.S, c))))
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
            if self.dry:
                ready[sid] = [row_of(c, dry_content(self.S, c)) for c in calls]
            elif self.offline or all((common.CACHE / (self.relay.key(c) + '.json')).exists() for c in calls):
                resp = self.relay.run_batch(f'{self.name}-cache', [{**c, 'id': f'{sid}::{c["id"]}'} for c in calls])
                ready[sid] = [resp[f'{sid}::{c["id"]}'] for c in calls]
            else:
                d_wait[sid] = calls
                d_since[sid] = time.time()

        def step(sid, value):
            try:
                calls = gens[sid].send(value)
            except StopIteration as stop:
                record, chain = stop.value
                results[sid], chain_out[sid] = record, chain
                del gens[sid]
                if on_done:
                    on_done(sid, record)
                return
            except Exception:
                traceback.print_exc()
                results[sid] = {'sid': sid, 'error': traceback.format_exc()[-3000:]}
                chain_out[sid] = None
                del gens[sid]
                return
            dispatch(sid, calls)

        for sid in list(gens):
            step(sid, None)
        t0, last_status = time.time(), 0.0
        while gens:
            progressed = False
            for sid in list(ready):
                step(sid, ready.pop(sid))
                progressed = True
            for sid in list(c_wait):
                pred = preds.get(sid)
                if pred is None or pred in chain_out:
                    calls = c_wait.pop(sid)
                    ready[sid] = [{'id': c['id'], 'value': chain_out.get(pred) if pred else None} for c in calls]
                    progressed = True
            for sid in list(p_wait):
                new = [(c, rid, row if row is not None else self.persona.poll(rid)) for c, rid, row in p_wait[sid]]
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
                blocked = all(sid in d_wait or sid in c_wait for sid in gens)
                if blocked or time.time() - min(d_since.values()) >= self.batch_wait:
                    self.jobs += 1
                    inflight = dict(d_wait)
                    d_wait.clear()
                    d_since.clear()
                    batch = [{k: v for k, v in c.items() if k != 'route'} | {'id': f'{sid}::{c["id"]}'}
                             for sid, calls in inflight.items() for c in calls]
                    self.ds_error = None
                    self.ds_thread = threading.Thread(target=self._ds_worker, args=(f'{self.name}-p{self.jobs:03d}', batch), daemon=True)
                    self.ds_thread.start()
                    progressed = True
            if time.time() - last_status >= 60:
                last_status = time.time()
                print(json.dumps({'t': round(time.time() - t0), 'alive': len(gens), 'done': len(results),
                                  'persona_waiting': len(p_wait), 'chain_waiting': len(c_wait), 'ds_waiting': len(d_wait),
                                  'ds_inflight': len(inflight), 'ds_jobs': self.jobs, 'haiku_answered': self.persona.sent,
                                  'haiku_cached': self.persona.cached}), flush=True)
            if not progressed:
                time.sleep(0.5)
        return results


def ingest_staged(relay, name):
    """--resume: answers of this run's relay jobs that arrived after the runner stopped go into the cache, so the
    resumed run does not send them again."""
    n = 0
    for req in sorted(common.OUT_JOBS.glob(name + '-p*.request.json')):
        job = req.name[:-len('.request.json')]
        resp = relay._find_staged(job + '.response.jsonl')
        if resp is None:
            continue
        spec = common.load(req)
        calls = {c['id']: {'system': spec['prompts'][c['system_ref']], 'user': c['user'], 'params': c['params']} for c in spec['calls']}
        for line in resp.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            call = calls.get(row.get('id'))
            if not call or not row.get('ok'):
                continue
            path = common.CACHE / (relay.key(call) + '.json')
            if path.exists():
                continue
            try:
                row['output'], row['parse_error'] = json.loads(row.get('content') or ''), None
            except ValueError:
                row['output'], row['parse_error'] = None, 'JSONDecodeError'
            common.save(path, row)
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--people', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--questions', default='')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--sim-config')
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--batch-wait', type=float, default=12.0)
    ap.add_argument('--ds-timeout', type=float, default=1800.0)
    ap.add_argument('--chains', default='interview', choices=('interview', 'module'),
                    help="interview: production (one speaker_last_close chain over the skeleton, one over all 72 guided "
                         "questions); module: one chain per module, the first question of each module starts without a "
                         "last close (approximation: the six modules as separate sessions; 7 chains run in parallel)")
    ap.add_argument('--persona', default=None, choices=('queue', 'openai'),
                    help='elder backend (default: SHINIAN_PERSONA_BACKEND or queue); cached elder answers are reused either way')
    ap.add_argument('--resume', action='store_true', help='run again into an existing run directory (all answers so far '
                    'come back from the caches); relay job numbers continue after the ones already written')
    a = ap.parse_args()
    run_dir = common.RUNS / a.name
    run_dir.mkdir(parents=True, exist_ok=a.resume)
    S = v6flow.Setup(a.sim_config)
    relay = common.Relay(run_dir, offline=a.offline, wait_seconds=a.ds_timeout, dry=(lambda c: dry_content(S, c)) if a.dry else None)
    persona = persona_backend.make(a.persona)
    people = [p for p in a.people.split(',') if p]
    plan = S.plan()
    if a.questions:
        keep = set(a.questions.split(','))
        plan = [q for q in plan if q in keep]
    if a.limit:
        plan = plan[:a.limit]
    common.save(run_dir / 'plan.json', {'people': people, 'plan': plan, 'bundle': str(v6flow.BUNDLE.relative_to(common.ROOT)),
                                        'pin': v6flow.V6_PIN, 'speaker_config': S.rt.speaker_config.get('version'),
                                        'sim_config': a.sim_config or 'docs/prototypes/full-interview-v4/sim-config.json',
                                        'max_elder': v6flow.MAX_ELDER, 'supplement_cap': v6flow.SUPPLEMENT_CAP, 'chains': a.chains,
                                        'argv': sys.argv})
    if not a.dry:  # every start of the run, with how DeepSeek and the elder were reached (no keys)
        with (run_dir / 'starts.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'argv': sys.argv,
                                'ds_mode': 'direct' if common.DIRECT else 'relay',
                                'ds_base_url': common.DIRECT_BASE_URL if common.DIRECT else None,
                                'persona': type(persona).__name__, 'persona_model': getattr(persona, 'tag', None)
                                or os.environ.get('SHINIAN_WORKER_MODEL') or None}) + '\n')
    gens, preds = {}, {}
    for nid in people:
        last = {'life': None, 'guided': None}
        for qid in plan:
            sid = f'{nid}:{qid}'
            life = qid.startswith('SK')
            gens[sid] = (v6flow.life_question if life else v6flow.guided_question)(S, nid, qid)
            chain = 'life' if life else ('guided' if a.chains == 'interview' else S.module_of(qid))
            preds[sid] = last.get(chain)
            last[chain] = sid
    print(json.dumps({'run': str(run_dir), 'people': people, 'questions': len(plan), 'generators': len(gens)}, ensure_ascii=False), flush=True)
    done_dir = run_dir / 'questions'

    def on_done(sid, record):
        common.save(done_dir / (sid.replace(':', '__') + '.json'), record)

    t0 = time.time()
    sched = Scheduler(S, relay, persona, a.name, a.batch_wait, a.offline, a.dry)
    if a.resume:
        import re as _re
        done = [int(m.group(1)) for f in common.OUT_JOBS.glob(a.name + '-p*.request.json')
                if (m := _re.match(_re.escape(a.name) + r'-p(\d+)', f.name))]
        sched.jobs = max(done, default=0)
        print(json.dumps({'resume_ingested': ingest_staged(relay, a.name)}), flush=True)
    try:
        results = sched.run(gens, preds, on_done)
    except (common.RelayError, persona_backend.PersonaError) as exc:
        print(json.dumps({'stopped': 'provider_stopped_rerun_with_resume', 'error': str(exc), 'tokens_sent': relay.usage.get('total_tokens', 0)}), flush=True)
        sys.exit(3)
    for nid in people:
        recs = [results[f'{nid}:{qid}'] for qid in plan]
        common.save(run_dir / 'sessions' / f'{nid}.json', {'narrator_id': nid, 'name': S.personas.names.get(nid, nid),
                                                         'flow': 'v6', 'plan': plan, 'questions': recs})
    summary = {'elapsed': round(time.time() - t0, 1), 'relay': {'sent': relay.calls_sent, 'cached': relay.calls_cached,
                                                                 'usage': relay.usage, 'jobs': sched.jobs},
               'haiku': {'persona_answered': persona.sent, 'persona_cached': persona.cached},
               'errors': [sid for sid, r in results.items() if r.get('error')]}
    common.save(run_dir / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
