"""Workstream 1 tests: source registry, adapter contracts, ingest_source job.

No live network or database is required.  All external calls are intercepted
via httpx.MockTransport or a fake asyncpg pool.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from intercal_ingest.jobs import ingest_source, score_source_health
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
    """register_all_defaults() loads Wikidata + GitHub adapters."""
    reg = SourceRegistry()
    reg.register_all_defaults()
    names = reg.all_names()
    assert "wikidata_changes_v1" in names
    assert "github_releases_v1" in names


# ── SourcePort contract for built-in adapters ────────────────────────────────


def test_wikidata_adapter_has_correct_name() -> None:
    from intercal_shared.adapters.source_wikidata import WikidataChangesAdapter

    adapter = WikidataChangesAdapter()
    assert adapter.adapter_name == "wikidata_changes_v1"


def test_github_adapter_has_correct_name() -> None:
    from intercal_shared.adapters.source_github import GitHubReleasesAdapter

    adapter = GitHubReleasesAdapter()
    assert adapter.adapter_name == "github_releases_v1"


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


# ── ingest_source job — fake asyncpg pool ────────────────────────────────────


def _make_fake_pool(
    source_row: dict[str, Any] | None,
    last_run_row: dict[str, Any] | None = None,
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
