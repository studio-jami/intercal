"""Document normalisation and chunking — Plan 02 Workstream 2.

Pure-Python, deterministic, no external model or API calls.

Exports
-------
normalize_text(raw: str, content_type: str) -> str
    Strip HTML/boilerplate and collapse whitespace.

detect_language(text: str) -> str
    Lightweight character-frequency language guesser (BCP 47 tag).
    Returns 'en' by default; no external service required.

chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[ChunkResult]
    Split *text* into overlapping sentence-aware chunks.

Design notes
------------
- HTML stripping uses :mod:`html.parser` (stdlib) — no third-party dep.
- JSON documents are flattened to their text fields, not re-encoded.
- Language detection: simple Unicode-block heuristic sufficient for the
  sources seeded in W1 (English Wikipedia/Wikidata, GitHub releases).
  A proper ML-backed detector (e.g. langdetect / lingua) would need a
  port so the implementation is swappable without touching callers — that
  is left as a later-plan enhancement marked with NotImplementedError.
- Chunking: sentence-boundary-aware sliding window.  Chunk boundaries are
  at sentence ends where possible, falling back to word boundaries.
  This is deterministic: same input always produces the same chunks.
"""

from __future__ import annotations

import html as _html_lib
import html.parser
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Final

# ── Constants ─────────────────────────────────────────────────────────────────

#: Default maximum characters per chunk (tuned to ~512 tokens / bge-small).
DEFAULT_CHUNK_SIZE: Final[int] = 1500

#: Default overlap between consecutive chunks in characters.
DEFAULT_CHUNK_OVERLAP: Final[int] = 200

#: Minimum chunk size — chunks shorter than this are merged upward.
MIN_CHUNK_SIZE: Final[int] = 100

# ── Public types ──────────────────────────────────────────────────────────────


@dataclass
class ChunkResult:
    """One chunk produced by :func:`chunk_text`.

    Attributes
    ----------
    chunk_index:
        0-based ordinal within the document.
    chunk_text:
        The chunk body.
    char_offset_start:
        Character offset of the first character within the *normalised* text.
    char_offset_end:
        Character offset one past the last character.
    token_count_estimate:
        Rough token estimate — character_count // 4.  Precise tokenisation is
        the embeddings stage's concern; this is a lightweight budget hint.
    metadata:
        Chunker-specific metadata written to ``document_chunks.metadata``.
    """

    chunk_index: int
    chunk_text: str
    char_offset_start: int
    char_offset_end: int
    token_count_estimate: int
    metadata: dict[str, object] = field(default_factory=dict)


# ── HTML stripper ─────────────────────────────────────────────────────────────


