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

W3 scope:
    ``extract_mentions`` — rule-based NER baseline augmented by LLM span
    extraction.  Writes to ``mentions`` with character offsets (source spans)
    into ``cleaned_text`` / ``document_chunks``.

    ``extract_claims`` — LLM-driven structured extraction validated against
    CLAIMS_SCHEMA.  Writes to ``claims``, ``claim_evidence`` with source spans
    that trace each claim back to its chunk and character range.

    Entity resolution (W6/W7/W8) and relationship derivation are deferred
    with explicit ``NotImplementedError`` stubs.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

_log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# JSON Schemas for structured LLM extraction
# ──────────────────────────────────────────────────────────────────────────────

# Mention extraction schema — the LLM returns a list of spans.
# Each span must carry:
#   text_span    — raw text of the mention as it appears in the chunk
#   proposed_type — entity category (PERSON/ORG/GPE/ROLE/PRODUCT/CONCEPT/EVENT/LAW/SOURCE/ARTIFACT)
#   char_offset_start — start character offset within the chunk text (0-based)
#   char_offset_end   — exclusive end offset
#   confidence   — extraction confidence 0.0-1.0
MENTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["mentions"],
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "text_span",
                    "proposed_type",
                    "char_offset_start",
                    "char_offset_end",
                    "confidence",
                ],
                "properties": {
                    "text_span": {"type": "string"},
                    "proposed_type": {
                        "type": "string",
                        "enum": [
                            "PERSON",
                            "ORG",
                            "GPE",
                            "ROLE",
                            "PRODUCT",
                            "CONCEPT",
                            "EVENT",
                            "LAW",
                            "SOURCE",
                            "ARTIFACT",
                        ],
                    },
                    "char_offset_start": {"type": "integer"},
                    "char_offset_end": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}

# Claims extraction schema — the LLM returns a list of atomic factual assertions.
# Each claim carries:
#   subject_text     — raw text of the subject (entity, person, org, etc.)
#   predicate        — relationship / assertion verb (e.g. "holds_role", "founded")
#   object_text      — raw text of the object
#   normalized_text  — canonical natural-language restatement of the claim
#   qualifiers       — optional additional context (location, manner, units, etc.)
#   valid_from       — ISO 8601 date/datetime when this claim became true (nullable)
#   valid_until      — ISO 8601 date/datetime when it stopped being true (nullable)
#   confidence       — extraction confidence 0.0-1.0
#   char_offset_start — start offset into the chunk text for this claim's primary span
#   char_offset_end   — end offset (exclusive)
CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "subject_text",
                    "predicate",
                    "object_text",
                    "normalized_text",
                    "confidence",
                    "char_offset_start",
                    "char_offset_end",
                ],
                "properties": {
                    "subject_text": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object_text": {"type": "string"},
                    "normalized_text": {"type": "string"},
                    "qualifiers": {"type": "object"},
                    # Use plain "string" to stay compatible with Gemini response_schema
                    # (which rejects union type arrays like ["string","null"]).
                    # parse_valid_time() treats empty strings and missing keys as None.
                    "valid_from": {"type": "string"},
                    "valid_until": {"type": "string"},
                    "confidence": {"type": "number"},
                    "char_offset_start": {"type": "integer"},
                    "char_offset_end": {"type": "integer"},
                },
            },
        }
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Extractor name constants (stored in mentions.extractor / claims.extractor)
# ──────────────────────────────────────────────────────────────────────────────

EXTRACTOR_RULE = "rule_regex_v1"
EXTRACTOR_LLM = "llm_extract_v1"

# ──────────────────────────────────────────────────────────────────────────────
# Rule-based NER baseline
# ──────────────────────────────────────────────────────────────────────────────

