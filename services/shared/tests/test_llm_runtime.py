"""Tests for W8 LLM runtime routing and provider-usage telemetry."""

from __future__ import annotations

from typing import Any

import pytest
from intercal_shared.llm_runtime import (
    FallbackLlm,
    UsageRecordingLlm,
    llm_daily_request_usage,
    llm_provider_budget_states,
)
from intercal_shared.ports.llm import (
    LlmBudgetExceededError,
    LlmRateLimitError,
    LlmResponse,
    StructuredResult,
)


class _FakeLlm:
    def __init__(self, *, response: Any | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response or LlmResponse(
            text="ok",
            model="fixture-model",
            input_tokens=3,
            output_tokens=5,
        )

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response or StructuredResult(
            data={"ok": True},
            model="fixture-model",
            input_tokens=7,
            output_tokens=11,
        )


class _FakePool:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        fail_fetch: bool = False,
        usage_quantity: int = 0,
    ) -> None:
        self.rows = rows or []
        self.fail_fetch = fail_fetch
        self.usage_quantity = usage_quantity
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        return "INSERT 0 1"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        if self.fail_fetch:
            raise RuntimeError("view missing")
        return self.rows

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any]:
        if self.fail_fetch:
            raise RuntimeError("table missing")
        return {"quantity_used": self.usage_quantity}


@pytest.mark.asyncio
async def test_usage_recording_emits_request_and_tokens_when_usage_known() -> None:
    pool = _FakePool()
    llm = UsageRecordingLlm(inner=_FakeLlm(), provider="vertex", pool=pool)

    result = await llm.complete("hello")

    assert result.text == "ok"
    assert len(pool.executed) == 2
    request_args = pool.executed[0][1]
    token_args = pool.executed[1][1]
    assert request_args[0:5] == ("vertex", "daily_requests", "requests", "requests", 1)
    assert token_args[0:5] == ("vertex", "daily_token_cap", "tokens", "tokens", 8)


@pytest.mark.asyncio
async def test_usage_recording_does_not_zero_fill_unknown_tokens() -> None:
    pool = _FakePool()
    inner = _FakeLlm(response=LlmResponse(text="ok", model="fixture", input_tokens=None))
    llm = UsageRecordingLlm(inner=inner, provider="gemini", pool=pool)

    await llm.complete("hello")

    assert len(pool.executed) == 1
    assert pool.executed[0][1][1] == "daily_requests"


@pytest.mark.asyncio
async def test_fallback_tries_next_provider_on_rate_limit() -> None:
    primary = _FakeLlm(error=LlmRateLimitError("quota"))
    fallback = _FakeLlm(response=LlmResponse(text="fallback", model="gemini"))
    llm = FallbackLlm([("vertex", primary), ("gemini", fallback)])

    result = await llm.complete("hello")

    assert result.text == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fallback_does_not_cross_local_budget_guard() -> None:
    primary = _FakeLlm(error=LlmBudgetExceededError("local budget"))
    fallback = _FakeLlm(response=LlmResponse(text="fallback", model="gemini"))
    llm = FallbackLlm([("vertex", primary), ("gemini", fallback)])

    with pytest.raises(LlmBudgetExceededError):
        await llm.complete("hello")

    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_llm_provider_budget_states_returns_warning_and_exceeded() -> None:
    pool = _FakePool(
        rows=[
            {"provider": "vertex", "budget_state": "warning"},
            {"provider": "gemini", "budget_state": "exceeded"},
        ]
    )

    assert await llm_provider_budget_states(pool=pool) == {
        "vertex": "warning",
        "gemini": "exceeded",
    }


@pytest.mark.asyncio
async def test_llm_provider_budget_states_unavailable_is_empty() -> None:
    assert await llm_provider_budget_states(pool=_FakePool(fail_fetch=True)) == {}


@pytest.mark.asyncio
async def test_llm_daily_request_usage_reads_real_usage_rows() -> None:
    assert await llm_daily_request_usage(pool=_FakePool(usage_quantity=17)) == 17


@pytest.mark.asyncio
async def test_llm_daily_request_usage_unavailable_is_zero() -> None:
    assert await llm_daily_request_usage(pool=_FakePool(fail_fetch=True)) == 0
