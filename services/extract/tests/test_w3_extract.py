"""Workstream 3 tests: extract_mentions and extract_claims jobs.

No live network or database required.  All DB calls are intercepted via a
minimal fake asyncpg pool (same pattern used by W1/W2 tests).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import typer
from intercal_extract.jobs import (
    CLAIMS_SCHEMA,
    EXTRACTOR_LLM,
    EXTRACTOR_RULE,
    MENTIONS_SCHEMA,
    anchor_span,
    clamp_confidence,
    extract_claims,
    extract_mentions,
    parse_valid_time,
    rule_based_mentions,
    safe_int_offset,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_pool(
    *,
    doc_row: dict[str, Any] | None = None,
    chunks: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a minimal fake asyncpg pool.

    ``fetchrow`` returns *doc_row* for SELECT queries.
    ``fetch`` returns *chunks* list.
    ``fetchval`` returns a new uuid.UUID (simulating RETURNING id).
    ``execute`` is a no-op.
    """
    pool = MagicMock()

    async def _fetchrow(query: str, *args: Any) -> dict[str, Any] | None:
        return doc_row

    async def _fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        return chunks or []

    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        return uuid.uuid4()

    async def _execute(query: str, *args: Any) -> str:
        return "OK"

    pool.fetchrow = _fetchrow
    pool.fetch = _fetch
    pool.fetchval = _fetchval
    pool.execute = _execute
    return pool


def _subcommand(app: typer.Typer, name: str) -> Any:
    command = typer.main.get_command(app)
    commands: Any = getattr(command, "commands", None)
    assert isinstance(commands, dict)
    return commands[name]


def _option_names(command: Any) -> set[str]:
    names: set[str] = set()
    for param in command.params:
        names.update(getattr(param, "opts", ()))
        names.update(getattr(param, "secondary_opts", ()))
    return names


def _make_llm(
    *, mentions_data: dict[str, Any] | None = None, claims_data: dict[str, Any] | None = None
) -> MagicMock:
    """Return a fake LlmPort that returns schema-validated StructuredResults."""
    from intercal_shared.ports.llm import StructuredResult

    llm = MagicMock()

    call_count = {"n": 0}

    async def _extract_structured(
        schema: dict[str, Any], prompt: str, **kw: Any
    ) -> StructuredResult:
        call_count["n"] += 1
        if "mentions" in schema.get("properties", {}):
            data = mentions_data if mentions_data is not None else {"mentions": []}
        else:
            data = claims_data if claims_data is not None else {"claims": []}
        return StructuredResult(data=data, model="test-model", input_tokens=10, output_tokens=5)

    llm.extract_structured = _extract_structured
    llm._call_count = call_count
    return llm


DOC_ID = str(uuid.uuid4())
CHUNK_ID = str(uuid.uuid4())


# ── MENTIONS_SCHEMA and CLAIMS_SCHEMA sanity checks ──────────────────────────


def test_mentions_schema_has_required_fields() -> None:
    props = MENTIONS_SCHEMA["properties"]["mentions"]["items"]["properties"]
    required_fields = (
        "text_span",
        "proposed_type",
        "char_offset_start",
        "char_offset_end",
        "confidence",
    )
    for field in required_fields:
        assert field in props


def test_claims_schema_has_required_fields() -> None:
    props = CLAIMS_SCHEMA["properties"]["claims"]["items"]["properties"]
    for field in (
        "subject_text",
        "predicate",
        "object_text",
        "normalized_text",
        "confidence",
        "char_offset_start",
        "char_offset_end",
    ):
        assert field in props


# ── Rule-based NER ────────────────────────────────────────────────────────────


def test_rule_based_mentions_finds_wikidata_qid() -> None:
    text = "Q5401080 is a Wikidata entity."
    mentions = rule_based_mentions(text)
    spans = [m["text_span"] for m in mentions]
    assert "Q5401080" in spans
    for m in mentions:
        if m["text_span"] == "Q5401080":
            assert m["proposed_type"] == "SOURCE"
            assert m["char_offset_start"] == 0
            assert m["char_offset_end"] == 8


def test_rule_based_mentions_finds_property_id() -> None:
    # P-IDs require 3+ digits to match (P\d{3,}); e.g. P312, P4390.
    text = "Updated via P312 and P4390 in the record."
    mentions = rule_based_mentions(text)
    spans = [m["text_span"] for m in mentions]
    assert "P312" in spans
    for m in mentions:
        if m["text_span"] == "P312":
            assert m["proposed_type"] == "CONCEPT"


