import json
import logging
import os
import base64
from urllib.parse import urlparse

import httpx
from openai import OpenAI, DefaultHttpxClient
from pydantic import ValidationError

from app.ai.prompts import (
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
)
from app.schemas.memory import MemoryExtraction
from app.schemas.story_information import StoryInformation
from app.schemas.story_guidance import ConversationReply, SavedStoryReply


class LLMConfigurationError(Exception):
    pass


class LLMServiceError(Exception):
    pass


class LLMResponseFormatError(Exception):
    pass


class LLMClient:
    deepseek_compatible = True

    def warm_transport(self):
        """Prepare reusable API connections without generating model output."""
        from concurrent.futures import ThreadPoolExecutor
        bounded = self.client.with_options(timeout=3.0, max_retries=0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(bounded.models.list) for _ in range(2 if self.turn_parallel else 1)]
            for future in futures:
                future.result()

    def _structured(self, instruction, payload, schema, validate=None):
        response_schema = schema.model_json_schema()
        compact = schema.__name__ in ('CompactInterviewTurn','CompactInterviewAnalysis')
        if schema.__name__ == 'SelectedAnalysis' and payload.get('messages'):
            from copy import deepcopy
            from app.services.story_guidance import _direct_generation_command
            latest = payload['messages'][-1]
            request_schema = deepcopy(response_schema['$defs']['SourceRange'])
            request_schema['properties']['message_id']['const'] = latest['id']
            for key in ('start_fragment', 'end_fragment'):
                request_schema['properties'][key]['maximum'] = len(latest['fragments'])
            if _direct_generation_command(latest['content']):
                response_schema['properties']['generation_request'] = request_schema
                instruction += '\n最新用户明确请求整理，generation_request 必须引用该请求，不能为 null。'
            else:
                response_schema['properties']['generation_request'] = {'anyOf': [request_schema, {'type': 'null'}]}
            instruction += ('\ngeneration_request 如非 null，message_id 只能是最新用户消息 ' + latest['id']
                            + '；片段编号只使用该消息的 fragments，不引用之前相似的整理请求。其他信息维度仍可引用历史讲述。')
        if compact and payload.get('messages'):
            from app.services.story_guidance import _direct_generation_command, needs_boundary_notice
            latest = payload['messages'][-1]
            bounds = ', '.join(str(item['message_index']) + ':' + str(len(item['fragments']))
                               for item in payload['messages'])
            instruction += ('\n所有事实及兼容/矛盾引用的消息编号只能在 1 至 '
                            + str(len(payload['messages'])) + ' 之间；每条消息可用片段编号上限（消息:上限）为 '
                            + bounds + '。数组里的片段数字必须是原文 index，不能当作日期或句子数猜测。')
            # Keep the provider grammar stable across turns. Actual message and
            # fragment bounds, latest-request scope and intent still pass the
            # evidence validators before any reply or offer is committed.
            instruction += ('\ngeneration_request 非 null 时只能引用最新消息编号 '
                            + str(latest['message_index']) + '，片段编号范围 1 至 '
                            + str(len(latest['fragments'])) + '。')
            if _direct_generation_command(latest['content']):
                instruction += '\n最新用户明确请求整理，generation_request 必须引用最新请求，不能省略或为 null。'
            if needs_boundary_notice(latest['content'],payload['previous_information']['event']['status']!='missing'):
                instruction += ('\n本轮用户明确讲另一件具体的事，event_boundary 必须是 independent 并引用旧事及最新新事的原文范围。'
                                '六项基本信息沿用原事件，不自动拆分或保存。')
                if schema.__name__=='CompactInterviewTurn':
                    instruction += 'reply 自然提醒是另一段往事，由用户决定记录方式，action=continue。'
            if schema.__name__=='CompactInterviewTurn':
                response_schema['$defs']['ConversationReply']['properties']['text']['pattern'] = r'^[^你？?]*(?:[？?][^你？?]*)?$'
        policy = payload.get('generation_policy', {}) if schema is ConversationReply else None
        if policy is not None:
            # Make the action restriction explicit even when the user's request
            # or the analysis hint asks to save an incomplete/conflicting story.
            if not policy.get('allowed'):
                instruction += '\n本轮 action 必须是 continue，不能建议生成。即使用户要求保存，也先自然回应；允许追问时，只针对缺项或矛盾询问一个问题。不能声称已生成或保存。'
                response_schema['properties']['action']['enum'] = ['continue']
            elif policy.get('required_offer'):
                instruction += '\n本轮 action 必须是 offer_generation，请用自然语言提示先整理草稿、确认后再保存，不继续追问。'
                response_schema['properties']['action']['enum'] = ['offer_generation']
            if not policy.get('allow_question', True):
                instruction += '\n本轮不提问。用户希望暂停，给用户空间，只做自然回应。'
        # The strict wire schema is already sent in response_format. Duplicating
        # it as natural-language context increases prefill without adding facts.
        strict_draft = schema.__name__ == 'SelectedDraft' and getattr(self, 'nonthinking_json', False)
        strict_reply = schema is ConversationReply and getattr(self,'nonthinking_json',False)
        if strict_draft:
            instruction += '\nsource_indices 只能选择 accepted_user_excerpts 的 index，范围 1 至 ' + str(len(payload['accepted_user_excerpts'])) + '。'
        schema_text = (json.dumps(response_schema, ensure_ascii=False, separators=(',', ':'))
                       if getattr(self, 'provider_json_object_only', False) else
                       '' if compact or strict_draft or strict_reply else
                       json.dumps(response_schema, ensure_ascii=False))
        messages = [
            {'role': 'system', 'content': instruction + '\n只返回符合指定 schema 的紧凑单行 JSON，不使用 Markdown、缩进、换行或不必要的空格。\n' + schema_text},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ]
        transport = self
        if getattr(self, 'provider_json_object_only', False):
            from copy import copy
            transport = copy(self)
            transport.provider_response_format = {'type': 'json_object'}
        if compact or strict_draft or strict_reply:
            from copy import copy
            transport = copy(self)
            transport.provider_response_format = {
                'type': 'json_schema',
                'json_schema': {'name': 'memory_draft' if strict_draft else 'interview_reply' if strict_reply else
                                'interview_analysis' if schema.__name__=='CompactInterviewAnalysis' else 'interview_turn',
                                'strict': True, 'schema': response_schema},
            }
            if getattr(self, 'provider_json_object_only', False):
                transport.provider_response_format = {'type': 'json_object'}
        # One bounded repair for JSON/schema/evidence mistakes; never silently
        # relax fact checks. Transport failures still propagate immediately.
        for attempt in range(2):
            content = transport.chat(messages)
            try:
                value = schema.model_validate(json.loads(content))
                return validate(value) if validate else value
            except (json.JSONDecodeError, ValidationError, LLMResponseFormatError) as exc:
                reason = 'generation_policy' if isinstance(exc, LLMResponseFormatError) and 'Generation' in str(exc) else type(exc).__name__
                # No transcript, generated text, credentials or exception dumps.
                logging.getLogger('aimemories').warning('AI output rejected schema=%s attempt=%s reason=%s', schema.__name__, attempt + 1, reason)
                if attempt:
                    raise LLMResponseFormatError('Invalid evidence structure') from exc
                repair = ('输出未通过校验：' + str(exc) + '\n请修正并重新返回完整 JSON。只依据最初输入，')
                if compact:
                    repair += ('维度及原文引用仍使用最初 schema 的紧凑数组，不返回 UUID、value 或 source 对象。'
                               '不编造事实或感受，不声称已保存。'
                               '严格根据校验原因修正生成动作和暂停回应，不能通过删除真实矛盾改变就绪。'
                               '最新明确整理请求必须引用最新原文。六项维度及 latest_has_narrative 必填，缺失用 null，空的可选数组省略，修正后返回完整 JSON。')
                    if schema.__name__=='CompactInterviewTurn':
                        repair += 'reply 只含 text/action，用您，最多一个问题。'
                    else:
                        repair += '仅返回分析，不返回 reply。'
                elif schema is ConversationReply:
                    repair += ('只返回 text 和 action。text 面向记录对象，用您及自然中文，最多一个问题，'
                        '不编造或推断经历与感受，不出现任何后台状态词或英文标签。'
                        '例如不要说“等您 ready 了”，改为“您慢慢想，我在听”。'
                        '遵守最初 generation_policy，整理建议必须与 offer_generation 动作一致。')
                    if not policy.get('allowed'):
                        repair += '本轮 action 必须是 continue，不能建议生成。用户要求保存不代表可以绕过就绪判断；允许追问时，自然回应后只确认尚缺或矛盾的信息。'
                    elif policy.get('required_offer'):
                        repair += '本轮 action 必须是 offer_generation，用简短语言说明先整理草稿供用户确认，不再追问。'
                    if not policy.get('allow_question', True):
                        repair += '本轮不提问。用户希望暂停，只做自然回应，不能转到其他话题追问。'
                    if '多个问号' in str(exc):
                        repair += ('本轮修正只做自然承接，不再提任何问题。text 中问号数量必须为0；'
                            '把重复确认用户想讲什么的句子改成陈述，邀请用户继续讲也用句号收尾。')
                elif schema is SavedStoryReply:
                    repair += ('只返回 text，逐字提及原 saved_title，说明已经保存，'
                               '用您自然邀请分享其他事情，最多一个问题。不添加任何故事事实。')
                else:
                    repair += ('分析时 source 使用 message_id、start_fragment、end_fragment，两个编号必须选择该用户消息 fragments 的 index，单片段编号相同。不要输出或改写引文。'
                        '不要返回 value 或 source_message_ids。矛盾放在顶层 conflicts，status 使用五种规定值。'
                        '草稿只返回 text 和 source_indices，索引必须来自输入，保持记录对象第一人称。不得编造事实。')
                messages += [{'role': 'assistant', 'content': content}, {'role': 'user', 'content': repair}]

    def analyze_story(self, messages, person, previous):
        from app.ai.prompts import STORY_INFORMATION_PROMPT
        from app.services.story_guidance import validate_analysis
        from app.ai.evidence import SelectedAnalysis, resolve_analysis, source_fragments
        from types import SimpleNamespace
        from uuid import UUID
        sources = [SimpleNamespace(id=UUID(item['id']), role='user', type='text', content=item['content']) for item in messages]
        return self._structured(STORY_INFORMATION_PROMPT,
            {'record_subject': person, 'previous_information': previous.model_dump(mode='json', exclude={'conversation', 'analyzed_message_ids', 'narrative_sources'}),
             'messages': [{**item, 'fragments': [{'index': f['index'], 'text': f['text']} for f in source_fragments(item['content'])]} for item in messages]}, SelectedAnalysis, lambda value: validate_analysis(
                 resolve_analysis(value, {m.id: m.content for m in sources}), sources, previous))

    def converse(self, history, person, information, result, hint='', explicit_request=False, event_boundary=None):
        from app.ai.prompts import NATURAL_CONVERSATION_PROMPT
        from app.services.story_guidance import validate_reply, reply_policy
        policy = reply_policy(information, result, history, explicit_request, event_boundary, person)
        payload = {'record_subject': person, 'history': history,
                   'information': information.model_dump(mode='json', exclude={'conversation'}),
                   'readiness': result.model_dump(mode='json'), 'analysis_hint': hint,
                   'generation_policy': policy}
        return self._structured(NATURAL_CONVERSATION_PROMPT, payload, ConversationReply,
            lambda value: validate_reply(value, history, policy))

    def interview_turn(self, transcript, messages, history, person, previous, primary_person_id):
        # Opt-in configuration keeps drafting, openings and existing deployments
        # on their established model. No mutable state is shared across requests.
        if not getattr(self, 'turn_model', None):
            return None
        from copy import copy
        from app.ai.interview_turn import interview_turn, control_turn
        control = control_turn(messages,history,person,previous,primary_person_id)
        if control is not None:
            return control
        turn = copy(self)
        turn.model = self.turn_model
        turn.nonthinking_json = True
        # Bound losing requests as well as the visible reply. A transport failure
        # retains the user's durable message for the existing idempotent retry.
        short_input = len(transcript[-1]['content']) <= 200 if transcript else True
        turn.client = self.client.with_options(
            timeout=6.0 if short_input else 45.0,
            max_retries=0 if short_input else 1,
        )
        if getattr(self,'turn_strategy','race')=='parallel_tasks' and getattr(self,'turn_parallel',False):
            from app.ai.interview_turn import parallel_tasks
            interviewer = copy(turn)
            interviewer.model = getattr(self,'turn_secondary_model',None) or self.turn_model
            return parallel_tasks(turn,interviewer,transcript,messages,history,person,previous,primary_person_id)
        args = (turn, transcript, messages, history, person, previous, primary_person_id)
        if not getattr(self, 'turn_parallel', False):
            return interview_turn(*args)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from contextvars import copy_context
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='interview')
        try:
            models = (self.turn_model, getattr(self, 'turn_secondary_model', None) or self.turn_model)
            futures = []
            for model in models:
                branch = copy(turn)
                branch.model = model
                futures.append(pool.submit(copy_context().run, interview_turn, branch, *args[1:]))
            last_error = None
            for future in as_completed(futures):
                try:
                    # Only a fully resolved and validated turn can win. These
                    # workers never publish messages; the workflow writes once.
                    return future.result()
                except Exception as error:
                    last_error = error
            raise last_error
        finally:
            # An already running loser may finish its bounded model call, but
            # cannot delay the winner, touch the database or change this reply.
            pool.shutdown(wait=False, cancel_futures=True)

    def compose_story(self, evidence, person, information):
        from app.ai.prompts import GROUNDED_DRAFT_PROMPT
        from app.services.story_guidance import validate_draft
        from app.ai.evidence import SelectedDraft, resolve_draft
        # Raw dimension values can overlap a corrected or withheld excerpt. Only
        # filtered source fragments are facts; metadata supplies statuses alone.
        statuses = {key: {'status': getattr(information, key).status.value}
                    for key in ('people', 'event', 'time', 'place', 'feeling', 'detail')}
        writer = self
        if getattr(self, 'draft_model', None):
            from copy import copy
            writer = copy(self)
            writer.model = self.draft_model
            writer.nonthinking_json = True
            writer.client = self.client.with_options(timeout=10.0, max_retries=0)
        return writer._structured(GROUNDED_DRAFT_PROMPT,
            {'record_subject': person, 'information': statuses,
             'accepted_user_excerpts': [{'index': index, **item} for index, item in enumerate(evidence, 1)]},
             SelectedDraft, lambda value: validate_draft(resolve_draft(value, evidence), evidence, person, information))

    def acknowledge_saved_story(self, person, title):
        from copy import copy
        from app.ai.prompts import SAVED_STORY_REPLY_PROMPT
        from app.services.story_guidance import validate_saved_reply
        # This optional reply follows an already committed save. Bound each
        # attempt so an unavailable provider cannot hold the save UI for minutes.
        bounded = copy(self)
        bounded.client = self.client.with_options(timeout=6.0, max_retries=0)
        return bounded._structured(SAVED_STORY_REPLY_PROMPT,
            {'record_subject': person, 'saved_title': title}, SavedStoryReply,
            lambda value: validate_saved_reply(value, title))

    def __init__(self) -> None:

        encoded_api_key = os.getenv('LLM_API_KEY_B64')
        if encoded_api_key:
            try:
                api_key = base64.b64decode(encoded_api_key, validate=True).decode('utf-8')
            except (ValueError, UnicodeDecodeError) as error:
                raise LLMConfigurationError('LLM_API_KEY_B64 is invalid') from error
        else:
            api_key = os.getenv('LLM_API_KEY') or os.getenv('DASHSCOPE_API_KEY')

        base_url = os.getenv('LLM_BASE_URL') or os.getenv('DASHSCOPE_BASE_URL') or ''

        self.model = os.getenv(
            "LLM_MODEL"
        )

        self.provider_json_object_only = urlparse(base_url).hostname == 'api.deepseek.com'

        if not api_key:
            raise LLMConfigurationError(
                "LLM_API_KEY or DASHSCOPE_API_KEY is not configured"
            )

        if not base_url:
            raise LLMConfigurationError(
                "LLM_BASE_URL or DASHSCOPE_BASE_URL is not configured"
            )

        if not self.model:
            raise LLMConfigurationError(
                "LLM_MODEL is not configured"
            )

        self.turn_model = os.getenv('LLM_TURN_MODEL', '').strip() or None
        self.turn_secondary_model = os.getenv('LLM_TURN_SECONDARY_MODEL', '').strip() or None
        self.draft_model = os.getenv('LLM_DRAFT_MODEL', '').strip() or None
        parallel = os.getenv('LLM_TURN_PARALLEL', 'false').strip().lower()
        if parallel not in ('true', 'false'):
            raise LLMConfigurationError('LLM_TURN_PARALLEL must be true or false')
        self.turn_parallel = parallel == 'true'
        self.turn_strategy = os.getenv('LLM_TURN_STRATEGY','race').strip().lower()
        if self.turn_strategy not in ('race','parallel_tasks'):
            raise LLMConfigurationError('LLM_TURN_STRATEGY must be race or parallel_tasks')

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=45.0,
            max_retries=1,
            http_client=DefaultHttpxClient(limits=httpx.Limits(
                max_connections=1000, max_keepalive_connections=100,
                keepalive_expiry=120.0,
            )),
        )

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        try:

            response = (
                self.client
                .chat
                .completions
                .create(
                    model=self.model,
                    messages=messages,
                    temperature=0.4,
                    **({'extra_body': {'thinking': {'type': 'disabled'}},
                        'response_format': getattr(self, 'provider_response_format', {'type': 'json_object'})}
                       if getattr(self, 'provider_json_object_only', False) else
                       {'extra_body': {'enable_thinking': False},
                        'response_format': getattr(self, 'provider_response_format', {'type': 'json_object'})}
                       if getattr(self, 'nonthinking_json', False) else {}),
                )
            )

            content = (
                response
                .choices[0]
                .message
                .content
            )

            if not content:
                raise LLMServiceError(
                    "LLM returned empty content"
                )

            return content

        except LLMServiceError:
            raise

        except Exception as exc:
            raise LLMServiceError(
                "LLM request failed"
            ) from exc

    def extract_memory(
        self,
        raw_content: str,
    ) -> MemoryExtraction:
        """
        向 AI 发送：
        - system: 提取规则（要求返回 JSON）
        - user: 访谈原文 raw_content
        再把模型返回的 JSON 解析成 MemoryExtraction。
        """

        # 1) 真正请求 AI（内部会调 OpenAI compatible API）
        content = self.chat(
            [
                {
                    "role": "system",
                    "content": MEMORY_EXTRACTION_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": raw_content,
                },
            ]
        )

        # 2) content 是模型返回的字符串，期望是 JSON
        try:
            data = json.loads(content)
            return MemoryExtraction.model_validate(data)

        except (
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise LLMResponseFormatError(
                "LLM returned invalid memory structure"
            ) from exc
