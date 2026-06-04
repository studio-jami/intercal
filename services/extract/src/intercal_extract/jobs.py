"""Extraction job functions.

Every job is:
- An async function accepting typed keyword arguments.
- Idempotent: re-running on already-processed input must not create duplicate
  mentions or claims.
- Invocable from the CLI (``python -m intercal_extract <job>``) or by the
  scheduler adapter.

Architecture note (hybrid extraction):
    The foundation report prescribes a hybrid approach — deterministic rule/NLP
    baselines with LLM outputs treated as proposed structured data requiring
    schema validation.  The LLM port is injected; callers control which provider
    is used.  LLM-extracted claims must be validated against a schema before
    they are persisted.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# extract_mentions
# ──────────────────────────────────────────────────────────────────────────────


async def extract_mentions(
    *,
    document_id: str,
    pool: Any,
    llm: Any | None = None,
) -> None:
    """Extract entity mention spans from a normalised source document.

    Idempotent: existing mentions for *document_id* are deleted and replaced on
    each run so partial extraction failures can be safely retried.

    Steps:
    1. Load `source_documents.normalized_text` for *document_id*.
    2. Apply rule-based NER baseline (regex + vocabulary matching).
    3. Optionally augment with LLM-based span extraction (LlmPort).
    4. Validate and deduplicate candidate spans.
    5. Upsert into `mentions` with span offsets, mention type, and confidence.

    Args:
        document_id: UUID of the normalised source document.
        pool: asyncpg connection pool.
        llm: Optional LlmPort adapter for LLM-augmented extraction.

    Raises:
        NotImplementedError: NER rules, LLM augmentation, and span normalisation
            are Plan-02 scope.  DB wiring is stubbed and ready.
    """
    _log.info("extract_mentions: document_id=%s", document_id)
    raise NotImplementedError(
        "Plan 02 — extract_mentions: NER rule baseline, LLM span augmentation, "
        "and mention deduplication not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# extract_claims
# ──────────────────────────────────────────────────────────────────────────────


async def extract_claims(
    *,
    document_id: str,
    pool: Any,
    llm: Any,
) -> None:
    """Extract atomic factual claims from a normalised source document.

    Idempotent: existing claims for *document_id* are replaced on each run
    so failed or partial extraction passes can be safely retried.

    Claims are first-class.  Each claim should capture:
    - subject / predicate / object
    - valid-time qualifiers if present in the source text
    - confidence (extraction model + rule confidence)
    - source document ID and raw text span (where license permits)
    - normalized claim text
    - lifecycle status (candidate | active | contradicted | superseded)

    LLM outputs are treated as proposed structured data and validated against
    the claims JSON schema before persistence.

    Steps:
    1. Load `source_documents.normalized_text` for *document_id*.
    2. Call `llm.extract_structured(CLAIMS_SCHEMA, text)`.
    3. Validate response against schema.
    4. Upsert validated claims into `claims` and `claim_evidence`.

    Args:
        document_id: UUID of the normalised source document.
        pool: asyncpg connection pool.
        llm: LlmPort adapter (required for claim extraction).

    Raises:
        NotImplementedError: Claims schema, LLM extraction prompt, validation,
            and DB persistence are Plan-02 scope.
    """
    _log.info("extract_claims: document_id=%s", document_id)
    raise NotImplementedError(
        "Plan 02 — extract_claims: CLAIMS_SCHEMA definition, LLM prompt engineering, "
        "schema validation, and claim persistence not yet implemented."
    )
