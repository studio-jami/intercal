from __future__ import annotations

import json
import socket
from typing import Any

import pytest
from intercal_shared.adapters.source_github import GitHubReleasesAdapter
from intercal_shared.adapters.source_historical import (
    ArxivAdapter,
    MediaWikiRevisionsAdapter,
    RegistryReleasesAdapter,
    RssFeedAdapter,
    WikidataSparqlBatchAdapter,
)
from intercal_shared.ports.source import RawDocument, SourceFetchError
from intercal_shared.source_registry import SourceRegistry


def _fake_getaddrinfo(mapping: dict[str, list[str]]) -> Any:
    def _impl(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        ips = mapping.get(host)
        if ips is None:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        out: list[Any] = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr: tuple[Any, ...] = (
                (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
            )
            out.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))
        return out

    return _impl


def test_registry_register_all_defaults_includes_historical_adapters() -> None:
    reg = SourceRegistry()
    reg.register_all_defaults()
    assert "registry_releases_v1" in reg.all_names()
    assert "arxiv_v1" in reg.all_names()
    assert "rss_feed_v1" in reg.all_names()
    assert "wikidata_sparql_batch_v1" in reg.all_names()
    assert "mediawiki_revisions_v1" in reg.all_names()


@pytest.mark.asyncio
async def test_registry_releases_adapter_yields_pypi_and_npm_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _fake_getaddrinfo({"pypi.org": ["151.101.0.223"], "registry.npmjs.org": ["104.16.0.35"]}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "pypi.org" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "info": {"name": "openai"},
                    "releases": {
                        "1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00Z"}],
                        "1.1.0": [{"upload_time_iso_8601": "2023-02-01T00:00:00Z"}],
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "2.0.0"},
                "time": {"1.0.0": "2023-01-15T00:00:00.000Z"},
                "versions": {"1.0.0": {"name": "@scope/pkg", "version": "1.0.0"}},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = RegistryReleasesAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={
            "pypi_projects": ["openai"],
            "npm_packages": ["@scope/pkg"],
            "start_date": "2023-01-10",
            "end_date": "2023-02-28",
        },
        max_documents=10,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert [doc.external_id for doc in docs] == ["pypi:openai:1.1.0", "npm:@scope/pkg:1.0.0"]
    assert json.loads(docs[0].content)["registry"] == "pypi"
    assert docs[1].metadata["registry"] == "npm"
    assert sink["offsets"] == {"pypi:openai": 1, "npm:@scope/pkg": 1}


@pytest.mark.asyncio
async def test_registry_releases_adapter_yields_huggingface_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"huggingface.co": ["18.64.0.1"]}))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"id": "org/model", "createdAt": "2024-04-18T12:00:00.000Z"},
            )
        )
    )
    adapter = RegistryReleasesAdapter()
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"huggingface_models": ["org/model"], "start_date": "2024-01-01"},
        max_documents=5,
        http_client=client,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "huggingface:org/model"
    assert docs[0].url == "https://huggingface.co/org/model"


@pytest.mark.asyncio
async def test_arxiv_adapter_yields_atom_entries_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"export.arxiv.org": ["151.101.1.91"]})
    )
    atom = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2303.00001</id>
        <title> Test Paper </title>
        <summary> Abstract text. </summary>
        <published>2023-03-01T00:00:00Z</published>
        <updated>2023-03-02T00:00:00Z</updated>
        <author><name>Ada Lovelace</name></author>
        <category term="cs.CL" />
      </entry>
    </feed>"""
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, text=atom)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ArxivAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={
            "categories": ["cs.CL"],
            "start_date": "2023-03-01",
            "end_date": "2023-03-31",
        },
        max_documents=5,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "https://arxiv.org/abs/2303.00001"
    assert json.loads(docs[0].content)["authors"] == ["Ada Lovelace"]
    assert "submittedDate:[202303010000 TO 202303312359]" in seen_params["search_query"]
    assert sink["start"] == 1


@pytest.mark.asyncio
async def test_rss_feed_adapter_yields_entries_dedupes_and_rejects_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"feeds.example.com": ["93.184.216.34"]})
    )
    rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>item-1</guid><title>Launch</title>
        <link>https://example.com/launch</link>
        <pubDate>Tue, 05 Mar 2024 10:00:00 GMT</pubDate>
        <description>Summary.</description>
      </item>
    </channel></rss>"""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=rss))
    )
    adapter = RssFeedAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"feed_urls": ["https://feeds.example.com/rss.xml"]},
        cursor_state={"seen_ids": []},
        max_documents=5,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "item-1"
    assert sink["seen_ids"] == ["item-1"]
    assert sink["latest_published_at"] == "2024-03-05T10:00:00Z"

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))
    with pytest.raises(SourceFetchError, match="SSRF"):
        async for _ in adapter.fetch(
            adapter_config={"feed_urls": ["http://169.254.169.254/rss.xml"]},
            max_documents=1,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        ):
            pass


