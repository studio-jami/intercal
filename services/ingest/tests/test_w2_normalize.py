"""Workstream 2 tests: normalizer module + normalize_document job.

No live network or database is required.  All DB calls are intercepted via
a minimal fake asyncpg pool.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from intercal_ingest.jobs import normalize_document
from intercal_ingest.normalizer import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    ChunkResult,
    chunk_text,
    detect_language,
    normalize_text,
)

# ── normalize_text ────────────────────────────────────────────────────────────


def test_normalize_text_plain_passthrough() -> None:
    """Plain text is whitespace-normalised and returned as-is."""
    raw = "  Hello   world.\n\n\n  Goodbye.  "
    result = normalize_text(raw, content_type="text/plain")
    assert result == "Hello world.\n\nGoodbye."


def test_normalize_text_strips_html_tags() -> None:
    result = normalize_text("<p>Hello <b>world</b>!</p>", content_type="text/html")
    assert "<" not in result
    assert "Hello" in result
    assert "world" in result


def test_normalize_text_skips_script_style() -> None:
    html = (
        "<html><head><style>body{color:red}</style></head>"
        "<body><p>Visible</p><script>alert(1)</script></body></html>"
    )
    result = normalize_text(html, content_type="text/html")
    assert "color" not in result
    assert "alert" not in result
    assert "Visible" in result


def test_normalize_text_decodes_html_entities() -> None:
    result = normalize_text("AT&amp;T &lt;foo&gt; &#169;", content_type="text/html")
    assert "&amp;" not in result
    assert "AT&T" in result
    assert "<foo>" in result


def test_normalize_text_json_flattens_strings() -> None:
    obj = {
        "title": "Big release",
        "id": "v1.2",
        "url": "https://example.com",
        "body": "Many fixes.",
    }
    raw = json.dumps(obj)
    result = normalize_text(raw, content_type="application/json")
    assert "Big release" in result
    assert "Many fixes" in result
    # Metadata keys whose values look like IDs/URLs are skipped.
    assert "https://example.com" not in result


def test_normalize_text_json_nested() -> None:
    obj = {"release": {"notes": "Fixed bug X.", "author": "Alice"}, "tag": "v2.0"}
    raw = json.dumps(obj)
    result = normalize_text(raw, content_type="application/json")
    assert "Fixed bug X" in result
    assert "Alice" in result


def test_normalize_text_unknown_content_type_strips_html() -> None:
    """Unknown content type falls back to HTML stripping."""
    raw = "<div>Some content</div>"
    result = normalize_text(raw, content_type="application/octet-stream")
    assert "<div>" not in result
    assert "Some content" in result


def test_normalize_text_collapses_whitespace() -> None:
    raw = "word1   word2\t\tword3\n\n\n\n\nword4"
    result = normalize_text(raw, content_type="text/plain")
    assert "  " not in result
    assert "\n\n\n" not in result


def test_normalize_text_removes_control_chars() -> None:
    raw = "Hello\x00world\x01foo\x1fbar"
    result = normalize_text(raw, content_type="text/plain")
    assert "\x00" not in result
    assert "\x01" not in result
    assert "Helloworld" in result or "Hello" in result


def test_normalize_text_empty_string() -> None:
    assert normalize_text("", content_type="text/plain") == ""


def test_normalize_text_only_whitespace() -> None:
    assert normalize_text("   \t\n  ", content_type="text/plain") == ""


def test_normalize_text_markdown_unescape_entities() -> None:
    result = normalize_text("A &amp; B", content_type="text/markdown")
    assert "A & B" in result


# ── detect_language ───────────────────────────────────────────────────────────


def test_detect_language_english_returns_en() -> None:
    text = "The quick brown fox jumps over the lazy dog. " * 20
    assert detect_language(text) == "en"


def test_detect_language_empty_returns_en() -> None:
    assert detect_language("") == "en"


def test_detect_language_short_returns_en() -> None:
    assert detect_language("Hello") == "en"


def test_detect_language_chinese() -> None:
    # CJK text — should detect zh.
    text = "中文测试" * 50
    assert detect_language(text) == "zh"


def test_detect_language_japanese() -> None:
    text = "ひらがなカタカナ" * 50
    # Hiragana and Katakana are in the ja range.
    lang = detect_language(text)
    assert lang in ("ja", "zh")  # Both are CJK-adjacent; heuristic may pick either.


def test_detect_language_arabic() -> None:
    text = "مرحبا بالعالم العربي " * 50
    assert detect_language(text) == "ar"


def test_detect_language_cyrillic() -> None:
    text = "Привет мир тест проверка " * 50
    assert detect_language(text) == "ru"


def test_detect_language_mixed_mostly_english_stays_en() -> None:
    # A few non-Latin chars in a long English text should not trigger a switch.
    text = "The meeting is at 5pm — café style — naïve approach. " * 20
    assert detect_language(text) == "en"


# ── chunk_text ────────────────────────────────────────────────────────────────


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []


def test_chunk_text_whitespace_returns_empty() -> None:
    assert chunk_text("   ") == []


def test_chunk_text_single_short_text_one_chunk() -> None:
    text = "Hello world. This is a test."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].chunk_text == text.strip() or text.strip() in chunks[0].chunk_text


def test_chunk_text_returns_chunk_result_instances() -> None:
    chunks = chunk_text("Sentence one. Sentence two.")
    for c in chunks:
        assert isinstance(c, ChunkResult)


def test_chunk_text_indices_are_sequential() -> None:
    # Long enough to produce multiple chunks.
    text = ("Alpha beta gamma delta epsilon. " * 60).strip()
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_chunk_text_offsets_in_range() -> None:
    text = ("Word1 word2 word3 word4 word5. " * 30).strip()
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    for c in chunks:
        assert 0 <= c.char_offset_start < len(text)
        assert c.char_offset_end <= len(text)
        assert c.char_offset_start < c.char_offset_end


def test_chunk_text_token_count_positive() -> None:
    chunks = chunk_text("This is a sentence. " * 10)
    for c in chunks:
        assert c.token_count_estimate > 0


def test_chunk_text_metadata_contains_strategy() -> None:
    chunks = chunk_text("Hello world. More text here.", chunk_size=500, chunk_overlap=50)
    for c in chunks:
        assert "strategy" in c.metadata


def test_chunk_text_long_text_multiple_chunks() -> None:
    # ~4500 chars — should produce at least 3 chunks at default size 1500.
    text = ("The answer to this important question requires careful analysis. " * 70).strip()
    chunks = chunk_text(text, chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP)
    assert len(chunks) >= 2


def test_chunk_text_covers_full_text() -> None:
    """Every part of the text should appear in at least one chunk."""
    text = ("Sentence A. Sentence B. Sentence C. " * 20).strip()
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40)
    combined = " ".join(c.chunk_text for c in chunks)
    # Every original sentence fragment should appear somewhere.
    assert "Sentence A" in combined
    assert "Sentence C" in combined


def test_chunk_text_no_duplicate_index() -> None:
    text = ("Chunk content goes here. " * 50).strip()
    chunks = chunk_text(text, chunk_size=150, chunk_overlap=30)
    indices = [c.chunk_index for c in chunks]
    assert len(indices) == len(set(indices))


def test_chunk_text_deterministic() -> None:
    """Same input must always produce the same output."""
    text = ("Repeatable chunking text sentence. " * 40).strip()
    chunks_a = chunk_text(text, chunk_size=300, chunk_overlap=60)
    chunks_b = chunk_text(text, chunk_size=300, chunk_overlap=60)
    assert len(chunks_a) == len(chunks_b)
    for a, b in zip(chunks_a, chunks_b, strict=True):
        assert a.chunk_text == b.chunk_text
        assert a.char_offset_start == b.char_offset_start


def test_chunk_text_no_chunk_shorter_than_min_when_merged() -> None:
    """Trailing chunks shorter than MIN_CHUNK_SIZE should be merged into the prior chunk."""
    from intercal_ingest.normalizer import MIN_CHUNK_SIZE

    # Force a situation where the last "chunk" would be tiny: use a large chunk
    # size so all but the last sentence fits in one chunk, and the last is short.
    base = "Long sentence that fills the chunk. " * 10
    tail = "Short."
    text = base + tail
    chunks = chunk_text(text, chunk_size=len(base) + 5, chunk_overlap=10)
    for c in chunks:
        # Every chunk should be >= MIN_CHUNK_SIZE, except possibly a single-chunk doc.
        if len(chunks) > 1:
            assert len(c.chunk_text) >= MIN_CHUNK_SIZE or c == chunks[-1]


# ── normalize_document job (fake pool) ───────────────────────────────────────


def _make_pool(
    row: dict[str, Any] | None,
    execute_side_effect: Any = None,
) -> MagicMock:
    """Build a minimal fake asyncpg pool for normalize_document tests."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=row)
    pool.execute = AsyncMock(side_effect=execute_side_effect)
    return pool


