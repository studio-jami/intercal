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
from datetime import UTC, datetime
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
# W7 constants
# ──────────────────────────────────────────────────────────────────────────────

# Actor tag written into fact_versions.produced_by and relationship derivation logs.
_W7_ACTOR = "derive_relationships_v1"

# Minimum claim extraction_confidence to attempt relationship derivation.
MIN_CLAIM_CONFIDENCE = 0.50

# Predicate keyword → relationship type_id mapping.
# The claim predicate is free-text (LLM-extracted); we map it to the controlled
# vocabulary by checking whether any keyword appears in the lowercased predicate.
# Order matters: more-specific rules listed first.
_PREDICATE_TO_TYPE: list[tuple[list[str], str]] = [
    # Person ↔ role / office
    (["holds_role", "holds role", "ceo", "cto", "coo", "vp", "president", "director",
      "appointed", "serves as", "named as", "role of"],
     "person_holds_role"),
    (["holds_office", "holds office", "secretary", "minister", "commissioner",
      "governor", "senator", "representative", "chancellor", "prime minister"],
     "person_holds_office"),
    # Person ↔ place (birth)
    (["born_in", "born in", "birthplace", "native of"],
     "person_born_in"),
    # Organization ↔ person (employment)
    (["employs", "employed by", "works for", "works at", "member of staff",
      "employee", "hired", "staff"],
     "organization_employs_person"),
    # Organization ↔ product / artifact
    (["owns", "developed", "created", "built", "maintains", "launched", "released",
      "produces", "owns_product"],
     "organization_owns_product"),
    # Organization ↔ artifact (publication)
    (["published", "released", "announced", "organization_published"],
     "organization_published_artifact"),
    # Person ↔ artifact (authorship)
    (["authored", "wrote", "co-authored", "created by", "person_authored"],
     "person_authored_artifact"),
    # Organization ↔ organization (subsidiary / acquisition / merger)
    (["subsidiary", "subsidiary_of", "division of", "owned by"],
     "organization_subsidiary_of"),
    (["acquired", "acquisition", "bought", "purchased"],
     "company_acquired_company"),
    (["merged", "merger", "merged_with"],
     "company_merged_with_company"),
    # Organization ↔ place (HQ / location)
    (["headquartered", "hq", "based in", "located in", "located_in",
      "offices in", "is located"],
     "organization_headquartered_in"),
    # Legislation
    (["amends", "supersedes", "amends_law", "replaces law"],
     "law_amends_law"),
    (["enacted", "enacted_by", "jurisdiction_enacted"],
     "jurisdiction_enacted_legislation"),
    # Event ↔ place
    (["occurred in", "took place in", "event_occurred"],
     "event_occurred_in_place"),
    # Source / provenance
    (["reported", "stated", "claimed", "reported_claim", "source_reported"],
     "source_reported_claim"),
    # Concept
    (["instance of", "is a", "is_a", "type of", "entity_instance"],
     "entity_instance_of_concept"),
    (["related to", "concept_related"],
     "concept_related_to_concept"),
    # Paper citations
    (["cites", "cited", "references", "paper_cites"],
     "paper_cites_paper"),
]


def map_predicate_to_type(predicate: str) -> str | None:
    """Map a free-text predicate to a seeded relationship type_id, or None.

    Returns the first matching type_id from ``_PREDICATE_TO_TYPE``, or
    ``None`` if no keyword matches (caller must decide whether to skip or
    use a fallback type).
    """
    pred_lower = predicate.lower()
    for keywords, type_id in _PREDICATE_TO_TYPE:
        for kw in keywords:
            if kw in pred_lower:
                return type_id
    return None


# Internal alias kept for backward compat (module-level callers use the public name)
_map_predicate_to_type = map_predicate_to_type


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


