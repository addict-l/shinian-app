"""Offline full45 replay of the backend v3j judgment layer through cached DeepSeek answers.

Every checkpoint of the full45 dataset goes through the backend V3jPipeline with
an SDK stand-in that answers from the evaluation cache by Relay.key (the
content hash of system, user and parameters). A request the backend builds
differently from the evaluated pipeline misses the cache and fails the test, so
no provider is ever called and no token is spent. Each checkpoint result must
equal the saved run branch-check-v3j, and the evaluation's own scoring must give
197/204.

Needs the full repository (tools/interview_eval) and the git-ignored evaluation
data (.runtime/interview-eval, or SHINIAN_EVAL_HOME / SHINIAN_EVAL_RUNS /
SHINIAN_EVAL_CACHE); skips when they are absent.

  cd cloud-deployment/backend && python3 -m unittest tests.test_interview_v3j_full45_replay -v
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))
from app.ai.contract_interview_v3j import V3jPipeline, V3jRuntime  # noqa: E402

EVAL_HOME = Path(os.getenv('SHINIAN_EVAL_HOME', ROOT / '.runtime/interview-eval'))
RUNS = Path(os.getenv('SHINIAN_EVAL_RUNS', EVAL_HOME / 'runs'))
CACHE = Path(os.getenv('SHINIAN_EVAL_CACHE', EVAL_HOME / 'cache'))
RUNTIME = BACKEND / 'app/ai/interview_runtime_v3j_v4d'
DATASET = RUNS / 'datasets/full45.json'
REFERENCE = RUNS / 'branch-check-v3j'


def load_eval_common():
    tools = ROOT / 'tools/interview_eval'
    if not (tools / 'common.py').exists():
        raise unittest.SkipTest('tools/interview_eval is not part of this checkout')
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import common
    return common


class CachedDeepSeek:
    """SDK stand-in answering from the evaluation cache; a miss is recorded and raised, never sent."""

    def __init__(self, key, cache=CACHE):
        self.key, self.cache = key, cache
        self.client = self
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.calls, self.misses, self.requests = [], [], []

    def with_options(self, **options):
        assert options == {'timeout': options['timeout'], 'max_retries': 0}, options
        return self

    def create(self, **request):
        # The exact evaluated request shape: thinking disabled, no reasoning_effort or other switches.
        assert set(request) == {'model', 'messages', 'max_tokens', 'temperature', 'response_format', 'extra_body'}, request.keys()
        assert request['extra_body'] == {'thinking': {'type': 'disabled'}}
        assert request['response_format'] == {'type': 'json_object'}
        system, user = [m['content'] for m in request['messages']]
        assert [m['role'] for m in request['messages']] == ['system', 'user']
        params = {'model': request['model'], 'thinking': 'disabled', 'max_tokens': request['max_tokens'],
                  'temperature': request['temperature'], 'json_mode': True}
        key = self.key({'system': system, 'user': user, 'params': params})
        self.calls.append(key)
        self.requests.append({'system': system, 'user': user, 'params': params, 'key': key})
        path = self.cache / (key + '.json')
        if not path.exists():
            self.misses.append(self.requests[-1])
            raise RuntimeError('offline cache miss')
        row = json.loads(path.read_text(encoding='utf-8'))
        return SimpleNamespace(id=row.get('id'), model=row.get('response_model'), usage=None,
                               choices=[SimpleNamespace(message=SimpleNamespace(content=row.get('content')),
                                                        finish_reason=row.get('finish_reason'))])


def runtime():
    return V3jRuntime(RUNTIME, sha256((RUNTIME / 'manifest.json').read_bytes()).hexdigest())


class Full45ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATASET.exists() and CACHE.is_dir() and (REFERENCE / 'cases').is_dir()):
            raise unittest.SkipTest('Evaluation data (full45, response cache, branch-check-v3j) not present')
        cls.common = load_eval_common()

    def test_full45_backend_replay_matches_reference_and_scores_197(self):
        data = json.loads(DATASET.read_text(encoding='utf-8'))
        fake = CachedDeepSeek(self.common.Relay.key)
        pipeline = V3jPipeline(runtime(), fake)
        results, differing, checkpoints, stages = {}, [], 0, {}
        for case in data['cases']:
            qid = case['question_id']
            previous, counts = {}, {}
            for index, turn in enumerate(case['turns']):
                # Same sources and multi-turn state as tools/interview_eval/run.py (payload_for + case_runner).
                sources = []
                for t in case['turns'][:index + 1]:
                    source = deepcopy(t['source'])
                    source.update(question_id=qid, speaker='narrator')
                    source.setdefault('question', None)
                    if t.get('focus'):
                        source['target_field_id'] = t['focus']['field_id']
                    sources.append(source)
                saved = []
                outcome = pipeline.run(qid, sources, {'previous_fields': previous, 'ask_counts': counts, 'focus': turn.get('focus')},
                                       save_call=lambda stage, entry: saved.append(stage))
                result = outcome['result']
                for stage in saved:
                    stages[stage] = stages.get(stage, 0) + 1
                reference = json.loads((REFERENCE / 'cases' / case['id'] / ('turn-%03d.json' % index)).read_text(encoding='utf-8'))
                if reference['record'].get('result') != result:
                    differing.append((case['id'], index))
                results[(case['id'], index)] = {'kind': 'evaluated', 'result': result}
                checkpoints += 1
                if result.get('decision') == 'invalid':
                    break
                previous = result.get('fields', {})
                target = result.get('target')
                if result.get('decision') == 'ask' and target:
                    counts[target] = counts.get(target, 0) + 1
        rows, summary = self.common.score_rows(data, results)
        print(f"\nfull45 backend replay: checkpoints {checkpoints}, provider requests {len(fake.calls)} "
              f"(judge {stages.get('judge', 0)}, verify {stages.get('verify', 0)}), cache misses {len(fake.misses)}, "
              f"differing from branch-check-v3j {len(differing)}, passes "
              f"{summary['all_critical_checkpoint_passes']}/{summary['planned_checkpoints']}")
        self.assertEqual(fake.misses, [])
        self.assertEqual(differing, [])
        self.assertEqual(checkpoints, 204)
        self.assertEqual((summary['all_critical_checkpoint_passes'], summary['planned_checkpoints']), (197, 204))


if __name__ == '__main__':
    unittest.main()
