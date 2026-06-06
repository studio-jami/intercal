"""Runtime LLM wrappers for budget routing and consumption telemetry.

The provider adapters stay responsible for provider SDK calls.  This module wraps
the LLM port with provider-agnostic policies:

- Vertex -> Gemini fallback on provider-side auth/quota/timeout failures.
- Real usage-event emission after an adapter returns measured usage.
- Optional budget-state degradation from Plan 04 observability views.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable
from typing import Any

from intercal_shared.ports.llm import (
    LlmAuthError,
    LlmBudgetExceededError,
    LlmExtractionError,
    LlmPort,
    LlmRateLimitError,
    LlmResponse,
    LlmTimeoutError,
    StructuredResult,
)

_log = logging.getLogger(__name__)

_ProviderName = str
_FallbackError = (LlmAuthError, LlmRateLimitError, LlmTimeoutError)


def utc_day_window(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    """Return the current UTC day window used for daily provider-usage rows."""
    current = now or dt.datetime.now(tz=dt.UTC)
    start = dt.datetime(current.year, current.month, current.day, tzinfo=dt.UTC)
    return start, start + dt.timedelta(days=1)


class UsageRecordingLlm:
    """LlmPort wrapper that appends real provider usage observations.

    It records one ``requests`` event after every successful provider response,
    and records a ``tokens`` event only when the adapter surfaced a real token
    count.  Unknown token usage is left unavailable instead of zero-filled.
    """

    def __init__(self, *, inner: LlmPort, provider: str, pool: Any) -> None:
        self._inner = inner
        self._provider = provider
        self._pool = pool

    @property
    def provider(self) -> str:
        return self._provider

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        result = await self._inner.complete(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        await self._record_usage(operation="complete", result=result)
        return result

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResult:
        result = await self._inner.extract_structured(
            schema,
            prompt,
            system=system,
            max_tokens=max_tokens,
        )
        await self._record_usage(operation="extract_structured", result=result)
        return result

    async def _record_usage(
        self,
        *,
        operation: str,
        result: LlmResponse | StructuredResult,
    ) -> None:
        period_start, period_end = utc_day_window()
        model = getattr(result, "model", None)
        metadata = {"operation": operation, "model": model}

        try:
            await self._insert_usage_event(
                allowance_key="daily_requests",
                metric_name="requests",
                metric_unit="requests",
                quantity=1,
                period_start=period_start,
                period_end=period_end,
                metadata=metadata,
            )
            token_total = _token_total(
                getattr(result, "input_tokens", None),
                getattr(result, "output_tokens", None),
            )
            if token_total is not None:
                await self._insert_usage_event(
                    allowance_key="daily_token_cap",
                    metric_name="tokens",
                    metric_unit="tokens",
                    quantity=token_total,
                    period_start=period_start,
                    period_end=period_end,
                    metadata=metadata,
                )
        except Exception as exc:
            _log.warning(
                "LLM provider usage could not be recorded for provider=%s operation=%s: %s",
                self._provider,
                operation,
                exc,
            )

    async def _insert_usage_event(
        self,
        *,
        allowance_key: str,
        metric_name: str,
        metric_unit: str,
        quantity: int,
        period_start: dt.datetime,
        period_end: dt.datetime,
        metadata: dict[str, Any],
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO provider_usage_events
                (provider, allowance_key, metric_name, metric_unit, quantity,
                 cost_usd, period_start, period_end, source, metadata)
            VALUES ($1, $2, $3, $4, $5, NULL, $6, $7, $8, $9::jsonb)
            """,
            self._provider,
            allowance_key,
            metric_name,
            metric_unit,
            quantity,
            period_start,
            period_end,
            "services/shared/llm_runtime.py",
            json.dumps(metadata, sort_keys=True),
        )


class FallbackLlm:
    """LlmPort wrapper that tries providers in order.

    Local budget exhaustion is terminal and never falls back, because the budget
    is shared across providers.  Schema/extraction errors are also terminal: a
    fallback retry there would hide extraction-quality issues as routing.
    """

    def __init__(self, providers: list[tuple[_ProviderName, LlmPort]]) -> None:
        if not providers:
            raise ValueError("FallbackLlm requires at least one provider.")
        self._providers = providers

    @property
    def providers(self) -> list[str]:
        return [name for name, _ in self._providers]

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        async def _call(provider: LlmPort) -> LlmResponse:
            return await provider.complete(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        return await self._call_with_fallback("complete", _call)

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResult:
        async def _call(provider: LlmPort) -> StructuredResult:
            return await provider.extract_structured(
                schema,
                prompt,
                system=system,
                max_tokens=max_tokens,
            )

        return await self._call_with_fallback("extract_structured", _call)

    async def _call_with_fallback(
        self,
        operation: str,
        call: Callable[[LlmPort], Any],
    ) -> Any:
        last_provider_error: Exception | None = None
        for index, (provider_name, provider) in enumerate(self._providers):
            try:
                return await call(provider)
            except LlmBudgetExceededError:
                raise
            except LlmExtractionError:
                raise
            except _FallbackError as exc:
                last_provider_error = exc
                if index == len(self._providers) - 1:
                    raise
                next_provider = self._providers[index + 1][0]
                _log.warning(
                    "LLM provider=%s operation=%s failed with %s; falling back to provider=%s",
                    provider_name,
                    operation,
                    type(exc).__name__,
                    next_provider,
                )
        assert last_provider_error is not None
        raise last_provider_error


async def llm_provider_budget_states(*, pool: Any) -> dict[str, str]:
    """Return LLM providers currently at warning/exceeded budget state.

    The Plan 04 view is authoritative when available.  If the view/table is not
    migrated yet, return an empty dict and let local request-budget enforcement
    remain the hard guard.
    """
    try:
        rows = await pool.fetch(
            """
            SELECT provider, budget_state
            FROM observability_provider_consumption
            WHERE provider = ANY($1::text[])
              AND allowance_key = 'daily_requests'
              AND budget_state IN ('warning', 'exceeded')
            """,
            ["vertex", "gemini"],
        )
    except Exception as exc:
        _log.warning("LLM budget-state view unavailable; local budget only: %s", exc)
        return {}
    return {str(row["provider"]): str(row["budget_state"]) for row in rows}


async def llm_daily_request_usage(*, pool: Any) -> int:
    """Return today's real LLM request usage across routed providers.

    The local budget remains the pre-call reservation guard.  This read seeds it
    from append-only successful usage rows so separate worker invocations on the
    same UTC day do not reset the daily budget.
    """
    period_start, period_end = utc_day_window()
    try:
        row = await pool.fetchrow(
            """
            SELECT COALESCE(sum(quantity), 0)::bigint AS quantity_used
            FROM provider_usage_events
            WHERE provider = ANY($1::text[])
              AND allowance_key = 'daily_requests'
              AND (
                observed_at >= $2
                OR period_end >= $2
              )
              AND observed_at < $3
            """,
            ["vertex", "gemini"],
            period_start,
            period_end,
        )
    except Exception as exc:
        _log.warning("LLM daily request usage unavailable; local budget only: %s", exc)
        return 0
    if row is None:
        return 0
    return max(0, int(row["quantity_used"] or 0))


def _token_total(input_tokens: int | None, output_tokens: int | None) -> int | None:
    values = [v for v in (input_tokens, output_tokens) if isinstance(v, int) and v >= 0]
    if not values:
        return None
    return sum(values)
