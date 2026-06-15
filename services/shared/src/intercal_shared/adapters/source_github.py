"""GitHub releases source adapter.

Fetches releases from one or more GitHub repositories using the GitHub REST
API (``GET /repos/{owner}/{repo}/releases``).

``adapter_name``: ``"github_releases_v1"``

adapter_config keys:
    repos (list[str], required):
        List of ``"owner/repo"`` strings to fetch releases from.
        Example: ``["torvalds/linux", "python/cpython"]``
    github_api_url (str, optional):
        Base URL for the GitHub REST API.
        Default: ``"https://api.github.com"``
    include_prereleases (bool-string, optional):
        ``"true"`` to include pre-releases.  Default: ``"false"``.
    per_page (int-string, optional):
        Releases per page (1-100).  Default: ``"30"``.
    start_date / end_date (ISO date/datetime, optional):
        Historical window bounds.  When either is present the adapter persists
        a per-repo ``page_by_repo`` cursor in ``cursor_sink`` so long backfills
        can resume GitHub pagination without skipping already-crawled pages.
    max_pages_per_repo (int-string, optional):
        Historical request cap per repo per run. Default: ``"10"``.

Authentication: pass ``GITHUB_TOKEN`` in the environment for higher rate
limits (5,000/hr authenticated vs 60/hr unauthenticated).  The adapter reads
the token from ``adapter_config["github_token_env"]`` (env var name) or falls
back to the ``GITHUB_TOKEN`` environment variable.  If neither is set the
adapter runs unauthenticated; this is fine for low-cadence public repo
ingestion within the free 60 req/hr limit.

License: GitHub release notes are typically the project's own license.
``redistribution_allowed`` is left at ``false`` in the source row by default;
operators should set it per-source after checking the project's license.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from intercal_shared.ports.source import RawDocument, SourceFetchError, SourceRateLimitError
from intercal_shared.ssrf import SsrfError, create_guarded_client, resolve_and_validate

_log = logging.getLogger(__name__)

_DEFAULT_GITHUB_API = "https://api.github.com"
_USER_AGENT = (
    "intercal/0.1 (https://github.com/studio-jami/intercal; jamie@yrka.io) python-httpx/0.2x"
)


class GitHubReleasesAdapter:
    """SourcePort adapter: GitHub releases for a list of repositories.

    Yields one ``RawDocument`` per release, containing the full GitHub API
    release JSON object.  Releases are fetched newest-first (GitHub default).

    The adapter respects ``max_documents`` across all configured repos by
    distributing the budget evenly (floor division, remainder to first repos).
    """

    adapter_name: str = "github_releases_v1"

    async def fetch(
        self,
        *,
        adapter_config: dict[str, object],
        cursor_state: dict[str, object] | None = None,
        max_documents: int = 200,
        http_client: object | None = None,
        cursor_sink: dict[str, object] | None = None,
    ) -> AsyncIterator[RawDocument]:
        """Yield release documents from GitHub repositories.

        Incremental runs fetch newest-first every run; idempotency is enforced
        downstream by the ``content_hash`` dedup.  Historical date-window runs
        additionally persist a per-repo page cursor so a bounded backfill can
        resume across runs without re-walking earlier pages.
        """
        import httpx

        client: httpx.AsyncClient | None = None
        owns_client = False

        try:
            # Resolve GitHub token (optional for public repos).
            token_env_key = str(adapter_config.get("github_token_env", "GITHUB_TOKEN"))
            github_token = os.environ.get(token_env_key) or os.environ.get("GITHUB_TOKEN")

            headers: dict[str, str] = {
                "User-Agent": _USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"
                _log.debug("GitHubReleases: using authenticated requests")
            else:
                _log.debug("GitHubReleases: using unauthenticated requests (60 req/hr limit)")

            if http_client is not None and isinstance(http_client, httpx.AsyncClient):
                # Borrowed client: do NOT mutate its headers (that would leak
                # our auth/version headers into other adapters sharing it).
                # GitHub headers are passed per-request instead.  A borrowed
                # client (e.g. a test MockTransport) is trusted as-is; the SSRF
                # guard still pre-validates the configured base URL below.
                client = http_client
                owns_client = False
            else:
                # Own client: IP-pinned + scheme-allowlisted + no auto-redirects
                # via the SSRF guard, so an operator/user-configured github_api_url
                # cannot point the fetcher at an internal/metadata address.
                client = create_guarded_client(headers=headers)
                owns_client = True

            api_url = str(adapter_config.get("github_api_url", _DEFAULT_GITHUB_API)).rstrip("/")

            # SSRF guard: validate the configured API base URL before any fetch.
            try:
                resolve_and_validate(api_url)
            except SsrfError as exc:
                raise SourceFetchError(
                    f"GitHub adapter: configured github_api_url blocked by SSRF policy: {exc}"
                ) from exc
            include_pre = str(adapter_config.get("include_prereleases", "false")).lower() == "true"
            per_page = min(int(str(adapter_config.get("per_page", "30"))), 100)
            start_date = _parse_config_date_bound(adapter_config, "start_date")
            end_date = _parse_config_date_bound(adapter_config, "end_date", end_of_day=True)
            historical_mode = start_date is not None or end_date is not None
            cursor_page_by_repo = _cursor_page_by_repo(cursor_state or {})
            max_pages_per_repo = max(int(str(adapter_config.get("max_pages_per_repo", "10"))), 1)

            repos_raw = adapter_config.get("repos", [])
            if not isinstance(repos_raw, list):
                raise SourceFetchError(
                    "adapter_config['repos'] must be a list of 'owner/repo' strings"
                )
            repos: list[str] = [_validate_repo_name(str(r)) for r in repos_raw]
            if not repos:
                _log.warning("GitHubReleases: no repos configured; yielding nothing")
                return

            # Distribute document budget across repos.
            n_repos = len(repos)
            base_budget = max_documents // n_repos
            remainder = max_documents % n_repos

            yielded_total = 0

            for repo_idx, repo in enumerate(repos):
                if yielded_total >= max_documents:
                    break
                repo_budget = base_budget + (1 if repo_idx < remainder else 0)
                if repo_budget <= 0:
                    continue

                page = int(cursor_page_by_repo.get(repo, 1)) if historical_mode else 1

                yielded_for_repo = 0
                repo_done = False
                pages_fetched = 0

                while yielded_for_repo < repo_budget and pages_fetched < max_pages_per_repo:
                    url = f"{api_url}/repos/{repo}/releases"
                    params: dict[str, str | int] = {
                        "per_page": min(per_page, repo_budget - yielded_for_repo),
                        "page": page,
                    }
                    _log.debug("GitHubReleases: GET %s page=%d", url, page)
                    try:
                        response = await client.get(url, params=params, headers=headers)
                    except httpx.TimeoutException as exc:
                        raise SourceFetchError(
                            f"GitHub API request timed out for {repo}: {exc}"
                        ) from exc
                    except httpx.RequestError as exc:
                        raise SourceFetchError(
                            f"GitHub API network error for {repo}: {exc}"
                        ) from exc

                    # GitHub signals rate limiting with 403 or 429 (per the REST
                    # rate-limit docs).  Detect via the documented header signals
                    # first (x-ratelimit-remaining == 0 or a retry-after), then
                    # fall back to the body marker for older error shapes.
                    if response.status_code in (403, 429):
                        remaining = response.headers.get("x-ratelimit-remaining")
                        retry_after = response.headers.get("retry-after")
                        if (
                            response.status_code == 429
                            or remaining == "0"
                            or retry_after is not None
                            or "rate limit" in response.text.lower()
                        ):
                            raise SourceRateLimitError(
                                f"GitHub API rate limit hit for {repo}: "
                                f"status={response.status_code} "
                                f"x-ratelimit-remaining={remaining} "
                                f"x-ratelimit-reset="
                                f"{response.headers.get('x-ratelimit-reset')} "
                                f"retry-after={retry_after}"
                            )
                    if response.status_code == 404:
                        _log.warning("GitHubReleases: repo %r not found (404); skipping", repo)
                        break
                    if response.status_code >= 500:
                        raise SourceFetchError(
                            f"GitHub API server error {response.status_code} for {repo}"
                        )
                    if response.status_code >= 400:
                        raise SourceFetchError(
                            f"GitHub API client error {response.status_code} for {repo}: "
                            f"{response.text[:200]}"
                        )
                    pages_fetched += 1

                    try:
                        releases: list[dict[str, Any]] = response.json()
                    except Exception as exc:
                        raise SourceFetchError(
                            f"GitHub API returned non-JSON response for {repo}: "
                            f"{response.text[:200]}"
                        ) from exc

                    if not releases:
                        repo_done = True
                        break  # No more releases for this repo.

                    for release in releases:
                        if yielded_for_repo >= repo_budget or yielded_total >= max_documents:
                            break

                        # Skip pre-releases unless opted in.
                        if not include_pre and release.get("prerelease", False):
                            continue
                        # Skip drafts — they are not published.
                        if release.get("draft", False):
                            continue
                        published_dt = _parse_datetime(str(release.get("published_at", "") or ""))
                        if historical_mode and published_dt is None:
                            continue
                        if (
                            end_date is not None
                            and published_dt is not None
                            and published_dt > end_date
                        ):
                            continue
                        if (
                            start_date is not None
                            and published_dt is not None
                            and published_dt < start_date
                        ):
                            repo_done = True
                            continue

                        content_bytes = json.dumps(release, ensure_ascii=False).encode()
                        release_id = str(release.get("id", ""))
                        tag = str(release.get("tag_name", ""))
                        html_url = str(release.get("html_url", ""))
                        name = str(release.get("name", "") or tag)
                        published_at = str(release.get("published_at", "") or "")

                        yield RawDocument(
                            content=content_bytes,
                            external_id=release_id or None,
                            url=html_url or None,
                            title=f"{repo} {name}" if name else None,
                            published_at=published_at or None,
                            language="en",
                            content_type="application/json",
                            metadata={
                                "adapter": self.adapter_name,
                                "repo": repo,
                                "tag": tag,
                                "release_id": release_id,
                                "prerelease": str(release.get("prerelease", False)),
                            },
                        )
                        yielded_for_repo += 1
                        yielded_total += 1

                    page += 1
                    # Stop paging if GitHub signals no more pages via Link header.
                    link_header = response.headers.get("Link", "")
                    if repo_done or 'rel="next"' not in link_header:
                        break
                if historical_mode:
                    if repo_done:
                        cursor_page_by_repo.pop(repo, None)
                    else:
                        cursor_page_by_repo[repo] = page

            if historical_mode and cursor_sink is not None:
                cursor_sink["page_by_repo"] = cursor_page_by_repo

        finally:
            if owns_client and client is not None:
                await client.aclose()


def _cursor_page_by_repo(cursor_state: dict[str, object]) -> dict[str, int]:
    raw = cursor_state.get("page_by_repo", {})
    if not isinstance(raw, dict):
        return {}
    return {str(repo): int(page) for repo, page in raw.items()}


def _validate_repo_name(repo: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise SourceFetchError(
            "adapter_config['repos'] entries must be GitHub 'owner/repo' identifiers"
        )
    return repo


def _parse_date_bound(value: object, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value_text = str(value)
    if len(value_text) == 10 and value_text[4] == "-" and value_text[7] == "-":
        try:
            date_value = datetime.fromisoformat(value_text).date()
        except ValueError:
            return None
        time_value = datetime.max.time() if end_of_day else datetime.min.time()
        return datetime.combine(date_value, time_value, tzinfo=UTC)
    parsed = _parse_datetime(value_text)
    if parsed is not None:
        return parsed
    try:
        date_value = datetime.fromisoformat(value_text).date()
    except ValueError:
        return None
    time_value = datetime.max.time() if end_of_day else datetime.min.time()
    return datetime.combine(date_value, time_value, tzinfo=UTC)


def _parse_config_date_bound(
    adapter_config: dict[str, object],
    key: str,
    *,
    end_of_day: bool = False,
) -> datetime | None:
    raw = adapter_config.get(key)
    if not raw:
        return None
    parsed = _parse_date_bound(raw, end_of_day=end_of_day)
    if parsed is None:
        raise SourceFetchError(f"Invalid {key} date bound: {raw!r}")
    return parsed


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
