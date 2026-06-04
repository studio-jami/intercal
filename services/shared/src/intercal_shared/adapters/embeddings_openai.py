"""OpenAI hosted embeddings adapter.

Requires: `intercal-shared[embeddings-openai]` (openai) and OPENAI_API_KEY.

IMPORTANT: Store the model name and dimension alongside every vector row so a
future model change can be detected and re-embedding triggered.
"""

from __future__ import annotations

import logging

from intercal_shared.ports.embeddings import EmbeddingsError

_log = logging.getLogger(__name__)

# Known dimensions for common OpenAI embedding models.
_KNOWN_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingsAdapter:
    """EmbeddingsPort implementation backed by the OpenAI Embeddings API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  A clear error is raised if absent.
    model_name:
        OpenAI model identifier, e.g. ``"text-embedding-3-small"``.
    dim:
        Expected output dimension.  Defaults to the known value for the model
        or raises if unknown and not supplied.
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
        if dim is None:
            if model_name not in _KNOWN_DIMS:
                raise ValueError(
                    f"Unknown dimension for model {model_name!r}. Supply `dim` explicitly."
                )
            self._dim = _KNOWN_DIMS[model_name]
        else:
            self._dim = dim

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
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model_name,
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            raise EmbeddingsError(f"OpenAI embeddings failed: {exc}") from exc
