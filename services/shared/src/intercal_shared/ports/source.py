"""SourcePort — provider-agnostic interface for source adapters.

A source adapter knows how to fetch raw documents from one specific origin
(Wikidata recent-changes, GitHub releases, arXiv, RSS, etc.) and nothing
more.  It does not own canonical parsing, normalisation, or storage; those
are downstream pipeline stages.

Import:
    from intercal_shared.ports.source import SourcePort, RawDocument

Implementations live in ``intercal_shared/adapters/source_*.py`` and are
selected by the source registry via ``adapter_name`` in the ``sources`` table.

Design note on the fetch signature
-----------------------------------
``fetch`` is an **async generator** method: callers iterate it with
``async for doc in adapter.fetch(...)``.  Python async generators do not
satisfy ``Protocol`` matching for ``AsyncIterator`` cleanly via structural
typing alone, so the port is documented here as a guide rather than enforced
as a ``@runtime_checkable`` protocol.  Adapter conformance is verified by
tests.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator


@dataclasses.dataclass
class RawDocument:
    """An unprocessed document emitted by a source adapter.

    All fields except ``content`` are optional; the adapter fills what it
    knows and leaves the rest as ``None`` for downstream stages to fill.

    Attributes
    ----------
    content:
        Raw bytes — the adapter's fetched payload, verbatim.  Mandatory.
    external_id:
        The source's own identifier for this document (URL, QID, DOI, …).
    url:
        Canonical URL for the document, if known.
    title:
        Document title, if known.
    published_at:
        When the source says this document was published (ISO-8601 string or
        empty — the downstream normaliser converts to timestamptz).
    language:
        BCP 47 language tag, e.g. ``"en"``.  Defaults to ``"en"``.
    content_type:
        MIME type of ``content`` bytes, e.g. ``"application/json"``.
    metadata:
        Arbitrary key/value adapter metadata (page number, shard, etc.).
    """

    content: bytes
    external_id: str | None = None
    url: str | None = None
    title: str | None = None
    published_at: str | None = None
    language: str = "en"
    content_type: str = "application/octet-stream"
    metadata: dict[str, str] = dataclasses.field(
        default_factory=lambda: {}  # pyright infers dict[str, str] from the annotation
    )


class SourcePort:
    """Base class for source adapters.

    Subclass and implement ``fetch`` as an async generator.

    Attributes
    ----------
    adapter_name:
        Registry key — must be unique across all adapters and match the
        value stored in ``sources.adapter_name``.
    """

    #: Unique registry key; subclasses must override.
    adapter_name: str = ""

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
    ) -> AsyncIterator[RawDocument]:
        """Yield raw documents from the source.

        Implementations must be async generator methods:

            async def fetch(self, *, adapter_config, cursor_state,
                            max_documents, http_client):
                ...
                yield RawDocument(...)

        Parameters
        ----------
        adapter_config:
            The ``sources.adapter_config`` JSONB blob for this source row.
        cursor_state:
            Opaque pagination token from a previous run.  ``None`` = start
            from the beginning / most-recent window.
        max_documents:
            Hard upper bound on documents to yield in this run.
        http_client:
            Optional shared ``httpx.AsyncClient``.  Adapters that receive
            one must not close it.

        Yields
        ------
        RawDocument

        Raises
        ------
        SourceFetchError
            On non-retryable network or API errors.
        SourceRateLimitError
            When the upstream source signals rate limiting.
        """
        raise NotImplementedError(f"{type(self).__name__}.fetch is not implemented")
        # Make this an async generator so the type is correct.
        # This yield is unreachable but satisfies the async-generator contract.
        yield  # type: ignore[misc]


class SourceFetchError(Exception):
    """Raised by source adapters on non-retryable fetch failures."""


class SourceRateLimitError(SourceFetchError):
    """Raised when the upstream source returns a rate-limit signal."""