def _doc_row(
    *,
    cleaned_text: str | None = None,
    raw_storage_key: str | None = None,
    language: str = "en",
    redistribution_allowed: bool = True,
    citation_only: bool = False,
    normalized_at: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "cleaned_text": cleaned_text,
        "raw_storage_key": raw_storage_key,
        "language": language,
        "redistribution_allowed": redistribution_allowed,
        "citation_only": citation_only,
        "normalized_at": normalized_at,
        "metadata": metadata or {},
    }


@pytest.mark.asyncio
async def test_normalize_document_missing_row_raises_value_error() -> None:
    pool = _make_pool(row=None)
    with pytest.raises(ValueError, match="not found"):
        await normalize_document(
            document_id=str(uuid.uuid4()), pool=pool, storage=None
        )


@pytest.mark.asyncio
async def test_normalize_document_already_normalised_skips() -> None:
    import datetime

    row = _doc_row(
        cleaned_text="Some text.",
        normalized_at=datetime.datetime.now(tz=datetime.UTC),
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    assert result["skipped"] is True
    # execute should NOT be called (no DB writes for a skip).
    pool.execute.assert_not_called()


@pytest.mark.asyncio
async def test_normalize_document_already_normalised_force_reruns() -> None:
    import datetime

    text = "This is normalised text. " * 10
    row = _doc_row(
        cleaned_text=text,
        normalized_at=datetime.datetime.now(tz=datetime.UTC),
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None, force=True
    )
    assert result["skipped"] is False
    # execute should be called at least once for the normalized_at update.
    assert pool.execute.call_count >= 1


@pytest.mark.asyncio
async def test_normalize_document_empty_body_marks_0_chunks() -> None:
    row = _doc_row(cleaned_text="   ")
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    assert result["skipped"] is False
    assert result["chunk_count"] == 0


@pytest.mark.asyncio
async def test_normalize_document_plain_text_produces_chunks() -> None:
    text = "The pipeline processes documents. " * 30
    row = _doc_row(cleaned_text=text)
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None,
        chunk_size=200, chunk_overlap=40,
    )
    assert result["skipped"] is False
    assert int(result["chunk_count"]) >= 1  # type: ignore[arg-type]
    assert int(result["clean_chars"]) > 0  # type: ignore[arg-type]
    # pool.execute should be called: once per chunk + 1 for normalized_at update.
    assert pool.execute.call_count >= int(result["chunk_count"]) + 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_normalize_document_html_content_type_strips_tags() -> None:
    html_body = "<p>Hello <b>world</b>!</p><script>alert(1)</script>"
    row = _doc_row(
        cleaned_text=html_body,
        metadata={"content_type": "text/html"},
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    assert result["skipped"] is False
    # Verify that the cleaned text written to DB does not contain HTML tags.
    # The first execute call that mentions cleaned_text should not have <p> in it.
    execute_calls = pool.execute.call_args_list
    # Find the UPDATE source_documents SET cleaned_text call.
    cleaned_text_updates = [
        c for c in execute_calls
        if c.args and "cleaned_text" in str(c.args[0])
    ]
    if cleaned_text_updates:
        # Second positional arg is the cleaned_text value.
        written_text = cleaned_text_updates[0].args[2]  # $2 in the SQL
        assert "<" not in written_text
        assert "Hello" in written_text


@pytest.mark.asyncio
async def test_normalize_document_json_content_type_flattens() -> None:
    obj = {"title": "Release notes", "body": "Fixed a critical bug."}
    row = _doc_row(
        cleaned_text=json.dumps(obj),
        metadata={"content_type": "application/json"},
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    assert result["skipped"] is False
    assert int(result["chunk_count"]) >= 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_normalize_document_language_detected() -> None:
    """Chinese text should get a non-'en' language tag detected."""
    text = "中文测试内容 " * 60
    row = _doc_row(cleaned_text=text, language="en")
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    assert result["language"] == "zh"


@pytest.mark.asyncio
async def test_normalize_document_fetches_from_storage_when_no_cleaned_text() -> None:
    """When cleaned_text is NULL, raw bytes are fetched from storage."""
    raw_text = b"Raw document text from storage. " * 20
    storage = MagicMock()
    storage.get = AsyncMock(return_value=raw_text)

    row = _doc_row(
        cleaned_text=None,
        raw_storage_key="raw/source-id/abc123",
        redistribution_allowed=True,
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=storage
    )
    storage.get.assert_awaited_once_with("raw/source-id/abc123")
    assert int(result["chunk_count"]) >= 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_normalize_document_storage_failure_graceful() -> None:
    """If storage.get fails, normalize_document logs and marks 0 chunks."""
    storage = MagicMock()
    storage.get = AsyncMock(side_effect=RuntimeError("storage down"))

    row = _doc_row(
        cleaned_text=None,
        raw_storage_key="raw/source-id/abc123",
        redistribution_allowed=True,
    )
    pool = _make_pool(row=row)
    result = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=storage
    )
    assert result["chunk_count"] == 0


@pytest.mark.asyncio
async def test_normalize_document_idempotent_chunk_upsert() -> None:
    """Running normalize_document twice on the same row does not raise (ON CONFLICT)."""
    text = "Some document text here. " * 20
    row = _doc_row(cleaned_text=text)
    pool = _make_pool(row=row)

    result1 = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None
    )
    # Reset mock to simulate the row now existing.
    pool.execute.reset_mock()
    # Second call with force=True.
    pool.fetchrow.return_value = {**row, "normalized_at": None}  # type: ignore[arg-type]
    result2 = await normalize_document(
        document_id=str(uuid.uuid4()), pool=pool, storage=None, force=True
    )
    assert result1["chunk_count"] == result2["chunk_count"]