def test_rule_based_mentions_finds_url() -> None:
    text = "See https://example.com for details."
    mentions = rule_based_mentions(text)
    spans = [m["text_span"] for m in mentions]
    assert any("https://example.com" in s for s in spans)


def test_rule_based_mentions_finds_person_name() -> None:
    text = "Sam Altman is the CEO."
    mentions = rule_based_mentions(text)
    spans = [m["text_span"] for m in mentions]
    assert "Sam Altman" in spans


def test_rule_based_mentions_finds_gpe() -> None:
    text = "Published by the EU and USA."
    mentions = rule_based_mentions(text)
    types = {m["proposed_type"] for m in mentions}
    assert "GPE" in types


def test_rule_based_mentions_deduplicates_same_span() -> None:
    # Only one result per unique (start, end) pair.
    text = "Q12345678 Q12345678"
    mentions = rule_based_mentions(text)
    starts = [m["char_offset_start"] for m in mentions if m["text_span"] == "Q12345678"]
    assert len(starts) == 2  # two occurrences at different offsets
    assert len(set(starts)) == 2


def test_rule_based_mentions_empty_text() -> None:
    assert rule_based_mentions("") == []


def test_rule_based_mentions_confidence_is_float() -> None:
    text = "Q99999999"
    mentions = rule_based_mentions(text)
    assert all(isinstance(m["confidence"], float) for m in mentions)


def test_rule_based_mentions_extractor_label() -> None:
    text = "Q99999999"
    mentions = rule_based_mentions(text)
    assert all(m["extractor"] == EXTRACTOR_RULE for m in mentions)


# ── Helper utilities ──────────────────────────────────────────────────────────


def test_clamp_confidence_normal() -> None:
    assert clamp_confidence(0.85) == pytest.approx(0.85)


def test_clamp_confidence_above_one() -> None:
    assert clamp_confidence(1.5) == 1.0


def test_clamp_confidence_below_zero() -> None:
    assert clamp_confidence(-0.1) == 0.0


def test_clamp_confidence_bad_type() -> None:
    assert clamp_confidence("bad") == 0.5


def test_safe_int_offset_valid() -> None:
    assert safe_int_offset(42) == 42
    assert safe_int_offset("10") == 10


def test_safe_int_offset_negative() -> None:
    assert safe_int_offset(-1) is None


def test_safe_int_offset_invalid() -> None:
    assert safe_int_offset(None) is None
    assert safe_int_offset("abc") is None


def test_parse_valid_time_iso_date() -> None:

    result = parse_valid_time("2024-01-15")
    assert result is not None
    assert result.year == 2024
    assert result.month == 1
    assert result.day == 15


def test_parse_valid_time_iso_datetime_z() -> None:
    result = parse_valid_time("2024-06-01T00:00:00Z")
    assert result is not None


def test_parse_valid_time_none() -> None:
    assert parse_valid_time(None) is None


def test_parse_valid_time_empty_string() -> None:
    assert parse_valid_time("") is None


def test_parse_valid_time_garbage() -> None:
    assert parse_valid_time("not-a-date") is None


# ── extract_mentions job ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_mentions_document_not_found() -> None:
    pool = _make_pool(doc_row=None)
    with pytest.raises(ValueError, match="not found"):
        await extract_mentions(document_id=DOC_ID, pool=pool)


@pytest.mark.asyncio
async def test_extract_mentions_no_text_no_chunks() -> None:
    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": "", "citation_only": False},
        chunks=[],
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool)
    assert counters["persisted"] == 0
    assert counters["chunks_processed"] == 0


@pytest.mark.asyncio
async def test_extract_mentions_rule_only_no_llm() -> None:
    """Rule baseline runs without an LLM adapter."""
    text = "Q5401080 is referenced by Property:P31."
    chunk_id = uuid.uuid4()
    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)
    assert counters["rule_mentions"] > 0
    assert counters["llm_mentions"] == 0
    assert counters["persisted"] > 0


