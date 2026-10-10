import json
import logging
import os

from openai import OpenAI
from pydantic import ValidationError

from app.ai.prompts import (
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
)
from app.schemas.memory import MemoryExtraction
from app.schemas.story_information import StoryInformation
from app.schemas.story_guidance import ConversationReply


class LLMConfigurationError(Exception):
    pass


class LLMServiceError(Exception):
    pass


class LLMResponseFormatError(Exception):
    pass


class LLMClient:

    def _structured(self, instruction, payload, schema, validate=None):
        response_schema = schema.model_json_schema()
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
        messages = [
            {'role': 'system', 'content': instruction + '\n只返回符合以下 schema 的 JSON，不使用 Markdown：\n'
             + json.dumps(response_schema, ensure_ascii=False)},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ]
        # One bounded repair for JSON/schema/evidence mistakes; never silently
        # relax fact checks. Transport failures still propagate immediately.
        for attempt in range(2):
            content = self.chat(messages)
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
                if schema is ConversationReply:
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
            {'record_subject': person, 'previous_information': previous.model_dump(mode='json', exclude={'conversation', 'analyzed_message_ids'}),
             'messages': [{**item, 'fragments': [{'index': f['index'], 'text': f['text']} for f in source_fragments(item['content'])]} for item in messages]}, SelectedAnalysis, lambda value: validate_analysis(
                 resolve_analysis(value, {m.id: m.content for m in sources}), sources))

    def converse(self, history, person, information, result, hint='', explicit_request=False):
        from app.ai.prompts import NATURAL_CONVERSATION_PROMPT
        from app.services.story_guidance import validate_reply, reply_policy
        policy = reply_policy(information, result, history, explicit_request)
        payload = {'record_subject': person, 'history': history,
                   'information': information.model_dump(mode='json', exclude={'conversation'}),
                   'readiness': result.model_dump(mode='json'), 'analysis_hint': hint,
                   'generation_policy': policy}
        return self._structured(NATURAL_CONVERSATION_PROMPT, payload, ConversationReply,
            lambda value: validate_reply(value, history, policy))

    def compose_story(self, evidence, person, information):
        from app.ai.prompts import GROUNDED_DRAFT_PROMPT
        from app.services.story_guidance import validate_draft
        from app.ai.evidence import SelectedDraft, resolve_draft
        # Raw dimension values can overlap a corrected or withheld excerpt. Only
        # filtered source fragments are facts; metadata supplies statuses alone.
        statuses = {key: {'status': getattr(information, key).status.value}
                    for key in ('people', 'event', 'time', 'place', 'feeling', 'detail')}
        return self._structured(GROUNDED_DRAFT_PROMPT,
            {'record_subject': person, 'information': statuses,
             'accepted_user_excerpts': [{'index': index, **item} for index, item in enumerate(evidence, 1)]},
             SelectedDraft, lambda value: validate_draft(resolve_draft(value, evidence), evidence, person, information))

    def __init__(self) -> None:

        api_key = os.getenv(
            "DASHSCOPE_API_KEY"
        )

        base_url = os.getenv(
            "DASHSCOPE_BASE_URL"
        )

        self.model = os.getenv(
            "LLM_MODEL"
        )

        if not api_key:
            raise LLMConfigurationError(
                "DASHSCOPE_API_KEY is not configured"
            )

        if not base_url:
            raise LLMConfigurationError(
                "DASHSCOPE_BASE_URL is not configured"
            )

        if not self.model:
            raise LLMConfigurationError(
                "LLM_MODEL is not configured"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=45.0,
            max_retries=1,
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
