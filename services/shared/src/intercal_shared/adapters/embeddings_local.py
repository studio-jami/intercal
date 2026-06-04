"""Local ONNX embeddings adapter using fastembed (zero-cost default).

Requires: `intercal-shared[embeddings-local]` (fastembed).

Default model: BAAI/bge-small-en-v1.5 (384 dims).
Suitable alternatives: BAAI/bge-base-en-v1.5 (768), nomic-ai/nomic-embed-text-v1.5 (768).

fastembed runs fully local via ONNX Runtime — no API key, no egress.
The model is downloaded once to ~/.cache/fastembed on first use.

IMPORTANT: The model name and dimension must be stored alongside every vector row
so a future model change can be detected and re-embedding triggered.
"""

from __future__ import annotations

import asyncio
import logging

from intercal_shared.ports.embeddings import EmbeddingsError

_log = logging.getLogger(__name__)


class LocalEmbeddingsAdapter:
    """EmbeddingsPort implementation backed by fastembed (local ONNX).

    Parameters
    ----------
    model_name:
        fastembed model identifier, e.g. ``"BAAI/bge-small-en-v1.5"``.
    dim:
        Expected output dimension.  Must match the model.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "fastembed is required for the local embeddings adapter. "
                "Install it with: pip install 'intercal-shared[embeddings-local]'"
            ) from exc

        self._model_name = model_name
        self._dim = dim
        # Initialise in __init__ so import failures surface early.
        self._model = TextEmbedding(model_name=model_name)
        _log.info("Loaded local embeddings model %r (dim=%d)", model_name, dim)

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* using the local ONNX model.

        fastembed is synchronous; we run it in the default thread pool to avoid
        blocking the event loop.
        """
        if not texts:
            return []
        try:
            loop = asyncio.get_event_loop()
            embeddings: list[list[float]] = await loop.run_in_executor(
                None, self._embed_sync, texts
            )
            return embeddings
        except Exception as exc:
            raise EmbeddingsError(f"Local embeddings failed: {exc}") from exc

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]