@pytest.mark.asyncio
async def test_wikidata_sparql_batch_adapter_yields_binding_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"query.wikidata.org": ["208.80.154.224"]})
    )
    data = {
        "results": {
            "bindings": [
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q42"},
                    "itemLabel": {"type": "literal", "value": "Douglas Adams"},
                }
            ]
        }
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    )
    adapter = WikidataSparqlBatchAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"entity_ids": ["Q42"]},
        max_documents=5,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "wikidata_sparql:http://www.wikidata.org/entity/Q42"
    assert json.loads(docs[0].content)["qid"] == "Q42"
    assert sink["offset"] == 1


@pytest.mark.asyncio
async def test_mediawiki_revisions_adapter_yields_revisions_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"en.wikipedia.org": ["208.80.154.224"]})
    )
    data = {
        "query": {
            "pages": [
                {
                    "title": "ChatGPT",
                    "revisions": [
                        {
                            "revid": 123,
                            "parentid": 122,
                            "timestamp": "2022-11-30T00:00:00Z",
                            "user": "Editor",
                            "comment": "create",
                            "slots": {"main": {"content": "ChatGPT page text"}},
                        }
                    ],
                }
            ]
        },
        "continue": {"rvcontinue": "next-token"},
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    )
    adapter = MediaWikiRevisionsAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={"pages": ["ChatGPT"], "start_date": "2022-11-30T00:00:00Z"},
        max_documents=1,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert len(docs) == 1
    assert docs[0].external_id == "mediawiki:ChatGPT:123"
    assert "ChatGPT page text" in json.loads(docs[0].content)["revision"]["content"]
    assert sink["rvcontinue_by_page"] == {"ChatGPT": "next-token"}


@pytest.mark.asyncio
async def test_github_releases_adapter_filters_historical_window_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"api.github.com": ["140.82.112.6"]})
    )
    releases = [
        {
            "id": 1,
            "tag_name": "v2",
            "name": "v2",
            "html_url": "https://github.com/x/y/releases/tag/v2",
            "published_at": "2024-01-01T00:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        {
            "id": 2,
            "tag_name": "v1",
            "name": "v1",
            "html_url": "https://github.com/x/y/releases/tag/v1",
            "published_at": "2023-01-01T00:00:00Z",
            "prerelease": False,
            "draft": False,
        },
    ]
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_pages.append(dict(request.url.params).get("page", ""))
        return httpx.Response(200, json=releases, headers={"Link": '<x>; rel="next"'})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GitHubReleasesAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={
            "repos": ["x/y"],
            "start_date": "2023-06-01",
            "end_date": "2024-12-31",
            "per_page": "2",
        },
        cursor_state={"page_by_repo": {"x/y": 3}},
        max_documents=3,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert seen_pages == ["3"]
    assert [doc.external_id for doc in docs] == ["1"]
    assert sink["page_by_repo"] == {}


@pytest.mark.asyncio
async def test_github_historical_window_caps_page_walk_when_skipping_newer_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_getaddrinfo({"api.github.com": ["140.82.112.6"]})
    )
    releases = [
        {
            "id": 10,
            "tag_name": "v10",
            "name": "v10",
            "html_url": "https://github.com/x/y/releases/tag/v10",
            "published_at": "2025-01-01T00:00:00Z",
            "prerelease": False,
            "draft": False,
        }
    ]
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_pages.append(dict(request.url.params).get("page", ""))
        return httpx.Response(200, json=releases, headers={"Link": '<x>; rel="next"'})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GitHubReleasesAdapter()
    sink: dict[str, object] = {}
    docs: list[RawDocument] = []
    async for doc in adapter.fetch(
        adapter_config={
            "repos": ["x/y"],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "max_pages_per_repo": "2",
        },
        max_documents=5,
        http_client=client,
        cursor_sink=sink,
    ):
        docs.append(doc)
    await client.aclose()

    assert docs == []
    assert seen_pages == ["1", "2"]
    assert sink["page_by_repo"] == {"x/y": 3}
