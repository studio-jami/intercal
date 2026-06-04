"""Intercal extract service CLI.

Entry point: ``python -m intercal_extract <command> [options]``
"""

from __future__ import annotations

import asyncio
import logging
import sys

import typer
from intercal_shared.config import Settings

app = typer.Typer(
    name="intercal-extract",
    help="Intercal extraction service worker.",
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


@app.command("extract-mentions")
def extract_mentions_cmd(
    document_id: str = typer.Option(
        ..., "--document-id", help="UUID of the normalised source document."
    ),
) -> None:
    """Extract entity mention spans from a normalised document.

    Idempotent — existing mentions are replaced on each run.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool

        from intercal_extract.jobs import extract_mentions

        pool = await get_pool(cfg.database_url)
        await extract_mentions(document_id=document_id, pool=pool)

    asyncio.run(_run())


@app.command("extract-claims")
def extract_claims_cmd(
    document_id: str = typer.Option(
        ..., "--document-id", help="UUID of the normalised source document."
    ),
) -> None:
    """Extract atomic factual claims from a normalised document via the LLM adapter.

    Idempotent — existing claims are replaced on each run.
    LLM provider is selected via LLM_PROVIDER / LLM_MODEL env vars.
    """
    cfg = _get_settings()
    _setup_logging(cfg.log_level)

    async def _run() -> None:
        from intercal_shared.db import get_pool
        from intercal_shared.factory import make_llm

        from intercal_extract.jobs import extract_claims

        pool = await get_pool(cfg.database_url)
        llm = make_llm(cfg)
        await extract_claims(document_id=document_id, pool=pool, llm=llm)

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