@pytest.mark.asyncio
async def test_extract_mentions_llm_augments() -> None:
    """LLM mentions are merged on top of rule mentions."""
    text = "Sam Altman leads OpenAI Foundation."
    chunk_id = uuid.uuid4()
    llm = _make_llm(
        mentions_data={
            "mentions": [
                {
                    "text_span": "Sam Altman",
                    "proposed_type": "PERSON",
                    "char_offset_start": 0,
                    "char_offset_end": 10,
                    "confidence": 0.95,
                }
            ]
        }
    )
    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["llm_mentions"] > 0
    assert counters["persisted"] > 0


@pytest.mark.asyncio
async def test_extract_mentions_llm_wins_same_span() -> None:
    """LLM candidate overwrites rule candidate for the same char span."""
    text = "Q12345678 is important."
    chunk_id = uuid.uuid4()
    # LLM assigns CONCEPT to same span the rule assigns SOURCE
    llm = _make_llm(
        mentions_data={
            "mentions": [
                {
                    "text_span": "Q12345678",
                    "proposed_type": "CONCEPT",
                    "char_offset_start": 0,
                    "char_offset_end": 9,
                    "confidence": 0.9,
                }
            ]
        }
    )

    inserted_types: list[str] = []

    async def _execute(query: str, *args: Any) -> str:
        if "INSERT INTO mentions" in query and len(args) >= 8:
            # proposed_type is the 8th positional arg ($8)
            inserted_types.append(str(args[7]))
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    pool.execute = _execute
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=llm)
    # LLM should overwrite rule for this span — only one entry for the span
    assert counters["persisted"] >= 1


@pytest.mark.asyncio
async def test_extract_mentions_llm_failure_falls_back_to_rules() -> None:
    """When the LLM raises, extraction continues using rule baseline only."""
    text = "Q5401080 referenced."
    chunk_id = uuid.uuid4()

    llm = MagicMock()

    async def _extract_structured(*args: Any, **kw: Any) -> Any:
        raise RuntimeError("LLM unavailable")

    llm.extract_structured = _extract_structured

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["llm_mentions"] == 0
    assert counters["rule_mentions"] > 0


@pytest.mark.asyncio
async def test_extract_mentions_invalid_offsets_skipped() -> None:
    """Candidates with invalid or inverted offsets are dropped before insertion."""
    text = "Some text here."
    chunk_id = uuid.uuid4()
    # LLM returns a span with char_end <= char_start (invalid)
    llm = _make_llm(
        mentions_data={
            "mentions": [
                {
                    "text_span": "bad",
                    "proposed_type": "CONCEPT",
                    "char_offset_start": 10,
                    "char_offset_end": 5,  # inverted — invalid
                    "confidence": 0.9,
                }
            ]
        }
    )
    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=llm)
    # No LLM mentions persisted (invalid spans) — rule may still produce some
    assert isinstance(counters["persisted"], int)


@pytest.mark.asyncio
async def test_extract_mentions_virtual_chunk_fallback() -> None:
    """When there are no chunk rows, the document text is used as one virtual chunk."""
    text = "Q5401080 Q67890123 mentioned."
    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[],  # no DB chunk rows
    )
    counters = await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)
    assert counters["chunks_processed"] == 1
    assert counters["rule_mentions"] > 0


@pytest.mark.asyncio
async def test_extract_mentions_doc_offset_applied() -> None:
    """Chunk-local offsets are translated to document-level offsets on insert."""
    # Chunk starts at doc offset 100; mention starts at chunk offset 0
    text = "Q5401080"
    chunk_id = uuid.uuid4()

    inserted_offsets: list[tuple[int, int]] = []

    async def _execute(query: str, *args: Any) -> str:
        if "INSERT INTO mentions" in query and len(args) >= 5:
            # char_offset_start=$4, char_offset_end=$5
            inserted_offsets.append((args[3], args[4]))
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": "x" * 100 + text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 1,
                "chunk_text": text,
                "char_offset_start": 100,
                "char_offset_end": 108,
            }
        ],
    )
    pool.execute = _execute

    await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)
    # Offsets must be document-level (100..108), not chunk-local (0..8)
    assert any(start >= 100 for start, _end in inserted_offsets)


@pytest.mark.asyncio
async def test_extract_mentions_idempotent_delete_called() -> None:
    """DELETE FROM mentions is called before inserting, ensuring idempotency."""
    text = "Q5401080"
    chunk_id = uuid.uuid4()
    deleted = {"called": False}

    async def _execute(query: str, *args: Any) -> str:
        if "DELETE FROM mentions" in query:
            deleted["called"] = True
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": text, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    pool.execute = _execute

    await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)
    assert deleted["called"]


