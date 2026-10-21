"""Use the frozen interview engine and the exact whole-question A/B policy.

No Python translation of semantic rules: the accepted JavaScript artifact is
loaded verbatim. This module never changes another question's state, advances
an interview, writes a database row, or sends a question to a user on its own.
The caller saves raw answers before invoking it and durably records each model
call through ``save_call`` before moving on to a later stage.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import monotonic

from app.ai.llm_client import (
    LLMConfigurationError, LLMResponseFormatError, LLMServiceError,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


class ContractInterviewRuntime:
    """An immutable deployment artifact; only its directory is configurable."""

    def __init__(self, directory=None, expected_manifest_sha256=None):
        self.directory = Path(directory or os.getenv('INTERVIEW_RUNTIME_DIR', '')).resolve()
        expected = expected_manifest_sha256 or os.getenv('INTERVIEW_RUNTIME_MANIFEST_SHA256', '')
        if not expected:
            raise LLMConfigurationError('A pinned interview runtime manifest is required')
        try:
            manifest_bytes = (self.directory / 'manifest.json').read_bytes()
            if sha256(manifest_bytes).hexdigest() != expected:
                raise ValueError('manifest_mismatch')
            manifest = json.loads(manifest_bytes)
            for name, digest in manifest['files'].items():
                target = (self.directory / name).resolve()
                if not target.is_relative_to(self.directory) or sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError('runtime_file_mismatch')
            required = {'engine.js', 'contracts.json', 'extractor-prompt.txt',
                        'reviewer-prompt.txt', 'provider-settings.json'}
            if not required.issubset(manifest['files']):
                raise ValueError('runtime_files_missing')
            self.contracts = json.loads((self.directory / 'contracts.json').read_text())
            self.settings = json.loads((self.directory / 'provider-settings.json').read_text())
            self.extractor_prompt = (self.directory / 'extractor-prompt.txt').read_text()
            self.reviewer_prompt = (self.directory / 'reviewer-prompt.txt').read_text()
            self.version = self.contracts['version']
            self.manifest_sha256 = expected
            self.questions = {q['id']: q for q in self.contracts['questions']}
            protocol = self.contracts['output_protocol']
            if (self.contracts['question_context_mode'] != 'independent'
                    or protocol.get('review_mode') is not None or protocol.get('workflow')
                    or protocol.get('model_input_projection') != 'target_fields_v1'):
                raise ValueError('unsupported_runtime_protocol')
            if set(self.settings) != {'model', 'thinking', 'max_tokens'}:
                raise ValueError('unsupported_provider_configuration')
            if self.settings['thinking'] != 'disabled':
                raise ValueError('unsupported_provider_configuration')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LLMConfigurationError('Interview runtime integrity check failed') from exc

    def _bridge(self, payload):
        try:
            result = subprocess.run(
                [os.getenv('INTERVIEW_NODE_BINARY', 'node'),
                 str(Path(__file__).with_name('contract_interview_bridge.js')), str(self.directory)],
                input=json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                text=True, capture_output=True, timeout=10, check=True,
            )
            return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise LLMResponseFormatError('Interview contract validation unavailable') from exc

    def build(self, question_id, sources, context=None):
        if question_id not in self.questions or not sources:
            raise LLMResponseFormatError('A known question and its own sources are required')
        if any(source.get('question_id') != question_id for source in sources):
            raise LLMResponseFormatError('Cross-question source use is prohibited')
        context = deepcopy(context or {})
        fields = {field['id'] for field in self.questions[question_id]['elements']}
        if not set(context.get('previous_fields', {})).issubset(fields):
            raise LLMResponseFormatError('Cross-question state use is prohibited')
        # The source carries the question actually shown. Missing context is not
        # silently replaced with the main question as if it had been asked.
        context['current_question'] = sources[-1].get('question') or ''
        result = self._bridge({'operation': 'payload', 'question_id': question_id,
                               'sources': sources, 'context': context})
        result['payload']['current_question'] = context['current_question']
        return result

    def analyze(self, payload, call):
        return self._bridge({'operation': 'analyze', 'payload': payload, 'call': call})

    def review_input(self, model_input, candidate, checked):
        return self._bridge({'operation': 'review_input', 'model_input': model_input,
                             'candidate': candidate, 'checked': checked})


class ContractInterviewPipeline:
    def __init__(self, runtime, client):
        self.runtime = runtime
        self.client = client

    def _call(self, instruction, payload):
        settings = self.runtime.settings
        started = monotonic()
        try:
            response = self.client.client.with_options(timeout=110.0, max_retries=0).chat.completions.create(
                model=settings['model'],
                messages=[{'role': 'system', 'content': instruction},
                          {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                response_format={'type': 'json_object'}, max_tokens=settings['max_tokens'],
                extra_body={'thinking': {'type': 'disabled'}},
            )
        except Exception as exc:
            # Standard API handling retains durable input and offers idempotent
            # retry. Never expose an upstream exception containing private data.
            raise LLMServiceError('Interview provider request failed') from exc
        message = response.choices[0].message
        content = message.content or ''
        try:
            output, parse_error = json.loads(content), None
        except ValueError:
            output, parse_error = None, 'JSONDecodeError'
        return {'kind': 'model_call', 'raw_content': content, 'output': output,
                'parse_error': parse_error, 'finish_reason': response.choices[0].finish_reason,
                'response_id': response.id, 'response_model': response.model,
                'provider_settings': deepcopy(settings),
                'usage': response.usage.model_dump(mode='json') if response.usage else {},
                'seconds': monotonic() - started}

    def run(self, question_id, sources, context=None, saved_calls=None, save_call=None):
        """Always A then B; at most one protocol repair, exactly as evaluated.

        Saved calls must be server-owned records from the same pending request.
        Their request digest prevents an old response being reused after a source,
        prompt, model setting or accepted engine artifact changes. B's result is
        authoritative, even when A looked better. A semantic failure is retained
        as a missing answer; it does not cause extra provider retries.
        """
        built = self.runtime.build(question_id, sources, context)
        payload, model_input = built['payload'], built['model_input']
        calls, decisions = {}, {}

        def invoke(stage, instruction, value):
            digest = sha256(_json({'runtime': self.runtime.manifest_sha256,
                'settings': self.runtime.settings, 'instruction': instruction, 'payload': value}).encode()).hexdigest()
            saved = (saved_calls or {}).get(stage)
            if saved is not None:
                if saved.get('request_sha256') != digest:
                    raise LLMResponseFormatError('Saved provider response does not match pending input')
                call = deepcopy(saved['response'])
            else:
                call = self._call(instruction, value)
            entry = {'request_sha256': digest, 'payload': deepcopy(value), 'response': call}
            calls[stage] = entry
            if save_call is not None and saved is None:
                save_call(stage, deepcopy(entry))
            return call

        first = invoke('extractor', self.runtime.extractor_prompt, model_input)
        decisions['extractor'] = self.runtime.analyze(payload, first)
        review_input = self.runtime.review_input(model_input, first.get('output'), decisions['extractor'])
        final_call = invoke('reviewer', self.runtime.reviewer_prompt, review_input)
        result = decisions['reviewer'] = self.runtime.analyze(payload, final_call)
        repairs = 0
        if result['decision'] == 'invalid':
            repair_input = deepcopy(model_input)
            repair_input['extraction_retry'] = {'attempt': 1,
                'validation_errors': result.get('errors', []), 'previous_proposal': final_call.get('output')}
            final_call = invoke('repair1', self.runtime.reviewer_prompt, repair_input)
            result = decisions['repair1'] = self.runtime.analyze(payload, final_call)
            repairs = 1
        return {'runtime_version': self.runtime.version,
                'runtime_manifest_sha256': self.runtime.manifest_sha256,
                'result': result, 'calls': calls, 'decisions': decisions,
                'internal_repairs': repairs, 'semantic_review_calls': 1}
