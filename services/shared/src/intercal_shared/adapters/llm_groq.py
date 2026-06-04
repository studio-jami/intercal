"""Groq LLM adapter (free tier alternative).

Requires: `intercal-shared[llm-groq]` (groq) and GROQ_API_KEY.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from intercal_shared.ports.llm import LlmError, LlmExtractionError, LlmResponse

_log = logging.getLogger(__name__)


class GroqLlmAdapter:
    """LlmPort implementation backed by the Groq API.

    Parameters
    ----------
    api_key:
        Groq API key.  A clear error is raised at construction time if absent.
    model:
        Groq model name, e.g. ``"llama-3.3-70b-versatile"`` or ``"mixtral-8x7b-32768"``.
    """

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is required for the Groq LLM adapter. "
                "Set it in your .env or environment (GROQ_API_KEY=...)."
            )
        try:
            from groq import AsyncGroq  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "groq is required for the Groq LLM adapter. "
                "Install it with: pip install 'intercal-shared[llm-groq]'"
            ) from exc

        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        _log.info("Groq LLM adapter initialised (model=%r)", model)

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
            raise LlmError(f"Groq completion failed: {exc}") from exc

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        schema_hint = json.dumps(schema, indent=2)
        full_prompt = (
            f"{prompt}\n\nRespond ONLY with a JSON object matching this schema:\n{schema_hint}"
        )
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": full_prompt})
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
                    f"Groq returned non-JSON response: {raw[:200]!r}"
                ) from parse_exc
            return result
        except LlmExtractionError:
            raise
        except Exception as exc:
            raise LlmError(f"Groq structured extraction failed: {exc}") from exc
