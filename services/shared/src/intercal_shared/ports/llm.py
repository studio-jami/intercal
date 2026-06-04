"""LlmPort — provider-agnostic LLM completion and structured-extraction interface."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmPort(Protocol):
    """LLM interaction port.

    Two operations are exposed:
    - `complete`: free-form text generation.
    - `extract_structured`: guided extraction into a JSON-Schema-described dict.

    Provider-specific payloads (tool_calls, finish reasons, token counts) must
    not cross this boundary.  Callers that need usage metadata should consume
    the returned `LlmResponse` wrapper.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LlmResponse:
        """Generate a completion for *prompt*.

        Args:
            prompt: The user message / input text.
            system: Optional system / instruction preamble.
            max_tokens: Upper token limit for the response.
            temperature: Sampling temperature (0.0 = deterministic).

        Raises:
            LlmError: on provider errors or missing credentials.
        """
        ...

    async def extract_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Extract structured data from *prompt* guided by a JSON Schema *schema*.

        The adapter should use the provider's native structured-output or
        function-calling mechanism and validate the result against *schema*.

        Returns a plain dict conforming to *schema*.

        Raises:
            LlmExtractionError: if the provider returns malformed output.
            LlmError: on provider errors or missing credentials.
        """
        ...


class LlmResponse:
    """Thin wrapper around a completed LLM response."""

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


class LlmError(Exception):
    """Raised by LLM adapters on provider errors or missing credentials."""


class LlmExtractionError(LlmError):
    """Raised when structured extraction returns data that does not match the schema."""
