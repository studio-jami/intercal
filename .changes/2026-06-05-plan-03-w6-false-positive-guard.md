# claim verification — false-positive-support guard

Date: 2026-06-05
Type: fix
Packages: @intercal/core

## Summary

Plan 03 W6 audit pass 2. `verifyClaim` could report the strongest verdict (`supported`)
on mere lexical/vocabulary overlap, not actual claim-level agreement. The verdict path
classified ANY on-topic, same-polarity, non-substrate-contradicted FTS candidate as full
`support`, and emitted `supported` whenever support existed with zero contradiction mass.
Because bag-of-words retrieval is order- and role-blind, a claim that shares tokens with a
stored claim but asserts a *different proposition* (subject/object swapped, a token-subset
of a more specific stored claim) was falsely "supported" — the substrate over-claiming,
which is corruption-adjacent.

Proven against the **deployed** surface: the role-reordered nonsense claim
`"Windows configuration authored the Rust toolchain for Mike McCready"` returned
`verdict: "supported"` (the stored claim is `"Mike McCready authored the add Rust toolchain
automated configuration Windows"` — reversed roles, identical tokens).

## Decision

Lexical evidence can establish topical consistency and polarity but **cannot** establish
propositional identity (no symmetric overlap metric separates a role-swap from true support —
they are token-identical). So the strongest verdict is reserved for near-verbatim agreement,
and lexical-only matches are reported honestly as `partially_supported`. Under-claiming
(`partially_supported` / `unverified`) is the safe failure mode; a false `supported` is not.
Deterministic and provider-free — no LLM crosses the port boundary (unchanged from pass 1).

## Changes

- `packages/core/src/verify.ts`
  - `classify` now grades a SUPPORTING candidate with `supportStrength: 'strong' | 'weak'`:
    `strong` requires high SYMMETRIC content-token coverage (min of both directions ≥ 0.85)
    AND Jaccard ≥ 0.5 (essentially the same claim restated); everything else is `weak`.
  - `assembleVerification` reserves `supported` for ≥1 strong supporter; weak-only support
    (however much) caps at `partially_supported`. Citations/confidence/token-budget and the
    contradiction path are unchanged. No contract field added (`ClaimVerificationResponse`
    already carries the `partially_supported` verdict).
  - Added `coverage()` (directional content-token coverage) and the two strength thresholds
    as named, documented constants for auditability.
- `packages/core/src/verify.test.ts` — +5 deterministic tests (13 → 18): support-strength
  grading (near-verbatim strong; role-reorder weak; buried-subset weak) and the verdict
  demotion (weak-only → `partially_supported`, never `supported`; mixed → `supported`).
- `docs/roadmaps/2026-05-21-intercal-plan-03-agent-surface.md` — W6 audit-pass-2 note.

## Verification

`packages/core`: biome check, `tsc --noEmit`, `vitest run` (55 pass), `tsc` build — all clean.
Live on production Neon (read-only; no branches created/deleted): role-reorder & subset-vague
→ `partially_supported` (was `supported`); fabricated-CVE / wrong-version → `unverified`
(FTS AND guard); positive-of-a-negated-claim → `contradicted`; true-negated → `supported`;
point-in-time flips at the transaction-time boundary (pre-record → `unverified`, post-record
→ `partially_supported`). The fix lands on the live `/api/v1/claims/verify` + MCP
`verify_claim` on the next deploy of `@intercal/core`.
