"""Workstream 1 tests: source registry, adapter contracts, ingest_source job.

No live network or database is required.  All external calls are intercepted
via httpx.MockTransport or a fake asyncpg pool.
"""

from __future__ import annotations

import json
import socket
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import intercal_ingest.jobs as ingest_jobs
import pytest
from intercal_ingest.jobs import (
    _parse_timestamp,  # pyright: ignore[reportPrivateUsage]  # tested directly: load-bearing parse
    ingest_source,
    score_source_health,
)
from intercal_shared.ports.source import RawDocument, SourceFetchError, SourceRateLimitError
from intercal_shared.source_registry import SourceRegistry

# ── Source registry ──────────────────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    """register() adds an adapter; get() returns it by adapter_name."""
    reg = SourceRegistry()

    class FakeAdapter:
        adapter_name = "fake_v1"

    adapter = FakeAdapter()
    reg.register(adapter)  # type: ignore[arg-type]
    assert reg.get("fake_v1") is adapter


def test_registry_get_missing_raises_key_error() -> None:
    reg = SourceRegistry()
    with pytest.raises(KeyError, match="no_such_adapter"):
        reg.get("no_such_adapter")


def test_registry_all_names() -> None:
    reg = SourceRegistry()

    class A:
        adapter_name = "a_v1"

    class B:
        adapter_name = "b_v1"

    reg.register(A())  # type: ignore[arg-type]
    reg.register(B())  # type: ignore[arg-type]
    assert reg.all_names() == ["a_v1", "b_v1"]


def test_registry_register_all_defaults() -> None:
    """register_all_defaults() loads current built-in source adapters."""
    reg = SourceRegistry()
    reg.register_all_defaults()
    names = reg.all_names()
    assert "wikidata_changes_v1" in names
    assert "github_releases_v1" in names
    assert "registry_releases_v1" in names
    assert "arxiv_v1" in names
    assert "rss_feed_v1" in names
    assert "wikidata_sparql_batch_v1" in names
    assert "mediawiki_revisions_v1" in names


# ── SourcePort contract for built-in adapters ────────────────────────────────


def test_wikidata_adapter_has_correct_name() -> None:
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    adapter = WikidataChangesAdapter()
    assert adapter.adapter_name == "wikidata_changes_v1"


def test_github_adapter_has_correct_name() -> None:
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    adapter = GitHubReleasesAdapter()
    assert adapter.adapter_name == "github_releases_v1"


# ── _parse_timestamp ─────────────────────────────────────────────────────────


def test_parse_timestamp_handles_zulu_and_offsets_and_garbage() -> None:
    import datetime as dt

    ts = _parse_timestamp("2026-06-05T03:33:12Z")
    assert ts is not None
    assert ts.tzinfo is not None
    assert ts.utcoffset() == dt.timedelta(0)

    off = _parse_timestamp("2026-06-05T03:33:12+02:00")
    assert off is not None and off.utcoffset() == dt.timedelta(hours=2)

    assert _parse_timestamp(None) is None
    assert _parse_timestamp("") is None
    assert _parse_timestamp("not-a-date") is None


# ── RawDocument dataclass ────────────────────────────────────────────────────


def test_raw_document_defaults() -> None:
    doc = RawDocument(content=b"hello")
    assert doc.content == b"hello"
    assert doc.language == "en"
    assert doc.content_type == "application/octet-stream"
    assert doc.metadata == {}
    assert doc.external_id is None


# ── WikidataChangesAdapter.fetch — mock HTTP ─────────────────────────────────


@pytest.mark.asyncio
async def test_wikidata_adapter_yields_raw_documents() -> None:
    """Adapter should yield one RawDocument per change record."""
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 123,
                    "revid": 456,
                    "title": "Q42",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T12:00:00Z",
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={},
        cursor_state=None,
        max_documents=10,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    doc = docs[0]
    assert doc.external_id == "456"
    assert doc.title == "Q42"
    assert doc.language == "en"
    assert doc.content_type == "application/json"
    payload = json.loads(doc.content)
    assert payload["change"]["rcid"] == 123


