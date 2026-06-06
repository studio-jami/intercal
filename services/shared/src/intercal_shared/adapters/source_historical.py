"""Historical source adapters for corpus backfill.

These adapters only fetch and normalize source documents into ``RawDocument``
payloads. They do not extract claims, resolve entities, or write facts.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Iterable, Mapping
from email.utils import parsedate_to_datetime
from typing import Any

from intercal_shared.ports.source import RawDocument, SourceFetchError, SourceRateLimitError
from intercal_shared.ssrf import SsrfError, create_guarded_client, resolve_and_validate

_log = logging.getLogger(__name__)

_USER_AGENT = (
    "intercal/0.1 (https://github.com/JamiStudio/intercal; jamie@yrka.io) python-httpx/0.2x"
)
_DEFAULT_ARXIV_API = "https://export.arxiv.org/api/query"
_DEFAULT_WIKIDATA_SPARQL = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"
_DEFAULT_MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
_DEFAULT_PYPI_API = "https://pypi.org/pypi"
_DEFAULT_NPM_REGISTRY = "https://registry.npmjs.org"
_DEFAULT_HF_API = "https://huggingface.co/api"


class RegistryReleasesAdapter:
    """Fetch release/model records from versioned package and model registries.

    Supported configured origins:
    - PyPI project JSON: ``pypi_projects``.
    - npm package metadata: ``npm_packages``.
    - Hugging Face model metadata: ``huggingface_models``.
    """

    adapter_name = "registry_releases_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        client, owns_client = _get_client(http_client)
        try:
            yielded = 0
            start_date = _parse_date_bound(adapter_config.get("start_date"))
            end_date = _parse_date_bound(adapter_config.get("end_date"), end_of_day=True)
            state = dict(cursor_state or {})
            offsets = _cursor_offsets(state)

            for project in _string_list(adapter_config.get("pypi_projects")):
                if yielded >= max_documents:
                    break
                async for doc in self._fetch_pypi_project(
                    client=client,
                    project=project,
                    adapter_config=adapter_config,
                    start_date=start_date,
                    end_date=end_date,
                    offset=int(offsets.get(f"pypi:{project}", 0)),
                ):
                    if yielded >= max_documents:
                        break
                    yielded += 1
                    offsets[f"pypi:{project}"] = int(offsets.get(f"pypi:{project}", 0)) + 1
                    yield doc

            for package in _string_list(adapter_config.get("npm_packages")):
                if yielded >= max_documents:
                    break
                async for doc in self._fetch_npm_package(
                    client=client,
                    package=package,
                    adapter_config=adapter_config,
                    start_date=start_date,
                    end_date=end_date,
                    offset=int(offsets.get(f"npm:{package}", 0)),
                ):
                    if yielded >= max_documents:
                        break
                    yielded += 1
                    offsets[f"npm:{package}"] = int(offsets.get(f"npm:{package}", 0)) + 1
                    yield doc

            for model_id in _string_list(adapter_config.get("huggingface_models")):
                if yielded >= max_documents:
                    break
                key = f"huggingface:{model_id}"
                if bool(offsets.get(key, 0)):
                    continue
                doc = await self._fetch_huggingface_model(
                    client=client,
                    model_id=model_id,
                    adapter_config=adapter_config,
                    start_date=start_date,
                    end_date=end_date,
                )
                offsets[key] = 1
                if doc is not None:
                    yielded += 1
                    yield doc

            if cursor_sink is not None and offsets:
                cursor_sink["offsets"] = offsets
        finally:
            if owns_client:
                await client.aclose()

    async def _fetch_pypi_project(
        self,
        *,
        client: Any,
        project: str,
        adapter_config: Mapping[str, object],
        start_date: dt.datetime | None,
        end_date: dt.datetime | None,
        offset: int,
    ) -> AsyncIterator[RawDocument]:
        base_url = str(adapter_config.get("pypi_api_url", _DEFAULT_PYPI_API)).rstrip("/")
        url = f"{base_url}/{urllib.parse.quote(project, safe='')}/json"
        response = await _get_json(client, url, source_name=f"PyPI project {project}")
        releases_raw = response.get("releases", {})
        if not isinstance(releases_raw, dict):
            raise SourceFetchError(f"PyPI project {project}: expected releases object")

        rows: list[tuple[dt.datetime | None, str, object]] = []
        for version_raw, files in releases_raw.items():
            version = str(version_raw)
            uploaded_at = _first_upload_time(files)
            if not _within_window(uploaded_at, start_date, end_date):
                continue
            rows.append((uploaded_at, version, files))

        for uploaded_at, version, files in sorted(rows, key=lambda row: row[0] or dt.datetime.min):
            if offset > 0:
                offset -= 1
                continue
            payload = {
                "registry": "pypi",
                "project": project,
                "version": version,
                "release_files": files,
                "project_info": response.get("info", {}),
            }
            yield RawDocument(
                content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
                external_id=f"pypi:{project}:{version}",
                url=f"https://pypi.org/project/{project}/{version}/",
                title=f"PyPI {project} {version}",
                published_at=_format_dt(uploaded_at),
                language="en",
                content_type="application/json",
                metadata={
                    "adapter": self.adapter_name,
                    "registry": "pypi",
                    "project": project,
                    "version": version,
                },
            )

    async def _fetch_npm_package(
        self,
        *,
        client: Any,
        package: str,
        adapter_config: Mapping[str, object],
        start_date: dt.datetime | None,
        end_date: dt.datetime | None,
        offset: int,
    ) -> AsyncIterator[RawDocument]:
        base_url = str(adapter_config.get("npm_registry_url", _DEFAULT_NPM_REGISTRY)).rstrip("/")
        url = f"{base_url}/{urllib.parse.quote(package, safe='@/')}"
        response = await _get_json(client, url, source_name=f"npm package {package}")
        versions = response.get("versions", {})
        times = response.get("time", {})
        if not isinstance(versions, dict) or not isinstance(times, dict):
            raise SourceFetchError(f"npm package {package}: expected versions and time objects")

        rows: list[tuple[dt.datetime | None, str, object]] = []
        for version_raw, version_data in versions.items():
            version = str(version_raw)
            published_at = _parse_dt(str(times.get(version, "")))
            if not _within_window(published_at, start_date, end_date):
                continue
            rows.append((published_at, version, version_data))

        for published_at, version, version_data in sorted(
            rows, key=lambda row: row[0] or dt.datetime.min
        ):
            if offset > 0:
                offset -= 1
                continue
            payload = {
                "registry": "npm",
                "package": package,
                "version": version,
                "published_at": _format_dt(published_at),
                "version_data": version_data,
                "dist_tags": response.get("dist-tags", {}),
            }
            yield RawDocument(
                content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
                external_id=f"npm:{package}:{version}",
                url=f"https://www.npmjs.com/package/{package}/v/{version}",
                title=f"npm {package} {version}",
                published_at=_format_dt(published_at),
                language="en",
                content_type="application/json",
                metadata={
                    "adapter": self.adapter_name,
                    "registry": "npm",
                    "package": package,
                    "version": version,
                },
            )

    async def _fetch_huggingface_model(
        self,
        *,
        client: Any,
        model_id: str,
        adapter_config: Mapping[str, object],
        start_date: dt.datetime | None,
        end_date: dt.datetime | None,
    ) -> RawDocument | None:
        base_url = str(adapter_config.get("huggingface_api_url", _DEFAULT_HF_API)).rstrip("/")
        url = f"{base_url}/models/{urllib.parse.quote(model_id, safe='/')}"
        headers = _optional_bearer_header(adapter_config, "huggingface_token_env", "HF_TOKEN")
        response = await _get_json(
            client,
            url,
            source_name=f"Hugging Face model {model_id}",
            headers=headers,
            params={"cardData": "true"},
        )
        published_at_value = response.get("createdAt") or response.get("lastModified") or ""
        published_at = _parse_dt(str(published_at_value))
        if not _within_window(published_at, start_date, end_date):
            return None
        payload = {"registry": "huggingface", "model_id": model_id, "model_info": response}
        return RawDocument(
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
            external_id=f"huggingface:{model_id}",
            url=f"https://huggingface.co/{model_id}",
            title=f"Hugging Face model {model_id}",
            published_at=_format_dt(published_at),
            language="en",
            content_type="application/json",
            metadata={
                "adapter": self.adapter_name,
                "registry": "huggingface",
                "model_id": model_id,
            },
        )


class ArxivAdapter:
    """Fetch arXiv Atom search results as abstract-first source documents."""

    adapter_name = "arxiv_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        client, owns_client = _get_client(http_client)
        try:
            api_url = str(adapter_config.get("arxiv_api_url", _DEFAULT_ARXIV_API))
            categories = _string_list(adapter_config.get("categories"))
            terms = _string_list(adapter_config.get("search_terms"))
            start_date = str(adapter_config.get("start_date", "2022-11-01"))
            end_date = str(adapter_config.get("end_date", _today_date()))
            search_query = _arxiv_query(
                categories=categories,
                terms=terms,
                start_date=start_date,
                end_date=end_date,
            )
            offset = int(str((cursor_state or {}).get("start", 0)))
            batch_size = min(int(str(adapter_config.get("batch_size", "100"))), 100, max_documents)
            yielded = 0
            next_start = offset

            while yielded < max_documents:
                params = {
                    "search_query": search_query,
                    "start": next_start,
                    "max_results": min(batch_size, max_documents - yielded),
                    "sortBy": str(adapter_config.get("sort_by", "submittedDate")),
                    "sortOrder": str(adapter_config.get("sort_order", "ascending")),
                }
                response_text = await _get_text(client, api_url, params=params, source_name="arXiv")
                entries = _atom_entries(response_text)
                if not entries:
                    break
                for entry in entries:
                    if yielded >= max_documents:
                        break
                    yielded += 1
                    yield _arxiv_entry_to_doc(entry, self.adapter_name)
                next_start += len(entries)
                if len(entries) < int(params["max_results"]):
                    break
            if cursor_sink is not None:
                cursor_sink["start"] = next_start
                cursor_sink["query"] = search_query
        finally:
            if owns_client:
                await client.aclose()


class RssFeedAdapter:
    """Fetch RSS or Atom feed entries from configured feed URLs."""

    adapter_name = "rss_feed_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        client, owns_client = _get_client(http_client)
        try:
            start_date = _parse_date_bound(adapter_config.get("start_date"))
            end_date = _parse_date_bound(adapter_config.get("end_date"), end_of_day=True)
            seen_ids = set(_string_list((cursor_state or {}).get("seen_ids")))
            latest_seen = str((cursor_state or {}).get("latest_published_at", ""))
            latest_seen_dt = _parse_dt(latest_seen)
            emitted_ids: list[str] = []
            emitted_dates: list[dt.datetime] = []
            yielded = 0
            for feed_url in _string_list(adapter_config.get("feed_urls")):
                if yielded >= max_documents:
                    break
                response_text = await _get_text(
                    client, feed_url, source_name=f"RSS feed {feed_url}"
                )
                for item in _feed_items(response_text):
                    item_id = item.get("id") or item.get("link") or item.get("title")
                    published_at = _parse_dt(item.get("published_at", ""))
                    if not item_id or item_id in seen_ids:
                        continue
                    if latest_seen_dt and published_at and published_at <= latest_seen_dt:
                        continue
                    if not _within_window(published_at, start_date, end_date):
                        continue
                    emitted_ids.append(item_id)
                    if published_at is not None:
                        emitted_dates.append(published_at)
                    seen_ids.add(item_id)
                    yielded += 1
                    yield RawDocument(
                        content=json.dumps(item, ensure_ascii=False, sort_keys=True).encode(),
                        external_id=item_id,
                        url=item.get("link") or feed_url,
                        title=item.get("title"),
                        published_at=_format_dt(published_at),
                        language=str(adapter_config.get("language", "en")),
                        content_type="application/json",
                        metadata={
                            "adapter": self.adapter_name,
                            "feed_url": feed_url,
                            "entry_id": item_id,
                        },
                    )
                    if yielded >= max_documents:
                        break
            if cursor_sink is not None:
                cursor_sink["seen_ids"] = sorted(seen_ids)[-500:]
                if emitted_dates:
                    cursor_sink["latest_published_at"] = _format_dt(max(emitted_dates))
        finally:
            if owns_client:
                await client.aclose()


class WikidataSparqlBatchAdapter:
    """Fetch bounded Wikidata SPARQL rows as entity-spine source documents."""

    adapter_name = "wikidata_sparql_batch_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        client, owns_client = _get_client(http_client)
        try:
            endpoint = str(adapter_config.get("sparql_endpoint", _DEFAULT_WIKIDATA_SPARQL))
            entity_ids = _string_list(adapter_config.get("entity_ids"))
            query = str(adapter_config.get("query") or _wikidata_entity_query(entity_ids))
            if not query.strip():
                raise SourceFetchError(
                    "Wikidata SPARQL adapter requires adapter_config['query'] or entity_ids"
                )
            offset = int(str((cursor_state or {}).get("offset", 0)))
            limit = min(int(str(adapter_config.get("limit", "100"))), max_documents)
            bounded_query = f"{query.rstrip()}\nLIMIT {limit}\nOFFSET {offset}"
            data = await _get_json(
                client,
                endpoint,
                params={"query": bounded_query, "format": "json"},
                source_name="Wikidata SPARQL",
            )
            bindings = data.get("results", {}).get("bindings", [])
            if not isinstance(bindings, list):
                raise SourceFetchError("Wikidata SPARQL response missing results.bindings")
            yielded = 0
            for row in bindings:
                if yielded >= max_documents:
                    break
                payload = _sparql_binding_values(row)
                item = payload.get("item") or payload.get("qid") or f"offset:{offset + yielded}"
                yielded += 1
                yield RawDocument(
                    content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
                    external_id=f"wikidata_sparql:{item}",
                    url=str(payload.get("item", "")) or None,
                    title=str(payload.get("itemLabel") or item),
                    published_at=None,
                    language="en",
                    content_type="application/json",
                    metadata={"adapter": self.adapter_name, "source": "wikidata_sparql"},
                )
            if cursor_sink is not None:
                cursor_sink["offset"] = offset + yielded
                cursor_sink["query_hash"] = str(abs(hash(query)))
        finally:
            if owns_client:
                await client.aclose()


class MediaWikiRevisionsAdapter:
    """Fetch timestamped MediaWiki page revisions as source documents."""

    adapter_name = "mediawiki_revisions_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        client, owns_client = _get_client(http_client)
        try:
            api_url = str(adapter_config.get("mediawiki_api_url", _DEFAULT_MEDIAWIKI_API))
            pages = _string_list(adapter_config.get("pages"))
            if not pages:
                raise SourceFetchError("MediaWiki revisions adapter requires pages")
            yielded = 0
            state = dict(cursor_state or {})
            rvcontinue_by_page = _string_map(state.get("rvcontinue_by_page", {}))
            for page in pages:
                if yielded >= max_documents:
                    break
                params: dict[str, str | int] = {
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "prop": "revisions",
                    "titles": page,
                    "rvprop": "ids|timestamp|user|comment|content",
                    "rvslots": "main",
                    "rvlimit": min(int(str(adapter_config.get("rvlimit", "50"))), 50),
                    "rvdir": str(adapter_config.get("rvdir", "newer")),
                }
                if adapter_config.get("start_date"):
                    params["rvstart"] = str(adapter_config["start_date"])
                if adapter_config.get("end_date"):
                    params["rvend"] = str(adapter_config["end_date"])
                if rvcontinue_by_page.get(page):
                    params["rvcontinue"] = str(rvcontinue_by_page[page])

                while yielded < max_documents:
                    data = await _get_json(
                        client,
                        api_url,
                        params=params,
                        source_name=f"MediaWiki revisions {page}",
                    )
                    page_rows = data.get("query", {}).get("pages", [])
                    revisions = _mediawiki_revisions(page_rows)
                    if not revisions:
                        break
                    for revision in revisions:
                        if yielded >= max_documents:
                            break
                        yielded += 1
                        yield _mediawiki_revision_to_doc(page, revision, self.adapter_name)
                    next_token = data.get("continue", {}).get("rvcontinue")
                    if not next_token:
                        rvcontinue_by_page.pop(page, None)
                        break
                    rvcontinue_by_page[page] = next_token
                    params["rvcontinue"] = str(next_token)
            if cursor_sink is not None:
                cursor_sink["rvcontinue_by_page"] = rvcontinue_by_page
        finally:
            if owns_client:
                await client.aclose()


def _get_client(http_client: object | None) -> tuple[Any, bool]:
    import httpx

    if http_client is not None and isinstance(http_client, httpx.AsyncClient):
        return http_client, False
    return create_guarded_client(headers={"User-Agent": _USER_AGENT}), True


async def _get_json(
    client: Any,
    url: str,
    *,
    source_name: str,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    text = await _get_text(client, url, source_name=source_name, params=params, headers=headers)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceFetchError(f"{source_name}: returned non-JSON response") from exc
    if not isinstance(data, dict):
        raise SourceFetchError(f"{source_name}: expected JSON object response")
    return data


async def _get_text(
    client: Any,
    url: str,
    *,
    source_name: str,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
) -> str:
    import httpx

    try:
        resolve_and_validate(url)
    except SsrfError as exc:
        raise SourceFetchError(
            f"{source_name}: configured URL blocked by SSRF policy: {exc}"
        ) from exc

    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException as exc:
        raise SourceFetchError(f"{source_name}: request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise SourceFetchError(f"{source_name}: network error: {exc}") from exc
    if response.status_code == 429:
        raise SourceRateLimitError(f"{source_name}: returned 429 Too Many Requests")
    if response.status_code >= 500:
        raise SourceFetchError(f"{source_name}: server error {response.status_code}")
    if response.status_code >= 400:
        raise SourceFetchError(
            f"{source_name}: client error {response.status_code}: {response.text[:200]}"
        )
    return response.text


def _optional_bearer_header(
    adapter_config: Mapping[str, object], config_key: str, default_env: str
) -> dict[str, str]:
    token_env = str(adapter_config.get(config_key, default_env))
    token = os.environ.get(token_env) or os.environ.get(default_env)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, Iterable):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()]


def _cursor_offsets(state: Mapping[str, object]) -> dict[str, int]:
    raw = state.get("offsets", {})
    if isinstance(raw, Mapping):
        return {str(key): int(value) for key, value in raw.items()}
    return {}


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(raw_value) for key, raw_value in value.items()}


def _parse_date_bound(value: object, *, end_of_day: bool = False) -> dt.datetime | None:
    if not value:
        return None
    value_text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value_text):
        date_value = dt.date.fromisoformat(value_text)
        time_value = dt.time.max if end_of_day else dt.time.min
        return dt.datetime.combine(date_value, time_value, tzinfo=dt.UTC)
    parsed = _parse_dt(value_text)
    if parsed is not None:
        return parsed
    try:
        date_value = dt.date.fromisoformat(value_text)
    except ValueError:
        return None
    time_value = dt.time.max if end_of_day else dt.time.min
    return dt.datetime.combine(date_value, time_value, tzinfo=dt.UTC)


def _parse_dt(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _format_dt(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _within_window(
    value: dt.datetime | None,
    start_date: dt.datetime | None,
    end_date: dt.datetime | None,
) -> bool:
    if value is None:
        return True
    if start_date is not None and value < start_date:
        return False
    return not (end_date is not None and value > end_date)


def _first_upload_time(files: object) -> dt.datetime | None:
    if not isinstance(files, list):
        return None
    dates: list[dt.datetime] = []
    for file_row in files:
        if isinstance(file_row, Mapping):
            uploaded_at = file_row.get("upload_time_iso_8601") or file_row.get("upload_time")
            parsed = _parse_dt(str(uploaded_at or ""))
            if parsed is not None:
                dates.append(parsed)
    return min(dates) if dates else None


def _today_date() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def _arxiv_query(
    *,
    categories: list[str],
    terms: list[str],
    start_date: str,
    end_date: str,
) -> str:
    clauses: list[str] = []
    if categories:
        clauses.append("(" + " OR ".join(f"cat:{category}" for category in categories) + ")")
    if terms:
        clauses.append("(" + " OR ".join(f'all:"{term}"' for term in terms) + ")")
    start = re.sub(r"[^0-9]", "", start_date)[:8] + "0000"
    end = re.sub(r"[^0-9]", "", end_date)[:8] + "2359"
    clauses.append(f"submittedDate:[{start} TO {end}]")
    return " AND ".join(clauses)


def _atom_entries(text: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceFetchError("Atom feed returned malformed XML") from exc
    return list(root.findall("{http://www.w3.org/2005/Atom}entry"))


def _elem_text(parent: ET.Element, tag: str) -> str:
    elem = parent.find(tag)
    return (elem.text or "").strip() if elem is not None else ""


def _arxiv_entry_to_doc(entry: ET.Element, adapter_name: str) -> RawDocument:
    ns = "{http://www.w3.org/2005/Atom}"
    arxiv_id = _elem_text(entry, f"{ns}id")
    title = " ".join(_elem_text(entry, f"{ns}title").split())
    summary = " ".join(_elem_text(entry, f"{ns}summary").split())
    published = _elem_text(entry, f"{ns}published")
    authors = [
        _elem_text(author, f"{ns}name")
        for author in entry.findall(f"{ns}author")
        if _elem_text(author, f"{ns}name")
    ]
    categories = [
        str(category.attrib.get("term", ""))
        for category in entry.findall(f"{ns}category")
        if category.attrib.get("term")
    ]
    payload = {
        "id": arxiv_id,
        "title": title,
        "summary": summary,
        "published": published,
        "updated": _elem_text(entry, f"{ns}updated"),
        "authors": authors,
        "categories": categories,
    }
    return RawDocument(
        content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
        external_id=arxiv_id or None,
        url=arxiv_id or None,
        title=title or None,
        published_at=published or None,
        language="en",
        content_type="application/json",
        metadata={"adapter": adapter_name, "source": "arxiv", "categories": "|".join(categories)},
    )


def _feed_items(text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceFetchError("Feed returned malformed XML") from exc
    items: list[dict[str, str]] = []
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            items.append(
                {
                    "id": _elem_text(item, "guid") or _elem_text(item, "link"),
                    "title": _elem_text(item, "title"),
                    "link": _elem_text(item, "link"),
                    "published_at": _elem_text(item, "pubDate"),
                    "summary": _elem_text(item, "description"),
                }
            )
        return items
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{ns}entry"):
        link_elem = entry.find(f"{ns}link")
        link = str(link_elem.attrib.get("href", "")) if link_elem is not None else ""
        items.append(
            {
                "id": _elem_text(entry, f"{ns}id") or link,
                "title": _elem_text(entry, f"{ns}title"),
                "link": link,
                "published_at": _elem_text(entry, f"{ns}published")
                or _elem_text(entry, f"{ns}updated"),
                "summary": _elem_text(entry, f"{ns}summary") or _elem_text(entry, f"{ns}content"),
            }
        )
    return items


def _wikidata_entity_query(entity_ids: list[str]) -> str:
    if not entity_ids:
        return ""
    values = " ".join(f"wd:{qid}" for qid in entity_ids if re.fullmatch(r"Q[0-9]+", qid))
    if not values:
        return ""
    return f"""
