"""LlmPort — provider-agnostic LLM completion and structured-extraction interface.

This module owns the *contract* between the pipeline (extraction in W3, synthesis
in Plan 03) and any LLM provider.  Provider-specific payloads (tool calls, finish
reasons, raw token blocks) never cross this boundary; callers receive only the
canonical types defined here.

The contract guarantees four things the pipeline depends on:

1. **Structured extraction is schema-validated.**  ``extract_structured`` returns
   data that has been validated against the supplied JSON Schema (subset).  A
   provider that returns valid JSON of the *wrong shape* raises
   ``LlmExtractionError`` — it never silently leaks into claim persistence.
2. **Bounded retries on transient failures.**  Adapters retry malformed /
   schema-invalid structured output and provider rate-limit / timeout errors up
   to a small bound before giving up.
3. **A typed error taxonomy.**  Callers can distinguish retryable
   (``LlmRateLimitError``, ``LlmTimeoutError``) from fatal
   (``LlmAuthError``, ``LlmBudgetExceededError``) and malformed-output
   (``LlmExtractionError``) conditions.
4. **Usage accounting + budget enforcement hook.**  Every call surfaces token
   usage, and an optional :class:`RequestBudget` is consulted before each call so
   the resource-budget daily cap (``LLM_DAILY_REQUEST_BUDGET``) is enforced at the
   port boundary rather than reinvented per caller.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmPort(Protocol):
    """LLM interaction port.

    Two operations are exposed:
    - `complete`: free-form text generation.
    - `extract_structured`: guided extraction into a JSON-Schema-described dict,
      validated against that schema before it is returned.

    Provider-specific payloads (tool_calls, finish reasons, raw token blocks) must
    not cross this boundary.  Callers that need usage metadata consume the returned
    `LlmResponse` / `StructuredResult` wrappers.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        """Generate a completion for *prompt*.

        Args:
            prompt: The user message / input text.
            system: Optional system / instruction preamble.
            max_tokens: Upper token limit for the response.  ``None`` uses the
                adapter's configured default output cap (``LLM_MAX_OUTPUT_TOKENS``).
            temperature: Sampling temperature (0.0 = deterministic).

        Raises:
            LlmBudgetExceededError: if the daily request budget is exhausted.
            LlmRateLimitError / LlmTimeoutError: transient provider failures.
            LlmAuthError: missing or rejected credentials.
            LlmError: other provider errors.
        """
        ...

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResult:
        """Extract structured data from *prompt* guided by a JSON Schema *schema*.

        The adapter uses the provider's native structured-output mechanism where
        available (e.g. Gemini ``response_schema``, Anthropic tool-use), parses the
        result, and **validates it against** *schema* before returning.  Malformed
        or schema-invalid output is retried a bounded number of times; persistent
        failure raises ``LlmExtractionError``.

        Returns a :class:`StructuredResult` carrying the validated ``data`` dict
        plus usage metadata.

        Raises:
            LlmExtractionError: if the provider returns malformed or schema-invalid
                output after the retry budget is exhausted.
            LlmBudgetExceededError: if the daily request budget is exhausted.
            LlmRateLimitError / LlmTimeoutError: transient provider failures.
            LlmAuthError: missing or rejected credentials.
            LlmError: other provider errors.
        """
        ...


@runtime_checkable
class RequestBudget(Protocol):
    """Hook consulted by an adapter before each LLM call.

    Lets the resource-budget daily cap (``LLM_DAILY_REQUEST_BUDGET``) be enforced
    at the port boundary.  The default :class:`InMemoryRequestBudget` is a simple
    process-local counter; a deployment may inject a Redis/Postgres-backed
    implementation (Plan 04 observability owns durable counters) without touching
    adapter code.
    """

    def check_and_consume(self, *, cost: int = 1) -> None:
        """Reserve *cost* request(s) against the budget.

        Raises:
            LlmBudgetExceededError: if the budget would be exceeded.
        """
        ...


class InMemoryRequestBudget:
    """Process-local daily request counter implementing :class:`RequestBudget`.

    Intended for single-process pipeline runs (the common case: a scheduled
    GitHub Actions / Cloud Run job).  Not shared across processes — a distributed
    deployment should inject a durable counter.  ``limit <= 0`` disables the cap.
    """

    __slots__ = ("_limit", "_used")

    def __init__(self, limit: int, *, used: int = 0) -> None:
        self._limit = limit
        self._used = max(0, used)

    @property
    def used(self) -> int:
        return self._used

    @property
    def limit(self) -> int:
        return self._limit

    def check_and_consume(self, *, cost: int = 1) -> None:
        if self._limit <= 0:
            return
        if self._used + cost > self._limit:
            raise LlmBudgetExceededError(
                f"Daily LLM request budget exhausted: {self._used}/{self._limit} used "
                f"(LLM_DAILY_REQUEST_BUDGET). Refusing call to stay within the cost budget."
            )
        self._used += cost