@pytest.mark.asyncio
async def test_wikidata_adapter_rate_limit_raises() -> None:
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    with pytest.raises(SourceRateLimitError):
        async for _ in adapter.fetch(
            adapter_config={},
            cursor_state=None,
            max_documents=10,
            http_client=client,
        ):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_wikidata_adapter_server_error_raises() -> None:
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    with pytest.raises(SourceFetchError):
        async for _ in adapter.fetch(
            adapter_config={},
            cursor_state=None,
            max_documents=10,
            http_client=client,
        ):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_wikidata_adapter_max_documents_respected() -> None:
    """Adapter must not yield more than max_documents even if API returns more."""
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    changes = [
        {
            "rcid": i,
            "revid": i * 10,
            "title": f"Q{i}",
            "ns": 0,
            "type": "edit",
            "timestamp": "2026-06-04T12:00:00Z",
        }
        for i in range(20)
    ]
    api_response = {"query": {"recentchanges": changes}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={},
        cursor_state=None,
        max_documents=5,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 5


@pytest.mark.asyncio
async def test_wikidata_adapter_writes_cursor_sink_last_timestamp() -> None:
    """Adapter records the newest timestamp seen into cursor_sink for next run."""
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    # Newest-first order: first change is the newest.
    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 2,
                    "revid": 20,
                    "title": "Q2",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T12:00:00Z",
                },
                {
                    "rcid": 1,
                    "revid": 10,
                    "title": "Q1",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T11:00:00Z",
                },
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    sink: dict[str, object] = {}
    async for _ in adapter.fetch(
        adapter_config={},
        cursor_state=None,
        max_documents=10,
        http_client=client,
        cursor_sink=sink,
    ):
        pass
    await client.aclose()

    assert sink["last_timestamp"] == "2026-06-04T12:00:00Z"


@pytest.mark.asyncio
async def test_wikidata_adapter_resume_sets_rcend() -> None:
    """A stored last_timestamp is sent as rcend to bound the incremental window."""
    import httpx
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"query": {"recentchanges": []}})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = WikidataChangesAdapter()
    async for _ in adapter.fetch(
        adapter_config={},
        cursor_state={"last_timestamp": "2026-06-04T10:00:00Z"},
        max_documents=10,
        http_client=client,
    ):
        pass
    await client.aclose()

    assert seen_params.get("rcend") == "2026-06-04T10:00:00Z"
    assert seen_params.get("rcdir") == "older"


# ── GitHubReleasesAdapter.fetch — mock HTTP ──────────────────────────────────


@pytest.mark.asyncio
async def test_github_adapter_yields_releases() -> None:
    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    releases = [
        {
            "id": 1001,
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "html_url": "https://github.com/example/repo/releases/tag/v1.0.0",
            "published_at": "2026-06-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
            "body": "Initial release.",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=releases, headers={"Link": ""})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = GitHubReleasesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"repos": ["example/repo"]},
        cursor_state=None,
        max_documents=10,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    doc = docs[0]
    assert doc.external_id == "1001"
    assert "example/repo" in (doc.title or "")
    assert doc.metadata["repo"] == "example/repo"
    assert doc.metadata["tag"] == "v1.0.0"


@pytest.mark.asyncio
async def test_github_adapter_skips_prereleases_by_default() -> None:
    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    releases = [
        {
            "id": 1,
            "tag_name": "v2.0.0-rc1",
            "name": "RC1",
            "html_url": "https://github.com/x/y/releases/tag/v2.0.0-rc1",
            "published_at": "2026-06-01T00:00:00Z",
            "prerelease": True,
            "draft": False,
            "body": "",
        },
        {
            "id": 2,
            "tag_name": "v1.9.0",
            "name": "Stable",
            "html_url": "https://github.com/x/y/releases/tag/v1.9.0",
            "published_at": "2026-05-01T00:00:00Z",
            "prerelease": False,
            "draft": False,
            "body": "Stable release.",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=releases, headers={"Link": ""})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = GitHubReleasesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"repos": ["x/y"], "include_prereleases": "false"},
        cursor_state=None,
        max_documents=10,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "2"


