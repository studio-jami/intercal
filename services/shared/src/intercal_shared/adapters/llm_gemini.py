"""Google Gemini / Vertex AI LLM adapter.

Requires: ``intercal-shared[llm-gemini]`` (google-genai>=1.0.0; validated against 2.8.0).

Two credential modes — same adapter class, selected at construction time:

**Gemini API key mode** (``vertexai=False``, default):
    Requires ``GEMINI_API_KEY``.  Free-tier daily limits apply.
    ``Client(api_key=...)`` per the google-genai v2 SDK.

**Vertex AI mode** (``vertexai=True``):
    Uses Application Default Credentials (ADC) or an explicit service-account
    key file.  Requires ``VERTEX_PROJECT`` and ``VERTEX_LOCATION``.
    Primary provider per the program posture (yrka.io trial credits, ADC).
    ``Client(vertexai=True, project=..., location=...)`` per the
    google-genai v2 SDK (``project`` + ``location`` required for Vertex).

Vertex model names are the same as the Gemini API names (``gemini-2.5-flash``
etc.) — the SDK routes them correctly based on the ``vertexai`` flag.

Structured extraction uses the SDK's native ``response_schema`` +
``response_mime_type='application/json'`` (server-side JSON-Schema enforcement,
available across actively supported Gemini models) and then validates the result
client-side against the caller's schema (defence in depth).
"""

from __future__ import annotations

import logging
from typing import Any

from intercal_shared.adapters._llm_common import (
    consume_budget,
    parse_json_object,
    run_structured_with_retries,
    with_timeout,
)
from intercal_shared.ports.llm import (
    LlmAuthError,
    LlmError,
    LlmRateLimitError,
    LlmResponse,
    LlmTimeoutError,
    RequestBudget,
    StructuredResult,
)

_log = logging.getLogger(__name__)


