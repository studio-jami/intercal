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

from typing import TYPE_CHECKING

from intercal_shared.config import Settings

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


def make_llm(
    cfg: Settings,
) -> GeminiLlmAdapter | GroqLlmAdapter | AnthropicLlmAdapter | OpenAILlmAdapter:
    """Return the configured LLM adapter."""
    if cfg.llm_provider == "gemini":
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        return GeminiLlmAdapter(api_key=cfg.gemini_api_key or "", model=cfg.llm_model)
    if cfg.llm_provider == "groq":
        from intercal_shared.adapters.llm_groq import GroqLlmAdapter

        return GroqLlmAdapter(api_key=cfg.groq_api_key or "", model=cfg.llm_model)
    if cfg.llm_provider == "anthropic":
        from intercal_shared.adapters.llm_anthropic import AnthropicLlmAdapter

        return AnthropicLlmAdapter(api_key=cfg.anthropic_api_key or "", model=cfg.llm_model)
    if cfg.llm_provider == "openai":
        from intercal_shared.adapters.llm_openai import OpenAILlmAdapter

        return OpenAILlmAdapter(api_key=cfg.openai_api_key or "", model=cfg.llm_model)
    raise ValueError(f"Unsupported llm_provider: {cfg.llm_provider!r}")


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
