"""EmbeddingsPort — provider-agnostic text embeddings interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsPort(Protocol):
    """Text embeddings port.

    Implementors may use local ONNX models (fastembed) or hosted APIs (OpenAI).
    The model name and dimension are exposed as properties so callers can record
    them alongside each vector (required for vector-space safety on model changes).
    """

    @property
    def model(self) -> str:
        """Canonical model identifier (e.g. 'BAAI/bge-small-en-v1.5').

        Store this alongside every vector row to detect model mismatches on query.
        """
        ...

    @property
    def dim(self) -> int:
        """Output dimension for this model (e.g. 384, 768, 1536)."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of *texts*.

        Returns a list of float vectors, one per input text.  Empty input
        returns an empty list.

        Raises:
            EmbeddingsError: on backend failures.
        """
        ...


class EmbeddingsError(Exception):
    """Raised by embeddings adapter on non-recoverable errors."""