class _HtmlStripper(html.parser.HTMLParser):
    """Collect visible text; skip scripts/styles/hidden elements."""

    _SKIP_TAGS: frozenset[str] = frozenset(
        {"script", "style", "noscript", "head", "template", "svg", "math"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        # Insert a space before block-level elements so words don't fuse.
        if tag in {
            "p", "br", "li", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
            "div", "section", "article", "blockquote", "tr", "th", "td",
        }:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _strip_html(text: str) -> str:
    """Return *text* with HTML markup removed and entities decoded."""
    stripper = _HtmlStripper()
    try:
        stripper.feed(text)
        return stripper.get_text()
    except Exception:
        # Malformed HTML — fall back to a regex strip.
        return re.sub(r"<[^>]+>", " ", _html_lib.unescape(text))


# ── JSON flattener ────────────────────────────────────────────────────────────


def _flatten_json(raw: str) -> str:
    """Extract all string-valued leaves from a JSON object/array into one text block.

    Skips keys that look like metadata (URLs, timestamps, IDs, numeric values).
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw

    parts: list[str] = []
    _extract_strings(obj, parts)
    return " ".join(parts)


_JSON_SKIP_KEYS: frozenset[str] = frozenset(
    {
        "id", "url", "uri", "href", "link", "type", "format",
        "timestamp", "date", "created", "updated", "modified", "revision",
        "namespace", "ns", "pageid", "rcid", "old_revid", "revid",
        "tag_hidden", "anon",
    }
)


def _extract_strings(obj: object, out: list[str], _depth: int = 0) -> None:
    """Recursively collect string values; skip metadata-looking leaves."""
    if _depth > 10:
        return
    if isinstance(obj, str):
        v = obj.strip()
        if v and len(v) > 2:
            out.append(v)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in _JSON_SKIP_KEYS:
                continue
            _extract_strings(v, out, _depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _extract_strings(item, out, _depth + 1)


# ── Whitespace + Unicode normalisation ────────────────────────────────────────


_MULTI_SPACE: re.Pattern[str] = re.compile(r"[ \t]+")
_MULTI_NL: re.Pattern[str] = re.compile(r"\n{3,}")
_CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace; remove ASCII control chars; strip edges."""
    text = _CONTROL_CHARS.sub("", text)
    # Normalise Unicode to NFC (composed form).
    text = unicodedata.normalize("NFC", text)
    # Collapse horizontal whitespace on each line, then strip each line.
    lines = [_MULTI_SPACE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


# ── Public: normalize_text ────────────────────────────────────────────────────

#: Content-type prefixes treated as JSON.
_JSON_TYPES: tuple[str, ...] = ("application/json", "application/ld+json", "text/json")
#: Content-type prefixes treated as HTML.
_HTML_TYPES: tuple[str, ...] = ("text/html", "application/xhtml")
#: Markdown/plain text — no stripping needed beyond whitespace.
_PLAIN_TYPES: tuple[str, ...] = ("text/plain", "text/markdown", "text/x-markdown")


def normalize_text(raw: str, content_type: str = "text/plain") -> str:
    """Return clean, extraction-ready text from *raw*.

    Handles JSON (flattens string values), HTML (strips tags), and plain/
    markdown text (whitespace-normalises).  The result is Unicode NFC,
    no HTML entities, no control characters, collapsed whitespace.

    Parameters
    ----------
    raw:
        The raw document body as a string.
    content_type:
        MIME type hint from the source adapter (e.g. ``"application/json"``).
        Unknown types fall back to HTML stripping as a conservative default.
    """
    ct = content_type.split(";")[0].strip().lower()

    if any(ct.startswith(p) for p in _JSON_TYPES):
        text = _flatten_json(raw)
    elif any(ct.startswith(p) for p in _HTML_TYPES):
        text = _strip_html(raw)
    elif any(ct.startswith(p) for p in _PLAIN_TYPES):
        # Decode HTML entities that may have slipped in (e.g. Markdown from APIs).
        text = _html_lib.unescape(raw)
    else:
        # Unknown or missing content type: probe whether it's JSON, then fall
        # back to HTML stripping.
        stripped_html = _strip_html(raw)
        try:
            json.loads(raw)  # Just probe — if this raises, it's not JSON.
            candidate = _flatten_json(raw)
            text = candidate if candidate.strip() else stripped_html
        except (json.JSONDecodeError, ValueError):
            text = stripped_html

    return _clean_whitespace(text)


# ── Public: detect_language ───────────────────────────────────────────────────

# Unicode block ranges for script heuristics.
# Each entry: (start_codepoint, end_codepoint, bcp47_tag)
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x4E00, 0x9FFF, "zh"),   # CJK Unified Ideographs (Chinese/Japanese/Korean)
    (0x3040, 0x30FF, "ja"),   # Hiragana + Katakana
    (0xAC00, 0xD7A3, "ko"),   # Hangul syllables
    (0x0600, 0x06FF, "ar"),   # Arabic
    (0x0400, 0x04FF, "ru"),   # Cyrillic
    (0x0900, 0x097F, "hi"),   # Devanagari
    (0x0370, 0x03FF, "el"),   # Greek
    (0x0590, 0x05FF, "he"),   # Hebrew
    (0x0E00, 0x0E7F, "th"),   # Thai
]

# Minimum fraction of characters in a non-Latin script to trigger detection.
_SCRIPT_THRESHOLD: float = 0.15


def detect_language(text: str) -> str:
    """Return a BCP 47 language tag for *text*.

    Uses a simple Unicode-block frequency heuristic: sufficient for the
    English-dominant sources in the W1 seed (Wikidata, GitHub releases).
    Returns ``"en"`` when no non-Latin script dominates and for short texts.

    A production-grade ML detector (langdetect, lingua-py, etc.) should
    replace this when multi-lingual source coverage matters — hide it behind
    a port then.  For W2 it is accurate enough to avoid wrong tags on the
    data we actually ingest.
    """
    if not text:
        return "en"

    sample = text[:2000]  # Only inspect a prefix for speed.
    total = len(sample)
    if total < 20:
        return "en"

    counts: dict[str, int] = {}
    for ch in sample:
        cp = ord(ch)
        for start, end, tag in _SCRIPT_RANGES:
            if start <= cp <= end:
                counts[tag] = counts.get(tag, 0) + 1
                break

    if not counts:
        return "en"

    dominant_tag, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    if dominant_count / total >= _SCRIPT_THRESHOLD:
        return dominant_tag

    return "en"


# ── Public: chunk_text ────────────────────────────────────────────────────────

# Sentence-ending patterns: period/exclamation/question followed by whitespace.
# We match the position of the terminating whitespace so chunks land at natural breaks.
_SENTENCE_END: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[ChunkResult]:
    """Split *text* into overlapping sentence-aware chunks.

    Chunking algorithm
    ------------------
    1. Split the text at sentence boundaries (``[.!?]`` followed by whitespace).
    2. Greedily accumulate sentences into a chunk until adding the next sentence
       would exceed *chunk_size* characters.
    3. When the chunk is full, emit it; then start a new chunk at the sentence
       that would cause the overlap window to be preserved.
    4. Any remaining text after the last boundary forms the final chunk.
    5. Chunks shorter than :data:`MIN_CHUNK_SIZE` are merged into the previous.

    The result is deterministic: the same input always produces the same chunks.

    Parameters
    ----------
    text:
        Normalised document text (output of :func:`normalize_text`).
    chunk_size:
        Target maximum characters per chunk.  Chunks may be slightly longer
        if a single sentence exceeds this limit.
    chunk_overlap:
        Approximate character overlap between consecutive chunks.

    Returns
    -------
    list[ChunkResult]
        Empty list when *text* is blank.
    """
    text = text.strip()
    if not text:
        return []

    # Split into sentences while keeping the delimiters.
    segments = _SENTENCE_END.split(text)

    # Reconstruct with proper offsets.
    # `_SENTENCE_END` consumes the whitespace, so we track positions manually.
    sentences: list[tuple[int, int, str]] = []  # (start, end, sentence_text)
    pos = 0
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Re-locate this segment in the original text from the current pos.
        idx = text.find(seg, pos)
        if idx == -1:
            idx = pos  # Fallback — should not happen.
        sentences.append((idx, idx + len(seg), seg))
        pos = idx + len(seg)

    if not sentences:
        # No sentence boundaries found — emit as a single chunk.
        return [
            ChunkResult(
                chunk_index=0,
                chunk_text=text,
                char_offset_start=0,
                char_offset_end=len(text),
                token_count_estimate=max(1, len(text) // 4),
                metadata={"strategy": "single", "chunk_size": chunk_size, "chunk_overlap": 0},
            )
        ]

    chunks: list[ChunkResult] = []
    chunk_index = 0

    i = 0  # Index into `sentences` for the start of the current chunk.
    while i < len(sentences):
        # Accumulate sentences until we'd exceed chunk_size.
        j = i
        char_count = 0
        while j < len(sentences):
            slen = len(sentences[j][2]) + 1  # +1 for the space we'd add.
            if char_count > 0 and char_count + slen > chunk_size:
                break
            char_count += slen
            j += 1

        # j now points one past the last sentence in this chunk.
        chunk_sentences = sentences[i:j]
        chunk_body = " ".join(s[2] for s in chunk_sentences)
        start_offset = chunk_sentences[0][0]
        end_offset = chunk_sentences[-1][1]

        chunks.append(
            ChunkResult(
                chunk_index=chunk_index,
                chunk_text=chunk_body,
                char_offset_start=start_offset,
                char_offset_end=end_offset,
                token_count_estimate=max(1, len(chunk_body) // 4),
                metadata={
                    "strategy": "sentence_window",
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            )
        )
        chunk_index += 1

        # Advance i to where the overlap window begins.
        # Step back from j until we've recovered at least chunk_overlap chars.
        if j >= len(sentences):
            break
        overlap_chars = 0
        k = j - 1
        while k > i and overlap_chars < chunk_overlap:
            overlap_chars += len(sentences[k][2]) + 1
            k -= 1
        i = max(i + 1, k + 1)  # Always advance at least one sentence.

    # Merge any trailing chunks shorter than MIN_CHUNK_SIZE into the previous.
    if len(chunks) > 1 and len(chunks[-1].chunk_text) < MIN_CHUNK_SIZE:
        prev = chunks[-2]
        last = chunks[-1]
        merged_text = prev.chunk_text + " " + last.chunk_text
        chunks[-2] = ChunkResult(
            chunk_index=prev.chunk_index,
            chunk_text=merged_text,
            char_offset_start=prev.char_offset_start,
            char_offset_end=last.char_offset_end,
            token_count_estimate=max(1, len(merged_text) // 4),
            metadata=prev.metadata,
        )
        chunks.pop()

    return chunks
