#!/usr/bin/env python3
"""DeepSeek local relay for the Shinian interview evaluation.

Runs on your own computer. It ONLY does one thing: it watches the `jobs`
folder next to this file, sends the chat requests described in each
`*.request.json` to https://api.deepseek.com, and writes the answers to a
matching `*.response.jsonl`. It never executes code from the job files and
never sends your key anywhere except api.deepseek.com.

Key lookup order: env DEEPSEEK_API_KEY, then deepseek_key.txt in this folder
(create/replace it with import_key.py).

Start: double-click start_relay.bat (or run: py -3 ds_relay.py). Leave the
window open while tests run; Ctrl+C stops it.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import random
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = 'https://api.deepseek.com'
HERE = Path(__file__).resolve().parent
JOBS = HERE / 'jobs'
STATUS = HERE / 'relay_status.json'
LOG = HERE / 'relay.log'
VERSION = 'ds-relay-2'
POLL_SECONDS = 2.0
MAX_CONCURRENCY = 24
DEFAULTS = {'model': 'deepseek-v4-pro', 'max_tokens': 8192, 'temperature': 0.0,
            'thinking': 'disabled', 'json_mode': True, 'timeout': 180}

try:
    sys.stdout.reconfigure(errors='replace')  # Windows consoles
except Exception:
    pass

_log_lock = threading.Lock()
_state = {'version': VERSION, 'started_at': None, 'heartbeat': None, 'jobs_done': 0,
          'calls_done': 0, 'calls_failed': 0, 'current_job': None, 'key_check': None,
          'models': None, 'last_error': None}


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def log(msg):
    line = f'[{now_iso()}] {msg}'
    with _log_lock:
        print(line, flush=True)
        try:
            with LOG.open('a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass


def write_json_atomic(path: Path, obj):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, path)


def write_status():
    _state['heartbeat'] = now_iso()
    try:
        write_json_atomic(STATUS, _state)
    except OSError:
        pass


def load_key():
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        path = HERE / 'deepseek_key.txt'
        if path.exists():
            key = path.read_text(encoding='utf-8').strip()
    if not key:
        raise SystemExit('No API key: run import_key.py first (or set DEEPSEEK_API_KEY).')
    return key


def http(method, url, key, body=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + key,
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def redact(text, key):
    return str(text).replace(key, '[REDACTED]')


def check_key(key):
    try:
        models = http('GET', BASE_URL + '/models', key, timeout=30)
        ids = sorted(m.get('id') for m in models.get('data', []))
        _state['key_check'] = 'ok'
        _state['models'] = ids
        log('Key OK. Models available: ' + ', '.join(ids))
    except urllib.error.HTTPError as e:
        _state['key_check'] = f'http_{e.code}'
        log(f'Key check failed: HTTP {e.code}')
    except Exception as e:  # network problems
        _state['key_check'] = 'error:' + type(e).__name__
        log('Key check failed: ' + redact(repr(e), key))
    write_status()


def one_call(call, prompts, defaults, key):
    params = {**DEFAULTS, **defaults, **(call.get('params') or {})}
    system = call.get('system')
    if system is None and call.get('system_ref') is not None:
        system = prompts[call['system_ref']]
    user = call.get('user')
    if not isinstance(user, str):
        user = json.dumps(user, ensure_ascii=False)
    messages = ([{'role': 'system', 'content': system}] if system else []) + [{'role': 'user', 'content': user}]
    body = {'model': params['model'], 'messages': messages, 'max_tokens': int(params['max_tokens'])}
    if params.get('temperature') is not None:
        body['temperature'] = params['temperature']
    if params.get('json_mode'):
        body['response_format'] = {'type': 'json_object'}
    if params.get('thinking') == 'disabled':
        body['thinking'] = {'type': 'disabled'}
    elif params.get('thinking') == 'enabled':
        body['thinking'] = {'type': 'enabled'}
    out = {'id': call['id'], 'model_requested': body['model']}
    attempts = 0
    started = time.monotonic()
    while True:
        attempts += 1
        try:
            raw = http('POST', BASE_URL + '/chat/completions', key, body, timeout=params['timeout'])
            choice = raw['choices'][0]
            content = choice['message'].get('content') or ''
            out.update(ok=True, content=content, finish_reason=choice.get('finish_reason'),
                       usage=raw.get('usage'), response_model=raw.get('model'),
                       thinking_sent=body.get('thinking'))
            break
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = redact(e.read().decode('utf-8', 'replace')[:600], key)
            except Exception:
                pass
            retryable = e.code in (408, 409, 425, 429, 500, 502, 503, 504)
            if retryable and attempts < 5:
                time.sleep(min(30, 2 ** attempts + random.random()))
                continue
            out.update(ok=False, http_status=e.code, error='HTTPError', error_detail=detail,
                       fatal=e.code in (401, 402, 403))
            break
        except Exception as e:
            if attempts < 4:
                time.sleep(min(20, 2 ** attempts + random.random()))
                continue
            out.update(ok=False, error=type(e).__name__, error_detail=redact(repr(e), key)[:400])
            break
    out['attempts'] = attempts
    out['seconds'] = round(time.monotonic() - started, 3)
    return out


def process(request_path: Path, key):
    name = request_path.name[:-len('.request.json')]
    response_path = JOBS / (name + '.response.jsonl')
    done_path = JOBS / (name + '.done.json')
    try:
        job = json.loads(request_path.read_text(encoding='utf-8'))
    except Exception as e:
        write_json_atomic(done_path, {'job': name, 'ok': False, 'error': 'unreadable_request:' + type(e).__name__})
        return
    calls = job.get('calls') or []
    prompts = job.get('prompts') or {}
    defaults = job.get('defaults') or {}
    concurrency = max(1, min(MAX_CONCURRENCY, int(job.get('concurrency', 8))))
    _state['current_job'] = {'name': name, 'calls': len(calls), 'finished': 0, 'started': now_iso()}
    write_status()
    log(f'Job {name}: {len(calls)} calls, concurrency {concurrency}')
    tmp = response_path.with_name(response_path.name + '.tmp')
    t0 = time.monotonic()
    fatal = False
    results = 0
    failed = 0
    with tmp.open('w', encoding='utf-8') as out, concurrent.futures.ThreadPoolExecutor(concurrency) as pool:
        futures = [pool.submit(one_call, c, prompts, defaults, key) for c in calls]
        for fut in concurrent.futures.as_completed(futures):
            try:
                row = fut.result()
            except Exception as e:
                row = {'id': None, 'ok': False, 'error': 'relay_exception', 'error_detail': redact(repr(e), key)[:400]}
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            out.flush()
            results += 1
            failed += not row.get('ok')
            fatal = fatal or bool(row.get('fatal'))
            _state['current_job']['finished'] = results
            _state['calls_done'] += 1
            _state['calls_failed'] += not row.get('ok')
            if results % 5 == 0 or results == len(calls):
                write_status()
                log(f'  {name}: {results}/{len(calls)} done ({failed} failed)')
    os.replace(tmp, response_path)
    write_json_atomic(done_path, {'job': name, 'ok': True, 'calls': len(calls), 'failed': failed,
                                  'fatal_provider_error': fatal, 'seconds': round(time.monotonic() - t0, 1),
                                  'finished_at': now_iso(), 'relay_version': VERSION})
    _state['jobs_done'] += 1
    _state['current_job'] = None
    write_status()
    log(f'Job {name} finished in {time.monotonic() - t0:.1f}s ({failed} failed)')


def main():
    JOBS.mkdir(exist_ok=True)
    key = load_key()
    _state['started_at'] = now_iso()
    log(f'{VERSION} started in {HERE}')
    check_key(key)
    seen_bad = set()
    last_beat = 0.0
    while True:
        try:
            pending = sorted(p for p in JOBS.glob('*.request.json')
                             if not (JOBS / (p.name[:-len('.request.json')] + '.done.json')).exists())
            for p in pending:
                if p in seen_bad:
                    continue
                try:
                    process(p, key)
                except Exception as e:
                    seen_bad.add(p)
                    _state['last_error'] = redact(traceback.format_exc()[-800:], key)
                    log('Job failed: ' + redact(repr(e), key))
            if time.monotonic() - last_beat > 10:
                write_status()
                last_beat = time.monotonic()
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log('Stopped by user.')
            break


if __name__ == '__main__':
    main()
