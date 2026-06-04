"""Intercal runtime configuration loaded from environment / .env.

Every setting maps directly to a documented environment variable (see .env.example).
Provider-specific credentials (API keys) are optional; a clear error is raised by each
adapter when its required credential is missing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment variables or a `.env` file.

    All fields are provider-agnostic: they select an adapter name and supply
    connection parameters. No provider SDK is imported here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core datastore ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgres://intercal:intercal@localhost:5432/intercal",
        description="asyncpg-compatible DSN for the canonical Postgres store.",
    )

    # ── Object storage ────────────────────────────────────────────────────────
    storage_provider: Literal["s3"] = Field(
        default="s3",
        description="Object storage adapter selector. Only 's3' is implemented (S3-compatible).",
    )
    s3_endpoint: str = Field(
        default="http://localhost:9000",
        description="S3 endpoint URL. Point at MinIO locally, R2/S3 in prod.",
    )
    s3_region: str = Field(default="auto")
    s3_bucket: str = Field(default="intercal")
    s3_access_key_id: str = Field(default="intercal")
    s3_secret_access_key: str = Field(default="intercal-secret")
    s3_force_path_style: bool = Field(
        default=True,
        description="S3 path-style addressing (required for MinIO and most non-AWS endpoints).",
    )

    # ── Queue / cache ─────────────────────────────────────────────────────────
    queue_provider: Literal["redis", "postgres"] = Field(
        default="redis",
        description="Queue adapter: 'redis' (Upstash/Valkey) or 'postgres' (pgmq-style).",
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis / Upstash / Valkey connection URL.",
    )

    # ── Embeddings ────────────────────────────────────────────────────────────
    embeddings_provider: Literal["local", "openai"] = Field(
        default="local",
        description="Embeddings adapter: 'local' (fastembed/ONNX, zero-cost) or 'openai'.",
    )
    embeddings_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Model identifier forwarded to the embeddings adapter.",
    )
    embeddings_dim: int = Field(
        default=384,
        description="Expected output dimension. Must match the chosen model.",
    )

    # ── LLM extraction / synthesis ────────────────────────────────────────────
    llm_provider: Literal["gemini", "groq", "anthropic", "openai"] = Field(
        default="gemini",
        description="LLM adapter: 'gemini' (free default), 'groq', 'anthropic', 'openai'.",
    )
    llm_model: str = Field(
        default="gemini-2.5-flash",
        description="Model name forwarded to the LLM adapter.",
    )

    # Provider API keys — optional here; adapters raise clearly when missing.
    gemini_api_key: str | None = Field(default=None)
    groq_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler_provider: Literal["local"] = Field(
        default="local",
        description=(
            "Scheduler adapter. 'local' runs job functions inline/synchronously. "
            "In deployed envs (GitHub Actions, Modal, cron) the same CLI entrypoints "
            "are invoked directly — the adapter stays 'local'."
        ),
    )

    # ── API / MCP ─────────────────────────────────────────────────────────────
    api_port: int = Field(default=8787)
    mcp_port: int = Field(default=8788)
    public_api_base_url: str = Field(default="http://localhost:8787")

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: Literal["debug", "info", "warning", "error", "critical"] = Field(default="info")
    sentry_dsn: str | None = Field(default=None)


# Module-level singleton — import `settings` for a pre-built instance, or
# instantiate `Settings()` directly in tests to override fields.
settings: Settings = Settings()
