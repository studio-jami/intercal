"""Intercal ingest service CLI.

Entry point: ``python -m intercal_ingest <command> [options]``

These are the portable worker entrypoints invoked by:
- Local development: ``python -m intercal_ingest ingest-source --source-id <id>``
- GitHub Actions scheduled workflow: same command in a `run:` step.
- Modal: same command via ``modal run``.
- VPS cron: same command in a crontab or systemd timer.

No scheduler SDK is required — the external scheduler calls the CLI directly.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import typer
from intercal_shared.config import Settings

app = typer.Typer(
    name="intercal-ingest",
    help="Intercal ingestion service worker.",
    add_completion=False,
)


def _setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _get_settings() -> Settings:
    return Settings()


@app.command("ingest-source")
def ingest_source_cmd(
    source_id: str = typer.Option(..., "--source-id", help="UUID of the source to ingest."),
    max_documents: int = typer.Option(
        0,
        "--max-documents",
        help=(
            "Hard cap on documents per run.  0 = use INGEST_MAX_DOCS_PER_RUN from settings "
            "(default 200)."
        ),
    ),
) -> None:
    """Fetch and persist raw documents for a configured source.

    Idempotent — safe to re-run; already-ingested content hashes are skipped.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)
    effective_max = max_documents if max_documents > 0 else cfg.ingest_max_docs_per_run

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_storage

        from intercal_ingest.jobs import ingest_source

        pool = await get_pool(cfg.database_url)
        storage = make_storage(cfg)
        counters = await ingest_source(
            source_id=source_id,
            pool=pool,
            storage=storage,
            max_documents=effective_max,
        )
        import sys
        print(
            f"Done: fetched={counters['fetched']} new={counters['new']} "
            f"skipped={counters['skipped']} errors={counters['errors']}",
            file=sys.stderr,
        )

    asyncio.run(_run())


@app.command("normalize-document")
def normalize_document_cmd(
    document_id: str = typer.Option(
        ..., "--document-id", help="UUID of the document to normalise."
    ),
) -> None:
    """Normalise a raw source document into clean text and chunks.

    Idempotent — already-normalised documents are skipped.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_storage

        from intercal_ingest.jobs import normalize_document

        pool = await get_pool(cfg.database_url)
        storage = make_storage(cfg)
        await normalize_document(document_id=document_id, pool=pool, storage=storage)

    asyncio.run(_run())


@app.command("score-source-health")
def score_source_health_cmd(
    source_id: str = typer.Option(..., "--source-id", help="UUID of the source to score."),
    lookback_days: int = typer.Option(7, "--lookback-days", help="Days of history to consider."),
) -> None:
    """Recompute the health score for a source from recent run history.

    Idempotent — always overwrites the current health score.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool

        from intercal_ingest.jobs import score_source_health

        pool = await get_pool(cfg.database_url)
        await score_source_health(source_id=source_id, pool=pool, lookback_days=lookback_days)

    asyncio.run(_run())


@app.command("cleanup-expired-cache")
def cleanup_expired_cache_cmd(
    max_age_days: int = typer.Option(30, "--max-age-days", help="Fallback TTL for cache entries."),
) -> None:
    """Delete expired digest cache entries and their associated storage objects.

    Idempotent — already-deleted entries are ignored.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_storage

        from intercal_ingest.jobs import cleanup_expired_cache

        pool = await get_pool(cfg.database_url)
        storage = make_storage(cfg)
        await cleanup_expired_cache(pool=pool, storage=storage, max_age_days=max_age_days)

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
