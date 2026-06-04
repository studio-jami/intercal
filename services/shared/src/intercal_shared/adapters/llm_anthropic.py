"""Anthropic Claude LLM adapter.

Requires: `intercal-shared[llm-anthropic]` (anthropic) and ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from intercal_shared.ports.llm import LlmError, LlmExtractionError, LlmResponse

_log = logging.getLogger(__name__)


class AnthropicLlmAdapter:
    """LlmPort implementation backed by the Anthropic Messages API.

    Parameters
    ----------
    api_key:
        Anthropic API key.  A clear error is raised at construction time if absent.
    model:
        Claude model name, e.g. ``"claude-sonnet-4-5"`` or ``"claude-haiku-4-5"``.
    """

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for the Anthropic LLM adapter. "
                "Set it in your .env or environment (ANTHROPIC_API_KEY=...)."
            )
        try:
            import anthropic as _anthropic  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "anthropic is required for the Anthropic LLM adapter. "
                "Install it with: pip install 'intercal-shared[llm-anthropic]'"
            ) from exc

        self._client = _anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        _log.info("Anthropic LLM adapter initialised (model=%r)", model)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LlmResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            response = await self._client.messages.create(**kwargs)
            text = "".join(block.text for block in response.content if hasattr(block, "text"))
            return LlmResponse(
                text=text,
                model=self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as exc:
            raise LlmError(f"Anthropic completion failed: {exc}") from exc

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        schema_hint = json.dumps(schema, indent=2)
        tool_definition: dict[str, Any] = {
            "name": "extract_structured",
            "description": "Extract structured data from the provided text.",
            "input_schema": schema,
        }
        full_prompt = f"{prompt}\n\nSchema:\n{schema_hint}"
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": full_prompt}],
            "tools": [tool_definition],
            "tool_choice": {"type": "tool", "name": "extract_structured"},
        }
        if system:
            kwargs["system"] = system
        try:
            response = await self._client.messages.create(**kwargs)
            for block in response.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    result: dict[str, Any] = block.input  # type: ignore[assignment]
                    return result
            # Fallback: try to parse text content as JSON
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            try:
                return json.loads(text)  # type: ignore[no-any-return]
            except json.JSONDecodeError as parse_exc:
                raise LlmExtractionError(
                    f"Anthropic returned non-JSON response: {text[:200]!r}"
                ) from parse_exc
        except LlmExtractionError:
            raise
        except Exception as exc:
            raise LlmError(f"Anthropic structured extraction failed: {exc}") from exc
