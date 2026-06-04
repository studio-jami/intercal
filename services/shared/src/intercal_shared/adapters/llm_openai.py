"""OpenAI LLM adapter.

Requires: `intercal-shared[llm-openai]` (openai) and OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from intercal_shared.ports.llm import LlmError, LlmExtractionError, LlmResponse

_log = logging.getLogger(__name__)


class OpenAILlmAdapter:
    """LlmPort implementation backed by the OpenAI Chat Completions API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  A clear error is raised at construction time if absent.
    model:
        OpenAI model name, e.g. ``"gpt-4o-mini"`` or ``"gpt-4o"``.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for the OpenAI LLM adapter. "
                "Set it in your .env or environment (OPENAI_API_KEY=...)."
            )
        try:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openai is required for the OpenAI LLM adapter. "
                "Install it with: pip install 'intercal-shared[llm-openai]'"
            ) from exc

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        _log.info("OpenAI LLM adapter initialised (model=%r)", model)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LlmResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            return LlmResponse(
                text=text,
                model=self._model,
                input_tokens=response.usage.prompt_tokens if response.usage else None,
                output_tokens=response.usage.completion_tokens if response.usage else None,
            )
        except Exception as exc:
            raise LlmError(f"OpenAI completion failed: {exc}") from exc

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            try:
                result: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError as parse_exc:
                raise LlmExtractionError(
                    f"OpenAI returned non-JSON response: {raw[:200]!r}"
                ) from parse_exc
            return result
        except LlmExtractionError:
            raise
        except Exception as exc:
            raise LlmError(f"OpenAI structured extraction failed: {exc}") from exc
