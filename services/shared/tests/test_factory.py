"""Tests for intercal_shared.factory — adapter construction without live dependencies."""

from __future__ import annotations

import pytest
from intercal_shared.config import Settings
from intercal_shared.factory import make_llm, make_queue, make_scheduler, make_storage


def _isolated_settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def test_make_storage_s3_requires_no_network() -> None:
    """S3StorageAdapter should construct without a network connection."""
    pytest.importorskip("aioboto3", reason="aioboto3 not installed; skipping S3 adapter test")
    cfg = _isolated_settings(storage_provider="s3")
    adapter = make_storage(cfg)
    assert adapter is not None


def test_make_llm_gemini_raises_on_missing_key() -> None:
    """GeminiLlmAdapter should raise ValueError when the API key is absent."""
    pytest.importorskip("google.genai", reason="google-genai not installed")
    cfg = _isolated_settings(llm_provider="gemini", gemini_api_key=None)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        make_llm(cfg)


def test_make_llm_groq_raises_on_missing_key() -> None:
    pytest.importorskip("groq", reason="groq not installed")
    cfg = _isolated_settings(llm_provider="groq", groq_api_key=None)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        make_llm(cfg)


def test_make_llm_anthropic_raises_on_missing_key() -> None:
    pytest.importorskip("anthropic", reason="anthropic not installed")
    cfg = _isolated_settings(llm_provider="anthropic", anthropic_api_key=None)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        make_llm(cfg)


def test_make_llm_openai_raises_on_missing_key() -> None:
    pytest.importorskip("openai", reason="openai not installed")
    cfg = _isolated_settings(llm_provider="openai", openai_api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        make_llm(cfg)


def test_make_queue_redis_constructs() -> None:
    pytest.importorskip("redis", reason="redis not installed")
    cfg = _isolated_settings(queue_provider="redis")
    adapter = make_queue(cfg)
    assert adapter is not None


def test_make_queue_postgres_requires_pool() -> None:
    cfg = _isolated_settings(queue_provider="postgres")
    with pytest.raises(ValueError, match="pool"):
        make_queue(cfg, pool=None)


def test_make_scheduler_local() -> None:
    cfg = _isolated_settings(scheduler_provider="local")
    scheduler = make_scheduler(cfg)
    assert scheduler is not None


@pytest.mark.asyncio
async def test_scheduler_local_runs_job() -> None:
    """LocalSchedulerAdapter should execute an async job directly."""
    from intercal_shared.adapters.scheduler_local import LocalSchedulerAdapter

    scheduler = LocalSchedulerAdapter()
    ran: list[str] = []

    async def sample_job(*, label: str) -> None:
        ran.append(label)

    await scheduler.run_now(sample_job, label="hello")
    assert ran == ["hello"]