class LlmResponse:
    """Thin wrapper around a completed free-form LLM response."""

    __slots__ = ("input_tokens", "model", "output_tokens", "text")

    def __init__(
        self,
        text: str,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.text = text
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def __repr__(self) -> str:
        return (
            f"LlmResponse(model={self.model!r}, "
            f"input_tokens={self.input_tokens}, "
            f"output_tokens={self.output_tokens})"
        )


class StructuredResult:
    """A schema-validated structured-extraction result plus usage metadata.

    ``data`` has already been validated against the caller's JSON Schema by the
    adapter.  Token counts are surfaced for usage accounting (the same fields as
    :class:`LlmResponse`).
    """

    __slots__ = ("data", "input_tokens", "model", "output_tokens")

    def __init__(
        self,
        data: dict[str, Any],
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.data = data
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def __repr__(self) -> str:
        return (
            f"StructuredResult(model={self.model!r}, keys={sorted(self.data)!r}, "
            f"input_tokens={self.input_tokens}, output_tokens={self.output_tokens})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Error taxonomy
# ──────────────────────────────────────────────────────────────────────────────


class LlmError(Exception):
    """Base class for all LLM adapter errors."""


class LlmAuthError(LlmError):
    """Missing, malformed, or rejected credentials.  Fatal — not retryable."""


class LlmRateLimitError(LlmError):
    """Provider rate limit / quota hit.  Transient — retryable with backoff."""


class LlmTimeoutError(LlmError):
    """Request exceeded the configured timeout.  Transient — retryable."""


class LlmBudgetExceededError(LlmError):
    """The local daily request budget (``LLM_DAILY_REQUEST_BUDGET``) is exhausted.

    Fatal for the current run — not retryable.  Distinct from a provider rate
    limit: this is *our* cost guard, not the provider's.
    """


class LlmExtractionError(LlmError):
    """Structured extraction returned malformed JSON or data that fails schema validation.

    Raised after the adapter's bounded retry budget is exhausted.
    """


# ──────────────────────────────────────────────────────────────────────────────
# Dependency-free JSON Schema validation (extraction-schema subset)
# ──────────────────────────────────────────────────────────────────────────────

# We validate the subset of JSON Schema that extraction schemas actually use, with
# no third-party dependency: ``type`` (incl. lists / nullable), ``required``,
# ``properties``, ``items``, and ``enum``.  Unknown keywords are ignored (lenient),
# but every declared constraint is enforced.  This is intentionally narrow — it is a
# guard for LLM output shape, not a general-purpose validator.

_TYPE_CHECKS: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _matches_type(value: Any, type_name: str) -> bool:
    expected = _TYPE_CHECKS.get(type_name)
    if expected is None:
        return True  # unknown type keyword — be lenient
    if type_name == "integer":
        # JSON has no int/float distinction; accept integral floats, reject bool.
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if type_name == "number" and isinstance(value, bool):
        return False
    if type_name == "boolean":
        return isinstance(value, bool)
    return isinstance(value, expected)


def validate_against_schema(data: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    """Validate *data* against the supported JSON-Schema *schema* subset.

    Raises:
        LlmExtractionError: on the first constraint violation, with a JSON-path
            pointer to the offending node.
    """
    if not schema:
        return  # empty schema accepts anything

    declared_type = schema.get("type")
    if declared_type is not None:
        type_names = [declared_type] if isinstance(declared_type, str) else list(declared_type)
        if not any(_matches_type(data, t) for t in type_names):
            raise LlmExtractionError(
                f"Schema validation failed at {path}: expected type {declared_type!r}, "
                f"got {type(data).__name__}."
            )

    enum = schema.get("enum")
    if enum is not None and data not in enum:
        raise LlmExtractionError(
            f"Schema validation failed at {path}: value {data!r} not in enum {enum!r}."
        )

    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                raise LlmExtractionError(
                    f"Schema validation failed at {path}: missing required property {key!r}."
                )
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in data and isinstance(subschema, dict):
                validate_against_schema(data[key], subschema, path=f"{path}.{key}")

    if isinstance(data, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(data):
                validate_against_schema(item, item_schema, path=f"{path}[{index}]")
