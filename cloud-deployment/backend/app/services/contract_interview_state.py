"""Shared frozen catalog and question-local persistence helpers."""
from functools import lru_cache
import os
from copy import deepcopy
from app.ai.contract_interview import ContractInterviewRuntime

PREFIXES = {'childhood': 'CH', 'growth': 'GR', 'work': 'WK', 'family': 'FM',
            'later_life': 'LT', 'reflection': 'RV'}


def runtime_configured():
    return bool(os.getenv('INTERVIEW_RUNTIME_DIR'))


def enabled():
    """Gate new-schema creation only; existing states still need the runtime."""
    return runtime_configured() and os.getenv('INTERVIEW_NEW_SESSIONS_ENABLED', '1').strip().lower() not in ('0', 'false', 'off', 'no')


@lru_cache(maxsize=4)
def runtime(version=None):
    current = ContractInterviewRuntime()
    if version is None or version == current.version:
        return current
    if version in ('full-interview-v1.29.0', 'full-interview-v1.29.1'):
        return ContractInterviewRuntime(current.directory.with_name('interview_runtime_legacy'),
            '7d7505774dc93d8434a6211fee1d02f021997bfe6bbc9b4c26a9319ec51d9969')
    from app.ai.llm_client import LLMConfigurationError
    raise LLMConfigurationError('Unsupported saved interview runtime')


def questions(module, version=None):
    prefix = 'SK' if module == 'skeleton' else PREFIXES[module]
    return [q for q in runtime(version).questions.values() if q['id'].startswith(prefix)]


def fresh_question(question_id):
    return {'question_id': question_id, 'sources': [], 'fields': {}, 'ask_counts': {},
            'last_result': None, 'pending': None, 'audit': []}


def context_for(state):
    last = state.get('last_result') or {}
    return {'previous_fields': deepcopy(state.get('fields', {})),
            'ask_counts': deepcopy(state.get('ask_counts', {})),
            'focus': {'field_id': last['target']} if last.get('target') else None}


def finish_question_turn(state, outcome):
    result = outcome['result']
    state['audit'].append(outcome)
    state['last_result'] = deepcopy(result)
    state['pending'] = None
    state['fields'] = deepcopy(result['fields'])
    if result['decision'] in ('ask', 'ask_defer') and result.get('target'):
        target = result['target']
        state['ask_counts'][target] = state['ask_counts'].get(target, 0) + 1


def append_source(state, identity, text, asked_question):
    last = state.get('last_result') or {}
    source = {'id': str(identity), 'text': text, 'question_id': state['question_id'],
              'speaker': 'narrator', 'question': asked_question}
    if last.get('target'):
        source['target_field_id'] = last['target']
    prior = next((s for s in state['sources'] if s['id'] == str(identity)), None)
    if prior is None:
        state['sources'].append(source)
    elif prior != source:
        from app.ai.llm_client import LLMResponseFormatError
        raise LLMResponseFormatError('A saved answer cannot be changed during retry')