# Simple vocabulary-based regexes for common named entity categories.
# These are intentionally conservative (high precision, lower recall) —
# LLM augmentation fills in what the rules miss.
_NER_RULES: list[tuple[str, str]] = [
    # Wikidata QIDs
    (r"\bQ\d{5,}\b", "SOURCE"),
    # Property IDs
    (r"\bP\d{3,}\b", "CONCEPT"),
    # URLs / DOIs
    (r"https?://\S+", "SOURCE"),
    # Person names: two capitalised words (en)
    (r"\b[A-Z][a-z]{1,20}\s+[A-Z][a-z]{1,20}\b", "PERSON"),
    # Org signals: tokens ending in Inc / Ltd / Corp / Foundation / University / Institute
    (
        r"\b[A-Z][A-Za-z0-9 &\-']{0,40}"
        r"(?:Inc\.?|Ltd\.?|Corp\.?|LLC|Foundation|University|Institute|Association|Organization)\b",
        "ORG",
    ),
    # Country / city heuristic: short all-caps abbreviations (e.g. UK, USA, EU) or
    # proper-noun sequences followed by a geographic indicator
    (r"\b(?:USA|UK|EU|UN|US|UAE|WHO|IMF|NATO|OECD)\b", "GPE"),
]

_COMPILED_NER: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern), entity_type) for pattern, entity_type in _NER_RULES
]


def rule_based_mentions(text: str) -> list[dict[str, Any]]:
    """Apply regex NER rules to *text* and return raw mention dicts.

    Duplicate spans are de-duped (same start+end wins for first match).
    Confidence is fixed at 0.80 for rule-based matches (high-precision rules).
    """
    seen: dict[tuple[int, int], bool] = {}
    results: list[dict[str, Any]] = []
    for pattern, entity_type in _COMPILED_NER:
        for m in pattern.finditer(text):
            key = (m.start(), m.end())
            if key in seen:
                continue
            seen[key] = True
            results.append(
                {
                    "text_span": m.group(0),
                    "proposed_type": entity_type,
                    "char_offset_start": m.start(),
                    "char_offset_end": m.end(),
                    "confidence": 0.80,
                    "extractor": EXTRACTOR_RULE,
                }
            )
    return results