async def find_external_id_collisions(
    pool: Any,
) -> list[tuple[uuid.UUID, uuid.UUID, str, str]]:
    """Find pairs of live entities that share an identical external ID.

    An external ID (e.g. a Wikidata QID) is a strong, unambiguous co-reference
    signal: two non-deprecated entities carrying the same ``(namespace,
    external_id)`` are the same real-world thing and MUST collapse to one.

    This catches the realistic case where the same QID is minted under two
    surface forms (``Q5401080`` as a bare span in one document and a
    ``Property:``/prefixed form in another, or a name that later acquires the
    same ID) — distinct ``canonical_name`` rows that exact-name matching can
    never unify.

    Returns ``(left_id, right_id, namespace, external_id)`` tuples with
    ``left_id < right_id`` (UUID ordering), one per colliding pair, deterministic.
    """
    rows = await pool.fetch(
        """
        SELECT eei.namespace, eei.external_id,
               array_agg(DISTINCT eei.entity_id) AS entity_ids
        FROM entity_external_ids eei
        JOIN entities e ON e.id = eei.entity_id
        WHERE e.is_deprecated = false
        GROUP BY eei.namespace, eei.external_id
        HAVING count(DISTINCT eei.entity_id) > 1
        """,
    )
    pairs: list[tuple[uuid.UUID, uuid.UUID, str, str]] = []
    for r in rows:
        ids = sorted(uuid.UUID(str(i)) for i in r["entity_ids"])
        namespace = str(r["namespace"])
        external_id = str(r["external_id"])
        # Chain every entity onto the lowest-UUID survivor: (ids[0], ids[k]).
        for other in ids[1:]:
            left, right = ordered_pair(ids[0], other)
            pairs.append((left, right, namespace, external_id))
    return pairs


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

    # Bump the surviving target so the query layer's freshness signal
    # (getEntity reads entities.last_updated_at) reflects the merge.
    await pool.execute(
        "UPDATE entities SET last_updated_at = now(), updated_at = now() WHERE id = $1",
        target_id,
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

    # ── 4. External-ID collision → high-confidence merge candidates ───────────
    # Two live entities sharing an identical (namespace, external_id) are
    # unambiguously the same real-world thing.  Emit a 'merge' candidate at the
    # exact-match confidence floor; step 6 then auto-merges it.  This is the
    # principled, conservative merge trigger — name/embedding similarity alone
    # never auto-merges (those stay needs_review).
    for left_id, right_id, namespace, external_id in await find_external_id_collisions(pool):
        try:
            await _upsert_resolution_candidate(
                pool,
                left_id=left_id,
                right_id=right_id,
                proposed_decision="merge",
                confidence=EXACT_MATCH_CONFIDENCE,
                matching_signals=[{
                    "type": "external_id",
                    "namespace": namespace,
                    "external_id": external_id,
                    "weight": 1.0,
                }],
                negative_signals=[],
                decision_source="external_id_match",
                evidence_document_ids=[],
            )
            counters["candidates_created"] += 1
        except Exception as exc:
            _log.warning(
                "resolve_entities: failed to create external-id merge candidate "
                "for %s/%s: %s", namespace, external_id, exc,
            )

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
            # Re-parent every mention that pointed at the deprecated (source) entity
            # onto the surviving (target) entity so mention→entity provenance never
            # dangles to a deprecated row.  (mentions has no updated_at column —
            # resolved_at already records the link time.)
            await pool.execute(
                "UPDATE mentions SET entity_id = $1 WHERE entity_id = $2",
                left_id,
                right_id,
            )
        except Exception as exc:
            _log.warning(
                "resolve_entities: merge failed for candidate %s: %s", candidate_id, exc
            )

    _log.info("resolve_entities: %s", counters)
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# derive_relationships
# ──────────────────────────────────────────────────────────────────────────────


async def _resolve_claim_entity_id(
    pool: Any,
    *,
    claim_id: uuid.UUID,
    text: str,
    entity_id_col: uuid.UUID | None,
) -> uuid.UUID | None:
    """Return the best entity UUID for a claim subject/object.

    Preference order:
    1. ``entity_id_col`` — already resolved on the claim row.
    2. Look up a resolved mention whose ``text_span`` matches *text* and whose
       document is in the claim's ``source_document_ids``.
    3. ``None`` — caller must skip this claim end.
    """
    if entity_id_col is not None:
        return entity_id_col

    # Try to find a matching mention (case-insensitive) linked to the same claim's
    # source documents.
    row = await pool.fetchrow(
        """
        SELECT m.entity_id
        FROM mentions m
        JOIN claims c ON c.source_document_ids @> ARRAY[m.document_id]
        WHERE c.id = $1
          AND lower(m.text_span) = lower($2)
          AND m.resolution_status = 'resolved'
          AND m.entity_id IS NOT NULL
        ORDER BY m.extraction_confidence DESC
        LIMIT 1
        """,
        claim_id,
        text,
    )
    if row:
        return uuid.UUID(str(row["entity_id"]))
    return None


async def derive_relationships(
    *,
    claim_id: str,
    pool: Any,
) -> dict[str, int]:
    """Derive typed temporal relationships from an extracted claim.

    Algorithm
    ---------
    1. Load the claim row.  Skip if confidence < MIN_CLAIM_CONFIDENCE or status
       is not 'active'.
    2. Resolve subject and object entity UUIDs:
       - Use ``subject_entity_id`` / ``object_entity_id`` if already set.
       - Otherwise look up a resolved mention with a matching ``text_span``
         in the same document(s).
       - Skip the claim if either end cannot be resolved to a canonical entity
         (a relationship without both ends is meaningless).
    3. Map the claim's free-text predicate to a seeded relationship type_id via
       ``_map_predicate_to_type``.  Skip if no type maps (no fabricated types).
    4. Upsert the relationship.  Idempotent key:
       ``(type_id, subject_entity_id, object_entity_id, valid_from)``.
       - ``ON CONFLICT … DO UPDATE`` refreshes confidence + claim_ids when the
         same triple is submitted again (e.g. a re-run after new evidence).
       - ``valid_from`` NULL is part of the key (two NULLs are treated as equal
         by the application-layer dedup; the DB uses a partial unique index
         workaround via the ON CONFLICT clause below).

    Provenance
    ----------
    ``relationships.claim_ids`` always lists the originating claim UUID.
    ``relationships.source_document_ids`` is copied from the claim row.

    Idempotency
    -----------
    The combination (type_id, subject_entity_id, object_entity_id, valid_from)
    uniquely identifies the relationship assertion.  Re-running with the same
    claim yields no new row.

    Args:
        claim_id: UUID string of the claim to process.
        pool: asyncpg connection pool.

    Returns:
        Dict with counters: ``relationships_written``, ``relationships_skipped``.

    Raises:
        ValueError: If *claim_id* is not a valid UUID.
    """
    _log.info("derive_relationships: claim_id=%s", claim_id)

    claim_uuid = uuid.UUID(claim_id)

    counters: dict[str, int] = {
        "relationships_written": 0,
        "relationships_skipped": 0,
    }

    # ── 1. Load claim ─────────────────────────────────────────────────────────
    row = await pool.fetchrow(
        """
        SELECT id, subject_text, predicate, object_text,
               subject_entity_id, object_entity_id,
               valid_from, valid_until,
               extraction_confidence, source_document_ids, status
        FROM claims
        WHERE id = $1
        """,
        claim_uuid,
    )
    if row is None:
        _log.warning("derive_relationships: claim %s not found", claim_id)
        counters["relationships_skipped"] += 1
        return counters

    if str(row["status"]) != "active":
        _log.info(
            "derive_relationships: claim %s status=%s — skipping", claim_id, row["status"]
        )
        counters["relationships_skipped"] += 1
        return counters

    confidence = float(row["extraction_confidence"])
    if confidence < MIN_CLAIM_CONFIDENCE:
        _log.info(
            "derive_relationships: claim %s confidence=%.2f < %.2f — skipping",
            claim_id, confidence, MIN_CLAIM_CONFIDENCE,
        )
        counters["relationships_skipped"] += 1
        return counters

    # ── 2. Resolve entity IDs ─────────────────────────────────────────────────
    subject_entity_id = await _resolve_claim_entity_id(
        pool,
        claim_id=claim_uuid,
        text=str(row["subject_text"]),
        entity_id_col=(
            uuid.UUID(str(row["subject_entity_id"])) if row["subject_entity_id"] else None
        ),
    )
    object_entity_id = await _resolve_claim_entity_id(
        pool,
        claim_id=claim_uuid,
        text=str(row["object_text"]),
        entity_id_col=(
            uuid.UUID(str(row["object_entity_id"])) if row["object_entity_id"] else None
        ),
    )

    if subject_entity_id is None or object_entity_id is None:
        _log.info(
            "derive_relationships: claim %s — subject=%s object=%s, "
            "one or both entity ends unresolved — skipping",
            claim_id,
            subject_entity_id,
            object_entity_id,
        )
        counters["relationships_skipped"] += 1
        return counters

    if subject_entity_id == object_entity_id:
        _log.info(
            "derive_relationships: claim %s — subject == object entity %s "
            "(self-relationship) — skipping",
            claim_id,
            subject_entity_id,
        )
        counters["relationships_skipped"] += 1
        return counters

    # ── 3. Map predicate → relationship type ──────────────────────────────────
    predicate = str(row["predicate"])
    type_id = _map_predicate_to_type(predicate)
    if type_id is None:
        _log.info(
            "derive_relationships: claim %s predicate=%r — no type mapping — skipping",
            claim_id,
            predicate,
        )
        counters["relationships_skipped"] += 1
        return counters

    valid_from = row["valid_from"]   # datetime | None
    valid_until = row["valid_until"]  # datetime | None

    # Raw list from asyncpg may be strings or UUIDs — normalise to UUID list.
    raw_doc_ids: list[Any] = list(row["source_document_ids"] or [])
    source_document_ids: list[uuid.UUID] = [
        uuid.UUID(str(d)) for d in raw_doc_ids
    ]

    # ── 4. Upsert relationship ────────────────────────────────────────────────
    # Idempotent key: (type_id, subject_entity_id, object_entity_id, valid_from).
    # PostgreSQL UNIQUE constraints treat two NULLs as distinct, so we use
    # an application-layer ON CONFLICT that matches on the IS-NULL variant
    # via a partial unique index.  Since the schema does not have such an index
    # yet, we use a SELECT + conditional INSERT pattern which is safe for the
    # single-writer pipeline.  The DB has no unique constraint on this tuple,
    # so we check first, then insert only if absent.
    existing = await pool.fetchrow(
        """
        SELECT id, claim_ids, source_document_ids, confidence
        FROM relationships
        WHERE type_id = $1
          AND subject_entity_id = $2
          AND object_entity_id = $3
          AND (
              ($4::timestamptz IS NULL AND valid_from IS NULL)
              OR valid_from = $4::timestamptz
          )
          AND is_deprecated = false
        LIMIT 1
        """,
        type_id,
        subject_entity_id,
        object_entity_id,
        valid_from,
    )

    if existing is not None:
        # Relationship already recorded — merge claim_ids (idempotent union).
        existing_claim_ids: list[uuid.UUID] = [
            uuid.UUID(str(c)) for c in (existing["claim_ids"] or [])
        ]
        if claim_uuid not in existing_claim_ids:
            merged_claim_ids = [*existing_claim_ids, claim_uuid]
            existing_doc_ids: list[uuid.UUID] = [
                uuid.UUID(str(d)) for d in (existing["source_document_ids"] or [])
            ]
            merged_doc_ids = list(dict.fromkeys(existing_doc_ids + source_document_ids))
            new_confidence = max(float(existing["confidence"]), confidence)
            await pool.execute(
                """
                UPDATE relationships
                SET claim_ids           = $1,
                    source_document_ids = $2,
                    confidence          = $3,
                    updated_at          = now()
                WHERE id = $4
                """,
                merged_claim_ids,
                merged_doc_ids,
                round(new_confidence, 2),
                uuid.UUID(str(existing["id"])),
            )
            _log.debug(
                "derive_relationships: claim %s — updated existing relationship %s "
                "(type=%s, added claim_id)",
                claim_id,
                existing["id"],
                type_id,
            )
        else:
            _log.debug(
                "derive_relationships: claim %s — relationship already recorded (no change)",
                claim_id,
            )
        counters["relationships_written"] += 1
        return counters

    # New relationship
    rel_id = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO relationships (
            id, type_id,
            subject_entity_id, object_entity_id,
            valid_from, valid_until,
            recorded_at,
            confidence,
            source_document_ids,
            claim_ids,
            is_active, is_deprecated
        ) VALUES (
            $1, $2,
            $3, $4,
            $5, $6,
            now(),
            $7,
            $8,
            $9,
            true, false
        )
        """,
        rel_id,
        type_id,
        subject_entity_id,
        object_entity_id,
        valid_from,
        valid_until,
        round(confidence, 2),
        source_document_ids,
        [claim_uuid],
    )
    counters["relationships_written"] += 1
    _log.info(
        "derive_relationships: claim %s → relationship %s "
        "(type=%s, subject=%s, object=%s)",
        claim_id,
        rel_id,
        type_id,
        subject_entity_id,
        object_entity_id,
    )
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# write_fact_versions
# ──────────────────────────────────────────────────────────────────────────────


async def _build_entity_payload(pool: Any, entity_id: uuid.UUID) -> dict[str, Any]:
    """Build a canonical payload snapshot for an entity's current state.

    The payload is the stable, deterministic representation used for
    bitemporal diffing.  It must include all facts that matter for query-layer
    consumers (type, name, external IDs, active relationship count).

    Keys
    ----
    ``type_id``, ``canonical_name``, ``description``, ``external_ids``
    (sorted list of ``{namespace, external_id}``),
    ``active_relationship_count`` — deterministic integer.
    """
    entity_row = await pool.fetchrow(
        """
        SELECT type_id, canonical_name, description, metadata
        FROM entities
        WHERE id = $1 AND is_deprecated = false
        """,
        entity_id,
    )
    if entity_row is None:
        raise ValueError(f"entity {entity_id} not found or deprecated")

    ext_id_rows = await pool.fetch(
        """
        SELECT namespace, external_id
        FROM entity_external_ids
        WHERE entity_id = $1
        ORDER BY namespace, external_id
        """,
        entity_id,
    )
    external_ids = [
        {"namespace": str(r["namespace"]), "external_id": str(r["external_id"])}
        for r in ext_id_rows
    ]

    rel_count_row = await pool.fetchrow(
        """
        SELECT count(*) AS cnt
        FROM relationships
        WHERE (subject_entity_id = $1 OR object_entity_id = $1)
          AND is_active = true
          AND is_deprecated = false
        """,
        entity_id,
    )
    rel_count = int(rel_count_row["cnt"]) if rel_count_row else 0

    return {
        "type_id": str(entity_row["type_id"]),
        "canonical_name": str(entity_row["canonical_name"]),
        "description": entity_row["description"],
        "external_ids": external_ids,
        "active_relationship_count": rel_count,
    }


def payload_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Stable equality check for two entity payload dicts.

    Compares via canonical JSON serialisation (sorted keys) so that
    ordering differences in lists don't falsely trigger a new version.
    ``external_ids`` is already sorted by ``_build_entity_payload``.
    """
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# Internal alias
_payload_equal = payload_equal


# ──────────────────────────────────────────────────────────────────────────────
# link_claim_entities
# ──────────────────────────────────────────────────────────────────────────────

# Actor tag written into claims.metadata.claim_entity_links provenance.
_LINK_ACTOR = "link_claim_entities_v1"

# Conservative confidence floors for each link method.
# Claim entity linking is NOT entity merging — a wrong link corrupts the
# relationship graph (W7 produces a false triple).  Be MORE conservative here
# than W6 entity resolution: we only write a link when we are highly confident.
#
# Exact mention-span overlap (same doc, same text_span): very high confidence.
LINK_EXACT_MENTION_CONFIDENCE = 0.90
# Alias / exact-name lexical match across the entity table: high confidence.
LINK_EXACT_NAME_CONFIDENCE = 0.85
# Embedding cosine similarity: minimum confidence to record a link.
# Only fire when distance is well below the W6 COSINE_MERGE_THRESHOLD (0.15)
# so we stay strictly more conservative than entity resolution.
LINK_EMBEDDING_MIN_CONFIDENCE = 0.80
# Cosine distance threshold for claim entity linking (stricter than W6).
LINK_COSINE_THRESHOLD = 0.10  # distance ≤ this → link; above → NULL (conservative)


async def _link_one_end(
    pool: Any,
    *,
    claim_id: uuid.UUID,
    surface_text: str,
    source_document_ids: list[uuid.UUID],
    embeddings: Any | None,
) -> tuple[uuid.UUID | None, float, str]:
    """Find the best resolved entity for a claim subject or object surface text.

    Returns ``(entity_id, confidence, method)`` where *entity_id* may be ``None``
    if no confident link can be found.  Caller must respect the NULL — never
    fabricate a link.

    Resolution order (most → least precise):
    1. Exact mention-span overlap: find a resolved ``mentions`` row whose
       ``text_span`` matches *surface_text* (case-insensitive) and whose
       ``document_id`` is in ``source_document_ids``.
    2. Alias / exact canonical-name match: look up any live entity by
       exact normalized name or alias, type-agnostic (claim ends can be any type).
    3. Embedding cosine similarity against entity_embeddings: only if distance
       ≤ ``LINK_COSINE_THRESHOLD`` (0.10 — stricter than W6's 0.15).
    """
    norm_text = normalize_name(surface_text)

    # ── 1. Exact mention-span overlap ─────────────────────────────────────────
    if source_document_ids:
        row = await pool.fetchrow(
            """
            SELECT m.entity_id
            FROM mentions m
            WHERE m.document_id = ANY($1)
              AND lower(m.text_span) = $2
              AND m.resolution_status = 'resolved'
              AND m.entity_id IS NOT NULL
            ORDER BY m.extraction_confidence DESC
            LIMIT 1
            """,
            source_document_ids,
            norm_text,
        )
        if row and row["entity_id"]:
            # Confirm entity still live (not deprecated by a later merge).
            live = await pool.fetchrow(
                "SELECT id FROM entities WHERE id = $1 AND is_deprecated = false",
                uuid.UUID(str(row["entity_id"])),
            )
            if live:
                return (
                    uuid.UUID(str(row["entity_id"])),
                    LINK_EXACT_MENTION_CONFIDENCE,
                    "exact_mention_span",
                )

    # ── 2. Alias / exact canonical-name match (type-agnostic) ────────────────
    # Match on exact case-folded canonical name OR alias across all live
    # entities.  This is type-agnostic (claim ends can be any type), so unlike
    # W6's name match — which is scoped by type_id and therefore unambiguous —
    # the same surface form can resolve to two genuinely distinct entities
    # (e.g. "Apple" the company vs. "apple" the concept).  Picking one
    # arbitrarily would be a false link, which corrupts the relationship graph
    # exactly as a false entity merge would.  So we fetch the DISTINCT set of
    # live entity ids that match (capped at 2) and only link when there is
    # EXACTLY ONE — true ambiguity is left NULL (conservative), never guessed.
    name_rows = await pool.fetch(
        """
        SELECT DISTINCT entity_id FROM (
            SELECT id AS entity_id
            FROM entities
            WHERE lower(canonical_name) = $1
              AND is_deprecated = false
            UNION
            SELECT e.id AS entity_id
            FROM entity_aliases ea
            JOIN entities e ON e.id = ea.entity_id
            WHERE lower(ea.alias) = $1
              AND e.is_deprecated = false
        ) matches
        LIMIT 2
        """,
        norm_text,
    )
    if len(name_rows) == 1:
        return (
            uuid.UUID(str(name_rows[0]["entity_id"])),
            LINK_EXACT_NAME_CONFIDENCE,
            "exact_name",
        )
    if len(name_rows) > 1:
        _log.debug(
            "_link_one_end: ambiguous exact-name match for %r "
            "(%d distinct live entities) — leaving NULL",
            surface_text,
            len(name_rows),
        )

    # ── 3. Embedding cosine similarity ────────────────────────────────────────
    if embeddings is not None:
        try:
            vectors = await embeddings.embed([surface_text])
            if vectors:
                vec = vectors[0]
                vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
                emb_rows = await pool.fetch(
                    """
                    SELECT ee.entity_id, (ee.embedding <=> $1::halfvec) AS distance
                    FROM entity_embeddings ee
                    JOIN entities e ON e.id = ee.entity_id
                    WHERE e.is_deprecated = false
                      AND ee.model = $2
                    ORDER BY ee.embedding <=> $1::halfvec
                    LIMIT 1
                    """,
                    vec_literal,
                    embeddings.model,
                )
                if emb_rows:
                    best_dist = float(emb_rows[0]["distance"])
                    if best_dist <= LINK_COSINE_THRESHOLD:
                        confidence = round(
                            LINK_EMBEDDING_MIN_CONFIDENCE * (1.0 - best_dist), 2
                        )
                        return (
                            uuid.UUID(str(emb_rows[0]["entity_id"])),
                            confidence,
                            "embedding_cosine",
                        )
        except Exception as exc:
            _log.debug("_link_one_end: embedding lookup failed for %r: %s", surface_text, exc)

    return (None, 0.0, "none")


async def link_claim_entities(
    *,
    pool: Any,
    embeddings: Any | None = None,
    batch_size: int = 200,
    min_confidence: float | None = None,
) -> dict[str, int]:
    """Link claim subject/object surface text to resolved canonical entities.

    This step bridges W3 (claims) → W6 (resolved entities) → W7 (relationships).
    W3 leaves ``claims.subject_entity_id`` / ``claims.object_entity_id`` NULL
    because the LLM's claim surface form often differs from the NER mention span
    that created the entity (e.g. ``"PR #15589"`` vs. ``"PR [#15589](…/pull/…)"``).
    W7's ``derive_relationships`` skip-not-fabricate contract means almost all real
    claims produce zero relationships without this linking step.

    Algorithm
    ---------
    For each active claim with at least one NULL entity end:
    1. **Exact mention-span overlap** — find a resolved ``mentions`` row whose
       ``text_span`` matches the claim's subject or object text (case-insensitive)
       and whose ``document_id`` is in the claim's ``source_document_ids``.
       Confidence: ``LINK_EXACT_MENTION_CONFIDENCE`` (0.90).
    2. **Alias / exact canonical-name** — look up any live entity by exact
       normalized canonical name or alias, type-agnostic.
       Confidence: ``LINK_EXACT_NAME_CONFIDENCE`` (0.85).
    3. **Embedding cosine similarity** — embed the surface text and search
       ``entity_embeddings``; only link when distance ≤ ``LINK_COSINE_THRESHOLD``
       (0.10 — stricter than W6's 0.15).
       Confidence: scaled by ``LINK_EMBEDDING_MIN_CONFIDENCE * (1 - distance)``.

    If no method produces a confident link, the end is left NULL.
    **Never fabricate a link — a wrong link corrupts the relationship graph.**

    Idempotency
    -----------
    - If an entity end is already set AND the existing provenance confidence is ≥
      the new candidate's confidence, the link is left untouched (no churn).
    - If the new candidate is higher confidence (e.g. from a fresh embedding pass),
      the link is updated and provenance replaced.
    - Re-running on a claim with both ends already linked at equal or higher
      confidence is a no-op (no DB write).

    Provenance
    ----------
    Every link is recorded in ``claims.metadata`` under ``claim_entity_links``:
    ``{"subject": {"method": ..., "confidence": ..., "linked_by": ...},
       "object":  {"method": ..., "confidence": ..., "linked_by": ...}}``.

    Args:
        pool: asyncpg connection pool.
        embeddings: Optional EmbeddingsPort adapter for similarity-based linking.
            When ``None``, only exact-mention and lexical/alias methods run.
        batch_size: Maximum number of claims to process per call.
        min_confidence: Minimum confidence to write a link (default: uses
            ``LINK_EMBEDDING_MIN_CONFIDENCE`` as the floor for embedding links;
            exact matches always write).

    Returns:
        Dict with counters:
        ``claims_loaded``, ``subject_linked``, ``object_linked``,
        ``subject_skipped``, ``object_skipped``, ``claims_updated``.
    """
    _log.info(
        "link_claim_entities: batch_size=%d embeddings=%s",
        batch_size,
        embeddings is not None,
    )

    counters: dict[str, int] = {
        "claims_loaded": 0,
        "subject_linked": 0,
        "object_linked": 0,
        "subject_skipped": 0,
        "object_skipped": 0,
        "claims_updated": 0,
    }

    # ── 1. Load active claims with at least one NULL entity end ───────────────
    claims = await pool.fetch(
        """
        SELECT id, subject_text, object_text,
               subject_entity_id, object_entity_id,
               source_document_ids, extraction_confidence,
               metadata
        FROM claims
        WHERE status = 'active'
          AND (subject_entity_id IS NULL OR object_entity_id IS NULL)
        ORDER BY extraction_confidence DESC, created_at
        LIMIT $1
        """,
        batch_size,
    )

    counters["claims_loaded"] = len(claims)
    if not claims:
        _log.info("link_claim_entities: no unlinked claims found")
        return counters

    _log.info("link_claim_entities: loaded %d claims with unlinked ends", len(claims))

    for row in claims:
        claim_id = uuid.UUID(str(row["id"]))
        subject_text = str(row["subject_text"] or "").strip()
        object_text = str(row["object_text"] or "").strip()
        raw_doc_ids: list[Any] = list(row["source_document_ids"] or [])
        source_document_ids: list[uuid.UUID] = [uuid.UUID(str(d)) for d in raw_doc_ids]

        # Load existing metadata (preserve other keys).
        existing_meta_raw = row["metadata"]
        if isinstance(existing_meta_raw, str):
            try:
                existing_meta: dict[str, Any] = json.loads(existing_meta_raw)
            except Exception:
                existing_meta = {}
        elif isinstance(existing_meta_raw, dict):
            existing_meta = dict(existing_meta_raw)
        else:
            existing_meta = {}

        link_provenance: dict[str, Any] = dict(
            existing_meta.get("claim_entity_links", {})
        )

        new_subject_id: uuid.UUID | None = (
            uuid.UUID(str(row["subject_entity_id"]))
            if row["subject_entity_id"]
            else None
        )
        new_object_id: uuid.UUID | None = (
            uuid.UUID(str(row["object_entity_id"]))
            if row["object_entity_id"]
            else None
        )

        subject_changed = False
        object_changed = False

        # ── 2a. Link subject end if NULL ──────────────────────────────────────
        if new_subject_id is None and subject_text:
            entity_id, confidence, method = await _link_one_end(
                pool,
                claim_id=claim_id,
                surface_text=subject_text,
                source_document_ids=source_document_ids,
                embeddings=embeddings,
            )
            if entity_id is not None:
                # Idempotency: only write if improving or new.
                existing_prov = link_provenance.get("subject", {})
                existing_conf = float(existing_prov.get("confidence", 0.0))
                if confidence >= existing_conf:
                    new_subject_id = entity_id
                    link_provenance["subject"] = {
                        "method": method,
                        "confidence": round(confidence, 3),
                        "linked_by": _LINK_ACTOR,
                    }
                    subject_changed = True
                    counters["subject_linked"] += 1
                    _log.debug(
                        "link_claim_entities: claim %s subject %r → entity %s "
                        "(method=%s conf=%.3f)",
                        claim_id, subject_text, entity_id, method, confidence,
                    )
            else:
                counters["subject_skipped"] += 1
                _log.debug(
                    "link_claim_entities: claim %s subject %r — no confident link",
                    claim_id, subject_text,
                )

        # ── 2b. Link object end if NULL ───────────────────────────────────────
        if new_object_id is None and object_text:
            entity_id, confidence, method = await _link_one_end(
                pool,
                claim_id=claim_id,
                surface_text=object_text,
                source_document_ids=source_document_ids,
                embeddings=embeddings,
            )
            if entity_id is not None:
                existing_prov = link_provenance.get("object", {})
                existing_conf = float(existing_prov.get("confidence", 0.0))
                if confidence >= existing_conf:
                    new_object_id = entity_id
                    link_provenance["object"] = {
                        "method": method,
                        "confidence": round(confidence, 3),
                        "linked_by": _LINK_ACTOR,
                    }
                    object_changed = True
                    counters["object_linked"] += 1
                    _log.debug(
                        "link_claim_entities: claim %s object %r → entity %s "
                        "(method=%s conf=%.3f)",
                        claim_id, object_text, entity_id, method, confidence,
                    )
            else:
                counters["object_skipped"] += 1
                _log.debug(
                    "link_claim_entities: claim %s object %r — no confident link",
                    claim_id, object_text,
                )

        # ── 3. Persist updated entity links ───────────────────────────────────
        if subject_changed or object_changed:
            updated_meta = {**existing_meta, "claim_entity_links": link_provenance}
            try:
                await pool.execute(
                    """
                    UPDATE claims
                    SET subject_entity_id = $1,
                        object_entity_id  = $2,
                        metadata          = $3::jsonb,
                        updated_at        = now()
                    WHERE id = $4
                      AND status = 'active'
                    """,
                    new_subject_id,
                    new_object_id,
                    json.dumps(updated_meta),
                    claim_id,
                )
                counters["claims_updated"] += 1
            except Exception as exc:
                _log.warning(
                    "link_claim_entities: DB update failed for claim %s: %s",
                    claim_id, exc,
                )

    _log.info("link_claim_entities: %s", counters)
    return counters


async def write_fact_versions(
    *,
    entity_id: str,
    pool: Any,
) -> dict[str, int]:
    """Write append-only bitemporal fact version records for an entity.

    Bitemporal model
    ----------------
    * ``valid_from`` / ``valid_until`` — when the fact is true **in the world**.
      For entity-state snapshots this is the wall-clock interval during which
      the recorded state was known to be current.
    * ``recorded_at`` — when Intercal recorded this version (immutable, set at
      insert).

    These axes are independent: a historical fact may be recorded today; a fact
    recorded today may later be superseded without touching the original row.

    Append-only invariant
    ---------------------
    **Never UPDATE or DELETE a fact_versions row.**  Corrections insert a new
    row and mark the superseded row via ``superseded_by_id`` + ``superseded_at``
    + ``is_current = false``.  The old row remains as historical evidence.

    Algorithm
    ---------
    1. Load the entity and build a canonical payload snapshot.
    2. Load the current fact version (``is_current = true``) for this entity,
       if any.
    3. If the payload is identical to the current version → skip (idempotent).
    4. If different (or no current version exists):
       a. Insert a new fact_versions row (``is_current = true``).
       b. If a prior current version exists, close it:
          ``is_current = false``, ``valid_until = now()``,
          ``superseded_by_id = <new_id>``, ``superseded_at = now()``.
       The old row is **never deleted or updated** beyond this closing step —
       the modification of ``is_current``, ``valid_until``, and
       ``superseded_by_id`` on the old row is the minimum needed to close the
       interval while preserving the history.

    Provenance
    ----------
    ``fact_versions.claim_ids`` is populated from all active claims whose
    resolved entity matches this entity (subject or object).
    ``fact_versions.source_document_ids`` is the union of those claims'
    source_document_ids.

    Args:
        entity_id: UUID string of the entity to version.
        pool: asyncpg connection pool.

    Returns:
        Dict with counters: ``versions_written``, ``versions_skipped``.

    Raises:
        ValueError: If *entity_id* is not found or is deprecated.
    """
    _log.info("write_fact_versions: entity_id=%s", entity_id)

    entity_uuid = uuid.UUID(entity_id)

    counters: dict[str, int] = {
        "versions_written": 0,
        "versions_skipped": 0,
    }

    # ── 1. Build payload snapshot ─────────────────────────────────────────────
    payload = await _build_entity_payload(pool, entity_uuid)

    # ── 2. Load current fact version ─────────────────────────────────────────
    current_row = await pool.fetchrow(
        """
        SELECT id, payload, valid_from, recorded_at
        FROM fact_versions
        WHERE fact_subject_type = 'entity'
          AND fact_subject_id = $1
          AND is_current = true
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        entity_uuid,
    )

    if current_row is not None:
        existing_payload: dict[str, Any]
        raw = current_row["payload"]
        if isinstance(raw, str):
            existing_payload = json.loads(raw)
        elif isinstance(raw, dict):
            existing_payload = raw
        else:
            existing_payload = {}

        if _payload_equal(existing_payload, payload):
            _log.debug(
                "write_fact_versions: entity %s payload unchanged — skipping",
                entity_id,
            )
            counters["versions_skipped"] += 1
            return counters

    # ── 3. Gather provenance ──────────────────────────────────────────────────
    claim_rows = await pool.fetch(
        """
        SELECT id, source_document_ids
        FROM claims
        WHERE (subject_entity_id = $1 OR object_entity_id = $1)
          AND status = 'active'
        """,
        entity_uuid,
    )
    claim_ids: list[uuid.UUID] = [uuid.UUID(str(r["id"])) for r in claim_rows]
    doc_ids: list[uuid.UUID] = list(
        dict.fromkeys(
            uuid.UUID(str(d))
            for r in claim_rows
            for d in (r["source_document_ids"] or [])
        )
    )
    # Confidence: mean of claim confidences (or 0.5 as default).
    confidence_rows = await pool.fetch(
        """
        SELECT extraction_confidence FROM claims
        WHERE id = ANY($1) AND status = 'active'
        """,
        claim_ids,
    ) if claim_ids else []
    if confidence_rows:
        avg_confidence = round(
            sum(float(r["extraction_confidence"]) for r in confidence_rows)
            / len(confidence_rows),
            2,
        )
    else:
        avg_confidence = 0.50

    # ── 4a. Insert new fact version ───────────────────────────────────────────
    new_id = uuid.uuid4()
    now: datetime = datetime.now(UTC)
    await pool.execute(
        """
        INSERT INTO fact_versions (
            id,
            fact_subject_type,
            fact_subject_id,
            payload,
            valid_from, valid_until,
            recorded_at,
            source_document_ids,
            claim_ids,
            confidence,
            is_current,
            produced_by
        ) VALUES (
            $1, 'entity', $2,
            $3::jsonb,
            $4, NULL,
            $5,
            $6,
            $7,
            $8,
            true,
            $9
        )
        """,
        new_id,
        entity_uuid,
        json.dumps(payload),
        now,         # valid_from = now (state snapshot time)
        now,         # recorded_at = now
        doc_ids,
        claim_ids,
        avg_confidence,
        _W7_ACTOR,
    )
    _log.info(
        "write_fact_versions: entity %s → new fact_version %s",
        entity_id,
        new_id,
    )

    # ── 4b. Close prior version (append-only) ─────────────────────────────────
    # The old row is NOT deleted.  We only close its validity interval and point
    # superseded_by_id at the new row.  The old row is the history record.
    if current_row is not None:
        old_id = uuid.UUID(str(current_row["id"]))
        await pool.execute(
            """
            UPDATE fact_versions
            SET is_current       = false,
                valid_until      = $1,
                superseded_by_id = $2,
                superseded_at    = $1
            WHERE id = $3
            """,
            now,
            new_id,
            old_id,
        )
        _log.debug(
            "write_fact_versions: closed prior version %s (superseded by %s)",
            old_id,
            new_id,
        )

    counters["versions_written"] += 1
    return counters
