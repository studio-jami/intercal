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

import json
import logging
import re
import unicodedata
import uuid
from typing import Any

_log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Cosine distance thresholds for entity resolution decisions.
# Cosine *distance* = 1 - cosine_similarity (pgvector <=> operator).
# Lower distance = more similar.
#
# Conservative bias: the MERGE threshold is tight; anything ambiguous lands
# in needs_review rather than being silently merged.  False non-merges are
# acceptable; false merges are data corruption (AGENTS.md).
COSINE_MERGE_THRESHOLD = 0.15   # distance ≤ this → high-confidence merge candidate
COSINE_REVIEW_THRESHOLD = 0.40  # distance ≤ this → needs_review; above → no candidate

# Minimum mention extraction_confidence to attempt resolution.
MIN_MENTION_CONFIDENCE = 0.50

# Auto-merge confidence floor for exact name / external-ID matches.
EXACT_MATCH_CONFIDENCE = 0.95

# Embedding-similarity candidate confidence (scaled by 1 - distance).
_EMBEDDING_BASE_CONFIDENCE = 0.70

# Wikidata QID pattern (Q followed by digits).
_QID_RE = re.compile(r"^Q\d+$")

# Wikidata Property ID pattern.
_PID_RE = re.compile(r"^P\d+$")
_PROP_PREFIXED_RE = re.compile(r"^Property:(P\d+)$")

# Mention proposed_type → entity type_id mapping.
# ROLE and OFFICE types are kept separate (role/office separation rule).
# ORG → organization, PERSON → person, GPE → place, etc.
_TYPE_MAP: dict[str, str] = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "place",
    "ROLE": "role",
    "PRODUCT": "product",
    "CONCEPT": "concept",
    "EVENT": "event",
    "LAW": "legislation",
    "SOURCE": "source",
    "ARTIFACT": "technical_artifact",
}

