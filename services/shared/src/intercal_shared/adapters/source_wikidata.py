"""Wikidata/Wikipedia recent-changes source adapter.

Fetches recent changes from the Wikidata MediaWiki API (``action=query``,
``list=recentchanges``) and optionally the corresponding Wikipedia article
summaries via the Wikipedia REST Summary API.

``adapter_name``: ``"wikidata_changes_v1"``

adapter_config keys (all optional):
    wikidata_api_url (str):
        Base URL for the Wikidata MediaWiki API.
        Default: ``"https://www.wikidata.org/w/api.php"``
    wikipedia_summary_url (str):
        Base URL for Wikipedia REST Summary API.
        Default: ``"https://en.wikipedia.org/api/rest_v1/page/summary"``
    namespaces (str):
        Pipe-separated MediaWiki namespace IDs to include.
        Default: ``"0"`` (main/item namespace only).
    rctype (str):
        Pipe-separated change types: ``"edit|new"``.
        Default: ``"edit|new"``
    fetch_wikipedia_summary (bool-string):
        ``"true"`` to also fetch the Wikipedia article summary for each change.
        Default: ``"false"`` (keeps traffic minimal; enable for richer text).

Rate limiting: Wikidata requests use a User-Agent header as required by the
Wikimedia API policy (https://meta.wikimedia.org/wiki/User-Agent_policy).
The adapter does not self-throttle — the caller (ingest_source) handles
rate-limit errors and back-off.

License: Wikidata content is CC0; redistribution_allowed = true.
Wikipedia article text is CC BY-SA 4.0; redistribution_allowed = true,
citation required.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from intercal_shared.ports.source import RawDocument, SourceFetchError, SourceRateLimitError
from intercal_shared.ssrf import SsrfError, create_guarded_client, resolve_and_validate

_log = logging.getLogger(__name__)

_DEFAULT_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_DEFAULT_WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"
_USER_AGENT = (
    "intercal/0.1 (https://github.com/studio-jami/intercal; jamie@yrka.io) python-httpx/0.2x"
)


class WikidataChangesAdapter:
    """SourcePort adapter: Wikidata recent-changes + optional Wikipedia summaries.

    Fetches the most-recent *max_documents* changed Wikidata items in one
    request window.  For each item a ``RawDocument`` is yielded containing
    the change record as JSON.  Optionally, a follow-up Wikipedia summary
    fetch enriches each document.

    The adapter is stateless; ``cursor_state`` is used to carry the
    ``rccontinue`` pagination token between runs so incremental fetches
    only retrieve new changes.
    """

    adapter_name: str = "wikidata_changes_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        """Yield raw documents from Wikidata recent changes."""
        import httpx

        client: httpx.AsyncClient | None = None
        owns_client = False

        try:
            if http_client is not None and isinstance(http_client, httpx.AsyncClient):
                # A borrowed client (e.g. a test MockTransport) is trusted as-is;
                # the SSRF guard still pre-validates the configured URLs below.
                client = http_client
            else:
                # Own client: IP-pinned + scheme-allowlisted + no auto-redirects
                # (the SSRF guard re-validates every connection it opens, closing
                # the DNS-rebinding window for operator/user-configured URLs).
                client = create_guarded_client(headers={"User-Agent": _USER_AGENT})
                owns_client = True

            api_url = str(adapter_config.get("wikidata_api_url", _DEFAULT_WIKIDATA_API))
            namespaces = str(adapter_config.get("namespaces", "0"))
            rctype = str(adapter_config.get("rctype", "edit|new"))
            fetch_wp = str(adapter_config.get("fetch_wikipedia_summary", "false")).lower() == "true"
            wp_summary_url = str(
                adapter_config.get("wikipedia_summary_url", _DEFAULT_WIKIPEDIA_SUMMARY)
            )

            # SSRF guard: validate the configured endpoints before any fetch so a
            # malicious adapter_config URL (pointing at localhost / 169.254.169.254
            # / an internal host) is rejected up front, not after a request fires.
            try:
                resolve_and_validate(api_url)
                if fetch_wp:
                    resolve_and_validate(wp_summary_url)
            except SsrfError as exc:
                raise SourceFetchError(
                    f"Wikidata adapter: configured URL blocked by SSRF policy: {exc}"
                ) from exc

            params: dict[str, str | int] = {
                "action": "query",
                "list": "recentchanges",
                "rcnamespace": namespaces,
                "rctype": rctype,
                "rcprop": "ids|title|timestamp|sizes|flags|loginfo|comment",
                "rclimit": min(max_documents, 500),  # MediaWiki max per page = 500
                "rcdir": "older",  # newest-first (MediaWiki default; explicit for clarity)
                "format": "json",
                "formatversion": "2",
            }

            # Incremental resume across runs.  recentchanges enumerates
            # newest-first; ``rccontinue`` only paginates *within* one query
            # (walking toward older changes), so replaying it next run would
            # re-crawl history.  For only-new changes we instead bound the
            # window with ``rcend`` set to the newest timestamp we saw last
            # run.  A small overlap plus the content_hash UNIQUE dedup absorbs
            # the "changes inserted slightly out of timestamp order" caveat
            # documented at API:RecentChanges.
            if cursor_state and cursor_state.get("last_timestamp"):
                params["rcend"] = str(cursor_state["last_timestamp"])

            newest_seen: str | None = None
            yielded = 0
            while yielded < max_documents:
                _log.debug("WikidataChanges: GET %s params=%s", api_url, params)
                try:
                    response = await client.get(api_url, params=params)
                except httpx.TimeoutException as exc:
                    raise SourceFetchError(f"Wikidata API request timed out: {exc}") from exc
                except httpx.RequestError as exc:
                    raise SourceFetchError(f"Wikidata API network error: {exc}") from exc

                if response.status_code == 429:
                    raise SourceRateLimitError("Wikidata API returned 429 Too Many Requests")
                if response.status_code >= 500:
                    raise SourceFetchError(
                        f"Wikidata API server error {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise SourceFetchError(
                        f"Wikidata API client error {response.status_code}: {response.text[:200]}"
                    )

                try:
                    data: dict[str, Any] = response.json()
                except Exception as exc:
                    raise SourceFetchError(
                        f"Wikidata API returned non-JSON response: {response.text[:200]}"
                    ) from exc

                changes: list[dict[str, Any]] = data.get("query", {}).get("recentchanges", [])
                if not changes:
                    _log.debug("WikidataChanges: no more changes in window")
                    break

                for change in changes:
                    if yielded >= max_documents:
                        break

                    doc_payload: dict[str, Any] = {"change": change}

                    # Optionally enrich with Wikipedia article summary.
                    if fetch_wp and change.get("title"):
                        title = change["title"].replace(" ", "_")
                        try:
                            wp_resp = await client.get(f"{wp_summary_url.rstrip('/')}/{title}")
                            if wp_resp.status_code == 200:
                                doc_payload["wikipedia_summary"] = wp_resp.json()
                        except Exception as wp_exc:
                            _log.debug(
                                "WikidataChanges: Wikipedia summary fetch failed for %r: %s",
                                title,
                                wp_exc,
                            )

                    content_bytes = json.dumps(doc_payload, ensure_ascii=False).encode()
                    external_id = str(change.get("revid") or change.get("rcid") or "")
                    title_str: str = change.get("title", "")
                    timestamp: str = change.get("timestamp", "")
                    # Newest-first stream: the first timestamp we see is the
                    # newest; remember it for next run's incremental boundary.
                    if timestamp and newest_seen is None:
                        newest_seen = timestamp

                    yield RawDocument(
                        content=content_bytes,
                        external_id=external_id or None,
                        url=(f"https://www.wikidata.org/wiki/{title_str}" if title_str else None),
                        title=title_str or None,
                        published_at=timestamp or None,
                        language="en",
                        content_type="application/json",
                        metadata={
                            "adapter": self.adapter_name,
                            "rcid": str(change.get("rcid", "")),
                            "revid": str(change.get("revid", "")),
                            "ns": str(change.get("ns", "")),
                            "type": str(change.get("type", "")),
                        },
                    )
                    yielded += 1

                # Intra-run pagination only: rccontinue walks toward older
                # changes within this single newest-first query.  It is NOT
                # persisted across runs (see the rcend note above).
                continue_token = data.get("continue", {}).get("rccontinue")
                if not continue_token or yielded >= max_documents:
                    break
                params["rccontinue"] = continue_token

            # Record the newest timestamp seen so the next run only fetches
            # changes newer than this (via rcend).  Leave the cursor untouched
            # if this run saw nothing, so we don't lose the prior boundary.
            if cursor_sink is not None and newest_seen is not None:
                cursor_sink["last_timestamp"] = newest_seen

        finally:
            if owns_client and client is not None:
                await client.aclose()
