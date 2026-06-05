# claim verification — tokenizer edge-punctuation fix

Date: 2026-06-05
Type: fix
Packages: @intercal/core

## Summary

Plan 03 W6 audit pass 3. The strong-support gate added in pass 2 compares content-token
sets, but the tokenizer kept `. - _ ' \`` in the token charset so identifier-shaped tokens
survive intact (`Buffer.poolSize`, `1.96.0`, `tls.createServer`, `CVE-2026-5222`). Those same
characters as *boundary* punctuation are sentence noise, not part of the token: a stored claim
ending `"…default to 64 KiB."` tokenized `kib.` while a user's `"…64 KiB"` tokenized `kib`. A
trailing-period mismatch like that dropped an **exact verbatim restatement of a stored claim**
to min-coverage 0.8 (< 0.85) → `weak` → `partially_supported` instead of `supported` — the
substrate refusing to confirm a fact it contains verbatim.

Live-proven on production Neon (read-only; no branches): the deployed `/api/v1/claims/verify`
returns `partially_supported` for `"Buffer.poolSize increased its default to 64 KiB"` even
though that claim is stored verbatim.

## Fix

`tokenize` now strips the boundary-punctuation set `[. - _ ' \`]` from each token's leading and
trailing edges only, preserving interior structure. Two tokens that differ solely by edge
punctuation (`kib.` vs `kib`, `cve-2026-5222.` vs `cve-2026-5222`) compare equal; distinct
identifiers never merge, so the false-positive guard cannot widen — the change can only make a
genuine match score higher, never promote a non-match. (It also tightens negation detection:
`removed.` now matches the NEGATIONS list.)

## Changes

- `packages/core/src/verify.ts` — `tokenize` maps each token through `trimTokenEdges`
  (leading/trailing `[. - _ ' \`]` stripped, interior preserved). No contract or signature
  change; `classify` / `assembleVerification` unchanged.
- `packages/core/src/verify.test.ts` — +2 deterministic tests (18 → 20): exact verbatim
  restatement of a punctuation-terminated stored claim grades `strong`; a fabricated specific
  differing in an interior identifier (wrong CVE id) stays `weak` (guard intact).
- `docs/roadmaps/2026-05-21-intercal-plan-03-agent-surface.md` — W6 audit-pass-3 note.

## Verification

`packages/core`: biome lint, `tsc --noEmit`, `vitest run` (57 pass), `tsc` build — all clean.
Re-verified live on production Neon (read-only; no branches created/deleted) with the corrected
grading: verbatim and verbatim-with-trailing-`.` → min-coverage/Jaccard 1.0 → `strong` →
`supported`; role-swap and fabricated-CVE → `unverified` (FTS AND guard); subset-vague →
`partially_supported`; negation → `contradicted`. Citation integrity confirmed: zero dangling
`source_document_ids` across all active claims. The corrected verdict lands on the live endpoint
+ MCP `verify_claim` on the next deploy of `@intercal/core` (the deployed surface predates W6).