def clamp_confidence(value: Any) -> float:
    """Clamp a confidence value to [0.0, 1.0]."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def safe_int_offset(value: Any) -> int | None:
    """Convert *value* to a non-negative int, or None if invalid."""
    try:
        i = int(value)
        return i if i >= 0 else None
    except (TypeError, ValueError):
        return None


# Whitespace run — used to anchor a span whose internal whitespace differs
# between the chunk text and the document's cleaned_text.
_WS_RUN: re.Pattern[str] = re.compile(r"\s+")


def anchor_span(
    span_text: str,
    *,
    cleaned_text: str,
    region_start: int,
    region_end: int,
    occupied: list[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """Locate *span_text* inside ``cleaned_text`` and return its document offsets.

    This is the provenance anchor.  Chunk offsets cannot be added naively to a
    chunk-local offset to obtain a document offset: ``document_chunks.chunk_text``
    is a re-joined, whitespace-collapsed variant of its source region (the chunker
    strips sentence edges and joins sentences with a single space), so the same
    character index points at different content in ``chunk_text`` versus
    ``cleaned_text``.  Adding offsets therefore drifts wherever the source region
    contained newlines or repeated whitespace — corrupting every persisted span.

    Instead we find the *verbatim span text* within the chunk's known region of
    ``cleaned_text`` (``[region_start:region_end]``), so the returned offsets
    satisfy the only invariant that matters for provenance:
    ``cleaned_text[start:end] == cleaned_text[start:end]`` reconstructs the span.

    Resolution order (most to least precise):
    1. Exact substring match within the chunk's region.
    2. Whitespace-flexible match within the region (handles ``" "`` in chunk_text
       where cleaned_text has ``"\\n"`` / multiple spaces).
    3. Exact, then whitespace-flexible, over the whole document (covers a span the
       LLM lifted across a chunk boundary or lightly paraphrased the spacing of).

    *occupied* — ranges already claimed by earlier candidates *with the same span
    text*.  When a chunk mentions the same entity twice (``"Sam Altman met Sam
    Altman"``), each candidate must anchor to a *distinct* occurrence; otherwise
    both collapse onto the first hit and the second carries a fabricated offset.
    A match overlapping any occupied range is skipped in favour of the next
    occurrence.  Callers pass a per-span accumulator and append the returned range.

    Returns ``None`` when the span cannot be located.  Callers drop such spans
    rather than persist a fabricated offset — a false provenance pointer is
    corruption, a dropped one is merely a missed candidate.
    """
    span_text = span_text.strip()
    if not span_text:
        return None

    text_len = len(cleaned_text)
    lo = max(0, min(region_start, text_len))
    hi = max(lo, min(region_end, text_len))
    taken = occupied or []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < o_end and o_start < end for o_start, o_end in taken)

    def _verbatim(start: int, end: int) -> tuple[int, int] | None:
        idx = cleaned_text.find(span_text, start, end)
        while idx != -1:
            cand = (idx, idx + len(span_text))
            if not _overlaps(*cand):
                return cand
            idx = cleaned_text.find(span_text, idx + 1, end)
        return None

    def _ws_flexible(start: int, end: int) -> tuple[int, int] | None:
        tokens = [re.escape(t) for t in span_text.split()]
        if not tokens:
            return None
        pattern = re.compile(r"\s+".join(tokens))
        pos = start
        while True:
            m = pattern.search(cleaned_text, pos, end)
            if m is None:
                return None
            if not _overlaps(m.start(), m.end()):
                return m.start(), m.end()
            pos = m.start() + 1

    # 1 + 2: within the chunk's region (preferred — keeps the span local to its chunk).
    return (
        _verbatim(lo, hi)
        or _ws_flexible(lo, hi)
        # 3: widen to the full document as a last resort.
        or _verbatim(0, text_len)
        or _ws_flexible(0, text_len)
    )


# ──────────────────────────────────────────────────────────────────────────────
# extract_mentions
# ──────────────────────────────────────────────────────────────────────────────


async def extract_mentions(
    *,
    document_id: str,
    pool: Any,
    llm: Any | None = None,
) -> dict[str, int]:
    """Extract entity mention spans from a normalised source document.

    Reads ``source_documents.cleaned_text`` and ``document_chunks`` for
    *document_id*.  Existing mentions for this document are deleted first
    (idempotent replace-on-retry semantics).

    Steps:
    1. Load ``cleaned_text`` from ``source_documents`` and all chunks from
       ``document_chunks`` (ordered by ``chunk_index``).
    2. Apply rule-based NER baseline per chunk (regex + vocabulary).
    3. Optionally augment with LLM-based span extraction via
       ``llm.extract_structured(MENTIONS_SCHEMA, chunk_text)`` — returns
       a schema-validated ``StructuredResult``; token usage is logged.
    4. Merge rule + LLM candidates; deduplicate by (char_offset_start,
       char_offset_end) within each chunk (LLM wins over rule for the same
       span).  Convert chunk-local offsets to document-level offsets using
       ``chunk.char_offset_start``.
    5. Clamp confidence to [0.0, 1.0]; skip spans with invalid offsets.
    6. Delete existing mention rows, then bulk-insert validated candidates
       into ``mentions`` with chunk_id and document-level character offsets.

    Args:
        document_id: UUID of the normalised source document.
        pool: asyncpg connection pool.
        llm: Optional LlmPort adapter.  When ``None``, only the rule baseline
            is applied (no API spend).

    Returns:
        Dict with counters: ``chunks_processed``, ``rule_mentions``,
        ``llm_mentions``, ``persisted``.

    Raises:
        ValueError: If the document row is missing or has no normalised text.
    """
    _log.info("extract_mentions: document_id=%s llm=%s", document_id, llm is not None)

    doc_id = uuid.UUID(document_id)

    # ── 1. Load document + chunks ─────────────────────────────────────────────
    row = await pool.fetchrow(
        "SELECT id, cleaned_text, citation_only FROM source_documents WHERE id = $1",
        doc_id,
    )
    if row is None:
        raise ValueError(f"source_document not found: {document_id!r}")

    cleaned_text: str = row["cleaned_text"] or ""

    chunks = await pool.fetch(
        """
        SELECT id, chunk_index, chunk_text, char_offset_start, char_offset_end
        FROM document_chunks
        WHERE document_id = $1
        ORDER BY chunk_index
        """,
        doc_id,
    )

    # If no chunks, fall back to treating the whole document text as one
    # virtual chunk so we still extract from un-chunked docs.
    if not chunks and cleaned_text.strip():
        _log.info(
            "extract_mentions: no chunks found for document %s; using cleaned_text as single span",
            document_id,
        )
        # Use a synthetic chunk-like structure (no real DB id).
        virtual_chunks = [
            {
                "id": None,
                "chunk_index": 0,
                "chunk_text": cleaned_text,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned_text),
            }
        ]
    else:
        virtual_chunks = [dict(c) for c in chunks]

    # ── 2+3. Per-chunk rule + LLM extraction ─────────────────────────────────
    all_candidates: list[dict[str, Any]] = []
    rule_total = 0
    llm_total = 0

    for chunk in virtual_chunks:
        chunk_text_content: str = str(chunk["chunk_text"] or "")
        chunk_region_start: int = int(chunk["char_offset_start"] or 0)
        _region_end_raw = chunk["char_offset_end"]
        chunk_region_end: int = (
            int(_region_end_raw)
            if _region_end_raw is not None
            else chunk_region_start + len(chunk_text_content)
        )
        _chunk_id_raw = chunk["id"]
        chunk_db_id: uuid.UUID | None = (
            _chunk_id_raw if isinstance(_chunk_id_raw, uuid.UUID) else None
        )

        # Rule baseline (always runs — zero cost)
        rule_candidates = rule_based_mentions(chunk_text_content)
        rule_total += len(rule_candidates)

        # LLM augmentation (optional — one call per chunk)
        llm_candidates: list[dict[str, Any]] = []
        if llm is not None and chunk_text_content.strip():
            prompt = _mentions_prompt(chunk_text_content)
            try:
                result = await llm.extract_structured(MENTIONS_SCHEMA, prompt)
                _log.debug(
                    "extract_mentions: chunk %d LLM usage in=%s out=%s",
                    chunk["chunk_index"],
                    result.input_tokens,
                    result.output_tokens,
                )
                raw_mentions = result.data.get("mentions", [])
                for m in raw_mentions:
                    if not isinstance(m, dict):
                        continue
                    if not m.get("text_span") or not m.get("proposed_type"):
                        continue
                    llm_candidates.append(
                        {
                            "text_span": str(m["text_span"])[:512],
                            "proposed_type": str(m.get("proposed_type", "CONCEPT")),
                            "char_offset_start": safe_int_offset(
                                m.get("char_offset_start")
                            ),
                            "char_offset_end": safe_int_offset(m.get("char_offset_end")),
                            "confidence": clamp_confidence(m.get("confidence", 0.7)),
                            "extractor": EXTRACTOR_LLM,
                        }
                    )
                llm_total += len(llm_candidates)
            except Exception as llm_exc:
                _log.warning(
                    "extract_mentions: LLM extraction failed for chunk %d: %s; "
                    "falling back to rule-only",
                    chunk["chunk_index"],
                    llm_exc,
                )

        # ── 4. Merge: LLM wins over rule for same span ────────────────────────
        merged: dict[tuple[int | None, int | None], dict[str, Any]] = {}
        for cand in rule_candidates:
            key = (cand["char_offset_start"], cand["char_offset_end"])
            merged[key] = cand
        for cand in llm_candidates:
            key = (cand["char_offset_start"], cand["char_offset_end"])
            merged[key] = cand  # LLM overwrites rule for the same span

        # Track ranges already claimed per distinct span text within this chunk,
        # so a mention repeated in the chunk anchors to successive occurrences
        # rather than collapsing every copy onto the first hit (which would store
        # a fabricated offset for the later copies).  Sort by reported chunk-local
        # offset so occurrences are claimed left-to-right, matching their order.
        anchored_by_text: dict[str, list[tuple[int, int]]] = {}
        ordered = sorted(
            merged.values(),
            key=lambda c: (
                c["char_offset_start"] if c["char_offset_start"] is not None else 1 << 30
            ),
        )
        for cand in ordered:
            # Anchor the mention's verbatim text within this chunk's region of
            # cleaned_text to obtain document-level offsets.  Naive offset
            # addition drifts because chunk_text whitespace differs from the
            # cleaned_text region (see anchor_span).  The reported char offsets
            # (especially from the LLM) are only used as a fallback locator.
            span_text = str(cand["text_span"]).strip()
            taken = anchored_by_text.setdefault(span_text, [])
            anchored = anchor_span(
                span_text,
                cleaned_text=cleaned_text,
                region_start=chunk_region_start,
                region_end=chunk_region_end,
                occupied=taken,
            )
            if anchored is None:
                # Could not locate the span verbatim — drop it rather than
                # persist a fabricated provenance offset.
                continue
            taken.append(anchored)
            doc_start, doc_end = anchored

            all_candidates.append(
                {
                    "chunk_db_id": chunk_db_id,
                    "text_span": span_text,
                    "proposed_type": cand["proposed_type"],
                    "char_offset_start": doc_start,
                    "char_offset_end": doc_end,
                    "confidence": cand["confidence"],
                    "extractor": cand["extractor"],
                }
            )

    # ── 5. Skip invalid-offset candidates ────────────────────────────────────
    valid_candidates = [
        c
        for c in all_candidates
        if c["text_span"]
        and c["char_offset_start"] is not None
        and c["char_offset_end"] is not None
        and c["char_offset_end"] > c["char_offset_start"]
    ]

    # ── 6. Delete + bulk insert ───────────────────────────────────────────────
    await pool.execute("DELETE FROM mentions WHERE document_id = $1", doc_id)

    persisted = 0
    for cand in valid_candidates:
        await pool.execute(
            """
            INSERT INTO mentions (
                document_id, chunk_id,
                text_span, char_offset_start, char_offset_end,
                extractor, extraction_confidence, proposed_type,
                resolution_status, metadata
            ) VALUES (
                $1, $2,
                $3, $4, $5,
                $6, $7, $8,
                'unresolved', '{}'::jsonb
            )
            """,
            doc_id,
            cand["chunk_db_id"],
            cand["text_span"],
            cand["char_offset_start"],
            cand["char_offset_end"],
            cand["extractor"],
            cand["confidence"],
            cand["proposed_type"],
        )
        persisted += 1

    counters = {
        "chunks_processed": len(virtual_chunks),
        "rule_mentions": rule_total,
        "llm_mentions": llm_total,
        "persisted": persisted,
    }
    _log.info("extract_mentions: document_id=%s %s", document_id, counters)
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# extract_claims
# ──────────────────────────────────────────────────────────────────────────────


async def extract_claims(
    *,
    document_id: str,
    pool: Any,
    llm: Any,
    max_chunks: int = 20,
) -> dict[str, int]:
    """Extract atomic factual claims from a normalised source document.

    Reads ``document_chunks`` for *document_id* (ordered by ``chunk_index``).
    Existing claims for this document are deleted first (idempotent
    replace-on-retry semantics).

    Steps:
    1. Load document row (``cleaned_text``, ``redistribution_allowed``) and
       all chunks from ``document_chunks``.
    2. For each chunk (up to *max_chunks* to respect budget):
       a. Call ``await llm.extract_structured(CLAIMS_SCHEMA, prompt)`` — the
          W4 port validates the response against CLAIMS_SCHEMA and retries
          malformed output, returning a ``StructuredResult`` (validated
          ``.data`` + token usage).
       b. Accumulate validated claim dicts; log token usage.
    3. Delete existing ``claims`` rows for this document (cascade deletes
       ``claim_evidence``).
    4. For each validated claim:
       a. Insert into ``claims`` — subject/predicate/object, qualifiers,
          normalized_text, valid_from/until, confidence, source_document_ids.
          Include ``raw_spans`` carrying chunk_id + char offsets for provenance.
       b. Insert ``claim_evidence`` row linking the claim to this document
          with the character span for precise evidence tracing.

    Args:
        document_id: UUID of the normalised source document.
        pool: asyncpg connection pool.
        llm: LlmPort adapter (required for claim extraction).
        max_chunks: Upper bound on chunks to extract from in one run (budget
            guard — default 20; callers may pass a smaller value for testing).

    Returns:
        Dict with counters: ``chunks_processed``, ``claims_extracted``,
        ``claims_persisted``, ``input_tokens``, ``output_tokens``.

    Raises:
        ValueError: If the document row is missing.
        LlmError subclasses: propagated from the LLM port on fatal failures.
    """
    _log.info("extract_claims: document_id=%s max_chunks=%d", document_id, max_chunks)

    doc_id = uuid.UUID(document_id)

    # ── 1. Load document row + chunks ─────────────────────────────────────────
    row = await pool.fetchrow(
        "SELECT id, cleaned_text, redistribution_allowed FROM source_documents WHERE id = $1",
        doc_id,
    )
    if row is None:
        raise ValueError(f"source_document not found: {document_id!r}")

    redistribution_allowed: bool = bool(row["redistribution_allowed"])
    cleaned_text: str = row["cleaned_text"] or ""

    chunks = await pool.fetch(
        """
        SELECT id, chunk_index, chunk_text, char_offset_start, char_offset_end
        FROM document_chunks
        WHERE document_id = $1
        ORDER BY chunk_index
        LIMIT $2
        """,
        doc_id,
        max_chunks,
    )

    if not chunks and cleaned_text.strip():
        # No chunks yet — treat cleaned_text as one virtual chunk.
        virtual_chunks = [
            {
                "id": None,
                "chunk_index": 0,
                "chunk_text": cleaned_text,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned_text),
            }
        ]
    else:
        virtual_chunks = [dict(c) for c in chunks]

    if not virtual_chunks:
        _log.info("extract_claims: document %s has no text; 0 claims", document_id)
        return {
            "chunks_processed": 0,
            "claims_extracted": 0,
            "claims_persisted": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    # ── 2. Per-chunk LLM extraction ───────────────────────────────────────────
    all_validated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    # (claim_data, chunk_meta) — we keep chunk meta for span provenance
    total_input_tokens = 0
    total_output_tokens = 0

    for chunk in virtual_chunks:
        chunk_text_content: str = str(chunk["chunk_text"] or "")
        if not chunk_text_content.strip():
            continue

        prompt = _claims_prompt(chunk_text_content)
        try:
            result = await llm.extract_structured(CLAIMS_SCHEMA, prompt)
            total_input_tokens += result.input_tokens or 0
            total_output_tokens += result.output_tokens or 0
            _log.debug(
                "extract_claims: chunk %d usage in=%s out=%s",
                chunk["chunk_index"],
                result.input_tokens,
                result.output_tokens,
            )
            raw_claims = result.data.get("claims", [])
            for raw in raw_claims:
                if not isinstance(raw, dict):
                    continue
                has_req = (
                    raw.get("subject_text") and raw.get("predicate") and raw.get("object_text")
                )
                if not has_req:
                    _log.debug(
                        "extract_claims: skipping claim missing required fields: %s", raw
                    )
                    continue
                all_validated.append((raw, dict(chunk)))
        except Exception as llm_exc:
            _log.warning(
                "extract_claims: LLM extraction failed for chunk %d: %s",
                chunk["chunk_index"],
                llm_exc,
            )
            # Non-fatal per chunk — continue to the next chunk.

    # ── 3. Delete existing claims for this document ───────────────────────────
    # claim_evidence has ON DELETE CASCADE from claims, so this covers both.
    # We delete by source_document_ids array containment to catch any existing
    # claims from prior runs that reference this document.
    await pool.execute(
        "DELETE FROM claims WHERE $1 = ANY(source_document_ids)",
        doc_id,
    )

    # ── 4. Persist validated claims + evidence ────────────────────────────────
    persisted = 0
    for raw_claim, chunk_meta in all_validated:
        chunk_db_id: uuid.UUID | None = chunk_meta.get("id")
        chunk_body: str = str(chunk_meta.get("chunk_text") or "")
        chunk_region_start: int = int(chunk_meta.get("char_offset_start") or 0)
        _claim_region_end_raw = chunk_meta.get("char_offset_end")
        chunk_region_end: int = (
            int(_claim_region_end_raw)
            if _claim_region_end_raw is not None
            else chunk_region_start + len(chunk_body)
        )

        # Resolve the evidence span and a reconstructable quote.
        #
        # The LLM reports chunk-local offsets for the claim's evidence span.  We
        # slice the candidate quote from chunk_text using those offsets, then
        # *anchor* that verbatim quote back into cleaned_text (anchor_span) so the
        # persisted document offsets actually index the source text.  Naive
        # offset addition drifts (chunk_text whitespace != cleaned_text region).
        # If the offsets are missing/invalid, or the quote cannot be anchored, we
        # store NULL offsets + no quote (chunk_id still records provenance) rather
        # than a fabricated span.
        raw_start = safe_int_offset(raw_claim.get("char_offset_start"))
        raw_end = safe_int_offset(raw_claim.get("char_offset_end"))
        doc_char_start: int | None = None
        doc_char_end: int | None = None
        anchored_quote: str | None = None
        if (
            raw_start is not None
            and raw_end is not None
            and raw_end > raw_start
            and raw_end <= len(chunk_body)
        ):
            candidate_quote = chunk_body[raw_start:raw_end].strip()
            anchored = anchor_span(
                candidate_quote,
                cleaned_text=cleaned_text,
                region_start=chunk_region_start,
                region_end=chunk_region_end,
            )
            if anchored is not None:
                doc_char_start, doc_char_end = anchored
                anchored_quote = cleaned_text[doc_char_start:doc_char_end]

        # Build raw_spans provenance — carries chunk + character offsets for
        # full traceability from claim back to source evidence text.
        raw_spans_entry: dict[str, Any] = {
            "document_id": str(doc_id),
            "char_start": doc_char_start,
            "char_end": doc_char_end,
        }
        if chunk_db_id is not None:
            raw_spans_entry["chunk_id"] = str(chunk_db_id)
        # Only include the excerpt when the source allows redistribution.
        if redistribution_allowed and anchored_quote is not None:
            raw_spans_entry["text"] = anchored_quote

        qualifiers = raw_claim.get("qualifiers")
        if not isinstance(qualifiers, dict):
            qualifiers = {}

        valid_from = parse_valid_time(raw_claim.get("valid_from"))
        valid_until = parse_valid_time(raw_claim.get("valid_until"))
        confidence = clamp_confidence(raw_claim.get("confidence", 0.7))

        subject_text = str(raw_claim.get("subject_text", ""))[:1000]
        predicate = str(raw_claim.get("predicate", ""))[:200]
        object_text = str(raw_claim.get("object_text", ""))[:1000]
        normalized_text = str(raw_claim.get("normalized_text", "") or "")[:2000]
        if not normalized_text:
            normalized_text = f"{subject_text} {predicate} {object_text}"

        # raw_quote only if redistribution allowed — use the anchored quote so it
        # matches the persisted document offsets exactly.
        raw_quote: str | None = anchored_quote if redistribution_allowed else None

        try:
            claim_id: uuid.UUID = await pool.fetchval(
                """
                INSERT INTO claims (
                    subject_text, predicate, object_text,
                    qualifiers, normalized_text,
                    raw_quote, raw_spans,
                    valid_from, valid_until,
                    extractor, extraction_confidence,
                    source_document_ids,
                    contradiction_status, status
                ) VALUES (
                    $1, $2, $3,
                    $4::jsonb, $5,
                    $6, $7::jsonb,
                    $8, $9,
                    $10, $11,
                    ARRAY[$12::uuid],
                    'none', 'active'
                )
                RETURNING id
                """,
                subject_text,
                predicate,
                object_text,
                json.dumps(qualifiers),
                normalized_text,
                raw_quote,
                json.dumps([raw_spans_entry]),
                valid_from,
                valid_until,
                EXTRACTOR_LLM,
                confidence,
                doc_id,
            )

            # Insert claim_evidence row linking claim → source document.
            await pool.execute(
                """
                INSERT INTO claim_evidence (
                    claim_id, document_id,
                    support_strength, confidence,
                    char_offset_start, char_offset_end,
                    quote_excerpt
                ) VALUES (
                    $1, $2,
                    'supports', $3,
                    $4, $5,
                    $6
                )
                ON CONFLICT (claim_id, document_id) DO NOTHING
                """,
                claim_id,
                doc_id,
                confidence,
                doc_char_start,
                doc_char_end,
                raw_quote,
            )
            persisted += 1
        except Exception as db_exc:
            _log.warning(
                "extract_claims: DB insert failed for claim (%r %r %r): %s",
                subject_text,
                predicate,
                object_text,
                db_exc,
            )

    counters = {
        "chunks_processed": len(virtual_chunks),
        "claims_extracted": len(all_validated),
        "claims_persisted": persisted,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
    _log.info("extract_claims: document_id=%s %s", document_id, counters)
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# Deferred workstreams (W6/W7/W8)
# ──────────────────────────────────────────────────────────────────────────────


async def resolve_entities(
    *,
    document_id: str,
    pool: Any,
) -> None:
    """Resolve extracted mentions to canonical entities.

    Raises:
        NotImplementedError: Entity resolution is Plan 02 W6 scope.
    """
    raise NotImplementedError(
        "Plan 02 W6 — resolve_entities: conservative entity resolution "
        "not yet implemented."
    )


async def derive_relationships(
    *,
    document_id: str,
    pool: Any,
) -> None:
    """Derive temporal relationships and fact versions from validated claims.

    Raises:
        NotImplementedError: Relationship derivation is Plan 02 W7/W8 scope.
    """
    raise NotImplementedError(
        "Plan 02 W7/W8 — derive_relationships: relationship derivation "
        "and fact version writing not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ──────────────────────────────────────────────────────────────────────────────


def _mentions_prompt(chunk_text: str) -> str:
    """Build the LLM prompt for mention extraction from *chunk_text*."""
    return (
        "You are an information-extraction assistant. "
        "Identify all named entities in the following text and return them as JSON.\n\n"
        "For each entity mention return:\n"
        "  text_span: the exact text as it appears\n"
        "  proposed_type: one of PERSON, ORG, GPE, ROLE, PRODUCT, CONCEPT, EVENT,"
        " LAW, SOURCE, ARTIFACT\n"
        "  char_offset_start: 0-based character offset of text_span start in the input text\n"
        "  char_offset_end: exclusive end character offset\n"
        "  confidence: a float from 0.0 to 1.0\n\n"
        "Return ONLY a JSON object with key \"mentions\" containing the array.\n"
        "If no entities are found, return {\"mentions\": []}.\n\n"
        f"Text:\n{chunk_text}"
    )


def _claims_prompt(chunk_text: str) -> str:
    """Build the LLM prompt for claim extraction from *chunk_text*."""
    return (
        "You are a precise fact-extraction assistant building a knowledge base.\n"
        "Extract EVERY atomic factual assertion the text actually states. Decompose "
        "compound sentences into separate atomic claims — a sentence asserting three "
        "facts must yield three claims. Extract liberally, but ONLY facts that are "
        "explicitly supported by the text. Never invent, infer beyond the text, or "
        "guess. If a fact is not stated, do not include it.\n\n"
        "Capture facts such as: who someone/something is (is_a, instance_of), roles and "
        "positions (holds_role), membership/affiliation (member_of, part_of, works_for), "
        "founding/creation (founded, created, developed, authored), ownership/acquisition "
        "(owns, acquired), location (located_in, headquartered_in, born_in), dates and "
        "events (occurred_on, released, published, updated), identifiers and properties "
        "(has_property, identified_by), and stated assertions (stated, announced).\n\n"
        "For each claim return:\n"
        "  subject_text: the subject exactly as named in the text\n"
        "  predicate: a concise snake_case relationship verb (see examples above)\n"
        "  object_text: the object or value of the claim, as stated in the text\n"
        "  normalized_text: a single canonical natural-language sentence restating the claim\n"
        "  qualifiers: optional object with extra context (date, location, units, role, etc.)\n"
        "  valid_from: ISO 8601 date when this became true, or null if not stated\n"
        "  valid_until: ISO 8601 date when this stopped being true, or null if open/unstated\n"
        "  confidence: a float 0.0-1.0 reflecting how explicitly the text supports the claim\n"
        "  char_offset_start: 0-based character offset in the text where the supporting "
        "evidence span begins (copy the exact substring that states the fact)\n"
        "  char_offset_end: exclusive end character offset of that evidence span\n\n"
        "The char offsets must bracket a VERBATIM substring of the text below that supports "
        "the claim, so the evidence can be traced back to the source.\n"
        "Return ONLY a JSON object with key \"claims\" containing the array.\n"
        "If the text states no extractable facts (e.g. it is metadata or boilerplate), "
        "return {\"claims\": []}.\n\n"
        f"Text:\n{chunk_text}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def parse_valid_time(value: Any) -> Any:
    """Parse a valid_from / valid_until value into an aware datetime or None.

    Accepts ISO-8601 strings (date or datetime).  Returns None on any failure
    so claim persistence never errors on a malformed temporal qualifier.
    """
    if not value or not isinstance(value, str):
        return None
    import datetime as _dt

    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    # Try full datetime first, then date-only.
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = _dt.datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.UTC)
            return parsed
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        _log.debug("extract_claims: unparseable valid_time %r; storing NULL", value)
        return None
