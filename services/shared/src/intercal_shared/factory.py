"""Adapter factory — construct the configured adapter for each port.

Usage
-----
    from intercal_shared.config import settings
    from intercal_shared.factory import make_storage, make_embeddings, make_llm, make_queue

    storage   = make_storage(settings)
    embeddings = make_embeddings(settings)
    llm       = make_llm(settings)
    queue     = make_queue(settings)

All functions are synchronous constructors (adapters do any async init lazily
or inside methods).  Call them once at startup; pass the resulting object to
repositories and job functions.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from intercal_shared.config import Settings
from intercal_shared.llm_runtime import (
    FallbackLlm,
    UsageRecordingLlm,
    llm_daily_request_usage,
    llm_provider_budget_states,
)
from intercal_shared.ports.llm import InMemoryRequestBudget, LlmPort, RequestBudget

if TYPE_CHECKING:
    from intercal_shared.adapters.embeddings_local import LocalEmbeddingsAdapter
    from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter
    from intercal_shared.adapters.llm_anthropic import AnthropicLlmAdapter
    from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter
    from intercal_shared.adapters.llm_groq import GroqLlmAdapter
    from intercal_shared.adapters.llm_openai import OpenAILlmAdapter
    from intercal_shared.adapters.queue_postgres import PostgresQueueAdapter
    from intercal_shared.adapters.queue_redis import RedisQueueAdapter
    from intercal_shared.adapters.scheduler_local import LocalSchedulerAdapter
    from intercal_shared.adapters.storage_s3 import S3StorageAdapter

_log = logging.getLogger(__name__)


def make_storage(cfg: Settings) -> S3StorageAdapter:
    """Return the configured object storage adapter."""
    if cfg.storage_provider == "s3":
        from intercal_shared.adapters.storage_s3 import S3StorageAdapter

        return S3StorageAdapter(
            endpoint_url=cfg.s3_endpoint,
            region=cfg.s3_region,
            bucket=cfg.s3_bucket,
            access_key_id=cfg.s3_access_key_id,
            secret_access_key=cfg.s3_secret_access_key,
            force_path_style=cfg.s3_force_path_style,
        )
    # If new providers are added, extend here.
    raise ValueError(f"Unsupported storage_provider: {cfg.storage_provider!r}")


def make_embeddings(
    cfg: Settings,
) -> LocalEmbeddingsAdapter | OpenAIEmbeddingsAdapter:
    """Return the configured embeddings adapter."""
    if cfg.embeddings_provider == "local":
        from intercal_shared.adapters.embeddings_local import LocalEmbeddingsAdapter

        return LocalEmbeddingsAdapter(
            model_name=cfg.embeddings_model,
            dim=cfg.embeddings_dim,
        )
    if cfg.embeddings_provider == "openai":
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        return OpenAIEmbeddingsAdapter(
            api_key=cfg.openai_api_key or "",
            model_name=cfg.embeddings_model,
            dim=cfg.embeddings_dim if cfg.embeddings_dim else None,
        )
    raise ValueError(f"Unsupported embeddings_provider: {cfg.embeddings_provider!r}")


def make_request_budget(cfg: Settings) -> RequestBudget:
    """Construct the daily LLM request budget from ``LLM_DAILY_REQUEST_BUDGET``.

    A process-local counter by default.  ``<= 0`` disables the cap.  A distributed
    deployment may substitute a durable implementation (Plan 04 observability).
    """
    return InMemoryRequestBudget(limit=cfg.llm_daily_request_budget)


def make_llm(
    cfg: Settings,
    budget: RequestBudget | None = None,
    *,
    provider: str | None = None,
) -> GeminiLlmAdapter | GroqLlmAdapter | AnthropicLlmAdapter | OpenAILlmAdapter:
    """Return the configured LLM adapter, wired with port-policy knobs.

    Every adapter is constructed with the resource-budget output-token cap
    (``LLM_MAX_OUTPUT_TOKENS``), request timeout (``LLM_TIMEOUT_SECONDS``), and an
    optional :class:`RequestBudget` (defaults to one built from
    ``LLM_DAILY_REQUEST_BUDGET``) so the daily cap is enforced at the port boundary.

    Provider selection via ``provider`` (or ``LLM_PROVIDER`` when omitted):

    - ``vertex`` — Vertex AI mode; resolves project from ``VERTEX_PROJECT`` (or
      ``GCLOUD_PROJECT_ID``) and ADC.  If ``GOOGLE_APPLICATION_CREDENTIALS`` is not
      set but ``GOOGLE_SERVICE_ACCOUNT_KEY`` is, the latter is promoted into the
      process env so the Google SDK's ADC discovers it.  Primary per the program
      posture (yrka.io trial credits).
    - ``gemini`` — Gemini API key mode; requires ``GEMINI_API_KEY``.  Fallback.
    - ``groq`` / ``anthropic`` / ``openai`` — their respective API keys.
    """
    if budget is None:
        budget = make_request_budget(cfg)
    selected_provider = provider or cfg.llm_provider
    common = {
        "default_max_tokens": cfg.llm_max_output_tokens,
        "timeout": cfg.llm_timeout_seconds,
        "budget": budget,
    }

    if selected_provider == "vertex":
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        # Promote a SA-key path into the SDK's ADC env var if the canonical one
        # is unset.  Never logs or writes the key contents — only the path.
        adc = cfg.resolved_adc_credentials
        if adc and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc
            _log.info("Promoted service-account key path to GOOGLE_APPLICATION_CREDENTIALS (ADC).")
        return GeminiLlmAdapter(
            model=cfg.llm_model,
            vertexai=True,
            project=cfg.resolved_vertex_project,
            location=cfg.vertex_location,
            **common,  # type: ignore[arg-type]
        )
    if selected_provider == "gemini":
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        return GeminiLlmAdapter(
            api_key=cfg.gemini_api_key or "",
            model=cfg.llm_model,
            **common,  # type: ignore[arg-type]
        )
    if selected_provider == "groq":
        from intercal_shared.adapters.llm_groq import GroqLlmAdapter

        return GroqLlmAdapter(
            api_key=cfg.groq_api_key or "",
            model=cfg.llm_model,
            **common,  # type: ignore[arg-type]
        )
    if selected_provider == "anthropic":
        from intercal_shared.adapters.llm_anthropic import AnthropicLlmAdapter

        return AnthropicLlmAdapter(
            api_key=cfg.anthropic_api_key or "",
            model=cfg.llm_model,
            **common,  # type: ignore[arg-type]
        )
    if selected_provider == "openai":
        from intercal_shared.adapters.llm_openai import OpenAILlmAdapter

        return OpenAILlmAdapter(
            api_key=cfg.openai_api_key or "",
            model=cfg.llm_model,
            **common,  # type: ignore[arg-type]
        )
    raise ValueError(f"Unsupported llm_provider: {selected_provider!r}")


async def make_budgeted_llm(cfg: Settings, *, pool: object) -> LlmPort:
    """Return the runtime LLM with W8 budget fallback + usage recording.

    This is the worker-path constructor.  It shares one request budget across
    providers, prefers ``LLM_PRIMARY`` (default Vertex), falls back to Gemini
    when the primary is unavailable or already at a Plan 04 warning threshold,
    and appends real provider-usage observations after successful calls.
    """
    used_requests = await llm_daily_request_usage(pool=pool)
    budget = InMemoryRequestBudget(limit=cfg.llm_daily_request_budget, used=used_requests)
    budget_states = await llm_provider_budget_states(pool=pool)
    providers = llm_provider_order(cfg, budget_states=budget_states)
    adapters: list[tuple[str, LlmPort]] = []

    for name in providers:
        try:
            adapter = make_llm(cfg, budget=budget, provider=name)
        except Exception as exc:
            if name == providers[-1]:
                raise
            _log.warning(
                "LLM provider=%s could not be constructed (%s); trying fallback provider.",
                name,
                exc,
            )
            continue
        adapters.append((name, UsageRecordingLlm(inner=adapter, provider=name, pool=pool)))

    if not adapters:
        raise ValueError("No configured LLM provider could be constructed.")
    if len(adapters) == 1:
        return adapters[0][1]
    return FallbackLlm(adapters)


def llm_provider_order(cfg: Settings, *, budget_states: dict[str, str]) -> list[str]:
    """Provider order for W8 runtime routing."""
    primary = cfg.llm_primary
    order = [primary]
    if primary != "gemini":
        order.append("gemini")

    deduped: list[str] = []
    for provider in order:
        if provider not in deduped:
            deduped.append(provider)

    exceeded = [provider for provider in deduped if budget_states.get(provider) == "exceeded"]
    warning = [provider for provider in deduped if budget_states.get(provider) == "warning"]
    unavailable_states = {"warning", "exceeded"}
    available = [
        provider for provider in deduped if budget_states.get(provider) not in unavailable_states
    ]
    if warning:
        _log.warning(
            "LLM provider(s) at warning budget state; deprioritizing: %s",
            ", ".join(warning),
        )
    if exceeded:
        _log.warning(
            "LLM provider(s) at exceeded budget state; excluding from routing: %s",
            ", ".join(exceeded),
        )
    routed = available + warning
    if not routed:
        from intercal_shared.ports.llm import LlmBudgetExceededError

        raise LlmBudgetExceededError(
            "All configured LLM providers are at exceeded budget state in "
            "observability_provider_consumption."
        )
    return routed


def make_queue(
    cfg: Settings,
    pool: object | None = None,
) -> RedisQueueAdapter | PostgresQueueAdapter:
    """Return the configured queue adapter.

    Parameters
    ----------
    cfg:
        Runtime settings.
    pool:
        asyncpg pool — required when queue_provider is 'postgres'.
    """
    if cfg.queue_provider == "redis":
        from intercal_shared.adapters.queue_redis import RedisQueueAdapter

        return RedisQueueAdapter(redis_url=cfg.redis_url)
    if cfg.queue_provider == "postgres":
        if pool is None:
            raise ValueError(
                "An asyncpg pool must be supplied to make_queue() when queue_provider='postgres'."
            )
        from intercal_shared.adapters.queue_postgres import PostgresQueueAdapter

        return PostgresQueueAdapter(pool=pool)
    raise ValueError(f"Unsupported queue_provider: {cfg.queue_provider!r}")


def make_scheduler(cfg: Settings) -> LocalSchedulerAdapter:
    """Return the configured scheduler adapter."""
    if cfg.scheduler_provider == "local":
        from intercal_shared.adapters.scheduler_local import LocalSchedulerAdapter

        return LocalSchedulerAdapter()
    raise ValueError(f"Unsupported scheduler_provider: {cfg.scheduler_provider!r}")