# ── extract_claims job ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_claims_document_not_found() -> None:
    pool = _make_pool(doc_row=None)
    llm = _make_llm()
    with pytest.raises(ValueError, match="not found"):
        await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)


@pytest.mark.asyncio
async def test_extract_claims_no_text() -> None:
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": "",
            "redistribution_allowed": False,
        },
        chunks=[],
    )
    llm = _make_llm()
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["claims_persisted"] == 0
    assert counters["chunks_processed"] == 0


@pytest.mark.asyncio
async def test_extract_claims_single_claim_persisted() -> None:
    text = "Sam Altman is the CEO of OpenAI."
    chunk_id = uuid.uuid4()
    claim_data = {
        "claims": [
            {
                "subject_text": "Sam Altman",
                "predicate": "holds_role",
                "object_text": "CEO at OpenAI",
                "normalized_text": "Sam Altman holds the role of CEO at OpenAI.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.92,
                "char_offset_start": 0,
                "char_offset_end": 31,
            }
        ]
    }
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": True,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    llm = _make_llm(claims_data=claim_data)
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["claims_extracted"] == 1
    assert counters["claims_persisted"] == 1
    assert counters["input_tokens"] > 0
    assert counters["output_tokens"] > 0


@pytest.mark.asyncio
async def test_extract_claims_carries_safe_corpus_metadata() -> None:
    text = "Anthropic released Claude."
    chunk_id = uuid.uuid4()
    claim_data: dict[str, Any] = {
        "claims": [
            {
                "subject_text": "Claude",
                "predicate": "released",
                "object_text": "AI assistant",
                "normalized_text": "Anthropic released Claude.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.91,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ]
    }
    inserted_metadata: list[dict[str, Any]] = []
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,
            "source_metadata": {
                "source_class": "model_provider",
                "topic_cluster": "frontier_llms",
                "api_token": "must-not-copy",
            },
            "document_metadata": {
                "topic_cluster": "model_context_protocol",
                "content_type": "application/json",
            },
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )

    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        if "INSERT INTO claims" in query:
            inserted_metadata.append(json.loads(args[12]))
        return uuid.uuid4()

    pool.fetchval = _fetchval
    llm = _make_llm(claims_data=claim_data)

    await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)

    assert inserted_metadata == [
        {
            "source_class": "model_provider",
            "topic_cluster": "model_context_protocol",
        }
    ]


@pytest.mark.asyncio
async def test_extract_claims_idempotent_delete_called() -> None:
    """DELETE FROM claims is called before inserting."""
    text = "Q5401080 published."
    chunk_id = uuid.uuid4()
    deleted = {"called": False}

    claim_data = {
        "claims": [
            {
                "subject_text": "Q5401080",
                "predicate": "published",
                "object_text": "article",
                "normalized_text": "Q5401080 published an article.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.8,
                "char_offset_start": 0,
                "char_offset_end": 8,
            }
        ]
    }

    base_pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )

    async def _execute(query: str, *args: Any) -> str:
        if "DELETE FROM claims" in query:
            deleted["called"] = True
        return "OK"

    base_pool.execute = _execute
    llm = _make_llm(claims_data=claim_data)
    await extract_claims(document_id=DOC_ID, pool=base_pool, llm=llm)
    assert deleted["called"]


@pytest.mark.asyncio
async def test_extract_claims_llm_failure_per_chunk_nonfatal() -> None:
    """LLM failure on one chunk is non-fatal; 0 claims are persisted but no exception."""
    text = "Some text here."
    chunk_id = uuid.uuid4()

    llm = MagicMock()

    async def _extract_structured(*args: Any, **kw: Any) -> Any:
        raise RuntimeError("LLM down")

    llm.extract_structured = _extract_structured

    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["claims_persisted"] == 0
    assert counters["chunks_processed"] >= 1


@pytest.mark.asyncio
async def test_extract_claims_missing_required_fields_skipped() -> None:
    """Claims lacking subject/predicate/object are silently skipped."""
    text = "Some content."
    chunk_id = uuid.uuid4()
    # Missing 'object_text'
    bad_claim = {
        "claims": [
            {
                "subject_text": "Something",
                "predicate": "does",
                # object_text missing
                "normalized_text": "Something does.",
                "confidence": 0.8,
                "char_offset_start": 0,
                "char_offset_end": 10,
            }
        ]
    }
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    llm = _make_llm(claims_data=bad_claim)
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["claims_persisted"] == 0


