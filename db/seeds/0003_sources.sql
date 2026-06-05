-- 0003_sources.sql
-- Seed starter sources: Wikidata recent changes and GitHub releases.
-- These are the initial real sources for Phase B ingestion (Plan 02 W1).
-- Operators add more sources by INSERT or via the admin surface (Plan 04).
--
-- License notes:
--   Wikidata: CC0 — redistribution_allowed = true, citation_only = false.
--   GitHub releases: varies by project.  redistribution_allowed = false by
--     default; set to true per-source after verifying the project license.

INSERT INTO sources (
    slug,
    name,
    description,
    source_type,
    adapter_name,
    adapter_config,
    run_cadence_seconds,
    license_spdx,
    redistribution_allowed,
    summary_allowed,
    citation_only,
    license_notes,
    rate_limit_requests_per_minute,
    is_active,
    is_paused
) VALUES
(
    'wikidata-recent-changes',
    'Wikidata Recent Changes',
    'Wikidata item edits and new items via the MediaWiki recentchanges API. '
    'CC0 — freely redistributable.',
    'api',
    'wikidata_changes_v1',
    '{
        "wikidata_api_url": "https://www.wikidata.org/w/api.php",
        "wikipedia_summary_url": "https://en.wikipedia.org/api/rest_v1/page/summary",
        "namespaces": "0",
        "rctype": "edit|new",
        "fetch_wikipedia_summary": "false"
    }'::jsonb,
    21600,           -- run every 6 hours (matches INGEST_CRON default)
    'CC0-1.0',
    true,            -- Wikidata is CC0
    true,
    false,
    'Wikidata structured data is CC0. Wikipedia article text is CC BY-SA 4.0.',
    60,              -- Wikimedia rate-limit guideline: reasonable automated use
    true,
    false
),
(
    'github-releases-featured',
    'GitHub Releases — Featured Projects',
    'Release notes for selected open-source projects on GitHub. '
    'License varies per project; redistribution_allowed defaults to false.',
    'registry',
    'github_releases_v1',
    '{
        "repos": [
            "python/cpython",
            "nodejs/node",
            "rust-lang/rust",
            "golang/go",
            "kubernetes/kubernetes",
            "torvalds/linux",
            "microsoft/typescript",
            "django/django",
            "fastapi/fastapi",
            "pydantic/pydantic"
        ],
        "include_prereleases": "false",
        "per_page": "30"
    }'::jsonb,
    86400,           -- run once per day
    null,            -- varies per repo
    false,           -- release notes license varies; default false
    true,            -- summaries / citations of release notes are generally fine
    false,
    'License varies per repository. redistribution_allowed must be set per-source after verifying. '
    'Summary and citation use is generally permitted under fair use / CC norms.',
    30,
    true,
    false
)
ON CONFLICT (slug) DO NOTHING;
