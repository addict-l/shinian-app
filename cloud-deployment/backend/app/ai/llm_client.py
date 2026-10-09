import json
import os

from openai import OpenAI
from pydantic import ValidationError

from app.ai.prompts import (
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
)
from app.schemas.memory import MemoryExtraction


class LLMConfigurationError(Exception):
    pass


class LLMServiceError(Exception):
    pass


class LLMResponseFormatError(Exception):
    pass


class LLMClient:

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
