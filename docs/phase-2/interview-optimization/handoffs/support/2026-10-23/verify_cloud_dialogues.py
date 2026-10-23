"""Independent, offline verification of cloud API transcripts and provider audit.

Reads protected HTTP evidence and a server-extracted skeleton record. It never
makes network calls, imports product code, edits transcripts, or prints secrets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import zipfile


HERE = Path(__file__).resolve().parent
PRIVATE = Path('/Users/student03/Desktop/shinian-validation/private/interview-cloud-20261023')
REPO = Path('/tmp/shinian-question-review-20261023')
EXPORT = Path('/Users/student03/Documents/ChatGPT/ai memory/exports/云端双层采访问答_2026-10-23')
ORDER = ('skeleton', 'childhood', 'work', 'unmarried')
COMMIT = '770f8419c76e1edc7205c76e88c97100dbdf17b1'
ENDPOINT = 'https://aimemory.47-82-83-74.nip.io'


def load(path):
    return json.loads(path.read_text())


def digest_bytes(data):
    return sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def last_assistant(messages):
    return next(item['content'] for item in reversed(messages) if item['role'] == 'assistant')


def secret_keys(value):
    banned = {'password', 'token', 'authorization', 'api_key', 'apikey', 'access_token', 'refresh_token'}
    if isinstance(value, dict):
        return any(str(k).lower() in banned or secret_keys(v) for k, v in value.items())
    if isinstance(value, list):
        return any(secret_keys(v) for v in value)
    return False


class Speeches(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.current, self.items = 0, [], []

    def handle_starttag(self, tag, attrs):
        if self.depth:
            self.depth += 1
        elif tag == 'div' and 'speech' in dict(attrs).get('class', '').split():
            self.depth = 1
            self.current = []

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1
            if not self.depth:
                self.items.append(''.join(self.current))

    def handle_data(self, value):
        if self.depth:
            self.current.append(value)


class Verification:
    def __init__(self, args):
        self.args = args
        self.checks = []
        self.calls = {}
        self.by_scenario = {}
        self.secrets = []

    def check(self, name, condition, detail=None):
        row = {'check': name, 'passed': bool(condition)}
        if detail is not None:
            row['detail'] = detail
        self.checks.append(row)
        return bool(condition)

    def runtime(self):
        root = self.args.runtime_dir
        data = (root / 'manifest.json').read_bytes()
        manifest = json.loads(data)
        self.manifest = digest_bytes(data)
        self.check('runtime.pipeline', manifest['pipeline'] == 'v3j_v4d')
        self.check('runtime.file_integrity', all(digest_bytes((root / k).read_bytes()) == v
                                                for k, v in manifest['files'].items()))
        settings = load(root / 'provider-settings.json')
        self.params = {**settings, 'speaker': load(root / 'speaker-config.json')['model']}
        self.prompts = {stage: (root / f'{stage}-prompt.txt').read_text()
                        for stage in ('judge', 'verify', 'speaker')}
        self.check('runtime.thinking_disabled', all(p.get('thinking') == 'disabled' and 'reasoning_effort' not in p
                                                     for p in self.params.values()))
        self.check('runtime.model', all(p.get('model') == 'deepseek-v4-pro' for p in self.params.values()))

    def auth(self):
        state_path = self.args.private_dir / 'state.json'
        state = load(state_path)
        self.auth_state = state
        self.family = state['auth']['family_id']
        self.secrets = [state['auth'].get('token'), state.get('credentials', {}).get('password')]
        self.secrets = [value.encode() for value in self.secrets if isinstance(value, str) and value]
        self.check('identity.independent_test_family', state.get('purpose') == 'interview-cloud-validation-20261023'
                   and state.get('independent_validation_family') is True)
        self.check('identity.endpoint', state.get('base_url') == ENDPOINT)
        self.check('identity.auth_me_family', state.get('verified_identity', {}).get('family_id') == self.family)
        self.check('identity.auth_me_account', state.get('verified_identity', {}).get('account_id') == state['auth']['account_id'])
        private_files = list(self.args.private_dir.rglob('*.json'))
        self.check('security.private_json_mode', all(p.stat().st_mode & 0o077 == 0 for p in private_files))
        self.check('security.private_directory_mode', self.args.private_dir.stat().st_mode & 0o077 == 0)

    def verify_call(self, scenario, stage, entry):
        if stage not in self.params:
            self.check(f'{scenario}.unexpected_model_stage', False)
            return None
        response = entry.get('response') or {}
        rid = response.get('response_id')
        label = f'{scenario}.call_{stage}_{len(self.calls):03d}'
        self.check(label + '.provider_ok', response.get('ok') is True)
        self.check(label + '.response_id_present', isinstance(rid, str) and bool(rid))
        self.check(label + '.params', response.get('params') == self.params[stage])
        self.check(label + '.response_model', response.get('response_model') == self.params[stage]['model'])
        self.check(label + '.json_parsed', response.get('parse_error') is None and isinstance(response.get('output'), dict))
        expected = digest_bytes(canonical({'runtime': self.manifest, 'stage': stage,
            'params': self.params[stage], 'system': self.prompts[stage], 'user': entry.get('payload')}).encode())
        self.check(label + '.request_digest', entry.get('request_sha256') == expected)
        fingerprint = digest_bytes(canonical({'stage': stage, 'entry': entry}).encode())
        if rid:
            previous = self.calls.get(rid)
            self.check(label + '.response_id_consistent', previous is None or previous['fingerprint'] == fingerprint)
            self.calls.setdefault(rid, {'scenario': scenario, 'stage': stage, 'fingerprint': fingerprint,
                                         'response_id': rid, 'request_sha256': entry.get('request_sha256')})
        return rid

    def operations(self, scenario):
        folder = self.args.private_dir / scenario
        state = load(folder / 'state.json')
        rows = state['operations']
        self.check(f'{scenario}.all_operations_completed', all(row.get('completed') for row in rows.values()))
        self.check(f'{scenario}.request_ids_unique', len({row['data']['client_request_id'] for row in rows.values()
                   if isinstance(row.get('data'), dict) and row['data'].get('client_request_id')})
                   == sum(isinstance(row.get('data'), dict) and bool(row['data'].get('client_request_id')) for row in rows.values()))
        self.check(f'{scenario}.no_memory_write_operations', all('/draft' not in row['path'] and '/memories' not in row['path']
                                                                for row in rows.values()))
        self.check(f'{scenario}.member_mapping', self.auth_state['scenarios'][scenario]['person_id'] == state['person_id'])
        self.check(f'{scenario}.session_mapping', self.auth_state['scenarios'][scenario]['session_id'] == state['session_id'])

        def response(key):
            return load(folder / rows[key]['response_file'])

        member, opening = response('member'), response('open')
        self.check(f'{scenario}.family_isolation', member['family_id'] == self.family
                   and opening['session']['family_id'] == self.family
                   and opening['session']['primary_person_id'] == member['id'])
        return state, rows, response

    def skeleton_record(self, person_id, session_id):
        obj = load(self.args.server_skeleton)
        if isinstance(obj.get('scenarios'), dict):
            obj = obj['scenarios']['skeleton']
        self.check('skeleton.server_person_matches', obj.get('person_id', person_id) == person_id)
        self.check('skeleton.server_session_matches', obj.get('session_id', session_id) == session_id)
        data = obj.get('life_interview', obj)
        self.check('skeleton.server_questions_available', isinstance(data.get('questions'), dict))
        return data

    def scenario(self, scenario):
        report = load(self.args.root / 'sessions' / scenario / 'transcript.json')
        cfg, events = report['scenario'], report['events']
        state, operations, response = self.operations(scenario)
        self.check(f'{scenario}.completed', report.get('status') == 'completed')
        self.check(f'{scenario}.commit', report.get('commit') == COMMIT)
        self.check(f'{scenario}.endpoint', report.get('endpoint') == ENDPOINT and report.get('public_https') is True)
        self.check(f'{scenario}.pipeline', report.get('pipeline') == 'v3j_v4d')
        self.check(f'{scenario}.manifest', report.get('manifest_sha256') == self.manifest)
        self.check(f'{scenario}.independent_family', report.get('independent_validation_family') is True)
        self.check(f'{scenario}.no_saved_memories', report.get('saved_memories_created') == 0)
        opening = response('overview') if cfg['route'] == 'skeleton' else response('setup-module')
        opening_text = last_assistant(opening['turns'] if cfg['route'] == 'skeleton' else opening['messages'])
        self.check(f'{scenario}.opening_matches_api', events[0]['role'] == 'interviewer' and events[0]['text'] == opening_text)
        self.check(f'{scenario}.events_alternate', all(e['role'] == ('interviewer' if i % 2 == 0 else 'respondent')
                                                       for i, e in enumerate(events)))
        answers = [e for e in events if e['role'] == 'respondent']
        replies = [e for e in events if e['role'] == 'interviewer' and 'api_turn' in e]
        self.check(f'{scenario}.turn_counts', len(events) == len(answers) * 2 + 1 and len(replies) == len(answers))
        keys = sorted(k for k in operations if re.fullmatch(r'answer-\d{3}', k))
        self.check(f'{scenario}.no_omitted_answer_operations', len(keys) == len(answers))
        self.check(f'{scenario}.answer_turns_count', report.get('answer_turns') == len(answers))
        qid_ordinals = Counter()
        scenario_ids = set()
        expected_turn_stages = {}
        skeleton = self.skeleton_record(state['person_id'], state['session_id']) if scenario == 'skeleton' else None
        catalog = {m['id']: m['baseline_questions'] for m in response('catalog')}
        for i, (answer, reply) in enumerate(zip(answers, replies)):
            prefix = f'{scenario}.turn_{i:03d}'
            operation, body = operations[f'answer-{i:03d}'], response(f'answer-{i:03d}')
            req = operation['data']
            is_skeleton = cfg['route'] == 'skeleton'
            sent = req.get('text') if is_skeleton else req.get('content')
            self.check(prefix + '.request_matches', answer['text'] == sent and answer.get('api_turn') == i)
            raw_messages = body['life_overview']['turns'] if is_skeleton else body['messages']
            api_text = last_assistant(raw_messages)
            self.check(prefix + '.reply_matches_api', reply['text'] == api_text and reply.get('api_turn') == i)
            request_message = next((m for m in raw_messages if m['id'] == req['client_request_id'] and m['role'] == 'user'), None)
            self.check(prefix + '.request_id_in_api_history', request_message is not None and request_message['content'] == sent)
            self.check(prefix + '.generation_offer_matches', reply.get('generation_offer') == (body.get('generation_offer') is not None))
            if is_skeleton:
                life = body['life_overview']
                expected_state = {'phase': 'paused' if life['paused'] else life['status'], 'qid': life['question_id']}
                qid = answer['question_id']
                local = skeleton['questions'][qid]
                ordinal = qid_ordinals[qid]
                qid_ordinals[qid] += 1
                source = next((s for s in local.get('sources', []) if s['id'] == req['client_request_id']), None)
                self.check(prefix + '.server_source_matches', source is not None and source['text'] == sent)
                good_audits = [a for a in local.get('audit', []) if (a.get('result') or {}).get('decision') != 'invalid']
                audit = good_audits[ordinal] if ordinal < len(good_audits) else {}
            else:
                guide = body['session']['information']['guided_interview']
                topics = catalog[guide['module']]
                next_qid = topics[guide['topic_index']]['id'] if guide['topic_index'] < len(topics) else None
                expected_state = {'phase': guide['phase'], 'qid': next_qid}
                qid = answer['question_id']
                local = guide.get('contract_history', {}).get(qid) or guide.get('contract_state', {})
                audit = (local.get('audit') or [{}])[-1]
            self.check(prefix + '.state_matches', reply.get('state_after') == expected_state)
            if audit:
                self.check(prefix + '.audit_manifest', audit.get('runtime_manifest_sha256') == self.manifest)
                self.check(prefix + '.question_pipeline', local.get('pipeline') == 'v3j_v4d')
            else:
                self.check(prefix + '.audit_available', False)
            current_ids, stages = set(), []
            for stage, entry in (audit.get('calls') or {}).items():
                rid = self.verify_call(scenario, stage, entry)
                if rid:
                    current_ids.add(rid)
                    if rid not in scenario_ids:
                        stages.append(stage)
                        scenario_ids.add(rid)
            expected_turn_stages[i] = set(stages)
            self.check(prefix + '.stage_list_matches', set(reply.get('stages') or []) == set(stages))
            self.check(prefix + '.decision_matches', reply.get('engine_decision') == (local.get('last_result') or {}).get('decision')
                       if not is_skeleton else reply.get('engine_decision') == (audit.get('result') or {}).get('decision'))
        published_ids = []
        for row in report['model_calls']:
            rid = (row.get('response') or {}).get('response_id')
            published_ids.append(rid)
            entry = {key: row.get(key) for key in ('request_sha256', 'payload', 'response')}
            fingerprint = digest_bytes(canonical({'stage': row.get('stage'), 'entry': entry}).encode())
            self.check(f'{scenario}.published_call_{len(published_ids):03d}_exact',
                       rid in self.calls and self.calls[rid]['fingerprint'] == fingerprint)
        self.check(f'{scenario}.published_provider_ids_unique', len(published_ids) == len(set(published_ids)) and None not in published_ids)
        self.check(f'{scenario}.published_calls_match_evidence', set(published_ids) == scenario_ids)
        counts = Counter(self.calls[rid]['stage'] for rid in scenario_ids)
        self.check(f'{scenario}.model_call_counts', all(report.get('model_call_counts', {}).get(stage, 0) == counts[stage]
                                                      for stage in ('judge', 'verify', 'speaker')))
        self.check(f'{scenario}.judge_and_speaker_used', counts['judge'] > 0 and counts['speaker'] > 0)
        cutoff = report.get('sample_cutoff')
        if cfg['route'] == 'module':
            phase = replies[-1]['state_after']['phase'] if replies else None
            if phase == 'supplement':
                self.check(f'{scenario}.cutoff.disclosed', isinstance(cutoff, dict))
                cutoff = cutoff or {}
                self.check(f'{scenario}.cutoff.not_natural_completion', cutoff.get('natural_completion') is False)
                self.check(f'{scenario}.cutoff.phase_matches_api', cutoff.get('backend_phase') == phase)
                self.check(f'{scenario}.cutoff.reason_matches', cutoff.get('reason') == 'repeated_draft_prompt_after_no_more_content')
                self.check(f'{scenario}.cutoff.full_nine_api_turns', len(answers) == 9 and len(keys) == 9)
                self.check(f'{scenario}.cutoff.repeated_no_more_content', all('没有' in e['text'] for e in answers[-3:]))
                self.check(f'{scenario}.cutoff.repeated_draft_prompt', all('这段可以先整理成草稿了' in e['text']
                                                                           and e['state_after']['phase'] == phase
                                                                           for e in replies[-3:]))
            else:
                self.check(f'{scenario}.cutoff.natural_end_state', cutoff is None and phase in ('review', 'paused', 'module_review'))
        else:
            final_life = response(keys[-1])['life_overview']
            self.check(f'{scenario}.sample.five_questions_complete',
                       sum(f['status'] != 'pending' for f in final_life['fields']) == cfg['topic_limit'])
            self.check(f'{scenario}.sample.next_question_retained', final_life['question_id'] is not None
                       and final_life['question'] in replies[-1]['text'])
        unused_queue_responses = len(list((self.args.root / 'persona-queue' / scenario).glob('*.response.json'))) - len(answers)
        self.check(f'{scenario}.queue.no_unrecorded_api_answers', len(keys) == len(answers))
        self.by_scenario[scenario] = {'answer_turns': len(answers), 'unique_provider_calls': len(scenario_ids),
                                       'model_call_counts': dict(counts), 'sample_cutoff': cutoff,
                                       'unused_queue_replies_not_sent': max(0, unused_queue_responses),
                                       'events_exactly_match_api':
                                       all(c['passed'] for c in self.checks if c['check'].startswith(scenario + '.turn_')
                                           and (c['check'].endswith('reply_matches_api') or c['check'].endswith('request_matches')))}

    def exports(self):
        export = self.args.export_dir
        html_path, txt_path = export / '云端双层采访问答.html', export / '云端双层采访问答.txt'
        manifest_path, zip_path = export / '运行核验.json', export / '问答与原始核验.zip'
        for p in (html_path, txt_path, manifest_path, zip_path):
            self.check('export.' + p.suffix[1:] + '.exists', p.exists())
        if not all(p.exists() for p in (html_path, txt_path, manifest_path, zip_path)):
            return
        manifest = load(manifest_path)
        self.check('export.manifest_matches_runtime', manifest.get('manifest_sha256') == self.manifest)
        self.check('export.answer_turns', manifest.get('answer_turns') == sum(row['answer_turns'] for row in self.by_scenario.values()))
        self.check('export.call_count', sum(manifest.get('model_call_counts', {}).values()) == len(self.calls))
        self.check('export.file_digests', all(digest_bytes((export / name).read_bytes()) == meta['sha256']
                                             for name, meta in manifest.get('files', {}).items()))
        exported_sessions = {s['id']: s for s in manifest['sessions']}
        txt = txt_path.read_text()
        html_source = html_path.read_text()
        parser = Speeches()
        parser.feed(html_source)
        expected_speeches = []
        position_txt = 0
        for scenario in ORDER:
            transcript = load(self.args.root / 'sessions' / scenario / 'transcript.json')
            self.check(f'export.{scenario}.sample_cutoff_manifest',
                       exported_sessions.get(scenario, {}).get('sample_cutoff') == transcript.get('sample_cutoff'))
            if transcript.get('sample_cutoff'):
                section = re.search(r'<section id="' + scenario + r'">(.*?)</section>', html_source, re.S)
                end = re.search(r'<p class="end">(.*?)</p>', section.group(1), re.S) if section else None
                end_text = end.group(1) if end else ''
                self.check(f'export.{scenario}.sample_cutoff_html_disclosed', '结束采样' in end_text
                           and '补充阶段' in end_text and '重复' in end_text)
            for i, event in enumerate(transcript['events']):
                # Content is searched in order; repeated prompts must occur as
                # many times as they did in the original API interaction.
                label = f'export.{scenario}.event_{i:03d}'
                text = event['text']
                expected_speeches.append(text)
                at_txt = txt.find(text, position_txt)
                self.check(label + '.txt_in_order', at_txt >= 0)
                if at_txt >= 0:
                    position_txt = at_txt + len(text)
        self.check('export.html_speeches_exact_order', parser.items == expected_speeches)
        self.check('export.txt_sampling_limitation_disclosed', '九轮回答后结束采样' in txt
                   and '仍处于补充阶段' in txt and '重复草稿提示' in txt)
        safe = True
        safe_keys = not secret_keys(manifest)
        for p in (html_path, txt_path, manifest_path):
            content = p.read_bytes()
            safe &= all(secret not in content for secret in self.secrets)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            self.check('export.zip_safe_paths', all(not n.startswith('/') and '..' not in Path(n).parts
                                                    and 'private' not in n.lower() and 'auth' not in n.lower()
                                                    for n in names))
            self.check('export.zip_expected_members', len(names) == 7)
            for name in names:
                content = z.read(name)
                safe &= all(secret not in content for secret in self.secrets)
                if name.endswith('.json'):
                    safe_keys &= not secret_keys(json.loads(content))
            for scenario in ORDER:
                name = '原始记录/' + scenario + '.json'
                self.check(f'export.{scenario}.zip_exact_transcript', name in names and
                           z.read(name) == (self.args.root / 'sessions' / scenario / 'transcript.json').read_bytes())
        self.check('security.exports_no_credential_values', safe)
        self.check('security.exports_no_credential_keys', safe_keys)

    def run(self):
        self.runtime()
        self.auth()
        for scenario in ORDER:
            self.scenario(scenario)
        self.check('provider.response_ids_unique_between_scenarios', sum(r['unique_provider_calls'] for r in self.by_scenario.values()) == len(self.calls))
        self.exports()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE)
    parser.add_argument('--private-dir', type=Path, default=PRIVATE)
    parser.add_argument('--runtime-dir', type=Path, default=REPO / 'cloud-deployment/backend/app/ai/interview_runtime_v3j_v4d')
    parser.add_argument('--server-skeleton', type=Path, default=PRIVATE / 'server-skeleton.json')
    parser.add_argument('--export-dir', type=Path, default=EXPORT)
    parser.add_argument('--report', type=Path, default=HERE / 'independent-dialogue-verification.json')
    args = parser.parse_args()
    verifier = Verification(args)
    try:
        verifier.run()
    except Exception as exc:
        # Exception messages may contain raw source material or a private path;
        # only the type is included in this outward-facing report.
        verifier.check('verification.complete_evidence_available', False, type(exc).__name__)
    failed = [row for row in verifier.checks if not row['passed']]
    counts = Counter(row['stage'] for row in verifier.calls.values())
    report = {'passed': not failed, 'created_at': datetime.now(timezone.utc).isoformat(),
              'network_requests_sent': 0, 'product_code_modified': False,
              'manifest_sha256': getattr(verifier, 'manifest', None),
              'scenarios': verifier.by_scenario, 'model_call_counts': dict(counts),
              'unique_provider_response_ids': len(verifier.calls),
              'provider_response_ids_sha256': digest_bytes('\n'.join(sorted(verifier.calls)).encode()),
              'checks_run': len(verifier.checks), 'checks_passed': len(verifier.checks) - len(failed),
              'failed_checks': failed, 'checks': verifier.checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('checks', 'provider_response_ids_sha256')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