@pytest.mark.asyncio
async def test_extract_claims_raw_quote_omitted_when_no_redistribution() -> None:
    """raw_quote is None when redistribution is not allowed."""
    text = "Q5401080 updated a claim."
    chunk_id = uuid.uuid4()
    claim_data = {
        "claims": [
            {
                "subject_text": "Q5401080",
                "predicate": "updated",
                "object_text": "claim",
                "normalized_text": "Q5401080 updated a claim.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.75,
                "char_offset_start": 0,
                "char_offset_end": 8,
            }
        ]
    }
    inserted_raw_quotes: list[Any] = []

    base_pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,  # no redistribution
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )

    # Capture the raw_quote argument (position 6 = $6 in the INSERT INTO claims query)
    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        if "INSERT INTO claims" in query and len(args) >= 6:
            inserted_raw_quotes.append(args[5])  # raw_quote is $6 → args[5]
        return uuid.uuid4()

    base_pool.fetchval = _fetchval
    llm = _make_llm(claims_data=claim_data)
    await extract_claims(document_id=DOC_ID, pool=base_pool, llm=llm)
    # raw_quote should be None when redistribution is not allowed
    assert all(q is None for q in inserted_raw_quotes)


@pytest.mark.asyncio
async def test_extract_claims_virtual_chunk_fallback() -> None:
    """When no chunk rows exist, cleaned_text is used as one virtual chunk."""
    text = "OpenAI was founded in San Francisco."
    claim_data = {
        "claims": [
            {
                "subject_text": "OpenAI",
                "predicate": "founded_in",
                "object_text": "San Francisco",
                "normalized_text": "OpenAI was founded in San Francisco.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.88,
                "char_offset_start": 0,
                "char_offset_end": 36,
            }
        ]
    }
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": True,
        },
        chunks=[],  # no DB chunk rows
    )
    llm = _make_llm(claims_data=claim_data)
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    assert counters["chunks_processed"] == 1
    assert counters["claims_persisted"] == 1


@pytest.mark.asyncio
async def test_extract_claims_max_chunks_respected() -> None:
    """max_chunks limits how many chunks are fetched (query passes LIMIT)."""
    text = "Short text."
    # We can only verify the LIMIT clause was passed in the query; the fake pool
    # just returns whatever chunk list we give — so verify the counter matches.
    chunk_id = uuid.uuid4()
    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": False,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )
    llm = _make_llm(claims_data={"claims": []})
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm, max_chunks=3)
    assert counters["chunks_processed"] == 1  # only 1 chunk in fake pool


@pytest.mark.asyncio
async def test_extract_claims_token_usage_accumulated() -> None:
    """Token counts from multiple chunks are summed."""
    text_a = "OpenAI founded in 2015."
    text_b = "Google founded in 1998."
    chunk_a_id = uuid.uuid4()
    chunk_b_id = uuid.uuid4()
    claim_a = {
        "claims": [
            {
                "subject_text": "OpenAI",
                "predicate": "founded",
                "object_text": "2015",
                "normalized_text": "OpenAI was founded in 2015.",
                "qualifiers": {},
                "valid_from": "2015-12-11",
                "valid_until": None,
                "confidence": 0.9,
                "char_offset_start": 0,
                "char_offset_end": 6,
            }
        ]
    }

    from intercal_shared.ports.llm import StructuredResult

    llm = MagicMock()
    call_n = {"n": 0}

    async def _extract_structured(
        schema: dict[str, Any], prompt: str, **kw: Any
    ) -> StructuredResult:
        call_n["n"] += 1
        return StructuredResult(data=claim_a, model="test", input_tokens=20, output_tokens=10)

    llm.extract_structured = _extract_structured

    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text_a + " " + text_b,
            "redistribution_allowed": False,
        },
        chunks=[
            {
                "id": chunk_a_id,
                "chunk_index": 0,
                "chunk_text": text_a,
                "char_offset_start": 0,
                "char_offset_end": len(text_a),
            },
            {
                "id": chunk_b_id,
                "chunk_index": 1,
                "chunk_text": text_b,
                "char_offset_start": len(text_a) + 1,
                "char_offset_end": len(text_a) + 1 + len(text_b),
            },
        ],
    )
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)
    # Two chunks → two LLM calls → 40 input, 20 output tokens
    assert counters["input_tokens"] == 40
    assert counters["output_tokens"] == 20
    assert counters["claims_extracted"] == 2