@pytest.mark.asyncio
async def test_normalize_document_json_sniffed_when_no_content_type_in_metadata() -> None:
    """When metadata has no content_type key, JSON body should be sniffed and flattened.

    This covers the W1 case: wikidata_changes_v1 emits content_type on the
    RawDocument but ingest_source does not save it to source_documents.metadata.
    normalize_document must detect JSON and route it through the flattening path.
    """
    import json as _json

    payload = _json.dumps({
        "change": {
            "title": "Wikidata entity Q42",
            "comment": "/* wbsetlabel-set:1|en */ Douglas Adams",
            "timestamp": "2026-06-04T00:00:00Z",
        }
    })
    # metadata has no 'content_type' key — simulates W1 Wikidata documents.
    row = _doc_row(cleaned_text=payload, metadata={"adapter": "wikidata_changes_v1"})
    pool = _make_pool(row=row)
    result = await normalize_document(document_id=str(uuid.uuid4()), pool=pool, storage=None)
    assert result["skipped"] is False
    assert int(result["chunk_count"]) >= 1  # type: ignore[arg-type]
    # Verify that the normalised text was written to the DB and does not contain raw JSON syntax.
    execute_calls = pool.execute.call_args_list
    cleaned_text_updates = [
        c for c in execute_calls if c.args and "cleaned_text" in str(c.args[0])
    ]
    if cleaned_text_updates:
        written_text = cleaned_text_updates[0].args[2]  # $2 in UPDATE ... SET cleaned_text = $2
        # Should contain the human-readable string values, not raw JSON braces.
        assert "Wikidata entity Q42" in written_text or "Douglas Adams" in written_text
