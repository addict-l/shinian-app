"""Pluggable backends for the simulated elder (persona requests of v6flow / interview.elder_call).

Rule: DeepSeek never plays the elder (it is the system under test). Backends:
- queue  (default): the file queue <runs>/persona-queue served by agent workers (Claude Haiku so far, see WORKER.md;
          a Codex / GPT agent follows docs/prototypes/memoir-v1/handoffs/PERSONA_WORKER.md). A worker may tag its
          answers with SHINIAN_WORKER_MODEL (stored as the answer's model).
- openai: the OpenAI chat completions API (OPENAI_API_KEY from the environment only; OPENAI_PERSONA_MODEL,
          OPENAI_BASE_URL, OPENAI_PERSONA_CONCURRENCY). The request is the same instructions + input + output note
          a queue worker sees, with the worker rules of PERSONA_WORKER.md in front.

Both look up the same content-addressed cache first (HAIKU_CACHE/persona, key = queue_worker.request_key of the
unchanged request), so every elder answer already given -- by Haiku so far -- is reused as is and a replay costs
nothing. New answers are stored under the same key with the answering model in "model_requested" (it reaches each
elder message's calls[].model), so a run records which model played the elder for every answer.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request

import queue_worker as qw

# The persona rules of the Haiku worker instructions (simulate/WORKER.md), given verbatim to an API model.
WORKER_RULES = '''你在拾年采访测试里扮演接受回忆录采访的老人。规则：
- 只讲“你的资料”里有的事实；资料里没有的，就照指令说记不清、没什么印象，绝不编造人名、地名、年份、经历、感受。
- 严格照“本轮表现”的要求（长短、是否跑题、是否不想多说、是否要歇会儿、是否带语音错字）来说，这是测试设计的一部分，不要自行改成“更好的回答”。
- 只回答采访者最后那一句；用口语、第一人称、简体字。
- 只输出指令要求的 JSON：不加解释、不加 markdown 代码块、不加多余字段。'''


def make(name=None):
    name = (name or os.environ.get('SHINIAN_PERSONA_BACKEND') or 'queue').strip().lower()
    if name == 'queue':
        return qw.HaikuQueue('persona')
    if name == 'openai':
        return OpenAIPersona()
    raise SystemExit('unknown persona backend %r (queue | openai)' % name)


class PersonaError(RuntimeError):
    pass


class OpenAIPersona:
    """Same interface as queue_worker.HaikuQueue (submit / poll / sent / cached / waiting)."""

    def __init__(self):
        self.key = os.environ.get('OPENAI_API_KEY', '').strip()
        self.model = os.environ.get('OPENAI_PERSONA_MODEL', '').strip()
        if not self.key or not self.model:
            raise SystemExit('persona backend openai needs OPENAI_API_KEY and OPENAI_PERSONA_MODEL in the environment')
        self.base = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        self.tag = 'openai:' + self.model
        self.name = 'persona'
        self.cache = qw.HAIKU_CACHE / 'persona'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(int(os.environ.get('OPENAI_PERSONA_CONCURRENCY', '8') or 8))
        self.futures = {}
        self.sent = self.cached = 0

    def submit(self, instructions, input_text, output_note, validate_spec, meta=None):
        key = qw.request_key('persona', instructions, input_text, {'note': output_note, 'validate': validate_spec})
        rid = 'p-' + key[:16]
        hit = self.cache / f'{key}.json'
        if hit.exists():
            self.cached += 1
            return rid, {**qw._read(hit), 'cached': True}
        if rid not in self.futures:
            req = {'instructions': instructions, 'input': input_text, 'output_note': output_note, 'validate': validate_spec}
            self.futures[rid] = (key, time.time(), self.pool.submit(self._answer, req))
        return rid, None

    def poll(self, rid):
        key, t0, fut = self.futures[rid]
        if not fut.done():
            return None
        out, usage = fut.result()  # a PersonaError stops the run (rerun with --resume; answers so far are cached)
        row = {'id': rid, 'ok': True, 'output': out, 'content': json.dumps(out, ensure_ascii=False),
               'model_requested': self.tag, 'answered_at': time.time(), 'usage': usage}
        hit = self.cache / f'{key}.json'
        if not hit.exists():
            qw._write_atomic(hit, row)
        del self.futures[rid]
        self.sent += 1
        return {**row, 'seconds': round(time.time() - t0, 1)}

    def waiting(self):
        return sum(1 for _, _, f in self.futures.values() if not f.done())

    def _post(self, body):
        req = urllib.request.Request(self.base + '/chat/completions', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     method='POST', headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _answer(self, req):
        messages = [{'role': 'system', 'content': WORKER_RULES + '\n\n===== 指令（你这次要扮演的角色和规则，只照它做）=====\n'
                     + req['instructions'].rstrip()},
                    {'role': 'user', 'content': '===== 输入 =====\n' + req['input'].rstrip() + '\n\n===== 输出要求 =====\n'
                     + (req.get('output_note') or '只输出一个 JSON 对象。')}]
        usage = {}
        for attempt in range(6):
            body = {'model': self.model, 'messages': messages, 'response_format': {'type': 'json_object'}}
            if os.environ.get('OPENAI_PERSONA_TEMPERATURE'):
                body['temperature'] = float(os.environ['OPENAI_PERSONA_TEMPERATURE'])
            try:
                raw = self._post(body)
            except urllib.error.HTTPError as e:
                if e.code in (408, 409, 425, 429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(min(30, 2 ** attempt + 1))
                    continue
                raise PersonaError('OpenAI persona call failed: HTTP %s' % e.code) from None
            except Exception as e:  # network
                if attempt < 5:
                    time.sleep(min(20, 2 ** attempt + 1))
                    continue
                raise PersonaError('OpenAI persona call failed: %s' % type(e).__name__) from None
            for k, v in (raw.get('usage') or {}).items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
            text = ((raw.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
            try:
                out = json.loads(text)
            except ValueError:
                out, errs = None, ['不是合法 JSON']
            else:
                errs = qw.validate(req, out)
            if not errs:
                return out, usage
            # same as a queue worker: fix the JSON and hand it in again
            messages = messages[:2] + [{'role': 'assistant', 'content': text},
                                       {'role': 'user', 'content': 'ERROR：答案没通过检查：' + '；'.join(errs) + '。修正后重新只输出 JSON。'}]
        raise PersonaError('OpenAI persona answer invalid after retries')