def _classify_provider_error(exc: Exception, *, mode: str, op: str) -> LlmError:
    """Map an arbitrary SDK exception to the port error taxonomy."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if any(s in name or s in text for s in ("permissiondenied", "unauthenticated", "permission")):
        return LlmAuthError(f"{mode} {op} failed (auth): {exc}")
    if "401" in text or "403" in text or "credential" in text or "api key" in text:
        return LlmAuthError(f"{mode} {op} failed (auth): {exc}")
    if "resourceexhausted" in name or "rate" in text or "quota" in text or "429" in text:
        return LlmRateLimitError(f"{mode} {op} failed (rate limit): {exc}")
    if "timeout" in name or "deadline" in text or "timeout" in text:
        return LlmTimeoutError(f"{mode} {op} failed (timeout): {exc}")
    return LlmError(f"{mode} {op} failed: {exc}")


class GeminiLlmAdapter:
    """LlmPort implementation backed by Google Gemini / Vertex AI via google-genai v2.

    Parameters
    ----------
    api_key:
        Gemini API key for API-key mode.  Mutually exclusive with *vertexai=True*.
        A clear error is raised at construction time if absent when
        ``vertexai=False``.
    model:
        Model identifier, e.g. ``"gemini-2.5-flash"`` (the same name works for
        both Gemini API and Vertex AI modes).
    vertexai:
        If ``True`` the adapter uses Vertex AI mode.  ADC (or the JSON key file
        at ``GOOGLE_APPLICATION_CREDENTIALS``) must be valid.
        Requires *project* and *location*.
    project:
        GCP project ID.  Required when ``vertexai=True``.
    location:
        GCP region, e.g. ``"us-east4"``.  Required when ``vertexai=True``.
    default_max_tokens:
        Output-token cap applied when a caller does not pass ``max_tokens``
        (wired from ``LLM_MAX_OUTPUT_TOKENS``).
    timeout:
        Per-call timeout in seconds (``None`` disables).
    budget:
        Optional :class:`RequestBudget` consulted before each call to enforce the
        daily request cap at the port boundary.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        *,
        vertexai: bool = False,
        project: str = "",
        location: str = "us-east4",
        default_max_tokens: int = 2048,
        timeout: float | None = 60.0,
        budget: RequestBudget | None = None,
    ) -> None:
        try:
            import google.genai as genai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for the Gemini/Vertex LLM adapter. "
                "Install it with: pip install 'intercal-shared[llm-gemini]'"
            ) from exc

        if vertexai:
            if not project:
                raise ValueError(
                    "VERTEX_PROJECT is required for Vertex AI mode. "
                    "Set it in your .env (VERTEX_PROJECT=<gcp-project-id>)."
                )
            # ADC resolution order: GOOGLE_APPLICATION_CREDENTIALS env var,
            # then gcloud application-default, then metadata server.
            # Explicit SA key path is set via GOOGLE_APPLICATION_CREDENTIALS.
            self._client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
            _log.info(
                "Gemini/Vertex LLM adapter initialised (model=%r, project=%r, location=%r)",
                model,
                project,
                location,
            )
        else:
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is required for the Gemini LLM adapter (API-key mode). "
                    "Set it in your .env or environment (GEMINI_API_KEY=...). "
                    "To use Vertex AI instead, set LLM_PROVIDER=vertex."
                )
            self._client = genai.Client(api_key=api_key)
            _log.info("Gemini LLM adapter initialised (model=%r, mode=api-key)", model)

        self._genai = genai
        self._model = model
        self._vertexai = vertexai
        self._default_max_tokens = default_max_tokens
        self._timeout = timeout
        self._budget = budget

    @property
    def model(self) -> str:
        """Model identifier used by this adapter."""
        return self._model

    @staticmethod
    def _usage(response: Any) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None, None
        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None) or getattr(
            usage, "total_token_count", None
        )
        return input_tokens, output_tokens

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        import asyncio

        consume_budget(self._budget)
        mode = "Vertex" if self._vertexai else "Gemini"
        config: dict[str, Any] = {
            "max_output_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
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

        try:
            response = await with_timeout(loop.run_in_executor(None, _sync), self._timeout)
        except LlmError:
            raise
        except Exception as exc:
            raise _classify_provider_error(exc, mode=mode, op="completion") from exc

        input_tokens, output_tokens = self._usage(response)
        return LlmResponse(
            text=response.text or "",
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResult:
        import asyncio

        mode = "Vertex" if self._vertexai else "Gemini"
        loop = asyncio.get_event_loop()

        async def _attempt() -> StructuredResult:
            consume_budget(self._budget)
            config: dict[str, Any] = {
                "max_output_tokens": max_tokens
                if max_tokens is not None
                else self._default_max_tokens,
                "temperature": 0.0,
                "response_mime_type": "application/json",
                # Disable thinking for structured extraction.  On the 2.5 "thinking"
                # models, reasoning tokens are drawn from the same output budget; a
                # thinking spike truncates the JSON mid-object so the whole chunk
                # parses-fails and yields zero claims (the dominant under-extraction
                # cause observed in W3 live runs).  thinking_budget=0 spends the full
                # budget on the answer, making schema-bound extraction deterministic.
                # (Ignored by non-thinking models.)
                "thinking_config": self._genai.types.ThinkingConfig(thinking_budget=0),
            }
            # Native server-side JSON-Schema enforcement when a non-empty schema is given.
            if schema:
                config["response_schema"] = schema
            if system:
                config["system_instruction"] = system

            def _sync() -> Any:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._genai.types.GenerateContentConfig(**config),
                )

            try:
                response = await with_timeout(loop.run_in_executor(None, _sync), self._timeout)
            except LlmError:
                raise
            except Exception as exc:
                raise _classify_provider_error(exc, mode=mode, op="structured extraction") from exc

            data = parse_json_object(response.text or "", provider=mode)
            input_tokens, output_tokens = self._usage(response)
            return StructuredResult(
                data=data,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return await run_structured_with_retries(
            attempt=_attempt, schema=schema, provider=mode
        )
