"""Resolution job functions.

Every job is:
- An async function accepting typed keyword arguments.
- Idempotent: re-running must not produce duplicate resolution candidates,
  relationship records, or fact versions.
- Invocable from the CLI or by the scheduler adapter.

Resolution design principles (from foundation report):
- Conservative over aggressive: false non-merges are acceptable; false merges
  are data corruption.
- Auditable and reversible: every merge decision is recorded with signals,
  confidence, and decision source.
- Role/office separation: "US Secretary of State" is not an alias for the
  current occupant.  Roles are separate entity nodes.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities
# ──────────────────────────────────────────────────────────────────────────────


async def resolve_entities(
    *,
    pool: Any,
    embeddings: Any | None = None,
    batch_size: int = 100,
) -> None:
    """Generate entity resolution candidates from unresolved mentions and entities.

    Idempotent: resolution candidates are upserted by (left_entity_id, right_entity_id)
    so re-runs update existing candidates rather than creating duplicates.

    Resolution strategy (ordered by confidence):
    1. Exact external-ID match (Wikidata QID, GitHub handle, etc.) → auto-merge.
    2. Exact canonical name match (case-insensitive, alias-expanded) → high-confidence candidate.
    3. Embedding-based similarity above threshold → review candidate.
    4. Ambiguous / below threshold → ``needs_review`` status.

    False non-merges are acceptable.  False merges are data corruption.
    Human review queue handles ambiguous cases.

    Args:
        pool: asyncpg connection pool.
        embeddings: Optional EmbeddingsPort for similarity-based matching.
        batch_size: Number of unresolved mention pairs to process per run.

    Raises:
        NotImplementedError: Matching algorithms (exact-ID, name, embedding
            similarity), candidate scoring, and auto-merge logic are Plan-02.
    """
    _log.info("resolve_entities: batch_size=%d", batch_size)
    raise NotImplementedError(
        "Plan 02 — resolve_entities: matching algorithms (exact-ID, name similarity, "
        "embedding cosine), candidate scoring, and auto-merge not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# derive_relationships
# ──────────────────────────────────────────────────────────────────────────────


async def derive_relationships(
    *,
    claim_id: str,
    pool: Any,
) -> None:
    """Derive typed temporal relationships from an extracted claim.

    Idempotent: relationships with the same (subject_id, predicate, object_id,
    valid_from) triple are upserted rather than duplicated.

    Relationships are derived from claims, not extracted as free-floating facts.
    Each relationship carries:
    - valid_from / valid_until (bitemporal)
    - recorded_at
    - confidence
    - source claim ID(s)
    - relationship type (from the controlled `relationship_types` vocabulary)

    Args:
        claim_id: UUID of the claim to derive relationships from.
        pool: asyncpg connection pool.

    Raises:
        NotImplementedError: Claim-to-relationship mapping rules and
            temporal interval computation are Plan-02 scope.
    """
    _log.info("derive_relationships: claim_id=%s", claim_id)
    raise NotImplementedError(
        "Plan 02 — derive_relationships: claim-to-relationship mapping rules "
        "and temporal interval computation not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# write_fact_versions
# ──────────────────────────────────────────────────────────────────────────────


async def write_fact_versions(
    *,
    entity_id: str,
    pool: Any,
) -> None:
    """Write append-only fact version records for an entity's current state.

    Idempotent: fact versions are append-only.  A version is only written if
    the current derived state differs from the most recent version record.
    No existing version is ever mutated.

    Supports bitemporal reasoning:
    - ``valid_from`` / ``valid_until``: when the fact is/was true in the world.
    - ``recorded_at``: when Intercal learned or recorded it.

    Args:
        entity_id: UUID of the entity whose fact versions to update.
        pool: asyncpg connection pool.

    Raises:
        NotImplementedError: Entity state diffing, bitemporal interval
            construction, and `fact_versions` table writes are Plan-02 scope.
    """
    _log.info("write_fact_versions: entity_id=%s", entity_id)
    raise NotImplementedError(
        "Plan 02 — write_fact_versions: entity state diffing, bitemporal interval "
        "construction, and fact_versions persistence not yet implemented."
    )
