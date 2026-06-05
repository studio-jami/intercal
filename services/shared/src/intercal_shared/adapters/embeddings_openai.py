"""OpenAI hosted embeddings adapter.

Requires: `intercal-shared[embeddings-openai]` (openai) and OPENAI_API_KEY.

IMPORTANT: Store the model name and dimension alongside every vector row so a
future model change can be detected and re-embedding triggered.
"""

from __future__ import annotations

import logging

from intercal_shared.ports.embeddings import EmbeddingsError

_log = logging.getLogger(__name__)

# Native (default) output dimensions for common OpenAI embedding models.
_KNOWN_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

# Models that support the API ``dimensions`` parameter (Matryoshka truncation).
# Verified against the official OpenAI embeddings guide (2026-06): the v3 models
# accept ``dimensions``; ada-002 does not.
_SUPPORTS_DIMENSIONS: frozenset[str] = frozenset(
    {"text-embedding-3-small", "text-embedding-3-large"}
)


class OpenAIEmbeddingsAdapter:
    """EmbeddingsPort implementation backed by the OpenAI Embeddings API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  A clear error is raised if absent.
    model_name:
        OpenAI model identifier, e.g. ``"text-embedding-3-small"``.
    dim:
        Expected output dimension.  Defaults to the known native value for the
        model, or raises if unknown and not supplied.  A value *smaller* than the
        model's native dimension is forwarded to the API as ``dimensions`` (v3
        models only) so the reported ``.dim`` and the actual vector length always
        agree — the vector-space-safety contract callers rely on.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        dim: int | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for the OpenAI embeddings adapter. "
                "Set it in your .env or environment."
            )
        try:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openai is required for the OpenAI embeddings adapter. "
                "Install it with: pip install 'intercal-shared[embeddings-openai]'"
            ) from exc

        self._model_name = model_name
        native_dim = _KNOWN_DIMS.get(model_name)
        if dim is None:
            if native_dim is None:
                raise ValueError(
                    f"Unknown dimension for model {model_name!r}. Supply `dim` explicitly."
                )
            self._dim = native_dim
        else:
            self._dim = dim

        # Decide whether the API needs an explicit ``dimensions`` request.  Without
        # this, a custom ``dim`` would be reported by ``.dim`` while the API silently
        # returned its native-dimension vector — corrupting the model/dim metadata
        # stored alongside every vector (see provider-boundaries.md).
        self._request_dimensions: int | None = None
        if native_dim is not None and self._dim != native_dim:
            if model_name not in _SUPPORTS_DIMENSIONS:
                raise ValueError(
                    f"Model {model_name!r} does not support a custom embedding dimension "
                    f"(native dim={native_dim}); requested dim={self._dim}. "
                    f"Use a v3 model or set EMBEDDINGS_DIM={native_dim}."
                )
            if self._dim > native_dim:
                raise ValueError(
                    f"Requested dim={self._dim} exceeds the native dimension of "
                    f"{model_name!r} ({native_dim}); OpenAI can only shorten, not extend."
                )
            self._request_dimensions = self._dim

        self._client = AsyncOpenAI(api_key=api_key)
        _log.info("OpenAI embeddings adapter initialised (model=%r, dim=%d)", model_name, self._dim)

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            if self._request_dimensions is not None:
                response = await self._client.embeddings.create(
                    input=texts,
                    model=self._model_name,
                    dimensions=self._request_dimensions,
                )
            else:
                response = await self._client.embeddings.create(
                    input=texts,
                    model=self._model_name,
                )
        except Exception as exc:
            raise EmbeddingsError(f"OpenAI embeddings failed: {exc}") from exc

        vectors = [item.embedding for item in response.data]
        # Vector-space safety: the actual length must match the dim we advertise,
        # otherwise the per-vector model/dim metadata (and the pgvector column
        # sizing in W5) would be wrong.
        if vectors and len(vectors[0]) != self._dim:
            raise EmbeddingsError(
                f"OpenAI returned {len(vectors[0])}-dim vectors but adapter is "
                f"configured for dim={self._dim} (model={self._model_name!r}). "
                f"Set EMBEDDINGS_DIM to match the model."
            )
        return vectors