SELECT ?item ?itemLabel ?itemDescription ?inception ?officialWebsite WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P571 ?inception. }}
  OPTIONAL {{ ?item wdt:P856 ?officialWebsite. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
""".strip()


def _sparql_binding_values(row: object) -> dict[str, str]:
    if not isinstance(row, Mapping):
        return {}
    out: dict[str, str] = {}
    for key, value in row.items():
        if isinstance(value, Mapping):
            out[str(key)] = str(value.get("value", ""))
    if "item" in out and "/entity/" in out["item"]:
        out["qid"] = out["item"].rsplit("/", 1)[-1]
    return out


def _mediawiki_revisions(page_rows: object) -> list[Mapping[str, object]]:
    if not isinstance(page_rows, list):
        return []
    revisions: list[Mapping[str, object]] = []
    for page in page_rows:
        if isinstance(page, Mapping) and isinstance(page.get("revisions"), list):
            revisions.extend(
                revision for revision in page["revisions"] if isinstance(revision, Mapping)
            )
    return revisions


def _mediawiki_revision_to_doc(
    page: str, revision: Mapping[str, object], adapter_name: str
) -> RawDocument:
    rev_id = str(revision.get("revid") or "")
    timestamp = str(revision.get("timestamp") or "")
    slots = revision.get("slots", {})
    content = ""
    if isinstance(slots, Mapping):
        main = slots.get("main", {})
        if isinstance(main, Mapping):
            content = str(main.get("content") or main.get("*") or "")
    payload = {
        "page": page,
        "revision": {
            "revid": rev_id,
            "parentid": revision.get("parentid"),
            "timestamp": timestamp,
            "user": revision.get("user"),
            "comment": revision.get("comment"),
            "content": content,
        },
    }
    return RawDocument(
        content=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
        external_id=f"mediawiki:{page}:{rev_id}",
        url=(
            "https://en.wikipedia.org/w/index.php?"
            f"title={urllib.parse.quote(page.replace(' ', '_'))}&oldid={rev_id}"
        ),
        title=f"{page} revision {rev_id}",
        published_at=timestamp or None,
        language="en",
        content_type="application/json",
        metadata={"adapter": adapter_name, "page": page, "revision_id": rev_id},
    )
