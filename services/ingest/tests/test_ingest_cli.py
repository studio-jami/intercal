"""Tests for intercal_ingest CLI and job registry wiring — no live network required."""

from __future__ import annotations

import inspect

import pytest
from intercal_ingest.cli import app
from intercal_ingest.jobs import (
    cleanup_expired_cache,
    ingest_source,
    normalize_document,
    score_source_health,
)
from typer.testing import CliRunner

# ── Job function existence and signature ────────────────────────────────────


def test_jobs_are_importable() -> None:
    """All job functions should be importable from intercal_ingest.jobs."""
    assert callable(ingest_source)
    assert callable(normalize_document)
    assert callable(score_source_health)
    assert callable(cleanup_expired_cache)


def test_jobs_are_async() -> None:
    """Job functions must be async coroutine functions."""
    assert inspect.iscoroutinefunction(ingest_source)
    assert inspect.iscoroutinefunction(normalize_document)
    assert inspect.iscoroutinefunction(score_source_health)
    assert inspect.iscoroutinefunction(cleanup_expired_cache)


# ── W2/later stubs: still raise NotImplementedError ─────────────────────────


@pytest.mark.asyncio
async def test_normalize_document_raises_not_implemented() -> None:
    """normalize_document is Plan-02 W2; must still raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await normalize_document(document_id="test-id", pool=None, storage=None)


@pytest.mark.asyncio
async def test_cleanup_expired_cache_raises_not_implemented() -> None:
    """cleanup_expired_cache is Plan-02/03; must still raise NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await cleanup_expired_cache(pool=None, storage=None)


# ── CLI registration ─────────────────────────────────────────────────────────


def test_cli_help_lists_all_commands() -> None:
    """The CLI app should list all registered commands in --help output."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output
    assert "ingest-source" in output
    assert "normalize-document" in output
    assert "score-source-health" in output
    assert "cleanup-expired-cache" in output


def test_ingest_source_missing_option() -> None:
    """ingest-source requires --source-id; missing it should exit non-zero."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source"])
    assert result.exit_code != 0
