#!/usr/bin/env python3
"""File shuttle between the evaluation harness (cloud) and the DeepSeek relay (D:\\shinian_evl).

The operator loop (a cheap monitoring agent) is:
  python3 shuttle.py wait            -> blocks until ONE action is due, prints it as one JSON line
     {"action":"commit","name":N,"stagedPath":..,"devicePath":..}
         -> device_commit_files([{stagedPath, devicePath}]) ; then: python3 shuttle.py committed N
     {"action":"try_stage","name":N,"paths":[done, response]}
         -> device_stage_files(paths); if BOTH staged ok -> python3 shuttle.py staged N
                                        else            -> python3 shuttle.py notdone N
     {"action":"idle"}  -> nothing to do (call wait again)
     {"action":"stop"}  -> exit the loop
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

STATE = common.RUNS / 'shuttle-state.json'
STOP = common.RUNS / 'SHUTTLE_STOP'


def state():
    if STATE.exists():
        st = common.load(STATE)
        st.setdefault('jobs', {})
        return st
    return {'jobs': {}}


def staged(name):
    return any(True for _ in common.IN_ROOT.rglob(name + '.done.json')) and any(True for _ in common.IN_ROOT.rglob(name + '.response.jsonl'))


def due_action(st):
    now = time.time()
    for req in sorted(common.OUT_JOBS.glob('*.request.json')):
        name = req.name[:-len('.request.json')]
        job = st['jobs'].get(name)
        if job and job.get('staged'):
            continue
        if staged(name):
            continue
        if not job:
            return {'action': 'commit', 'name': name, 'stagedPath': str(req),
                    'devicePath': common.DEVICE_JOBS + '\\' + req.name}
        if now >= job['next_check']:
            dev = common.DEVICE_JOBS + '\\' + name
            return {'action': 'try_stage', 'name': name, 'paths': [dev + '.done.json', dev + '.response.jsonl']}
    return None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'wait'
    st = state()
    if cmd == 'committed':
        name = sys.argv[2]
        req = common.OUT_JOBS / (name + '.request.json')
        calls = len(common.load(req).get('calls', [])) if req.exists() else 16
        st['jobs'][name] = {'committed_at': time.time(), 'calls': calls, 'checks': 0,
                            'next_check': time.time() + 6 + 10 * math.ceil(calls / 16)}
        common.save(STATE, st)
        print('ok')
        return
    if cmd == 'notdone':
        job = st['jobs'][sys.argv[2]]
        job['checks'] += 1
        job['next_check'] = time.time() + min(60, 8 + 4 * job['checks'])
        common.save(STATE, st)
        print('ok')
        return
    if cmd == 'staged':
        st['jobs'].setdefault(sys.argv[2], {})['staged'] = True
        common.save(STATE, st)
        print('ok')
        return
    if cmd == 'wait':
        timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 600
        deadline = time.time() + timeout
        while time.time() < deadline:
            if STOP.exists():
                print(json.dumps({'action': 'stop'}))
                return
            action = due_action(state())
            if action:
                print(json.dumps(action, ensure_ascii=False))
                return
            time.sleep(2)
        print(json.dumps({'action': 'idle'}))
        return
    raise SystemExit('unknown command')


if __name__ == '__main__':
    main()