@pytest.mark.asyncio
async def test_github_adapter_no_repos_yields_nothing() -> None:
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    adapter = GitHubReleasesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"repos": []},
        cursor_state=None,
        max_documents=10,
    ):
        docs.append(doc)

    assert docs == []


@pytest.mark.asyncio
async def test_github_adapter_rate_limit_raises() -> None:
    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = GitHubReleasesAdapter()
    with pytest.raises(SourceRateLimitError):
        async for _ in adapter.fetch(
            adapter_config={"repos": ["x/y"]},
            cursor_state=None,
            max_documents=10,
            http_client=client,
        ):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_github_adapter_primary_rate_limit_403_header_raises() -> None:
    """A 403 with x-ratelimit-remaining: 0 is treated as rate limiting (no body marker)."""
    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "Forbidden"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = GitHubReleasesAdapter()
    with pytest.raises(SourceRateLimitError):
        async for _ in adapter.fetch(
            adapter_config={"repos": ["x/y"]},
            cursor_state=None,
            max_documents=10,
            http_client=client,
        ):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_github_adapter_does_not_mutate_borrowed_client_headers() -> None:
    """A borrowed client's headers must not be permanently mutated with auth."""
    import os

    import httpx
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"Link": ""})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    before = dict(client.headers)

    os.environ["GITHUB_TOKEN"] = "test-token-should-not-leak"
    try:
        adapter = GitHubReleasesAdapter()
        async for _ in adapter.fetch(
            adapter_config={"repos": ["x/y"]},
            cursor_state=None,
            max_documents=5,
            http_client=client,
        ):
            pass
    finally:
        os.environ.pop("GITHUB_TOKEN", None)

    # The borrowed client must not carry our Authorization header afterward.
    assert "authorization" not in {k.lower() for k in client.headers}
    assert dict(client.headers) == before
    await client.aclose()


# ── ingest_source job — fake asyncpg pool ────────────────────────────────────


def _make_fake_pool(
    source_row: dict[str, Any] | None,
    last_run_row: dict[str, Any] | None = None,
    last_run_rows: list[dict[str, Any]] | None = None,
    run_id: uuid.UUID | None = None,
) -> Any:
    """Build a minimal fake asyncpg pool for ingest_source tests."""
    if run_id is None:
        run_id = uuid.uuid4()

    pool = MagicMock()

    # fetchrow: first call returns source row, second returns last_run_row.
    call_count = {"n": 0}

    async def fake_fetchrow(query: str, *args: Any) -> Any:
        call_count["n"] += 1
        if "FROM sources" in query:
            if source_row is None:
                return None
            return source_row
        if "ingestion_runs" in query and "cursor_state" in query:
            return last_run_row
        return None

    async def fake_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO ingestion_runs" in query:
            return run_id
        # source_documents insert — return a UUID to simulate new row.
        if "INSERT INTO source_documents" in query:
            return uuid.uuid4()
        return None

    async def fake_execute(query: str, *args: Any) -> str:
        return "OK"

    async def fake_fetch(query: str, *args: Any) -> list[Any]:
        if "ingestion_runs" in query and "cursor_state" in query:
            if last_run_rows is not None:
                return last_run_rows
            if last_run_row is not None:
                return [last_run_row]
        return []

    pool.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool.fetchval = AsyncMock(side_effect=fake_fetchval)
    pool.execute = AsyncMock(side_effect=fake_execute)
    pool.fetch = AsyncMock(side_effect=fake_fetch)

    return pool


def _make_source_row(
    source_id: uuid.UUID,
    adapter_name: str = "fake_v1",
    adapter_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "slug": "test-source",
        "adapter_name": adapter_name,
        "adapter_config": adapter_config or {},
        "is_active": True,
        "is_paused": False,
        "redistribution_allowed": True,
        "summary_allowed": True,
        "citation_only": False,
        "rate_limit_requests_per_minute": None,
    }


