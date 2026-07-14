"""Small OpenAI-compatible client configured for the official DeepSeek API."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from .exceptions import ExternalServiceError
from .settings import Settings


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        if settings.deepseek_api_key is None:
            raise ExternalServiceError("DEEPSEEK_API_KEY is not configured")
        self.model = settings.deepseek_model
        self._client = OpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=0,
                stream=False,
            )
            content = response.choices[0].message.content
            if not content:
                raise ExternalServiceError("DeepSeek returned empty JSON content")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ExternalServiceError("DeepSeek JSON response is not an object")
            return parsed
        except ExternalServiceError:
            raise
        except Exception as exc:
            raise ExternalServiceError(f"DeepSeek JSON request failed: {exc}") from exc

    def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1600,
    ) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.2,
                stream=False,
            )
            content = response.choices[0].message.content
            if not content:
                raise ExternalServiceError("DeepSeek returned empty text content")
            return content.strip()
        except ExternalServiceError:
            raise
        except Exception as exc:
            raise ExternalServiceError(f"DeepSeek text request failed: {exc}") from exc


def format_evidence_for_prompt(evidence: Sequence[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{item['evidence_id']}] {item['title']}\n{item['excerpt']}\nURL: {item['source_url']}"
        for item in evidence
    )

