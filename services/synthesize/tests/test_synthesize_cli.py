"""Tests for intercal_synthesize CLI and job registry wiring — no live network required."""

from __future__ import annotations

import inspect

import pytest
from intercal_synthesize.cli import app
from intercal_synthesize.jobs import build_digest, notify_subscribers, recompute_freshness
from typer.testing import CliRunner


def test_jobs_are_importable() -> None:
    assert callable(build_digest)
    assert callable(recompute_freshness)
    assert callable(notify_subscribers)


def test_jobs_are_async() -> None:
    assert inspect.iscoroutinefunction(build_digest)
    assert inspect.iscoroutinefunction(recompute_freshness)
    assert inspect.iscoroutinefunction(notify_subscribers)


@pytest.mark.asyncio
async def test_build_digest_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await build_digest(
            topic_or_entity_id="test-id",
            since_date="2026-01-01",
            token_budget=512,
            pool=None,
            llm=None,
            storage=None,
        )


@pytest.mark.asyncio
async def test_recompute_freshness_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await recompute_freshness(topic_or_entity_id="test-id", pool=None)


@pytest.mark.asyncio
async def test_notify_subscribers_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await notify_subscribers(entity_or_topic_id="test-id", pool=None, queue=None)


def test_cli_help_lists_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "build-digest" in result.output
    assert "recompute-freshness" in result.output
    assert "notify-subscribers" in result.output


def test_build_digest_missing_options() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["build-digest"])
    assert result.exit_code != 0