@pytest.mark.asyncio
async def test_ingest_source_inactive_source_raises() -> None:
    """ingest_source raises ValueError for inactive sources."""
    source_id = uuid.uuid4()
    row = _make_source_row(source_id)
    row["is_active"] = False
    pool = _make_fake_pool(source_row=row)

    with pytest.raises(ValueError, match="inactive"):
        await ingest_source(source_id=str(source_id), pool=pool, storage=None)


@pytest.mark.asyncio
async def test_ingest_source_missing_source_raises() -> None:
    """ingest_source raises ValueError when source row does not exist."""
    source_id = uuid.uuid4()
    pool = _make_fake_pool(source_row=None)

    with pytest.raises(ValueError, match="not found"):
        await ingest_source(source_id=str(source_id), pool=pool, storage=None)


@pytest.mark.asyncio
async def test_ingest_source_paused_returns_zero_counters() -> None:
    """ingest_source returns all-zero counters for paused sources."""
    source_id = uuid.uuid4()
    row = _make_source_row(source_id)
    row["is_paused"] = True
    pool = _make_fake_pool(source_row=row)

    result = await ingest_source(source_id=str(source_id), pool=pool, storage=None)
    assert result == {"fetched": 0, "new": 0, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_ingest_source_success_with_fake_adapter() -> None:
    """ingest_source: docs are fetched, hashed, inserted, and counters returned."""
    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="wikidata_changes_v1")
    pool = _make_fake_pool(source_row=row)

    # Patch Wikidata API to return one change.
    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 999,
                    "revid": 9999,
                    "title": "Q1",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T00:00:00Z",
                }
            ]
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    reg = SourceRegistry()
    reg.register_all_defaults()

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        http_client=client,
        max_documents=5,
        registry=reg,
    )
    await client.aclose()

    assert result["fetched"] == 1
    assert result["new"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_ingest_source_records_owned_http_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Owned source HTTP clients append real request counts to provider_usage_events."""
    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="fake_http_v1")
    pool = _make_fake_pool(source_row=row)

    class FakeHttpAdapter:
        adapter_name = "fake_http_v1"

        async def fetch(
            self,
            *,
            adapter_config: dict[str, object],
            cursor_state: dict[str, object] | None = None,
            max_documents: int = 200,
            http_client: object | None = None,
            cursor_sink: dict[str, object] | None = None,
        ) -> Any:
            assert isinstance(http_client, httpx.AsyncClient)
            await http_client.get("https://sources.example.test/document")
            yield RawDocument(
                content=b"hello",
                external_id="fake-http:1",
                title="Fake HTTP document",
                published_at="2026-06-06T00:00:00Z",
                content_type="text/plain",
            )

    def counted_mock_client(
        usage: ingest_jobs._HttpUsageCounter,  # pyright: ignore[reportPrivateUsage]
    ) -> tuple[httpx.AsyncClient, bool]:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        return (
            httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                event_hooks={"request": [usage.record_request]},
            ),
            True,
        )

    monkeypatch.setattr(ingest_jobs, "_make_counted_http_client", counted_mock_client)
    reg = SourceRegistry()
    reg.register(FakeHttpAdapter())

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        max_documents=1,
        registry=reg,
        trigger="backfill",
    )

    assert result["new"] == 1
    usage_calls = [
        call
        for call in pool.execute.call_args_list
        if "INSERT INTO provider_usage_events" in call.args[0]
    ]
    assert len(usage_calls) == 1
    args = usage_calls[0].args
    assert args[1] == "source_http"
    assert args[2] == "requests"
    assert args[4] == 1
    metadata = json.loads(args[8])
    assert metadata["source_id"] == str(source_id)
    assert metadata["source_slug"] == "test-source"
    assert metadata["adapter_name"] == "fake_http_v1"
    assert metadata["trigger"] == "backfill"
    assert metadata["requests_by_host"] == {"sources.example.test": 1}


@pytest.mark.asyncio
async def test_ingest_source_http_usage_recording_is_non_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing observability migrations must not fail a successful ingest run."""
    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="fake_http_v1")
    pool = _make_fake_pool(source_row=row)

    async def execute_with_missing_usage_table(query: str, *args: Any) -> str:
        if "INSERT INTO provider_usage_events" in query:
            raise RuntimeError("relation provider_usage_events does not exist")
        return "OK"

    pool.execute = AsyncMock(side_effect=execute_with_missing_usage_table)

    class FakeHttpAdapter:
        adapter_name = "fake_http_v1"

        async def fetch(
            self,
            *,
            adapter_config: dict[str, object],
            cursor_state: dict[str, object] | None = None,
            max_documents: int = 200,
            http_client: object | None = None,
            cursor_sink: dict[str, object] | None = None,
        ) -> Any:
            assert isinstance(http_client, httpx.AsyncClient)
            await http_client.get("https://sources.example.test/document")
            yield RawDocument(content=b"hello", external_id="fake-http:1")

    def counted_mock_client(
        usage: ingest_jobs._HttpUsageCounter,  # pyright: ignore[reportPrivateUsage]
    ) -> tuple[httpx.AsyncClient, bool]:
        return (
            httpx.AsyncClient(
                transport=httpx.MockTransport(lambda req: httpx.Response(200, text="ok")),
                event_hooks={"request": [usage.record_request]},
            ),
            True,
        )

    monkeypatch.setattr(ingest_jobs, "_make_counted_http_client", counted_mock_client)
    reg = SourceRegistry()
    reg.register(FakeHttpAdapter())

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        max_documents=1,
        registry=reg,
    )

    assert result["new"] == 1


