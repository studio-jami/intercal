"""OpenAlex scholarly-works source adapter.

Fetches scholarly works from the OpenAlex REST API
(``GET https://api.openalex.org/works``) with a date-bounded ``filter`` and
**cursor pagination** (``cursor=*`` → ``meta.next_cursor``), emitting one
``RawDocument`` per work.

``adapter_name``: ``"openalex_v1"``

OpenAlex is **CC0** (public domain): ~250M+ scholarly works (the corpus the
research/benchmark clusters are built on), each dated and graph-structured
(works/authors/institutions/topics + citation graph). Because the data is CC0
the seeded source row carries ``redistribution_allowed=true`` — OpenAlex is part
of the Tier S "fact-redistributable" spine (see ``docs/operations/source-policy.md``).

adapter_config keys (all optional unless noted):
    openalex_api_url (str):
        Base URL for the OpenAlex works endpoint.
        Default: ``"https://api.openalex.org/works"``
    mailto (str):
        Contact email for the OpenAlex **polite pool** (faster, more reliable
        rate limits). Sent as the ``mailto`` query param on every request, per
        the OpenAlex docs (https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication).
        When omitted the adapter still works against the common pool.
    date_field (str):
        Which date the window filters on — ``"publication"`` (default,
        ``from_publication_date`` / ``to_publication_date``) or ``"created"``
        (``from_created_date`` / ``to_created_date``). ``created`` is the
        resumable-by-ingestion-date axis OpenAlex recommends for incremental
        harvesting.
    start_date / end_date (ISO date ``YYYY-MM-DD``):
        Window bounds applied to the chosen ``date_field``. ``start_date``
        defaults to ``"2022-11-01"`` (corpus epoch); ``end_date`` defaults to
        today (UTC).
    concepts / topics / search (str or list[str]):
        Optional corpus narrowing. ``concepts`` → ``concepts.id`` filter,
        ``topics`` → ``primary_topic.id`` filter (OR-joined via the OpenAlex
        ``key:a|b`` syntax); ``search`` → the ``search`` query param.
    extra_filters (str):
        Raw additional ``filter`` clauses appended verbatim (comma-joined),
        for filters the structured keys above do not cover.
    per_page (int-string):
        Results per request (1-200). Default ``"200"`` (the OpenAlex max).

Cursor pagination & resumability: OpenAlex cursor paging starts at ``cursor=*``
and each page returns ``meta.next_cursor``; a ``null`` next_cursor means the
final page. The adapter persists the live ``next_cursor`` into ``cursor_sink``
each run so a long backfill resumes exactly where it stopped — but only while
the *effective query* (endpoint + filter + search) is unchanged. The cursor is
scoped to a query hash; if the query changes the cursor resets to ``*`` rather
than replaying a token that belongs to a different result set.

Rate limiting: OpenAlex returns HTTP 429 when the (common or polite) pool limit
is exceeded. The adapter raises ``SourceRateLimitError`` so the caller
(``ingest_source``) records the run and backs off; it does not self-throttle.

License: OpenAlex is CC0 (https://docs.openalex.org/additional-help/faq).
``redistribution_allowed = true`` in the seeded source row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

from intercal_shared.ports.source import RawDocument, SourceFetchError, SourceRateLimitError
from intercal_shared.ssrf import SsrfError, create_guarded_client, resolve_and_validate

_log = logging.getLogger(__name__)

_DEFAULT_OPENALEX_API = "https://api.openalex.org/works"
_DEFAULT_START_DATE = "2022-11-01"
_USER_AGENT = (
    "intercal/0.1 (https://github.com/studio-jami/intercal; jamie@yrka.io) python-httpx/0.2x"
)


class OpenAlexWorksAdapter:
    """SourcePort adapter: OpenAlex scholarly works (CC0), cursor-paginated.

    Yields one ``RawDocument`` per OpenAlex work, containing the verbatim work
    JSON. Works are fetched in a single date-bounded query and paged via the
    OpenAlex cursor (``cursor=*`` → ``meta.next_cursor``) until ``max_documents``
    is reached or the result set is exhausted.

    The adapter is stateless; ``cursor_state`` carries the OpenAlex
    ``next_cursor`` token (scoped to a query hash) so incremental backfills
    resume without re-walking earlier pages.
    """

    adapter_name: str = "openalex_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        """Yield raw documents from OpenAlex works."""
        import httpx

        client: httpx.AsyncClient | None = None
        owns_client = False

        try:
            if http_client is not None and isinstance(http_client, httpx.AsyncClient):
                # A borrowed client (e.g. a test MockTransport) is trusted as-is;
                # the SSRF guard still pre-validates the configured URL below.
                client = http_client
            else:
                # Own client: IP-pinned + scheme-allowlisted + no auto-redirects
                # via the SSRF guard, closing the DNS-rebinding window for an
                # operator/user-configured openalex_api_url.
                client = create_guarded_client(headers={"User-Agent": _USER_AGENT})
                owns_client = True

            api_url = str(adapter_config.get("openalex_api_url", _DEFAULT_OPENALEX_API))

            # SSRF guard: validate the configured endpoint before any fetch so a
            # malicious adapter_config URL (localhost / 169.254.169.254 / internal
            # host) is rejected up front, not after a request fires.
            try:
                resolve_and_validate(api_url)
            except SsrfError as exc:
                raise SourceFetchError(
                    f"OpenAlex adapter: configured URL blocked by SSRF policy: {exc}"
                ) from exc

            filter_value = _build_filter(adapter_config)
            search_term = str(adapter_config.get("search", "") or "").strip()
            mailto = str(adapter_config.get("mailto", "") or "").strip()
            per_page = min(max(int(str(adapter_config.get("per_page", "200"))), 1), 200)

            base_params: dict[str, str | int] = {"filter": filter_value, "per-page": per_page}
            if search_term:
                base_params["search"] = search_term
            if mailto:
                base_params["mailto"] = mailto

            # The cursor is only valid for the exact query that produced it.
            # Hash the effective query so a config change starts a fresh scan
            # instead of replaying a token from a different result set.
            query_hash = hashlib.sha256(
                json.dumps(
                    {"url": api_url, "filter": filter_value, "search": search_term},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            state = cursor_state or {}
            stored_cursor = str(state.get("next_cursor", "") or "")
            stored_hash = str(state.get("query_hash", "") or "")
            cursor = stored_cursor if (stored_cursor and stored_hash == query_hash) else "*"

            yielded = 0
            last_cursor: str | None = None
            while yielded < max_documents:
                params = dict(base_params)
                params["per-page"] = min(per_page, max_documents - yielded)
                params["cursor"] = cursor
                _log.debug("OpenAlex: GET %s cursor=%s", api_url, cursor)
                try:
                    response = await client.get(api_url, params=params)
                except httpx.TimeoutException as exc:
                    raise SourceFetchError(f"OpenAlex API request timed out: {exc}") from exc
                except httpx.RequestError as exc:
                    raise SourceFetchError(f"OpenAlex API network error: {exc}") from exc

                if response.status_code == 429:
                    raise SourceRateLimitError("OpenAlex API returned 429 Too Many Requests")
                if response.status_code >= 500:
                    raise SourceFetchError(
                        f"OpenAlex API server error {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise SourceFetchError(
                        f"OpenAlex API client error {response.status_code}: {response.text[:200]}"
                    )

                try:
                    data: dict[str, Any] = response.json()
                except Exception as exc:
                    raise SourceFetchError(
                        f"OpenAlex API returned non-JSON response: {response.text[:200]}"
                    ) from exc

                results = data.get("results", [])
                if not isinstance(results, list):
                    raise SourceFetchError("OpenAlex API response missing results list")

                for work in results:
                    if yielded >= max_documents:
                        break
                    if not isinstance(work, Mapping):
                        continue
                    doc = _work_to_doc(work, self.adapter_name)
                    if doc is None:
                        continue
                    yielded += 1
                    yield doc

                # Advance the OpenAlex cursor. ``meta.next_cursor`` is null on the
                # final page; an empty results page also terminates the scan.
                meta = data.get("meta", {})
                next_cursor = meta.get("next_cursor") if isinstance(meta, Mapping) else None
                last_cursor = str(next_cursor) if next_cursor else None
                if not next_cursor or not results:
                    break
                cursor = str(next_cursor)

            if cursor_sink is not None:
                # Persist where the next run should resume. ``None`` next_cursor
                # (scan complete) is recorded as an empty token so the next run
                # restarts the (now-extended) window from ``*``.
                cursor_sink["next_cursor"] = last_cursor or ""
                cursor_sink["query_hash"] = query_hash
        finally:
            if owns_client and client is not None:
                await client.aclose()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, Iterable):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()]


def _validate_date(value: str, *, key: str) -> str:
    text = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise SourceFetchError(
            f"OpenAlex adapter: {key} must be an ISO date (YYYY-MM-DD): {value!r}"
        )
    try:
        dt.date.fromisoformat(text)
    except ValueError as exc:
        raise SourceFetchError(f"OpenAlex adapter: invalid {key} date {value!r}") from exc
    return text


def _build_filter(adapter_config: Mapping[str, object]) -> str:
    """Build the OpenAlex ``filter`` string from adapter_config.

    Maps the date window onto the configured ``date_field`` (publication or
    created) and appends optional concept/topic narrowing and raw extra
    clauses. OR within a single filter key uses the OpenAlex ``a|b`` syntax.
    """
    date_field = str(adapter_config.get("date_field", "publication")).strip().lower()
    if date_field not in ("publication", "created"):
        raise SourceFetchError(
            f"OpenAlex adapter: date_field must be 'publication' or 'created', got {date_field!r}"
        )

    start_raw = adapter_config.get("start_date", _DEFAULT_START_DATE)
    end_raw = adapter_config.get("end_date") or dt.datetime.now(dt.UTC).date().isoformat()
    start_date = _validate_date(str(start_raw), key="start_date")
    end_date = _validate_date(str(end_raw), key="end_date")

    clauses = [
        f"from_{date_field}_date:{start_date}",
        f"to_{date_field}_date:{end_date}",
    ]

    concepts = _string_list(adapter_config.get("concepts"))
    if concepts:
        clauses.append("concepts.id:" + "|".join(concepts))
    topics = _string_list(adapter_config.get("topics"))
    if topics:
        clauses.append("primary_topic.id:" + "|".join(topics))

    extra = str(adapter_config.get("extra_filters", "") or "").strip()
    if extra:
        clauses.append(extra)

    return ",".join(clauses)


def _work_to_doc(work: Mapping[str, object], adapter_name: str) -> RawDocument | None:
    """Convert one OpenAlex work object into a RawDocument.

    Emits the verbatim work JSON as content; surfaces the OpenAlex id, title,
    and publication date as the document's external_id / title / published_at.
    """
    openalex_id = str(work.get("id", "") or "")
    if not openalex_id:
        return None
    title = work.get("display_name") or work.get("title")
    title_str = str(title) if title else None
    doi = work.get("doi")
    published = str(work.get("publication_date") or "") or None
    primary_topic = work.get("primary_topic")
    topic_id = ""
    if isinstance(primary_topic, Mapping):
        topic_id = str(primary_topic.get("id", "") or "")

    return RawDocument(
        content=json.dumps(work, ensure_ascii=False, sort_keys=True).encode(),
        external_id=openalex_id,
        url=(str(doi) if doi else openalex_id),
        title=title_str,
        published_at=published,
        language="en",
        content_type="application/json",
        metadata={
            "adapter": adapter_name,
            "source": "openalex",
            "openalex_id": openalex_id.rsplit("/", 1)[-1],
            "primary_topic_id": topic_id.rsplit("/", 1)[-1] if topic_id else "",
        },
    )
