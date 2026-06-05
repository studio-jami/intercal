# Plan 02 W3 — Mention/claim extraction audit fixes

Date: 2026-06-05
Type: fix
Services: intercal-extract, intercal-shared

## Summary

Second fresh-context audit of Workstream 3 (mention and claim extraction). The
first pass landed `extract_mentions` (rule baseline + LLM augment) and
`extract_claims` (LLM-only, `raw_spans` provenance, redistribution-gated
quotes). This pass closed two correctness defects and one extraction-quality
defect, all while preserving the port/adapter seam.

## Changes

### Provenance offset corruption (critical) — `services/extract/jobs.py`

Document-level character offsets for mentions and claim evidence were computed
as `chunk.char_offset_start + llm_local_offset`. But `document_chunks.chunk_text`
is a re-joined, whitespace-collapsed variant of its source region (the W2
chunker strips sentence edges and joins sentences with a single space), so
chunk-text offsets do **not** align with `cleaned_text` wherever the region
contained a newline or repeated whitespace. Every persisted span past such a
point drifted: `cleaned_text[start:end]` no longer reconstructed the
mention/quote. A false provenance pointer is corruption.

- Added `anchor_span()`: locates the verbatim span text within the chunk's known
  region of `cleaned_text` (exact match, then whitespace-flexible, then a
  whole-document fallback) and returns document offsets that satisfy the
  provenance invariant — `cleaned_text[start:end]` reconstructs the span.
- `extract_mentions` anchors each candidate by its `text_span`; spans that
  cannot be located are **dropped**, never stored with a fabricated offset.
- `extract_claims` slices the candidate quote from `chunk_text` using the LLM's
  local offsets, then anchors that verbatim quote into `cleaned_text`; the
  persisted offsets and `raw_quote` / `raw_spans.text` are the anchored slice
  (so they agree exactly). Unanchorable evidence → NULL offsets + no quote, with
  `chunk_id` still recording provenance.

### Claim under-extraction — `services/shared/adapters/llm_gemini.py`

On the 2.5 "thinking" models, reasoning tokens are drawn from the same
`max_output_tokens` budget; a thinking spike truncated the structured-extraction
JSON mid-object, so the whole chunk parse-failed (after retries) and yielded
zero claims — the real reason the first pass got only 1 claim from 2 documents.
`extract_structured` now sets `thinking_config.thinking_budget=0` (verified
against google-genai 2.8.0), spending the full budget on the answer and making
schema-bound extraction deterministic. `complete()` is unchanged.

### Claim prompt — `services/extract/jobs.py`

Sharpened to decompose compound sentences into atomic claims and extract
liberally, while remaining explicitly factual-only (no fabrication, no inference
beyond the text).

## Tests

+8 W3 regression tests (245 service tests pass; lint + typecheck clean):
`anchor_span` (region match, whitespace-flexible, absent → None, region
preference), mention offset-reconstruction under whitespace drift,
unanchorable-LLM-mention drop, anchored claim quote/offset agreement, and
NULL-span-when-unanchorable.

## Live verification

On a dedicated Neon branch, using the **real** W2 normalizer to produce real
drifted chunks, then the real W3 jobs through the live LLM port:

- Vertex (primary): 20 mentions + 9 claims persisted, 0 span-reconstruction
  failures (2974 in / 1100 out tokens, 5 chunks).
- Gemini-key (fallback): 20 mentions + 3 claims, 0 span-reconstruction failures.
- Idempotent re-run: DB counts == persisted counts (no duplication).
- Error taxonomy exercised live: Vertex 429 → `LlmRateLimitError`; Gemini 503 →
  transient — both non-fatal with graceful per-chunk degrade.

Verification branch deleted after the run.