@pytest.mark.asyncio
async def test_ingest_source_backfill_cursor_is_scoped_to_effective_config() -> None:
    """A changed backfill window must not reuse an incompatible cursor token."""
    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="fake_cursor_v1")
    last_run_row = {
        "cursor_state": {
            "offset": 200,
            "__intercal_cursor_scope": {
                "trigger": "backfill",
                "adapter_config_hash": "old-window",
            },
        }
    }
    pool = _make_fake_pool(source_row=row, last_run_row=last_run_row)
    seen_cursor_state: list[dict[str, object] | None] = []

    class FakeCursorAdapter:
        adapter_name = "fake_cursor_v1"

        async def fetch(
            self,
            *,
            adapter_config: dict[str, object],
            cursor_state: dict[str, object] | None = None,
            max_documents: int = 200,
            http_client: object | None = None,
            cursor_sink: dict[str, object] | None = None,
        ) -> Any:
            seen_cursor_state.append(cursor_state)
            if cursor_sink is not None:
                cursor_sink["offset"] = 1
            yield RawDocument(
                content=json.dumps(adapter_config, sort_keys=True).encode(),
                external_id="fake:1",
                title="Fake backfill doc",
                published_at="2022-11-01T00:00:00Z",
                content_type="application/json",
            )

    reg = SourceRegistry()
    reg.register(FakeCursorAdapter())

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        max_documents=1,
        registry=reg,
        adapter_config_overrides={"start_date": "2022-11-01", "end_date": "2022-11-30"},
        trigger="backfill",
    )

    assert result["new"] == 1
    assert seen_cursor_state == [None]
    cursor_updates = [
        call.args[6]
        for call in pool.execute.call_args_list
        if "cursor_state = $6::jsonb" in call.args[0]
    ]
    assert cursor_updates
    persisted = json.loads(cursor_updates[0])
    assert persisted["offset"] == 1
    assert persisted["__intercal_cursor_scope"]["trigger"] == "backfill"
    assert persisted["__intercal_cursor_scope"]["adapter_config_hash"] != "old-window"


