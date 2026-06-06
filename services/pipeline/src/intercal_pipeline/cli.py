"""Intercal pipeline orchestrator CLI.

Entry point: ``python -m intercal_pipeline <command>``
Script entry point: ``intercal-pipeline <command>``

These are the portable orchestrator entrypoints invoked by:
- Local development: ``intercal-pipeline run --source-id <uuid>``
- GitHub Actions scheduled workflow: same command in a ``run:`` step.
- Cloud Run Jobs: same command as the container CMD.

No scheduler SDK is required — the external scheduler calls the CLI directly.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import sys
import uuid
from typing import Annotated, Any

import typer
from intercal_shared.config import Settings

app = typer.Typer(
    name="intercal-pipeline",
    help=(
        "Intercal pipeline orchestrator (Plan 02 W8).\n\n"
        "Chains: ingest → normalize → extract → embed → resolve → link → derive → version.\n"
        "Each stage is idempotent; re-running the full pipeline is always safe."
    ),
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


def _validate_date_bound(value: str | None, *, name: str) -> str | None:
    if not value:
        return None
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{name} must be YYYY-MM-DD, got {value!r}") from exc
    return value


def build_backfill_overrides(
    start_date: str | None, end_date: str | None
) -> dict[str, object]:
    start = _validate_date_bound(start_date, name="start-date")
    end = _validate_date_bound(end_date, name="end-date")
    if start and end and dt.date.fromisoformat(end) < dt.date.fromisoformat(start):
        raise typer.BadParameter("end-date must be on or after start-date")
    overrides: dict[str, object] = {}
    if start:
        overrides["start_date"] = start
    if end:
        overrides["end_date"] = end
    return overrides


async def select_sources(
    *,
    pool: Any,
    source_ids: list[str] | None = None,
    source_slugs: list[str] | None = None,
    source_class: str | None = None,
    adapter_name: str | None = None,
    max_sources: int = 0,
) -> list[dict[str, object]]:
    """Select active source rows for scheduled or backfill execution."""
    for source_id in source_ids or []:
        try:
            uuid.UUID(source_id)
        except ValueError as exc:
            raise typer.BadParameter(f"source-id must be a UUID, got {source_id!r}") from exc

    rows = await pool.fetch(
        """
        SELECT id, slug, adapter_name, metadata
        FROM sources
        WHERE is_active = true
          AND is_paused = false
          AND ($1::uuid[] IS NULL OR id = ANY($1::uuid[]))
          AND ($2::text[] IS NULL OR slug = ANY($2::text[]))
          AND ($3::text IS NULL OR metadata->>'source_class' = $3)
          AND ($4::text IS NULL OR adapter_name = $4)
        ORDER BY slug
        LIMIT CASE WHEN $5::integer > 0 THEN $5::integer ELSE 2147483647 END
        """,
        [uuid.UUID(value) for value in source_ids] if source_ids else None,
        source_slugs or None,
        source_class,
        adapter_name,
        max_sources,
    )
    return [
        {
            "id": str(row["id"]),
            "slug": row["slug"],
            "adapter_name": row["adapter_name"],
            "source_class": _metadata_source_class(row["metadata"]),
        }
        for row in rows
    ]


def _metadata_source_class(metadata: object) -> str | None:
    if isinstance(metadata, dict):
        value = metadata.get("source_class")
        return str(value) if value else None
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict) and parsed.get("source_class"):
            return str(parsed["source_class"])
    return None


async def _run_selected_sources(
    *,
    cfg: Settings,
    sources: list[dict[str, object]],
    max_documents: int,
    max_chunks: int,
    no_embeddings: bool,
    extract_force: bool,
    ingest_trigger: str,
    adapter_config_overrides: dict[str, object] | None = None,
) -> tuple[list[dict[str, object]], bool]:
    from intercal_shared.db import get_pool
    from intercal_shared.factory import make_budgeted_llm, make_embeddings, make_storage

    from intercal_pipeline.run import run_pipeline

    pool = await get_pool(cfg.database_url)
    storage = make_storage(cfg)
    llm = await make_budgeted_llm(cfg, pool=pool)
    embeddings = make_embeddings(cfg)
    effective_extract_force = extract_force or not cfg.extract_only_changed

    all_health: list[dict[str, object]] = []
    any_failed = False

    for src in sources:
        src_id = str(src["id"])
        print(
            f"Running pipeline for source: {src['slug']} ({src_id}) mode={ingest_trigger}",
            file=sys.stderr,
        )
        try:
            health = await run_pipeline(
                source_id=src_id,
                pool=pool,
                storage=storage,
                llm=llm,
                embeddings=embeddings,
                max_documents=max_documents,
                max_chunks_per_doc=max_chunks,
                embed_batch_size=cfg.embeddings_batch_size,
                use_embeddings_for_resolve=not no_embeddings,
                use_embeddings_for_link=not no_embeddings,
                extract_force=effective_extract_force,
                ingest_trigger=ingest_trigger,
                adapter_config_overrides=adapter_config_overrides,
                source_slug=str(src["slug"]),
                source_class=(
                    str(src["source_class"]) if src.get("source_class") is not None else None
                ),
            )
            all_health.append(health.to_dict())
            if health.status == "failed":
                any_failed = True
        except Exception as exc:
            print(f"  Source {src['slug']} pipeline error: {exc}", file=sys.stderr)
            all_health.append(
                {
                    "source_id": src_id,
                    "source_slug": src["slug"],
                    "mode": ingest_trigger,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            any_failed = True
    return all_health, any_failed


@app.command("run")
def run_cmd(
    source_id: str = typer.Option(
        ...,
        "--source-id",
        help="UUID of the source to process end-to-end.",
    ),
    max_documents: int = typer.Option(
        0,
        "--max-documents",
        help=(
            "Hard cap on documents per run.  "
            "0 = use INGEST_MAX_DOCS_PER_RUN from settings (default 200)."
        ),
    ),
    max_chunks: int = typer.Option(
        20,
        "--max-chunks",
        help="Maximum chunks to extract claims from per document (budget guard).",
    ),
    no_embeddings: bool = typer.Option(
        False,
        "--no-embeddings",
        help="Skip embedding-based resolution and linking (faster, exact-match only).",
    ),
    extract_force: bool = typer.Option(
        False,
        "--extract-force",
        help=(
            "Re-extract mentions/claims for already-processed documents.  "
            "Default skips them (keeps re-runs idempotent)."
        ),
    ),
) -> None:
    """Run the full pipeline for a single source.

    Chains: ingest → normalize → extract (mentions+claims) → embed →
    resolve entities → link claim entities → derive relationships →
    write fact versions.

    Idempotent — re-running skips already-processed work.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)
    effective_max = max_documents if max_documents > 0 else cfg.ingest_max_docs_per_run

    async def _run() -> None:
        from intercal_shared.db import close_all_pools, get_pool
        from intercal_shared.factory import make_budgeted_llm, make_embeddings, make_storage

        from intercal_pipeline.run import run_pipeline

        pool = await get_pool(cfg.database_url)
        storage = make_storage(cfg)
        llm = await make_budgeted_llm(cfg, pool=pool)
        embeddings = make_embeddings(cfg)
        effective_extract_force = extract_force or not cfg.extract_only_changed

        health = await run_pipeline(
            source_id=source_id,
            pool=pool,
            storage=storage,
            llm=llm,
            embeddings=embeddings,
            max_documents=effective_max,
            max_chunks_per_doc=max_chunks,
            embed_batch_size=cfg.embeddings_batch_size,
            use_embeddings_for_resolve=not no_embeddings,
            use_embeddings_for_link=not no_embeddings,
            extract_force=effective_extract_force,
        )

        await close_all_pools()

        print(json.dumps(health.to_dict(), indent=2), file=sys.stderr)

        if health.status == "failed":
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("run-all")
def run_all_cmd(
    max_documents: int = typer.Option(
        0,
        "--max-documents",
        help="Hard cap per source per run.  0 = INGEST_MAX_DOCS_PER_RUN.",
    ),
    max_chunks: int = typer.Option(
        20,
        "--max-chunks",
        help="Maximum chunks to extract claims from per document.",
    ),
    no_embeddings: bool = typer.Option(
        False,
        "--no-embeddings",
        help="Skip embedding-based resolution and linking.",
    ),
    extract_force: bool = typer.Option(
        False,
        "--extract-force",
        help=(
            "Re-extract already-processed documents. Default honors "
            "EXTRACT_ONLY_CHANGED=true and skips unchanged documents."
        ),
    ),
) -> None:
    """Run the full pipeline for ALL active, non-paused sources.

    Sources are processed sequentially (one source at a time) to stay within
    the LLM daily budget and Neon CU-hour budget (resource-budget.md).
    Idempotent — re-running is always safe.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)
    effective_max = max_documents if max_documents > 0 else cfg.ingest_max_docs_per_run

    async def _run() -> None:

        from intercal_shared.db import close_all_pools, get_pool

        pool = await get_pool(cfg.database_url)
        active_sources = await select_sources(pool=pool)

        if not active_sources:
            print("No active sources found.", file=sys.stderr)
            await close_all_pools()
            return

        all_health, any_failed = await _run_selected_sources(
            cfg=cfg,
            sources=active_sources,
            max_documents=effective_max,
            max_chunks=max_chunks,
            no_embeddings=no_embeddings,
            extract_force=extract_force,
            ingest_trigger="scheduled",
        )

        await close_all_pools()

        print(json.dumps(all_health, indent=2), file=sys.stderr)

        if any_failed:
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("backfill")
def backfill_cmd(
    source_ids: Annotated[
        list[str] | None,
        typer.Option("--source-id", help="Source UUID allowlist. May be repeated."),
    ] = None,
    source_slugs: Annotated[
        list[str] | None,
        typer.Option("--source-slug", help="Source slug allowlist. May be repeated."),
    ] = None,
    source_class: str | None = typer.Option(
        None,
        "--source-class",
        help="Restrict to sources whose metadata.source_class matches this value.",
    ),
    adapter_name: str | None = typer.Option(
        None,
        "--adapter-name",
        help="Restrict to sources using one adapter name.",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Historical window start date (YYYY-MM-DD), passed to source adapters.",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Historical window end date (YYYY-MM-DD), passed to source adapters.",
    ),
    max_documents: int = typer.Option(
        0,
        "--max-documents",
        help="Hard cap per source for this backfill run. 0 = INGEST_MAX_DOCS_PER_RUN.",
    ),
    max_sources: int = typer.Option(
        0,
        "--max-sources",
        help="Maximum selected sources to execute. 0 = no explicit cap.",
    ),
    max_chunks: int = typer.Option(
        20,
        "--max-chunks",
        help="Maximum chunks to extract claims from per document.",
    ),
    no_embeddings: bool = typer.Option(
        False,
        "--no-embeddings",
        help="Skip embedding-based resolution and linking.",
    ),
    extract_force: bool = typer.Option(
        False,
        "--extract-force",
        help="Re-extract already-processed documents. Default keeps re-runs idempotent.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print selected sources and effective backfill controls without fetching or writing.",
    ),
) -> None:
    """Run date-windowed historical backfill through the normal pipeline path."""
    cfg = _get_settings()
    _setup_logging(cfg.log_level)
    effective_max = max_documents if max_documents > 0 else cfg.ingest_max_docs_per_run
    overrides = build_backfill_overrides(start_date, end_date)

    async def _run() -> None:
        from intercal_shared.db import close_all_pools, get_pool

        pool = await get_pool(cfg.database_url)
        sources = await select_sources(
            pool=pool,
            source_ids=source_ids,
            source_slugs=source_slugs,
            source_class=source_class,
            adapter_name=adapter_name,
            max_sources=max_sources,
        )

        selection = {
            "mode": "backfill",
            "dry_run": dry_run,
            "max_documents_per_source": effective_max,
            "max_chunks_per_document": max_chunks,
            "adapter_config_overrides": overrides,
            "selected_source_count": len(sources),
            "sources": sources,
        }
        if dry_run:
            await close_all_pools()
            print(json.dumps(selection, indent=2), file=sys.stderr)
            return

        if not sources:
            await close_all_pools()
            print(json.dumps(selection, indent=2), file=sys.stderr)
            raise typer.Exit(code=1)

        all_health, any_failed = await _run_selected_sources(
            cfg=cfg,
            sources=sources,
            max_documents=effective_max,
            max_chunks=max_chunks,
            no_embeddings=no_embeddings,
            extract_force=extract_force,
            ingest_trigger="backfill",
            adapter_config_overrides=overrides or None,
        )

        await close_all_pools()
        print(json.dumps(all_health, indent=2), file=sys.stderr)
        if any_failed:
            raise typer.Exit(code=1)

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