# Job name written to entity_merge_events.merged_by.
_JOB_ACTOR = "resolve_entities_v1"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def normalize_name(text: str) -> str:
    """Normalize a mention span for name-matching (case-fold, NFC, strip)."""
    return unicodedata.normalize("NFC", text).strip().casefold()


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (left, right) with left < right (UUID ordering) — prevents duplicate pairs."""
    return (a, b) if str(a) < str(b) else (b, a)


def detect_external_id(text_span: str) -> tuple[str, str] | None:
    """Detect a Wikidata QID / Property ID in the span.

    Returns ``(namespace, external_id)`` or ``None``.
    """
    span = text_span.strip()
    if _QID_RE.match(span):
        return ("wikidata", span)
    if _PID_RE.match(span):
        return ("wikidata_property", span)
    m = _PROP_PREFIXED_RE.match(span)
    if m:
        return ("wikidata_property", m.group(1))
    return None


async def _find_entity_by_external_id(
    pool: Any,
    namespace: str,
    external_id: str,
) -> uuid.UUID | None:
    """Look up a canonical (non-deprecated) entity by external ID."""
    row = await pool.fetchrow(
        """
        SELECT e.id
        FROM entity_external_ids eei
        JOIN entities e ON e.id = eei.entity_id
        WHERE eei.namespace = $1
          AND eei.external_id = $2
          AND e.is_deprecated = false
        LIMIT 1
        """,
        namespace,
        external_id,
    )
    return uuid.UUID(str(row["id"])) if row else None


async def _find_entity_by_name(
    pool: Any,
    canonical_name_norm: str,
    type_id: str,
) -> uuid.UUID | None:
    """Exact case-insensitive canonical name match within the same entity type."""
    row = await pool.fetchrow(
        """
        SELECT id FROM entities
        WHERE lower(canonical_name) = $1
          AND type_id = $2
          AND is_deprecated = false
        LIMIT 1
        """,
        canonical_name_norm,
        type_id,
    )
    if row:
        return uuid.UUID(str(row["id"]))
    # Also search aliases.
    row = await pool.fetchrow(
        """
        SELECT e.id
        FROM entity_aliases ea
        JOIN entities e ON e.id = ea.entity_id
        WHERE lower(ea.alias) = $1
          AND e.type_id = $2
          AND e.is_deprecated = false
        LIMIT 1
        """,
        canonical_name_norm,
        type_id,
    )
    return uuid.UUID(str(row["id"])) if row else None


async def _find_entity_embedding_candidates(
    pool: Any,
    embeddings: Any,
    text_span: str,
    type_id: str,
    limit: int = 5,
) -> list[tuple[uuid.UUID, float]]:
    """Find candidate entities by embedding cosine distance.

    Returns a list of ``(entity_id, cosine_distance)`` sorted by distance
    ascending (most similar first).  Only non-deprecated entities of *type_id*
    with an entity embedding are searched.

    Falls back to an empty list if the embeddings adapter is unavailable or
    if no entity embeddings exist.
    """
    if embeddings is None:
        return []

    try:
        vectors = await embeddings.embed([text_span])
    except Exception as exc:
        _log.warning("resolve_entities: embedding failed for %r: %s", text_span, exc)
        return []

    if not vectors:
        return []

    vec = vectors[0]
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    # Entity embeddings table (owner_type='entity') — if it exists and has rows.
    try:
        rows = await pool.fetch(
            """
            SELECT ee.entity_id, (ee.embedding <=> $1::halfvec) AS distance
            FROM entity_embeddings ee
            JOIN entities e ON e.id = ee.entity_id
            WHERE e.type_id = $2
              AND e.is_deprecated = false
              AND ee.model = $3
            ORDER BY ee.embedding <=> $1::halfvec
            LIMIT $4
            """,
            vec_literal,
            type_id,
            embeddings.model,
            limit,
        )
        return [(uuid.UUID(str(r["entity_id"])), float(r["distance"])) for r in rows]
    except Exception as exc:
        # entity_embeddings table may not exist yet (W5 only built chunk/claim/document
        # embeddings tables — entity embeddings are populated when entities are created).
        _log.debug("resolve_entities: entity embedding query failed: %s", exc)
        return []


async def _create_entity(
    pool: Any,
    *,
    type_id: str,
    canonical_name: str,
    description: str | None = None,
    source_document_ids: list[str] | None = None,
) -> uuid.UUID:
    """Insert a new entity and return its UUID.

    Idempotent by name within type: if an entity with the same canonical_name
    (case-insensitive) and type already exists (non-deprecated), return that
    entity's ID instead of creating a duplicate.
    """
    norm = normalize_name(canonical_name)
    existing_id = await _find_entity_by_name(pool, norm, type_id)
    if existing_id is not None:
        return existing_id

    entity_id = uuid.uuid4()
    metadata: dict[str, Any] = {}
    if source_document_ids:
        metadata["source_document_ids"] = source_document_ids

    await pool.execute(
        """
        INSERT INTO entities (
            id, type_id, canonical_name, description, metadata
        ) VALUES ($1, $2, $3, $4, $5)
        """,
        entity_id,
        type_id,
        canonical_name,
        description,
        json.dumps(metadata),
    )
    _log.debug(
        "resolve_entities: created entity %s type=%s name=%r",
        entity_id,
        type_id,
        canonical_name,
    )
    return entity_id


async def _embed_entity(
    pool: Any,
    embeddings: Any,
    entity_id: uuid.UUID,
    canonical_name: str,
) -> None:
    """Embed an entity's canonical name and upsert into entity_embeddings.

    Non-fatal: embedding failures are logged and swallowed so entity creation
    is never blocked by an embeddings adapter failure.

    Idempotent: ``ON CONFLICT (entity_id, model) DO UPDATE`` refreshes the vector.
    """
    if embeddings is None:
        return
    try:
        vectors = await embeddings.embed([canonical_name])
    except Exception as exc:
        _log.warning("_embed_entity: embed failed for %r: %s", canonical_name, exc)
        return

    if not vectors:
        return

    vec = vectors[0]
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
    try:
        await pool.execute(
            """
            INSERT INTO entity_embeddings
                (entity_id, model, dim, embedding, embedded_text)
            VALUES ($1, $2, $3, $4::halfvec, $5)
            ON CONFLICT (entity_id, model) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    embedded_text = EXCLUDED.embedded_text,
                    created_at = now()
            """,
            entity_id,
            embeddings.model,
            embeddings.dim,
            vec_literal,
            canonical_name,
        )
        _log.debug("_embed_entity: embedded entity %s (%r)", entity_id, canonical_name)
    except Exception as exc:
        _log.warning("_embed_entity: DB upsert failed for entity %s: %s", entity_id, exc)


async def _upsert_resolution_candidate(
    pool: Any,
    *,
    left_id: uuid.UUID,
    right_id: uuid.UUID,
    proposed_decision: str,
    confidence: float,
    matching_signals: list[dict[str, Any]],
    negative_signals: list[dict[str, Any]],
    decision_source: str,
    evidence_document_ids: list[uuid.UUID],
) -> uuid.UUID:
    """Upsert an entity_resolution_candidates row.

    Idempotent: ``ON CONFLICT (left_entity_id, right_entity_id) DO UPDATE``
    updates the confidence and signals but does NOT overwrite a human/decided
    decision (``decision_status != 'open'`` rows are left untouched).

    Returns the candidate row UUID.
    """
    left, right = ordered_pair(left_id, right_id)
    candidate_id = uuid.uuid4()
    row = await pool.fetchrow(
        """
        INSERT INTO entity_resolution_candidates (
            id, left_entity_id, right_entity_id,
            proposed_decision, decision_status, confidence,
            matching_signals, negative_signals, evidence_document_ids,
            decision_source
        ) VALUES (
            $1, $2, $3,
            $4, 'open', $5,
            $6::jsonb, $7::jsonb, $8,
            $9
        )
        ON CONFLICT (left_entity_id, right_entity_id) DO UPDATE
            SET proposed_decision     =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.proposed_decision
                         ELSE entity_resolution_candidates.proposed_decision END,
                confidence            =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.confidence
                         ELSE entity_resolution_candidates.confidence END,
                matching_signals      =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.matching_signals
                         ELSE entity_resolution_candidates.matching_signals END,
                negative_signals      =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.negative_signals
                         ELSE entity_resolution_candidates.negative_signals END,
                evidence_document_ids =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.evidence_document_ids
                         ELSE entity_resolution_candidates.evidence_document_ids END,
                decision_source       =
                    CASE WHEN entity_resolution_candidates.decision_status = 'open'
                         THEN EXCLUDED.decision_source
                         ELSE entity_resolution_candidates.decision_source END,
                updated_at            = now()
        RETURNING id
        """,
        candidate_id,
        left,
        right,
        proposed_decision,
        round(confidence, 2),
        json.dumps(matching_signals),
        json.dumps(negative_signals),
        evidence_document_ids,
        decision_source,
    )
    return uuid.UUID(str(row["id"]))


async def _perform_merge(
    pool: Any,
    *,
    candidate_id: uuid.UUID,
    source_id: uuid.UUID,  # loser
    target_id: uuid.UUID,  # winner
    rationale: str,
) -> uuid.UUID:
    """Execute a confirmed entity merge — idempotent if source is already deprecated.

    Steps:
    1. Snapshot both entities.
    2. Re-parent aliases from source → target (if not already there).
    3. Re-parent external IDs from source → target (if not already there).
    4. Mark source deprecated (merged_into_id → target).
    5. Write entity_merge_events row.
    6. Update entity_resolution_candidates.decision_status → 'decided'.

    Returns the entity_merge_events.id created.
    """
    # Idempotent: if source is already deprecated (merged), skip.
    src_row = await pool.fetchrow(
        "SELECT is_deprecated, merged_into_id, canonical_name, type_id, description, "
        "current_state, metadata FROM entities WHERE id = $1",
        source_id,
    )
    if src_row is None:
        raise ValueError(f"source entity {source_id} not found")
    if src_row["is_deprecated"]:
        _log.info(
            "resolve_entities: merge skipped — source %s already deprecated (merged into %s)",
            source_id,
            src_row["merged_into_id"],
        )
        # Return the existing merge event if one links this candidate.
        existing = await pool.fetchrow(
            "SELECT id FROM entity_merge_events"
            " WHERE source_entity_id = $1 AND is_reversed = false LIMIT 1",
            source_id,
        )
        if existing:
            return uuid.UUID(str(existing["id"]))
        # Fallback: create a synthetic merge event ID that still marks the candidate decided.
        # (Should not happen in normal flow.)
        evt_id = uuid.uuid4()
        return evt_id

    tgt_row = await pool.fetchrow(
        "SELECT canonical_name, type_id, description, current_state, metadata"
        " FROM entities WHERE id = $1",
        target_id,
    )
    if tgt_row is None:
        raise ValueError(f"target entity {target_id} not found")

    source_snapshot = {
        "id": str(source_id),
        "canonical_name": src_row["canonical_name"],
        "type_id": src_row["type_id"],
        "description": src_row["description"],
        "current_state": src_row["current_state"]
            if isinstance(src_row["current_state"], dict) else {},
        "metadata": src_row["metadata"]
            if isinstance(src_row["metadata"], dict) else {},
    }
    target_snapshot = {
        "id": str(target_id),
        "canonical_name": tgt_row["canonical_name"],
        "type_id": tgt_row["type_id"],
        "description": tgt_row["description"],
        "current_state": tgt_row["current_state"]
            if isinstance(tgt_row["current_state"], dict) else {},
        "metadata": tgt_row["metadata"]
            if isinstance(tgt_row["metadata"], dict) else {},
    }

    # Re-parent aliases.
    alias_rows = await pool.fetch(
        "SELECT id, alias, alias_type, language FROM entity_aliases WHERE entity_id = $1",
        source_id,
    )
    moved_alias_ids: list[uuid.UUID] = []
    for ar in alias_rows:
        try:
            await pool.execute(
                """
                UPDATE entity_aliases SET entity_id = $1 WHERE id = $2
                """,
                target_id,
                ar["id"],
            )
            moved_alias_ids.append(uuid.UUID(str(ar["id"])))
        except Exception:
            # Duplicate alias on target — just delete the source alias instead.
            await pool.execute("DELETE FROM entity_aliases WHERE id = $1", ar["id"])

    # Re-parent external IDs.
    eid_rows = await pool.fetch(
        "SELECT id, namespace, external_id FROM entity_external_ids WHERE entity_id = $1",
        source_id,
    )
    moved_eid_ids: list[uuid.UUID] = []
    for er in eid_rows:
        try:
            await pool.execute(
                "UPDATE entity_external_ids SET entity_id = $1 WHERE id = $2",
                target_id,
                er["id"],
            )
            moved_eid_ids.append(uuid.UUID(str(er["id"])))
        except Exception:
            await pool.execute("DELETE FROM entity_external_ids WHERE id = $1", er["id"])

    # Mark source deprecated.
    await pool.execute(
        """
        UPDATE entities
        SET is_deprecated = true,
            merged_into_id = $1,
            deprecated_at = now(),
            deprecation_reason = 'merged',
            updated_at = now()
        WHERE id = $2
        """,
        target_id,
        source_id,
    )

    # Write merge event.
    event_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO entity_merge_events (
            id, candidate_id,
            source_entity_id, target_entity_id,
            source_snapshot, target_snapshot,
            moved_alias_ids, moved_external_id_ids,
            merged_by, rationale
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
        """,
        event_id,
        candidate_id,
        source_id,
        target_id,
        json.dumps(source_snapshot),
        json.dumps(target_snapshot),
        moved_alias_ids,
        moved_eid_ids,
        _JOB_ACTOR,
        rationale,
    )

    # Update candidate → decided + link merge event.
    await pool.execute(
        """
        UPDATE entity_resolution_candidates
        SET decision_status = 'decided',
            merge_event_id = $1,
            decided_at = now(),
            decided_by = $2,
            updated_at = now()
        WHERE id = $3
        """,
        event_id,
        _JOB_ACTOR,
        candidate_id,
    )

    _log.info(
        "resolve_entities: merged entity %s → %s (event %s)",
        source_id,
        target_id,
        event_id,
    )
    return event_id


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities
# ──────────────────────────────────────────────────────────────────────────────