@pytest.mark.asyncio
async def test_ingest_source_reuses_matching_backfill_cursor_from_recent_history() -> None:
    """Returning to an earlier backfill window resumes its scoped cursor.

    A later successful run for a different date window must not hide the
    newest matching cursor for this effective adapter config.
    """
    source_id = uuid.uuid4()
    overrides: dict[str, object] = {
        "start_date": "2022-11-01",
        "end_date": "2022-11-30",
    }
    matching_scope = ingest_jobs._cursor_scope(  # pyright: ignore[reportPrivateUsage]
        overrides,
        trigger="backfill",
    )
    row = _make_source_row(source_id, adapter_name="fake_cursor_v1")
    pool = _make_fake_pool(
        source_row=row,
        last_run_rows=[
            {
                "cursor_state": {
                    "offset": 999,
                    "__intercal_cursor_scope": {
                        "trigger": "backfill",
                        "adapter_config_hash": "newer-other-window",
                    },
                }
            },
            {
                "cursor_state": {
                    "offset": 200,
                    "__intercal_cursor_scope": matching_scope,
                }
            },
        ],
    )
    seen_cursor_state: list[dict[str, object] | None] = []

    class FakeCursorAdapter:
        adapter_name = "fake_cursor_v1"

        async def fetch(
            self,
            *,
            adapter_config: dict[str, object],
            cursor_state: dict[str, object] | None = None,
            max_documents: int = 200,
            http_client: object | None = None,
            cursor_sink: dict[str, object] | None = None,
        ) -> Any:
            seen_cursor_state.append(cursor_state)
            if cursor_sink is not None:
                cursor_sink["offset"] = 201
            yield RawDocument(
                content=b"resumed",
                external_id="fake:resumed",
                title="Fake resumed backfill doc",
                published_at="2022-11-02T00:00:00Z",
                content_type="text/plain",
            )

    reg = SourceRegistry()
    reg.register(FakeCursorAdapter())

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        max_documents=1,
        registry=reg,
        adapter_config_overrides=overrides,
        trigger="backfill",
    )

    assert result["new"] == 1
    assert seen_cursor_state == [{"offset": 200, "__intercal_cursor_scope": matching_scope}]


@pytest.mark.asyncio
async def test_ingest_source_persists_content_type_in_metadata() -> None:
    """The adapter's content_type must be written into source_documents.metadata
    so W2 normalisation can route deterministically without re-sniffing."""
    import json as _json

    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="wikidata_changes_v1")

    insert_args: list[tuple[Any, ...]] = []
    pool = MagicMock()

    async def fake_fetchrow(query: str, *args: Any) -> Any:
        if "FROM sources" in query:
            return row
        return None

    async def fake_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO ingestion_runs" in query:
            return uuid.uuid4()
        if "INSERT INTO source_documents" in query:
            insert_args.append(args)
            return uuid.uuid4()
        return None

    async def fake_execute(query: str, *args: Any) -> str:
        return "OK"

    async def fake_fetch(query: str, *args: Any) -> list[Any]:
        return []

    pool.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool.fetchval = AsyncMock(side_effect=fake_fetchval)
    pool.execute = AsyncMock(side_effect=fake_execute)
    pool.fetch = AsyncMock(side_effect=fake_fetch)

    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 999,
                    "revid": 9999,
                    "title": "Q1",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T00:00:00Z",
                }
            ]
        }
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=api_response))
    client = httpx.AsyncClient(transport=transport)
    reg = SourceRegistry()
    reg.register_all_defaults()

    await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        http_client=client,
        max_documents=5,
        registry=reg,
    )
    await client.aclose()

    assert insert_args, "expected an INSERT INTO source_documents"
    metadata_json = insert_args[0][-1]  # last positional arg is the metadata JSON
    metadata = _json.loads(metadata_json)
    assert metadata.get("content_type") == "application/json"


