"""Intercal synthesize service CLI.

Entry point: ``python -m intercal_synthesize <command> [options]``
"""

from __future__ import annotations

import asyncio
import logging
import sys

import typer
from intercal_shared.config import Settings

app = typer.Typer(
    name="intercal-synthesize",
    help="Intercal synthesis service worker.",
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


@app.command("build-digest")
def build_digest_cmd(
    target_id: str = typer.Option(..., "--target-id", help="UUID of the topic or entity."),
    since_date: str = typer.Option(..., "--since", help="ISO-8601 date (e.g. 2026-01-01)."),
    token_budget: int = typer.Option(1024, "--token-budget", help="Max tokens for the digest."),
) -> None:
    """Generate (or return cached) a token-budgeted digest for a topic/entity.

    Idempotent — cache is checked before calling the LLM.
    LLM provider is selected via LLM_PROVIDER / LLM_MODEL env vars.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_llm, make_storage

        from intercal_synthesize.jobs import build_digest

        pool = await get_pool(cfg.database_url)
        llm = make_llm(cfg)
        storage = make_storage(cfg)
        result = await build_digest(
            topic_or_entity_id=target_id,
            since_date=since_date,
            token_budget=token_budget,
            pool=pool,
            llm=llm,
            storage=storage,
        )
        typer.echo(result)

    asyncio.run(_run())


@app.command("recompute-freshness")
def recompute_freshness_cmd(
    target_id: str = typer.Option(..., "--target-id", help="UUID of the topic or entity."),
) -> None:
    """Recompute the freshness score for a topic or entity.

    Idempotent — always overwrites the current freshness score.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool

        from intercal_synthesize.jobs import recompute_freshness

        pool = await get_pool(cfg.database_url)
        score = await recompute_freshness(topic_or_entity_id=target_id, pool=pool)
        typer.echo(f"Freshness score: {score:.4f}")

    asyncio.run(_run())


@app.command("notify-subscribers")
def notify_subscribers_cmd(
    target_id: str = typer.Option(..., "--target-id", help="UUID of the changed entity/topic."),
) -> None:
    """Enqueue notifications for active subscribers of a changed entity/topic.

    Idempotent — at-most-once delivery per knowledge-change event per subscriber.
    Queue provider is selected via QUEUE_PROVIDER / REDIS_URL env vars.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_queue

        from intercal_synthesize.jobs import notify_subscribers

        pool = await get_pool(cfg.database_url)
        queue = make_queue(cfg)
        count = await notify_subscribers(
            entity_or_topic_id=target_id,
            pool=pool,
            queue=queue,
        )
        typer.echo(f"Enqueued {count} notification(s).")

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