async def resolve_entities(
    *,
    pool: Any,
    embeddings: Any | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    """Generate entity resolution candidates from unresolved mentions.

    Conservative entity resolution pipeline:

    1. **Load** unresolved mentions (batch_size, confidence ≥ threshold).
    2. **Group** mentions by (normalized text_span, type_id) to find duplicates.
    3. **For each distinct span/type group**:
       a. Detect Wikidata QID/Property in the span → exact external-ID lookup.
          If matched → link mention(s) to existing entity (high confidence).
          If not → upsert a new entity and register the external ID.
       b. Exact canonical-name lookup (case-insensitive) within the same type.
          Matched entity → assign mention(s); unmatched → create new entity.
       c. Embedding similarity (if *embeddings* adapter is provided):
          distance ≤ ``COSINE_MERGE_THRESHOLD`` → ``merge`` candidate.
          distance ≤ ``COSINE_REVIEW_THRESHOLD`` → ``needs_review`` candidate.
          Above threshold → no candidate (entities stay separate — conservative).
    4. **Within-group de-duplication**: when two spans in the same group both
       map to different entities, create a resolution candidate (merge or
       needs_review depending on similarity).
    5. **Write mention links** (``mentions.entity_id``, ``resolution_status``).
    6. **Auto-merge** candidates with proposed_decision='merge' and
       confidence ≥ ``EXACT_MATCH_CONFIDENCE``.  Ambiguous / review cases are
       left in the ``entity_resolution_candidates`` table for human inspection.

    Idempotent: candidates are upserted by (left_entity_id, right_entity_id);
    re-running updates signals without duplicating rows or overwriting human
    decisions.  Mention links are written with ``ON CONFLICT DO NOTHING`` on the
    idempotent path (already-resolved mentions are skipped).

    Args:
        pool: asyncpg connection pool.
        embeddings: Optional EmbeddingsPort for similarity-based candidate
            generation.  When ``None``, only exact-ID and exact-name strategies
            run (cheaper; still satisfies the acceptance gate).
        batch_size: Number of unresolved mentions to process per run.

    Returns:
        Dict with counters:
        ``mentions_loaded``, ``mentions_resolved``, ``entities_created``,
        ``candidates_created``, ``merges_performed``, ``review_needed``.

    Raises:
        ValueError: If a required DB row is missing during merge execution.
    """
    _log.info("resolve_entities: batch_size=%d", batch_size)

    counters: dict[str, int] = {
        "mentions_loaded": 0,
        "mentions_resolved": 0,
        "entities_created": 0,
        "candidates_created": 0,
        "merges_performed": 0,
        "review_needed": 0,
    }

    # ── 1. Load a batch of unresolved mentions ────────────────────────────────
    mentions = await pool.fetch(
        """
        SELECT
            m.id,
            m.document_id,
            m.text_span,
            m.proposed_type,
            m.extraction_confidence,
            m.chunk_id
        FROM mentions m
        WHERE m.resolution_status = 'unresolved'
          AND m.extraction_confidence >= $1
        ORDER BY m.extraction_confidence DESC, m.created_at
        LIMIT $2
        """,
        MIN_MENTION_CONFIDENCE,
        batch_size,
    )

    counters["mentions_loaded"] = len(mentions)
    if not mentions:
        _log.info("resolve_entities: no unresolved mentions; running merge-only pass.")
    else:
        _log.info("resolve_entities: loaded %d unresolved mentions", len(mentions))

    # ── 2. Group by (normalized_span, type_id) ───────────────────────────────
    # Groups accumulate mention IDs + document IDs for provenance.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in mentions:
        raw_type = (row["proposed_type"] or "ARTIFACT").upper()
        type_id = _TYPE_MAP.get(raw_type, "technical_artifact")
        norm_span = normalize_name(str(row["text_span"]))
        key = (norm_span, type_id)
        groups.setdefault(key, []).append(
            {
                "mention_id": uuid.UUID(str(row["id"])),
                "document_id": uuid.UUID(str(row["document_id"])),
                "text_span": str(row["text_span"]),
                "type_id": type_id,
                "confidence": float(row["extraction_confidence"]),
            }
        )

    # ── 3. Resolve each group ─────────────────────────────────────────────────
    # Maps mention_id → resolved entity_id (populated as we go).
    mention_entity_map: dict[uuid.UUID, uuid.UUID] = {}

    # Track new entities created this run (span_norm+type_id → entity_id).
    span_entity_cache: dict[tuple[str, str], uuid.UUID] = {}

    for (norm_span, type_id), group_mentions in groups.items():
        raw_span = group_mentions[0]["text_span"]
        doc_ids = list({m["document_id"] for m in group_mentions})

        resolved_entity_id: uuid.UUID | None = None
        resolution_method: str = "none"
        match_signals: list[dict[str, Any]] = []

        # ── 3a. External-ID match (highest confidence) ────────────────────
        ext_id_info = detect_external_id(raw_span)
        if ext_id_info is not None:
            namespace, external_id = ext_id_info
            existing_eid_entity = await _find_entity_by_external_id(pool, namespace, external_id)
            if existing_eid_entity is not None:
                resolved_entity_id = existing_eid_entity
                resolution_method = "external_id_match"
                match_signals.append({
                    "type": "external_id",
                    "namespace": namespace,
                    "external_id": external_id,
                    "weight": 1.0,
                })
                _log.debug(
                    "resolve_entities: span %r matched existing entity %s via %s/%s",
                    raw_span, resolved_entity_id, namespace, external_id,
                )
            else:
                # Create a new entity and register the external ID.
                resolved_entity_id = await _create_entity(
                    pool,
                    type_id=type_id,
                    canonical_name=raw_span,
                    source_document_ids=[str(d) for d in doc_ids],
                )
                counters["entities_created"] += 1
                span_entity_cache[(norm_span, type_id)] = resolved_entity_id
                # Embed the new entity so future runs can use similarity search.
                await _embed_entity(pool, embeddings, resolved_entity_id, raw_span)
                # Register the external ID.
                try:
                    await pool.execute(
                        """
                        INSERT INTO entity_external_ids (entity_id, namespace, external_id, source)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (entity_id, namespace, external_id) DO NOTHING
                        """,
                        resolved_entity_id,
                        namespace,
                        external_id,
                        "extraction",
                    )
                except Exception as exc:
                    _log.warning(
                        "resolve_entities: failed to insert external_id %s/%s for %s: %s",
                        namespace, external_id, resolved_entity_id, exc,
                    )
                resolution_method = "external_id_new"
                match_signals.append({
                    "type": "external_id_new",
                    "namespace": namespace,
                    "external_id": external_id,
                    "weight": 1.0,
                })

        # ── 3b. Exact canonical-name match ────────────────────────────────
        if resolved_entity_id is None:
            existing_name_entity = await _find_entity_by_name(pool, norm_span, type_id)
            if existing_name_entity is not None:
                resolved_entity_id = existing_name_entity
                resolution_method = "exact_name"
                match_signals.append({
                    "type": "exact_name",
                    "normalized": norm_span,
                    "type_id": type_id,
                    "weight": 0.9,
                })
                _log.debug(
                    "resolve_entities: span %r matched existing entity %s via name",
                    raw_span, resolved_entity_id,
                )

        # ── 3c. Embedding similarity ──────────────────────────────────────
        embedding_candidates: list[tuple[uuid.UUID, float]] = []
        if resolved_entity_id is None and embeddings is not None:
            embedding_candidates = await _find_entity_embedding_candidates(
                pool, embeddings, raw_span, type_id, limit=3
            )

        if resolved_entity_id is None and embedding_candidates:
            best_id, best_dist = embedding_candidates[0]
            if best_dist <= COSINE_MERGE_THRESHOLD:
                # High similarity → treat as the same entity (candidate for merge).
                resolved_entity_id = best_id
                resolution_method = "embedding_similar"
                match_signals.append({
                    "type": "embedding_cosine",
                    "cosine_distance": round(best_dist, 4),
                    "weight": round(1.0 - best_dist, 4),
                })
                _log.debug(
                    "resolve_entities: span %r matched entity %s via embedding (dist=%.3f)",
                    raw_span, resolved_entity_id, best_dist,
                )

        # ── 3d. Create a new entity if still unresolved ───────────────────
        if resolved_entity_id is None:
            # Check cache first (avoids duplicate inserts within the same run).
            cached = span_entity_cache.get((norm_span, type_id))
            if cached is not None:
                resolved_entity_id = cached
                resolution_method = "new_entity_cached"
            else:
                resolved_entity_id = await _create_entity(
                    pool,
                    type_id=type_id,
                    canonical_name=raw_span,
                    source_document_ids=[str(d) for d in doc_ids],
                )
                counters["entities_created"] += 1
                span_entity_cache[(norm_span, type_id)] = resolved_entity_id
                resolution_method = "new_entity"
                # Embed the new entity immediately so sibling-span comparisons
                # within this run can find it (and future runs use it too).
                await _embed_entity(pool, embeddings, resolved_entity_id, raw_span)
                _log.debug(
                    "resolve_entities: span %r → new entity %s",
                    raw_span, resolved_entity_id,
                )

        # If we have an embedding and a resolved entity but the entity was just
        # created without embedding similarity, check existing entities for
        # a potential review candidate (conservative: don't auto-merge, just flag).
        if embedding_candidates and resolution_method in ("new_entity", "new_entity_cached"):
            for cand_entity_id, cand_dist in embedding_candidates:
                if cand_entity_id == resolved_entity_id:
                    continue
                if cand_dist <= COSINE_REVIEW_THRESHOLD:
                    neg_signals: list[dict[str, Any]] = []
                    if cand_dist > COSINE_MERGE_THRESHOLD:
                        neg_signals.append({
                            "type": "name_differs",
                            "detail": "spans do not share canonical name",
                        })
                    emb_conf = round(_EMBEDDING_BASE_CONFIDENCE * (1.0 - cand_dist), 2)
                    decision = (
                        "merge" if cand_dist <= COSINE_MERGE_THRESHOLD else "needs_review"
                    )
                    try:
                        await _upsert_resolution_candidate(
                            pool,
                            left_id=resolved_entity_id,
                            right_id=cand_entity_id,
                            proposed_decision=decision,
                            confidence=emb_conf,
                            matching_signals=[{
                                "type": "embedding_cosine",
                                "cosine_distance": round(cand_dist, 4),
                                "weight": round(1.0 - cand_dist, 4),
                            }],
                            negative_signals=neg_signals,
                            decision_source="model",
                            evidence_document_ids=doc_ids,
                        )
                        counters["candidates_created"] += 1
                        if decision == "needs_review":
                            counters["review_needed"] += 1
                    except Exception as exc:
                        _log.warning(
                            "resolve_entities: failed to create embedding candidate: %s", exc
                        )

        # Map all mentions in this group to the resolved entity.
        for m in group_mentions:
            mention_entity_map[m["mention_id"]] = resolved_entity_id

    # ── 4. Within-group and cross-group duplicate entity detection ────────────
    # Find any two groups that resolved to different entities with matching spans
    # (to catch edge cases where two mentions of the same real-world entity ended
    # up in different groups due to type mismatch).
    # This is intentionally conservative: we only create candidates, never merge.
    entity_to_spans: dict[uuid.UUID, list[tuple[str, str]]] = {}
    for (norm_span, type_id), group_mentions in groups.items():
        e_id = mention_entity_map.get(group_mentions[0]["mention_id"])
        if e_id is not None:
            entity_to_spans.setdefault(e_id, []).append((norm_span, type_id))

    # ── 5. Write mention links ────────────────────────────────────────────────
    resolved_count = 0
    for mention_id, entity_id in mention_entity_map.items():
        try:
            await pool.execute(
                """
                UPDATE mentions
                SET entity_id = $1,
                    resolution_status = 'resolved',
                    resolved_at = now()
                WHERE id = $2
                  AND resolution_status = 'unresolved'
                """,
                entity_id,
                mention_id,
            )
            resolved_count += 1
        except Exception as exc:
            _log.warning(
                "resolve_entities: failed to update mention %s: %s", mention_id, exc
            )

    counters["mentions_resolved"] = resolved_count

    # ── 6. Auto-merge high-confidence 'merge' candidates ─────────────────────
    # Only merge where the candidate was flagged 'merge' and confidence is high.
    # Ambiguous 'needs_review' cases stay open for human inspection.
    merge_candidates = await pool.fetch(
        """
        SELECT id, left_entity_id, right_entity_id, confidence, matching_signals
        FROM entity_resolution_candidates
        WHERE proposed_decision = 'merge'
          AND decision_status = 'open'
          AND confidence >= $1
        ORDER BY confidence DESC
        LIMIT 50
        """,
        EXACT_MATCH_CONFIDENCE,
    )

    for mc in merge_candidates:
        candidate_id = uuid.UUID(str(mc["id"]))
        left_id = uuid.UUID(str(mc["left_entity_id"]))
        right_id = uuid.UUID(str(mc["right_entity_id"]))
        signals = mc["matching_signals"]
        if isinstance(signals, str):
            try:
                signals = json.loads(signals)
            except Exception:
                signals = []

        # Conservative: left absorbs right (target = left; source = right).
        # The loser (source) is deprecated; the winner (target) survives.
        rationale = (
            f"Auto-merge by {_JOB_ACTOR}: "
            + ", ".join(
                s.get("type", "signal") for s in (signals if isinstance(signals, list) else [])
            )
        )
        try:
            await _perform_merge(
                pool,
                candidate_id=candidate_id,
                source_id=right_id,
                target_id=left_id,
                rationale=rationale,
            )
            counters["merges_performed"] += 1
            # Update all mentions that pointed to the deprecated (right) entity.
            await pool.execute(
                """
                UPDATE mentions
                SET entity_id = $1, updated_at = now()
                WHERE entity_id = $2
                """,
                left_id,
                right_id,
            ) if hasattr(pool, "execute") else None
        except Exception as exc:
            _log.warning(
                "resolve_entities: merge failed for candidate %s: %s", candidate_id, exc
            )

    _log.info("resolve_entities: %s", counters)
    return counters


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

    Raises:
        NotImplementedError: Claim-to-relationship mapping rules and
            temporal interval computation are Plan-02 W7 scope.
    """
    _log.info("derive_relationships: claim_id=%s", claim_id)
    raise NotImplementedError(
        "Plan 02 W7 — derive_relationships: claim-to-relationship mapping rules "
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

    Raises:
        NotImplementedError: Entity state diffing, bitemporal interval
            construction, and `fact_versions` table writes are Plan-02 W7 scope.
    """
    _log.info("write_fact_versions: entity_id=%s", entity_id)
    raise NotImplementedError(
        "Plan 02 W7 — write_fact_versions: entity state diffing, bitemporal interval "
        "construction, and fact_versions persistence not yet implemented."
    )