@pytest.mark.asyncio
async def test_ingest_source_snapshots_policy_for_historical_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical adapters still enter through ingest_source and source policy.

    The adapter fetches registry metadata only. Policy decisions come from the
    source row and are snapshotted onto source_documents at ingest time.
    """

    import httpx

    def fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        if host != "registry.example.com":
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    source_id = uuid.uuid4()
    row = _make_source_row(
        source_id,
        adapter_name="registry_releases_v1",
        adapter_config={
            "pypi_projects": ["openai"],
            "pypi_api_url": "https://registry.example.com/pypi",
            "start_date": "2023-01-01",
        },
    )
    row["redistribution_allowed"] = False
    row["summary_allowed"] = True
    row["citation_only"] = True

    insert_args: list[tuple[Any, ...]] = []
    pool = MagicMock()

    async def fake_fetchrow(query: str, *args: Any) -> Any:
        if "FROM sources" in query:
            return row
        return None

    async def fake_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO ingestion_runs" in query:
            return uuid.uuid4()
        if "INSERT INTO source_documents" in query:
            insert_args.append(args)
            return uuid.uuid4()
        return None

    pool.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool.fetchval = AsyncMock(side_effect=fake_fetchval)
    pool.execute = AsyncMock(return_value="OK")
    pool.fetch = AsyncMock(return_value=[])

    response_payload = {
        "info": {"name": "openai"},
        "releases": {"1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00Z"}]},
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    )
    reg = SourceRegistry()
    reg.register_all_defaults()

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=None,
        http_client=client,
        max_documents=5,
        registry=reg,
    )
    await client.aclose()

    assert result["new"] == 1
    assert insert_args, "expected source_documents insert"
    args = insert_args[0]
    assert args[8] is None  # cleaned_text suppressed by citation_only.
    assert args[9] is None
    assert args[11] is False
    assert args[12] is True
    assert args[13] is True
    metadata = json.loads(args[14])
    assert metadata["adapter"] == "registry_releases_v1"
    assert metadata["content_type"] == "application/json"


@pytest.mark.asyncio
async def test_ingest_source_stores_raw_and_records_storage_key() -> None:
    """For new docs with storage + redistribution, raw bytes are stored and the
    resulting key is written back to source_documents.raw_storage_key."""
    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="wikidata_changes_v1")
    row["redistribution_allowed"] = True
    new_doc_id = uuid.uuid4()

    executed: list[tuple[str, tuple[Any, ...]]] = []
    pool = MagicMock()

    async def fake_fetchrow(query: str, *args: Any) -> Any:
        if "FROM sources" in query:
            return row
        return None

    async def fake_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO ingestion_runs" in query:
            return uuid.uuid4()
        if "INSERT INTO source_documents" in query:
            return new_doc_id
        return None

    async def fake_execute(query: str, *args: Any) -> str:
        executed.append((query, args))
        return "OK"

    async def fake_fetch(query: str, *args: Any) -> list[Any]:
        return []

    pool.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool.fetchval = AsyncMock(side_effect=fake_fetchval)
    pool.execute = AsyncMock(side_effect=fake_execute)
    pool.fetch = AsyncMock(side_effect=fake_fetch)

    # Fake storage capturing put() calls.
    put_calls: list[tuple[str, bytes]] = []

    class FakeStorage:
        async def put(self, key: str, data: bytes, **kwargs: Any) -> None:
            put_calls.append((key, data))

    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 7,
                    "revid": 77,
                    "title": "Q7",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T00:00:00Z",
                }
            ]
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    reg = SourceRegistry()
    reg.register_all_defaults()

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool,
        storage=FakeStorage(),
        http_client=client,
        max_documents=5,
        registry=reg,
    )
    await client.aclose()

    assert result["new"] == 1
    # Raw bytes were stored under the content-hash-addressed key.
    assert len(put_calls) == 1
    stored_key = put_calls[0][0]
    assert stored_key.startswith(f"raw/{source_id}/")
    # The key was written back to the document row via UPDATE.
    update_keys = [a for q, a in executed if "UPDATE source_documents SET raw_storage_key" in q]
    assert update_keys, "expected raw_storage_key UPDATE"
    assert update_keys[0][1] == stored_key


@pytest.mark.asyncio
async def test_ingest_source_deduplicates_existing_docs() -> None:
    """ingest_source skips documents when fetchval returns None (ON CONFLICT)."""
    import httpx
    from intercal_shared.source_registry import SourceRegistry

    source_id = uuid.uuid4()
    row = _make_source_row(source_id, adapter_name="wikidata_changes_v1")

    run_id = uuid.uuid4()
    pool_obj = MagicMock()

    async def fake_fetchrow(query: str, *args: Any) -> Any:
        if "FROM sources" in query:
            return row
        if "ingestion_runs" in query:
            return None
        return None

    async def fake_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO ingestion_runs" in query:
            return run_id
        # Return None to simulate ON CONFLICT DO NOTHING.
        if "INSERT INTO source_documents" in query:
            return None
        return None

    async def fake_execute(query: str, *args: Any) -> str:
        return "OK"

    async def fake_fetch(query: str, *args: Any) -> list[Any]:
        return []

    pool_obj.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool_obj.fetchval = AsyncMock(side_effect=fake_fetchval)
    pool_obj.execute = AsyncMock(side_effect=fake_execute)
    pool_obj.fetch = AsyncMock(side_effect=fake_fetch)

    api_response = {
        "query": {
            "recentchanges": [
                {
                    "rcid": 1,
                    "revid": 10,
                    "title": "Q2",
                    "ns": 0,
                    "type": "edit",
                    "timestamp": "2026-06-04T00:00:00Z",
                }
            ]
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    reg = SourceRegistry()
    reg.register_all_defaults()

    result = await ingest_source(
        source_id=str(source_id),
        pool=pool_obj,
        storage=None,
        http_client=client,
        max_documents=5,
        registry=reg,
    )
    await client.aclose()

    assert result["fetched"] == 1
    assert result["new"] == 0
    assert result["skipped"] == 1


# ── score_source_health ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_source_health_no_runs_returns_minus_one() -> None:
    """score_source_health returns -1.0 when no runs exist."""
    source_id = uuid.uuid4()
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.execute = AsyncMock(return_value="OK")

    result = await score_source_health(source_id=str(source_id), pool=pool)
    assert result == -1.0
    # Should NOT update sources row.
    pool.execute.assert_not_called()


@pytest.mark.asyncio
async def test_score_source_health_all_succeeded() -> None:
    """score_source_health returns 1.0 when all runs succeeded."""
    source_id = uuid.uuid4()

    class FakeRow:
        def __getitem__(self, key: str) -> str:
            return "succeeded"

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[FakeRow() for _ in range(5)])
    pool.fetchrow = AsyncMock(return_value={"consecutive_failures": 0})
    pool.execute = AsyncMock(return_value="OK")

    result = await score_source_health(source_id=str(source_id), pool=pool)
    assert result == 1.0
    pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_score_source_health_with_failures_and_streak() -> None:
    """score_source_health applies streak penalty correctly."""

    class FakeRow:
        def __init__(self, status: str) -> None:
            self._status = status

        def __getitem__(self, key: str) -> str | int:
            if key == "status":
                return self._status
            if key == "consecutive_failures":
                return 2
            return ""

    pool = MagicMock()
    # 3 succeeded out of 5 = 0.60 base; 2 consecutive failures = -0.20 penalty = 0.40
    pool.fetch = AsyncMock(
        return_value=[
            FakeRow("succeeded"),
            FakeRow("succeeded"),
            FakeRow("succeeded"),
            FakeRow("failed"),
            FakeRow("failed"),
        ]
    )
    pool.fetchrow = AsyncMock(return_value={"consecutive_failures": 2})
    pool.execute = AsyncMock(return_value="OK")

    source_id = uuid.uuid4()
    result = await score_source_health(source_id=str(source_id), pool=pool)
    assert result == 0.40
