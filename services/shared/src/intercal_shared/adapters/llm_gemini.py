"""Google Gemini LLM adapter (free-tier default: gemini-2.5-flash).

Requires: `intercal-shared[llm-gemini]` (google-genai>=1.0.0) and GEMINI_API_KEY.

Uses the official google-genai SDK (v1.x, imports as ``google.genai``).
Structured extraction uses JSON-mode generation_config.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from intercal_shared.ports.llm import LlmError, LlmExtractionError, LlmResponse

_log = logging.getLogger(__name__)


class GeminiLlmAdapter:
    """LlmPort implementation backed by Google Gemini via google-genai (v1.x).

    Parameters
    ----------
    api_key:
        Gemini API key.  A clear error is raised at construction time if absent.
    model:
        Gemini model name, e.g. ``"gemini-2.5-flash"`` (free default).
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for the Gemini LLM adapter. "
                "Set it in your .env or environment (GEMINI_API_KEY=...)."
            )
        try:
            # google-genai >= 1.0.0 imports as google.genai (not google.generativeai).
            import google.genai as genai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for the Gemini LLM adapter. "
                "Install it with: pip install 'intercal-shared[llm-gemini]'"
            ) from exc

        self._client = genai.Client(api_key=api_key)
        self._genai = genai
        self._model = model
        _log.info("Gemini LLM adapter initialised (model=%r)", model)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LlmResponse:
        import asyncio

        try:
            config: dict[str, Any] = {
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
            if system:
                config["system_instruction"] = system

            loop = asyncio.get_event_loop()

            def _sync() -> Any:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._genai.types.GenerateContentConfig(**config),
                )

            response = await loop.run_in_executor(None, _sync)
            text: str = response.text
            return LlmResponse(text=text, model=self._model)
        except Exception as exc:
            raise LlmError(f"Gemini completion failed: {exc}") from exc

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        import asyncio

        try:
            schema_hint = json.dumps(schema, indent=2)
            full_prompt = (
                f"{prompt}\n\nRespond ONLY with a JSON object matching this schema:\n{schema_hint}"
            )
            config: dict[str, Any] = {
                "max_output_tokens": max_tokens,
                "temperature": 0.0,
                "response_mime_type": "application/json",
            }
            if system:
                config["system_instruction"] = system

            loop = asyncio.get_event_loop()

            def _sync() -> Any:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=full_prompt,
                    config=self._genai.types.GenerateContentConfig(**config),
                )

            response = await loop.run_in_executor(None, _sync)
            raw = response.text.strip()
            try:
                result: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError as parse_exc:
                raise LlmExtractionError(
                    f"Gemini returned non-JSON response: {raw[:200]!r}"
                ) from parse_exc
            return result
        except LlmExtractionError:
            raise
        except Exception as exc:
            raise LlmError(f"Gemini structured extraction failed: {exc}") from exc
