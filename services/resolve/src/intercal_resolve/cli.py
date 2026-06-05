"""Intercal resolve service CLI.

Entry point: ``python -m intercal_resolve <command> [options]``
"""

from __future__ import annotations

import asyncio
import logging
import sys

import typer
from intercal_shared.config import Settings

app = typer.Typer(
    name="intercal-resolve",
    help="Intercal entity resolution and fact versioning worker.",
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


@app.command("resolve-entities")
def resolve_entities_cmd(
    batch_size: int = typer.Option(100, "--batch-size", help="Mentions to process per run."),
    use_embeddings: bool = typer.Option(
        True,
        "--embeddings/--no-embeddings",
        help="Use the configured embeddings adapter for similarity-based candidates.",
    ),
) -> None:
    """Generate entity resolution candidates from unresolved mentions.

    Idempotent — candidates are upserted; existing decisions are not overwritten.
    Auto-merges high-confidence exact matches; ambiguous cases land in needs_review.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_embeddings

        from intercal_resolve.jobs import resolve_entities

        pool = await get_pool(cfg.database_url)
        emb = make_embeddings(cfg) if use_embeddings else None

        counters = await resolve_entities(pool=pool, embeddings=emb, batch_size=batch_size)
        print(f"resolve-entities: {counters}")

    asyncio.run(_run())


@app.command("derive-relationships")
def derive_relationships_cmd(
    claim_id: str = typer.Option(..., "--claim-id", help="UUID of the claim to process."),
) -> None:
    """Derive typed temporal relationships from an extracted claim.

    Idempotent — existing relationships with the same typed edge are upserted.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool

        from intercal_resolve.jobs import derive_relationships

        pool = await get_pool(cfg.database_url)
        await derive_relationships(claim_id=claim_id, pool=pool)

    asyncio.run(_run())


@app.command("write-fact-versions")
def write_fact_versions_cmd(
    entity_id: str = typer.Option(..., "--entity-id", help="UUID of the entity to version."),
) -> None:
    """Write append-only fact version records for an entity's current state.

    Idempotent — a version is only written if the derived state has changed.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool

        from intercal_resolve.jobs import write_fact_versions

        pool = await get_pool(cfg.database_url)
        await write_fact_versions(entity_id=entity_id, pool=pool)

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
