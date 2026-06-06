"""Credential redaction helpers for log/output safety.

A connection URL (Postgres DSN, Redis URL, S3 endpoint with embedded keys, …)
carries its secret in the userinfo (``user:password@host``). Logging it verbatim
leaks the credential into every runner's logs (Cloud Run, GitHub Actions, local) —
a "secrets out of logs" violation (AGENTS.md hard rule). Use :func:`redact_url`
before logging any URL that may contain credentials.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """Return *url* with any embedded credentials masked, safe for logs.

    Keeps scheme / host / path / query visible for debugging but masks the
    password in the userinfo. Non-URL inputs fall back to a blanket mask so a
    malformed value can never leak a secret it might still contain.
    """
    try:
        parts = urlsplit(url)
        if not parts.hostname:
            return "<redacted-url>"
        userinfo = ""
        if parts.username:
            userinfo = parts.username + (":***" if parts.password else "") + "@"
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, f"{userinfo}{host}", parts.path, parts.query, ""))
    except ValueError:
        return "<redacted-url>"
