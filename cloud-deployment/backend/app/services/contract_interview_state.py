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


V3J_PIPELINE = 'v3j_v4d'
V5F_PIPELINE = 'v3j_v5f'  # v3j judgment + v5f speaking layer (story-question deepening), its own pinned bundle
V3J_FLOWS = (V3J_PIPELINE, V5F_PIPELINE)
PIPELINES = ('v2', V3J_PIPELINE, V5F_PIPELINE)


def configured_pipeline():
    """Flow for questions not yet started; started questions keep the flow saved with them."""
    value = os.getenv('INTERVIEW_PIPELINE', '').strip() or 'v2'
    if value not in PIPELINES:
        from app.ai.llm_client import LLMConfigurationError
        raise LLMConfigurationError('Unsupported interview pipeline')
    return value


@lru_cache(maxsize=4)
def _v3j_runtime(directory, digest, pipeline=V3J_PIPELINE):
    from app.ai.contract_interview_v3j import V3jRuntime
    return V3jRuntime(directory, digest, pipeline)


def v3j_runtime():
    return _v3j_runtime(os.getenv('INTERVIEW_V3J_RUNTIME_DIR', ''), os.getenv('INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256', ''))


def v5f_runtime():
    return _v3j_runtime(os.getenv('INTERVIEW_V5F_RUNTIME_DIR', ''), os.getenv('INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256', ''),
                        V5F_PIPELINE)


def flow_runtime(pipeline):
    """The pinned bundle of a v3j flow: a question keeps the bundle of the flow it started with."""
    return v5f_runtime() if pipeline == V5F_PIPELINE else v3j_runtime()


def validate_pipeline():
    """Fail at startup, like the main runtime pin, when the opted-in flow is not deployable.

    The v3j bundle must carry exactly the configured catalog (same question IDs,
    order and entry questions), so switching flows never moves a topic position.
    """
    if configured_pipeline() not in V3J_FLOWS:
        return
    bundle, current = flow_runtime(configured_pipeline()), runtime()
    if bundle.version != current.version or [(q['id'], q['main_question']) for q in bundle.contracts['questions']] != [
            (q['id'], q['main_question']) for q in current.contracts['questions']]:
        from app.ai.llm_client import LLMConfigurationError
        raise LLMConfigurationError('Interview v3j catalog differs from the configured runtime')


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