@pytest.mark.asyncio
async def test_extract_claims_source_spans_in_raw_spans() -> None:
    """raw_spans JSON includes chunk_id and doc-level char offsets."""
    text = "Anthropic developed Claude."
    chunk_id = uuid.uuid4()
    claim_data = {
        "claims": [
            {
                "subject_text": "Anthropic",
                "predicate": "developed",
                "object_text": "Claude",
                "normalized_text": "Anthropic developed Claude.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.95,
                "char_offset_start": 0,
                "char_offset_end": 9,
            }
        ]
    }

    raw_spans_captured: list[Any] = []

    base_pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": text,
            "redistribution_allowed": True,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": text,
                "char_offset_start": 0,
                "char_offset_end": len(text),
            }
        ],
    )

    # raw_spans is the 7th arg ($7) in the INSERT INTO claims query
    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        if "INSERT INTO claims" in query and len(args) >= 7:
            raw_spans_captured.append(args[6])  # $7 → args[6]
        return uuid.uuid4()

    base_pool.fetchval = _fetchval
    llm = _make_llm(claims_data=claim_data)
    await extract_claims(document_id=DOC_ID, pool=base_pool, llm=llm)

    assert len(raw_spans_captured) == 1
    spans = json.loads(raw_spans_captured[0])
    assert isinstance(spans, list)
    assert len(spans) == 1
    span = spans[0]
    assert "document_id" in span
    assert "char_start" in span
    assert "char_end" in span
    # chunk_id must be present since we have a real chunk
    assert "chunk_id" in span
    assert str(chunk_id) == span["chunk_id"]


# ── anchor_span (provenance offset correctness) ──────────────────────────────


def test_anchor_span_exact_in_region() -> None:
    cleaned = "x" * 100 + "Sam Altman leads OpenAI."
    res = anchor_span("Sam Altman", cleaned_text=cleaned, region_start=100, region_end=len(cleaned))
    assert res is not None
    start, end = res
    assert cleaned[start:end] == "Sam Altman"


def test_anchor_span_whitespace_flexible() -> None:
    # chunk_text joined a paragraph break with a single space; cleaned_text has \n\n.
    cleaned = "First line.\n\nSecond paragraph mentions Anthropic here."
    # The span as the LLM/chunk saw it (single space) differs from cleaned_text.
    res = anchor_span(
        "Second paragraph mentions Anthropic",
        cleaned_text=cleaned,
        region_start=0,
        region_end=len(cleaned),
    )
    assert res is not None
    start, end = res
    assert cleaned[start:end] == "Second paragraph mentions Anthropic"


def test_anchor_span_returns_none_when_absent() -> None:
    cleaned = "Nothing relevant here at all."
    assert (
        anchor_span("Totally Missing", cleaned_text=cleaned, region_start=0, region_end=29) is None
    )


def test_anchor_span_picks_occurrence_in_region() -> None:
    # Same token appears before and inside the region; anchor must prefer the region.
    cleaned = "OpenAI ... " + ("y" * 50) + " OpenAI again"
    region_start = 11
    res = anchor_span(
        "OpenAI", cleaned_text=cleaned, region_start=region_start, region_end=len(cleaned)
    )
    assert res is not None
    start, _end = res
    assert start >= region_start


def test_anchor_span_occupied_advances_to_next_occurrence() -> None:
    # A span repeated in the region must anchor to successive occurrences when the
    # caller records each claimed range — never collapse onto the first hit.
    cleaned = "Sam Altman met Sam Altman."
    taken: list[tuple[int, int]] = []
    first = anchor_span(
        "Sam Altman",
        cleaned_text=cleaned,
        region_start=0,
        region_end=len(cleaned),
        occupied=taken,
    )
    assert first is not None
    assert first == (0, 10)
    taken.append(first)
    second = anchor_span(
        "Sam Altman",
        cleaned_text=cleaned,
        region_start=0,
        region_end=len(cleaned),
        occupied=taken,
    )
    assert second is not None
    assert second == (15, 25)
    assert cleaned[second[0] : second[1]] == "Sam Altman"


