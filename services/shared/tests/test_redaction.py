"""Tests for credential redaction in log/output-safe URL formatting."""

from __future__ import annotations

from intercal_shared.redaction import redact_url


def test_redacts_postgres_password() -> None:
    dsn = "postgresql://neondb_owner:npg_secret123@ep-x-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    out = redact_url(dsn)
    assert "npg_secret123" not in out
    assert ":***@" in out
    # Non-secret parts stay visible for debugging.
    assert "neondb_owner" in out
    assert "ep-x-pooler.us-east-2.aws.neon.tech" in out
    assert "/neondb" in out
    assert "sslmode=require" in out


def test_redacts_redis_token() -> None:
    url = "redis://default:AYxxToKeNzzz@fly-upstash.upstash.io:6379"
    out = redact_url(url)
    assert "AYxxToKeNzzz" not in out
    assert out == "redis://default:***@fly-upstash.upstash.io:6379"


def test_preserves_port_and_path() -> None:
    out = redact_url("postgres://intercal:intercal@localhost:5432/intercal")
    assert out == "postgres://intercal:***@localhost:5432/intercal"


def test_url_without_credentials_unchanged() -> None:
    out = redact_url("redis://localhost:6379")
    assert out == "redis://localhost:6379"


def test_non_url_blanket_masked() -> None:
    # A key=value libpq DSN (or any non-URL) has no parseable host: mask wholesale
    # rather than risk leaking an embedded password.
    assert redact_url("host=localhost dbname=intercal password=secret") == "<redacted-url>"
