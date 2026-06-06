"""Tests for intercal_shared.factory — adapter construction without live dependencies."""

from __future__ import annotations

from typing import Any

import pytest
from intercal_shared.config import Settings
from intercal_shared.factory import (
    make_llm,
    make_queue,
    make_request_budget,
    make_scheduler,
    make_storage,
)
from intercal_shared.ports.llm import (
    InMemoryRequestBudget,
    LlmBudgetExceededError,
    LlmResponse,
    StructuredResult,
)


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


def test_llm_provider_order_prefers_vertex_then_gemini() -> None:
    from intercal_shared.factory import llm_provider_order

    cfg = _isolated_settings(llm_primary="vertex")
    assert llm_provider_order(cfg, budget_states={}) == ["vertex", "gemini"]


def test_llm_provider_order_excludes_exceeded_and_deprioritizes_warning() -> None:
    from intercal_shared.factory import llm_provider_order
    from intercal_shared.ports.llm import LlmBudgetExceededError

    cfg = _isolated_settings(llm_primary="vertex")
    assert llm_provider_order(cfg, budget_states={"vertex": "warning"}) == [
        "gemini",
        "vertex",
    ]
    assert llm_provider_order(cfg, budget_states={"vertex": "exceeded"}) == ["gemini"]
    with pytest.raises(LlmBudgetExceededError):
        llm_provider_order(cfg, budget_states={"vertex": "exceeded", "gemini": "exceeded"})


def test_make_request_budget_defaults_to_zero_used() -> None:
    budget = make_request_budget(_isolated_settings(llm_daily_request_budget=1))
    assert isinstance(budget, InMemoryRequestBudget)
    budget.check_and_consume()
    with pytest.raises(LlmBudgetExceededError):
        budget.check_and_consume()


@pytest.mark.asyncio
async def test_make_budgeted_llm_seeds_budget_from_same_day_usage(monkeypatch: Any) -> None:
    from intercal_shared import factory
    from intercal_shared.ports.llm import LlmPort

    class _FakePool:
        async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any]:
            return {"quantity_used": 1}

        async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
            return []

    class _FakeLlm:
        def __init__(self, budget: InMemoryRequestBudget) -> None:
            self.budget = budget

        async def complete(
            self,
            prompt: str,
            *,
            system: str | None = None,
            max_tokens: int | None = None,
            temperature: float = 0.0,
        ) -> LlmResponse:
            self.budget.check_and_consume()
            raise AssertionError("budget guard should fire before provider call")

        async def extract_structured(
            self,
            schema: dict[str, Any],
            prompt: str,
            *,
            system: str | None = None,
            max_tokens: int | None = None,
        ) -> StructuredResult:
            self.budget.check_and_consume()
            raise AssertionError("budget guard should fire before provider call")

    def _fake_make_llm(
        cfg: Settings,
        budget: object | None = None,
        *,
        provider: str | None = None,
    ) -> LlmPort:
        assert isinstance(budget, InMemoryRequestBudget)
        return _FakeLlm(budget)

    monkeypatch.setattr(factory, "make_llm", _fake_make_llm)

    cfg = _isolated_settings(llm_daily_request_budget=1, llm_primary="gemini")
    llm = await factory.make_budgeted_llm(cfg, pool=_FakePool())

    with pytest.raises(LlmBudgetExceededError):
        await llm.complete("hello")


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