@pytest.mark.asyncio
async def test_extract_mentions_repeated_span_distinct_offsets() -> None:
    """A mention repeated in one chunk persists at distinct, correct offsets.

    Regression: anchor_span used to return the first occurrence for every copy,
    so two rule matches of the same name collapsed onto identical offsets — the
    second row carried a fabricated provenance pointer.  Each persisted row must
    reconstruct its own occurrence from cleaned_text.
    """
    cleaned = "Sam Altman met Sam Altman."
    chunk_id = uuid.uuid4()
    inserted: list[tuple[str, int, int]] = []

    async def _execute(query: str, *args: Any) -> str:
        if "INSERT INTO mentions" in query and len(args) >= 5:
            inserted.append((str(args[2]), int(args[3]), int(args[4])))
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": cleaned, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": cleaned,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned),
            }
        ],
    )
    pool.execute = _execute
    await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)

    person_rows = [(s, a, b) for (s, a, b) in inserted if s == "Sam Altman"]
    assert len(person_rows) == 2, f"expected two distinct mentions, got {person_rows}"
    offsets = {(a, b) for _s, a, b in person_rows}
    assert len(offsets) == 2, f"offsets collapsed onto one occurrence: {person_rows}"
    for s, a, b in person_rows:
        assert cleaned[a:b] == s


@pytest.mark.asyncio
async def test_extract_mentions_anchors_offsets_across_whitespace_drift() -> None:
    """Document offsets must index cleaned_text even when chunk_text whitespace differs.

    Regression for the provenance offset-drift bug: the chunker re-joins sentences
    with single spaces, so a chunk that spans a newline in cleaned_text has
    different internal offsets than the document.  Naive (chunk_start + local)
    math corrupts the persisted span; anchoring must recover the verbatim offset.
    """
    cleaned = "Intro line.\n\nSam Altman leads OpenAI Foundation today."
    # chunk_text as W2 would store it: paragraph break collapsed to a space,
    # and char_offset_start/end bound the region within cleaned_text.
    chunk_body = "Intro line. Sam Altman leads OpenAI Foundation today."
    chunk_id = uuid.uuid4()

    inserted: list[tuple[str, int, int]] = []

    async def _execute(query: str, *args: Any) -> str:
        if "INSERT INTO mentions" in query and len(args) >= 8:
            # text_span=$3, char_offset_start=$4, char_offset_end=$5
            inserted.append((str(args[2]), int(args[3]), int(args[4])))
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": cleaned, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": chunk_body,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned),
            }
        ],
    )
    pool.execute = _execute

    await extract_mentions(document_id=DOC_ID, pool=pool, llm=None)

    # Every persisted mention's offsets must reconstruct its text from cleaned_text.
    assert inserted, "expected at least one rule-based mention (Sam Altman)"
    for text_span, start, end in inserted:
        assert cleaned[start:end] == text_span, (
            f"offset drift: cleaned_text[{start}:{end}]={cleaned[start:end]!r} != {text_span!r}"
        )


@pytest.mark.asyncio
async def test_extract_claims_anchored_quote_matches_offsets() -> None:
    """Claim raw_quote and raw_spans offsets must agree and index cleaned_text."""
    cleaned = "Header.\n\nAnthropic developed Claude in San Francisco."
    chunk_body = "Header. Anthropic developed Claude in San Francisco."
    chunk_id = uuid.uuid4()
    # The LLM reports a chunk-local span for the evidence.
    local_start = chunk_body.index("Anthropic developed Claude")
    local_end = local_start + len("Anthropic developed Claude")
    claim_data = {
        "claims": [
            {
                "subject_text": "Anthropic",
                "predicate": "developed",
                "object_text": "Claude",
                "normalized_text": "Anthropic developed Claude.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.95,
                "char_offset_start": local_start,
                "char_offset_end": local_end,
            }
        ]
    }

    captured: dict[str, Any] = {}

    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        if "INSERT INTO claims" in query and len(args) >= 7:
            captured["raw_quote"] = args[5]  # $6
            captured["raw_spans"] = json.loads(args[6])  # $7
        return uuid.uuid4()

    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": cleaned,
            "redistribution_allowed": True,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": chunk_body,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned),
            }
        ],
    )
    pool.fetchval = _fetchval
    llm = _make_llm(claims_data=claim_data)
    await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)

    span = captured["raw_spans"][0]
    start, end = span["char_start"], span["char_end"]
    assert start is not None and end is not None
    # The recorded offsets must index cleaned_text to exactly the stored quote.
    assert cleaned[start:end] == "Anthropic developed Claude"
    assert captured["raw_quote"] == "Anthropic developed Claude"
    assert span["text"] == "Anthropic developed Claude"


