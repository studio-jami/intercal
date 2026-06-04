"""Tests for intercal_resolve CLI and job registry wiring — no live network required."""

from __future__ import annotations

import inspect

import pytest
from intercal_resolve.cli import app
from intercal_resolve.jobs import derive_relationships, resolve_entities, write_fact_versions
from typer.testing import CliRunner


def test_jobs_are_importable() -> None:
    assert callable(resolve_entities)
    assert callable(derive_relationships)
    assert callable(write_fact_versions)


def test_jobs_are_async() -> None:
    assert inspect.iscoroutinefunction(resolve_entities)
    assert inspect.iscoroutinefunction(derive_relationships)
    assert inspect.iscoroutinefunction(write_fact_versions)


@pytest.mark.asyncio
async def test_resolve_entities_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await resolve_entities(pool=None)


@pytest.mark.asyncio
async def test_derive_relationships_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await derive_relationships(claim_id="test-claim", pool=None)


@pytest.mark.asyncio
async def test_write_fact_versions_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02"):
        await write_fact_versions(entity_id="test-entity", pool=None)


def test_cli_help_lists_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "resolve-entities" in result.output
    assert "derive-relationships" in result.output
    assert "write-fact-versions" in result.output


def test_derive_relationships_missing_option() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["derive-relationships"])
    assert result.exit_code != 0
