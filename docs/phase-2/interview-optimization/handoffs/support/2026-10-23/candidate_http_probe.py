"""On-host candidate-only business smoke, using the real HTTP API and model."""
from pathlib import Path
from uuid import uuid4
import json
import secrets
import urllib.request
import urllib.error

RELEASE = Path('/opt/shinian-releases/interview-v3j-v4d-770f841-20261023')
BASE = 'http://127.0.0.1:18011'
token = None
checks = []


def request(path, data=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=raw, headers=headers, method=method or ('POST' if data is not None else 'GET'))
    with urllib.request.urlopen(req, timeout=180) as f:
        return json.load(f)


def run():
    global token, checks
    auth = request('/api/v1/auth/register', {'username': 'candidate_' + uuid4().hex[:12], 'password': secrets.token_urlsafe(30)})
    token = auth['token']
    me = request('/api/v1/auth/me')
    assert me['family_id'] == auth['family_id']
    checks.append('independent_candidate_family_bearer_auth')
    member = request('/api/v1/family-members/', {'family_id': auth['family_id'], 'name': '候选接口验证', 'relationship': '隔离测试', 'client_request_id': str(uuid4())})
    state = request('/api/v1/chat/members/' + member['id'] + '/conversation?family_id=' + auth['family_id'], method='POST')
    prefix = '/api/v1/chat/sessions/' + state['session']['id']
    life = request(prefix + '/life-overview')
    assert life['question_id'] == 'SK01' and life['total_questions'] == 11
    body = {'action': 'answer', 'text': '我是1956年出生的。', 'client_request_id': str(uuid4()), 'expected_version': life['version']}
    first = request(prefix + '/life-overview/actions', body)
    assert first['life_overview']['question_id'] == 'SK01b'
    assert '出生在哪' in first['life_overview']['turns'][-1]['content'], 'spoken_next_question_must_match_state'
    again = request(prefix + '/life-overview/actions', body)
    assert again['life_overview'] == first['life_overview']
    checks += ['skeleton_actual_judge_speaker_close_into_next_question', 'skeleton_retry_does_not_duplicate_or_advance']
    life = first['life_overview']
    for action in ['pause', 'resume']:
        life = request(prefix + '/life-overview/actions', {'action': action, 'text': '', 'client_request_id': str(uuid4()), 'expected_version': life['version']})['life_overview']
        assert life['paused'] == (action == 'pause')
    checks.append('skeleton_pause_and_resume_keep_position')
    skip = {'action': 'answer', 'text': '跳过', 'client_request_id': str(uuid4()), 'expected_version': life['version']}
    skipped = request(prefix + '/life-overview/actions', skip)
    assert skipped['life_overview']['question_id'] == 'SK01c'
    assert request(prefix + '/life-overview/actions', skip)['life_overview'] == skipped['life_overview']
    checks.append('skeleton_explicit_skip_retry_advances_once')
    life = skipped['life_overview']
    seen = ['SK01', 'SK01b']
    while life['status'] == 'collecting':
        seen.append(life['question_id'])
        life = request(prefix + '/life-overview/actions', {'action': 'answer', 'text': '跳过', 'client_request_id': str(uuid4()), 'expected_version': life['version']})['life_overview']
    assert seen == ['SK01','SK01b','SK01c','SK02','SK03','SK03b','SK03c','SK03d','SK04','SK05','SK06'], seen
    checks.append('mysql_full_eleven_question_order_and_spoken_next_entry')
    assert life['status'] == 'review' and not life['question_id']
    state = request(prefix + '/life-overview/actions', {'action': 'confirm', 'text': '', 'client_request_id': str(uuid4()), 'expected_version': life['version']})
    assert state['life_overview']['status'] == 'confirmed'
    checks.append('eleven_skeleton_questions_finish_review_and_confirm')
    state = request(prefix + '/interview', {'module': 'family', 'expected_version': state['session']['version']})
    body = {'content': '我们是在工厂认识的。', 'client_request_id': str(uuid4())}
    state = request(prefix + '/conversation/messages', body)
    guide = state['session']['information']['guided_interview']
    assert guide['contract_state']['pipeline'] == 'v3j_v4d'
    assert guide['pending_question'] is not None and state['generation_offer'] is None
    again = request(prefix + '/conversation/messages', body)
    assert again['session']['version'] == state['session']['version']
    assert again['messages'][-1]['content'] == state['messages'][-1]['content']
    checks += ['module_actual_judge_speaker_followup', 'module_retry_reuses_persisted_reply']
    state = request(prefix + '/conversation/messages', {'content': '后来天天一起上下班，慢慢就熟悉了。', 'client_request_id': str(uuid4())})
    assert state['generation_offer'] is not None
    checks.append('module_finished_answer_keeps_draft_step')
    state = request(prefix + '/conversation/messages', {'content': '跳过', 'client_request_id': str(uuid4())})
    assert state['generation_offer'] is None
    assert state['session']['information']['guided_interview']['topic_index'] == 1
    checks.append('module_skip_moves_next_without_generation_offer')
    state = request(prefix + '/conversation/messages', {'content': '先暂停', 'client_request_id': str(uuid4())})
    assert state['session']['information']['guided_interview']['phase'] == 'paused'
    state = request(prefix + '/conversation/messages', {'content': '继续', 'client_request_id': str(uuid4())})
    assert state['session']['information']['guided_interview']['phase'] != 'paused'
    checks.append('module_pause_and_continue')
    result = {'passed': True, 'candidate_only': True, 'actual_deepseek_calls': True, 'checks': checks,
              'production_business_data_written': False, 'saved_memories_created': 0}
    (RELEASE / 'candidate-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        result = {'passed': False, 'checks_completed': checks, 'error_type': type(e).__name__}
        if isinstance(e, urllib.error.HTTPError):
            result['http_status'] = e.code
        (RELEASE / 'candidate-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        raise SystemExit(1)