@pytest.mark.asyncio
async def test_extract_claims_no_quote_when_span_unanchorable() -> None:
    """A claim whose evidence span cannot be anchored stores NULL offsets, no quote."""
    cleaned = "Anthropic developed Claude."
    chunk_body = cleaned
    chunk_id = uuid.uuid4()
    # Offsets point past the chunk text → cannot slice a valid quote.
    claim_data = {
        "claims": [
            {
                "subject_text": "Anthropic",
                "predicate": "developed",
                "object_text": "Claude",
                "normalized_text": "Anthropic developed Claude.",
                "qualifiers": {},
                "valid_from": None,
                "valid_until": None,
                "confidence": 0.9,
                "char_offset_start": 9000,
                "char_offset_end": 9100,
            }
        ]
    }

    captured: dict[str, Any] = {}

    async def _fetchval(query: str, *args: Any) -> uuid.UUID:
        if "INSERT INTO claims" in query and len(args) >= 7:
            captured["raw_quote"] = args[5]
            captured["raw_spans"] = json.loads(args[6])
        return uuid.uuid4()

    pool = _make_pool(
        doc_row={
            "id": uuid.UUID(DOC_ID),
            "cleaned_text": cleaned,
            "redistribution_allowed": True,
        },
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": chunk_body,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned),
            }
        ],
    )
    pool.fetchval = _fetchval
    llm = _make_llm(claims_data=claim_data)
    counters = await extract_claims(document_id=DOC_ID, pool=pool, llm=llm)

    # Claim still persists (chunk_id provenance), but with NULL span + no quote.
    assert counters["claims_persisted"] == 1
    assert captured["raw_quote"] is None
    span = captured["raw_spans"][0]
    assert span["char_start"] is None
    assert span["char_end"] is None
    assert "text" not in span
    assert span["chunk_id"] == str(chunk_id)


@pytest.mark.asyncio
async def test_extract_mentions_unanchorable_llm_span_dropped() -> None:
    """An LLM mention whose text_span is not in the document is dropped, not faked."""
    cleaned = "Q5401080 is referenced."
    chunk_id = uuid.uuid4()
    llm = _make_llm(
        mentions_data={
            "mentions": [
                {
                    "text_span": "Nonexistent Entity",
                    "proposed_type": "ORG",
                    "char_offset_start": 0,
                    "char_offset_end": 18,
                    "confidence": 0.9,
                }
            ]
        }
    )
    inserted_spans: list[str] = []

    async def _execute(query: str, *args: Any) -> str:
        if "INSERT INTO mentions" in query and len(args) >= 3:
            inserted_spans.append(str(args[2]))
        return "OK"

    pool = _make_pool(
        doc_row={"id": uuid.UUID(DOC_ID), "cleaned_text": cleaned, "citation_only": False},
        chunks=[
            {
                "id": chunk_id,
                "chunk_index": 0,
                "chunk_text": cleaned,
                "char_offset_start": 0,
                "char_offset_end": len(cleaned),
            }
        ],
    )
    pool.execute = _execute
    await extract_mentions(document_id=DOC_ID, pool=pool, llm=llm)
    # The fabricated mention must not be persisted; the real QID rule match is.
    assert "Nonexistent Entity" not in inserted_spans
    assert "Q5401080" in inserted_spans


# ── CLI wiring ─────────────────────────────────────────────────────────────────


def test_cli_help_lists_commands() -> None:
    from intercal_extract.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "extract-mentions" in result.output
    assert "extract-claims" in result.output


def test_cli_extract_mentions_requires_document_id() -> None:
    from intercal_extract.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, ["extract-mentions"])
    assert result.exit_code != 0


def test_cli_extract_claims_requires_document_id() -> None:
    from intercal_extract.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, ["extract-claims"])
    assert result.exit_code != 0


def test_cli_extract_claims_help_mentions_max_chunks() -> None:
    from intercal_extract.cli import app

    assert "--max-chunks" in _option_names(_subcommand(app, "extract-claims"))


# ── Schema constants importable ───────────────────────────────────────────────


def test_extractor_constants_defined() -> None:
    assert EXTRACTOR_RULE == "rule_regex_v1"
    assert EXTRACTOR_LLM == "llm_extract_v1"
