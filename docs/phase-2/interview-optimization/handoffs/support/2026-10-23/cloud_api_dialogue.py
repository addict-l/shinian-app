"""Live HTTPS verification, without server imports, mocks, SQL or model SDKs.

Create one independent test family and four test members. All progress is made
through the same authenticated API used by the app. Credentials, HTTP journals
and complete API snapshots stay in --private-dir; public transcripts contain
only dialogue, provenance and safe model audit records. This script does not
generate or save memories and never opens existing family records.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'interview-dialogue-20261023'
PURPOSE = 'interview-cloud-validation-20261023'
COMMIT = '770f8419c76e1edc7205c76e88c97100dbdf17b1'
SCENARIOS = ('skeleton', 'childhood', 'work', 'unmarried')


def save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o600)
    os.replace(tmp, path)


def read(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else deepcopy(default)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def log(**items):
    print(json.dumps(items, ensure_ascii=False), flush=True)


class APIError(RuntimeError):
    def __init__(self, status, path, detail):
        self.status, self.path, self.detail = status, path, detail
        super().__init__(f'HTTPS API error {status} at {path}')


class Client:
    def __init__(self, base_url, private_dir):
        if not base_url.startswith('https://'):
            raise ValueError('A public HTTPS endpoint is required')
        self.base = base_url.rstrip('/')
        self.private = private_dir
        self.auth = None

    def request(self, path, data=None, *, method=None, retry=True):
        # The exact data, including its client_request_id, is reused on retries.
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.auth:
            headers['Authorization'] = 'Bearer ' + self.auth['token']
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = Request(self.base + path, data=payload, headers=headers,
                      method=method or ('POST' if data is not None else 'GET'))
        for attempt in range(3 if retry else 1):
            try:
                with urlopen(req, timeout=450) as resp:
                    text = resp.read().decode()
                    return json.loads(text) if text else None
            except HTTPError as exc:
                try:
                    detail = json.loads(exc.read().decode())
                except (ValueError, UnicodeError):
                    detail = {'detail': 'non_json_error_response'}
                if retry and exc.code in (500, 502, 503, 504) and attempt < 2:
                    time.sleep((3, 10)[attempt])
                    continue
                raise APIError(exc.code, path, detail) from None
            except (URLError, TimeoutError, ConnectionError):
                if not retry or attempt == 2:
                    raise RuntimeError('HTTPS transport failed; retry resumes the same operation') from None
                time.sleep((3, 10)[attempt])

    def connect_auth(self, auth_path):
        with lock(auth_path.with_suffix('.lock')):
            stored = read(auth_path, {})
            if stored and (stored.get('purpose') != PURPOSE or not stored.get('independent_validation_family')):
                raise ValueError('Auth state must explicitly identify the independent validation family')
            if stored.get('base_url') and stored['base_url'] != self.base:
                raise ValueError('Auth state belongs to a different endpoint')
            if not stored:
                # Save before registration so an ambiguous network outcome can
                # be recovered by logging in with the same random credentials.
                stored = {'purpose': PURPOSE, 'independent_validation_family': True,
                          'base_url': self.base, 'created_at': datetime.now(timezone.utc).isoformat(),
                          'credentials': {'username': 'cloudint_' + uuid4().hex[:12],
                                          'password': secrets.token_urlsafe(30)}}
                save(auth_path, stored)
            if stored.get('auth'):
                self.auth = stored['auth']
                try:
                    identity = self.request('/api/v1/auth/me')
                except APIError as exc:
                    if exc.status != 401:
                        raise
                    self.auth = None
            if not self.auth:
                creds = stored['credentials']
                try:
                    auth = self.request('/api/v1/auth/login', creds, retry=False)
                except APIError as exc:
                    if exc.status not in (401, 404):
                        raise
                    try:
                        auth = self.request('/api/v1/auth/register', creds, retry=False)
                    except APIError as reg:
                        if reg.status != 409:
                            raise
                        auth = self.request('/api/v1/auth/login', creds, retry=False)
                stored['auth'] = auth
                self.auth = auth
                save(auth_path, stored)
                identity = self.request('/api/v1/auth/me')
            if identity['family_id'] != self.auth['family_id'] or identity['account_id'] != self.auth['account_id']:
                raise ValueError('Token identity does not match the saved independent test family')
            stored['verified_identity'] = identity
            stored['verified_at'] = datetime.now(timezone.utc).isoformat()
            save(auth_path, stored)
            return identity


class ScenarioRun:
    def __init__(self, args, client, cfg):
        self.args, self.api, self.cfg = args, client, cfg
        self.sid = args.scenario
        self.private = args.private_dir / self.sid
        self.private.mkdir(parents=True, exist_ok=True)
        self.state_path = self.private / 'state.json'
        self.state = read(self.state_path, {'scenario': self.sid, 'operations': {}})
        self.out = args.output_dir / 'sessions' / self.sid
        self.out.mkdir(parents=True, exist_ok=True)
        self.queue = args.output_dir / 'persona-queue' / self.sid
        self.queue.mkdir(parents=True, exist_ok=True)
        source_cfg = {k: v for k, v in cfg.items() if k != 'material_text'}
        self.report = read(self.out / 'transcript.json', {
            'scenario': source_cfg, 'commit': COMMIT, 'pipeline': 'v3j_v4d',
            'endpoint': self.api.base, 'public_https': True,
            'interviewer': 'Actual cloud backend HTTPS API; unmodified visible replies',
            'respondent': 'AI simulation grounded only in listed published excerpts; not the real person',
            'independent_validation_family': True, 'saved_memories_created': 0,
            'events': [], 'model_calls': [], 'status': 'running',
            'audit_note': 'Module audit is API-visible; skeleton audit is added from protected server evidence after the run.'})

    def operation(self, key, path, data=None, *, method=None):
        journal = self.state['operations'].get(key)
        if journal and journal.get('completed'):
            return read(self.private / journal['response_file'])
        if not journal:
            data = deepcopy(data)
            if isinstance(data, dict) and 'client_request_id' in data and not data['client_request_id']:
                data['client_request_id'] = str(uuid4())
            journal = {'path': path, 'data': data, 'method': method,
                       'response_file': f'{len(self.state["operations"]):03d}-{key}.json'}
            self.state['operations'][key] = journal
            save(self.state_path, self.state)
        # Resume with the saved request and version, not a newly built request.
        result = self.api.request(journal['path'], journal['data'], method=journal['method'])
        save(self.private / journal['response_file'], result)
        journal['completed'] = True
        save(self.state_path, self.state)
        return result

    def checkpoint(self):
        counts = {k: sum(row['stage'] == k for row in self.report['model_calls'])
                  for k in ('judge', 'verify', 'speaker')}
        self.report['model_call_counts'] = counts
        self.report['answer_turns'] = sum(e['role'] == 'respondent' for e in self.report['events'])
        save(self.out / 'transcript.json', self.report)

    def setup(self):
        family_id = self.api.auth['family_id']
        member = self.operation('member', '/api/v1/family-members/', {
            'client_request_id': None, 'family_id': family_id,
            'name': f'云端验证-{self.sid}', 'relationship': '独立采访测试'})
        if member['family_id'] != family_id:
            raise ValueError('Member unexpectedly belongs to another family')
        state = self.operation('open', f'/api/v1/chat/members/{member["id"]}/conversation?family_id={quote(family_id)}', method='POST')
        session = state['session']
        if session['family_id'] != family_id or session['primary_person_id'] != member['id']:
            raise ValueError('Session unexpectedly belongs to another family/member')
        self.session_id = session['id']
        self.state['person_id'], self.state['session_id'] = member['id'], self.session_id
        self.report['validation_person_id'], self.report['validation_session_id'] = member['id'], self.session_id
        save(self.state_path, self.state)
        auth_path = self.args.auth_state or self.args.private_dir / 'auth.json'
        with lock(auth_path.with_suffix('.lock')):
            auth_state = read(auth_path)
            auth_state.setdefault('scenarios', {})[self.sid] = {
                'person_id': member['id'], 'session_id': self.session_id,
                'name': member['name'], 'output_dir': str(self.out)}
            save(auth_path, auth_state)
        prefix = f'/api/v1/chat/sessions/{self.session_id}'
        catalog = self.operation('catalog', '/api/v1/chat/interview-modules')
        self.catalog = {item['id']: item['baseline_questions'] for item in catalog}
        overview = self.operation('overview', prefix + '/life-overview')
        if overview['total_questions'] != 11:
            raise ValueError('Expected the 11-question skeleton')
        if self.cfg['route'] == 'module':
            for i in range(11):
                if overview['status'] != 'collecting':
                    break
                body = self.operation(f'setup-skip-{i:02d}', prefix + '/life-overview/actions', {
                    'action': 'answer', 'text': '我不想回答这个问题',
                    'client_request_id': None, 'expected_version': overview['version']})
                following = body['life_overview']
                if following['question_id'] == overview['question_id']:
                    raise ValueError('Setup skip did not advance the skeleton')
                overview = following
            if overview['status'] != 'review':
                raise ValueError('Skeleton setup did not reach review')
            state = self.operation('setup-confirm', prefix + '/life-overview/actions', {
                'action': 'confirm', 'text': '', 'client_request_id': None,
                'expected_version': overview['version']})
            state = self.operation('setup-module', prefix + '/interview', {
                'module': self.cfg['module'], 'expected_version': state['session']['version']})
            guide = state['session']['information']['guided_interview']
            qid = self.catalog[guide['module']][guide['topic_index']]['id']
            opening = latest_assistant(state['messages'])
            phase = guide['phase']
            self.report['setup'] = {'skeleton_explicit_skips': 11, 'skeleton_confirmed': True,
                                    'module_selected_via_api': guide['module']}
        else:
            state = {'life_overview': overview}
            qid, opening = overview['question_id'], latest_assistant(overview['turns'])
            phase = overview['status']
            self.report['setup'] = {'fresh_skeleton_via_api': True}
        if qid != self.cfg['start_qid']:
            raise ValueError('Scenario opening question differs from expected config')
        if not self.report['events']:
            self.report['events'].append({'role': 'interviewer', 'text': opening,
                                          'origin': 'cloud_backend_opening', 'question_id': qid})
        self.checkpoint()
        return state, {'phase': phase, 'qid': qid}

    def actor(self, turn):
        rid = f'{turn:03d}'
        instruction = ('你在扮演资料中的受访者，只根据给出的本人原话回应采访者最新一句。'
                       '第一轮简短自然回应一句，不把所有资料一次讲完；后续根据实际追问继续说，通常15到70字，最多120字。'
                       '资料没有的细节明确说记不清或不知道，不编造关系、时间、地点和心情。'
                       '不主动制造暂停/拒答，不迎合采访者的事实暗示。只回答当前问题；被问还有补充吗且无新内容时说没有了。'
                       '用第一人称、口语、简体中文。给出reply和支持该回答的supporting_excerpt_ids；不知道用空数组。')
        path = self.queue / (rid + '.request.json')
        if not path.exists():
            save(path, {'name': self.cfg['name'], 'materials': self.cfg['materials'],
                        'dialogue': [{'role': e['role'], 'text': e['text']} for e in self.report['events']
                                     if e['role'] != 'note'], 'instruction': instruction, 'turn': turn})
        log(scenario=self.sid, awaiting_persona=rid)
        deadline = time.monotonic() + self.args.queue_timeout
        response = self.queue / (rid + '.response.json')
        while not response.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('respondent_queue_timeout')
            time.sleep(.3)
        actor = read(response)
        if not isinstance(actor.get('reply'), str) or not 1 <= len(actor['reply']) <= 300:
            raise ValueError('Invalid respondent reply')
        if set(actor.get('supporting_excerpt_ids', [])) - {m['id'] for m in self.cfg['materials']}:
            raise ValueError('Respondent cites an unknown excerpt')
        return actor

    def run(self):
        body, state = self.setup()
        if self.args.setup_only:
            log(scenario=self.sid, status='setup_ready', validation_session_id=self.session_id)
            return 0
        prefix = f'/api/v1/chat/sessions/{self.session_id}'
        # Existing completed turns are replayed only from private response files.
        # This reconstructs state while making no duplicate HTTP mutations.
        for turn in range(self.args.max_turns):
            event_turn = next((e for e in self.report['events'] if e.get('api_turn') == turn and e['role'] == 'interviewer'), None)
            actor = self.actor(turn) if event_turn is None else read(self.queue / f'{turn:03d}.response.json')
            prior_qid = state['qid']
            started = time.monotonic()
            if self.cfg['route'] == 'skeleton':
                overview = body['life_overview']
                body = self.operation(f'answer-{turn:03d}', prefix + '/life-overview/actions', {
                    'action': 'answer', 'text': actor['reply'], 'client_request_id': None,
                    'expected_version': overview['version']})
                overview = body['life_overview']
                state = {'phase': 'paused' if overview['paused'] else overview['status'],
                         'qid': overview['question_id']}
                text = latest_assistant(overview['turns'])
                completed = sum(item['status'] != 'pending' for item in overview['fields'])
                done = completed >= self.cfg['topic_limit'] or overview['paused'] or overview['status'] == 'review'
                audit, local = {}, {}
            else:
                body = self.operation(f'answer-{turn:03d}', prefix + '/conversation/messages', {
                    'content': actor['reply'], 'client_request_id': None})
                guide = body['session']['information']['guided_interview']
                topics = self.catalog[guide['module']]
                qid = topics[guide['topic_index']]['id'] if guide['topic_index'] < len(topics) else None
                state = {'phase': guide['phase'], 'qid': qid}
                text = latest_assistant(body['messages'])
                local = guide.get('contract_history', {}).get(prior_qid) or guide.get('contract_state', {})
                audit = (local.get('audit') or [{}])[-1]
                done = guide['phase'] in ('review', 'paused', 'module_review') or qid != self.cfg['start_qid']
            if event_turn is None:
                self.report['events'].append({'role': 'respondent', 'text': actor['reply'],
                    'question_id': prior_qid, 'api_turn': turn,
                    'supporting_excerpt_ids': actor.get('supporting_excerpt_ids', [])})
                calls = audit.get('calls') or {}
                stages = []
                seen = {row.get('call_sha256') for row in self.report['model_calls']}
                for stage, call in calls.items():
                    fingerprint = sha256(json.dumps({'stage': stage, 'call': call}, sort_keys=True).encode()).hexdigest()
                    if fingerprint in seen:
                        continue
                    stages.append(stage)
                    seen.add(fingerprint)
                    self.report['model_calls'].append({'stage': stage, 'api_turn': turn,
                        'provenance': 'cloud_api_state', 'response': call.get('response', call),
                        'payload': call.get('payload'), 'request_sha256': call.get('request_sha256'),
                        'call_sha256': fingerprint})
                self.report['events'].append({'role': 'interviewer', 'text': text,
                    'question_id': prior_qid, 'api_turn': turn, 'state_after': state,
                    'seconds': round(time.monotonic() - started, 2),
                    'stages': stages, 'generation_offer': body.get('generation_offer') is not None,
                    'engine_decision': (local.get('last_result') or {}).get('decision'),
                    'speaker': audit.get('speaker'), 'origin': 'actual_cloud_https_api'})
                self.report['manifest_sha256'] = local.get('pipeline_manifest_sha256') or self.report.get('manifest_sha256')
                self.checkpoint()
                log(scenario=self.sid, turn=turn, state=state, stages=stages, done=done)
            cutoffs = read(self.args.output_dir / 'sample-cutoffs.json', {})
            cutoff = self.sid in cutoffs and turn + 1 >= cutoffs[self.sid]
            if done or cutoff:
                if cutoff and not done:
                    self.report['sample_cutoff'] = {'reason': 'repeated_draft_prompt_after_no_more_content', 'backend_phase': state['phase'], 'natural_completion': False}
                self.report['status'] = 'completed'
                self.checkpoint()
                (self.queue / 'DONE').write_text('completed')
                log(scenario=self.sid, status='completed', answer_turns=self.report['answer_turns'])
                return 0
        self.report['status'] = 'turn_limit'
        self.checkpoint()
        (self.queue / 'DONE').write_text('turn_limit')
        return 1


def latest_assistant(messages):
    return next(item['content'] for item in reversed(messages) if item['role'] == 'assistant')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=SCENARIOS + ('init',))
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--auth-state', type=Path, help='Defaults to PRIVATE_DIR/auth.json')
    parser.add_argument('--output-dir', type=Path, default=HERE)
    parser.add_argument('--config-dir', type=Path, default=PRIOR)
    parser.add_argument('--setup-only', action='store_true')
    parser.add_argument('--max-turns', type=int, default=16)
    parser.add_argument('--queue-timeout', type=int, default=900)
    args = parser.parse_args()
    os.umask(0o077)
    args.private_dir.mkdir(parents=True, exist_ok=True)
    args.private_dir.chmod(0o700)
    api = Client(args.base_url, args.private_dir)
    api.connect_auth(args.auth_state or args.private_dir / 'auth.json')
    if args.scenario == 'init':
        log(status='independent_test_family_verified', public_https=True)
        return 0
    cfg = read(args.config_dir / (args.scenario + '-config.json'))
    with lock(args.private_dir / args.scenario / 'run.lock'):
        run = ScenarioRun(args, api, cfg)
        try:
            return run.run()
        except Exception as exc:
            # Store detailed API failures only in the private journal. Safe
            # public errors identify the operation without echoing response data.
            err = {'type': type(exc).__name__, 'message': str(exc)[:200]}
            if isinstance(exc, APIError):
                save(run.private / 'failed-api.json', {'status': exc.status, 'path': exc.path, 'detail': exc.detail})
            run.report['status'], run.report['error'] = 'error', err
            run.checkpoint()
            log(scenario=args.scenario, status='error', error=err)
            return 1


if __name__ == '__main__':
    sys.exit(main())
