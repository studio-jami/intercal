# Plan 02 Claim-Entity Linking — no-false-link audit fix

Date: 2026-06-05
Type: fix
Services: intercal-resolve

## Summary

Second fresh-context audit of the claim-end entity-linking bridge (W3 claims →
W6 entities → W7 relationships). Pass 1 landed `link_claim_entities` +
`_link_one_end` (exact-mention-span / exact-name / embedding-cosine, conservative
floors), the `link-claim-entities` CLI, 12 tests, and two predicate-vocab
additions. This pass closes one no-false-link precision gap (corruption-class) and
re-proves the loop on a relationship-rich real source. Stays in the linking lane;
W7's skip-not-fabricate contract and the port/adapter seams are untouched; W8
remains `NotImplementedError("Plan 02 …")`.

## Change (`services/resolve/src/intercal_resolve/jobs.py`)

- **Ambiguous exact-name match could mis-link.** The linking job's exact-name /
  alias path is intentionally type-agnostic (claim ends can be any type), unlike
  W6's name match which is scoped by `type_id`. `entities.canonical_name` is not
  unique (only a non-unique `lower(canonical_name)` index), so the same surface
  form can match two genuinely distinct live entities (e.g. "Apple" the company
  vs. the concept). The original two separate `LIMIT 1` lookups picked one
  arbitrarily at confidence 0.85 — a false link, which corrupts the relationship
  graph exactly as a false entity merge does. Replaced with a single unioned
  `SELECT DISTINCT entity_id … LIMIT 2` over canonical names + aliases; a link is
  written **only when exactly one** distinct live entity matches. True ambiguity
  (>1) is left NULL — conservative, never guessed.

## Verified correct — no change

- **Embedding-cosine floor is principled, not demo-tuned.** `LINK_COSINE_THRESHOLD
  = 0.10` (cosine similarity ≥ 0.90) is strictly stricter than W6's 0.15 merge /
  0.40 review bands. The mention-span path (doc-scoped, conf 0.90) and the
  nearest-neighbour embedding path were already safe and are unchanged.
- **Predicate-vocab additions are FK-valid and semantically sound.** `is_a →
  entity_instance_of_concept` and `located_in → organization_headquartered_in` are
  both seeded `relationship_types` ids. `organization_headquartered_in` presumes an
  org subject, but W7 does no subject-type validation for any of the 20 mappings
  (pre-existing, out of the linking lane) — flagged for a future type-aware
  predicate pass, not corruption-class.

## Tests

+1 regression test pins ambiguity rejection (two distinct same-name live entities
→ NULL, no UPDATE issued). 346 service tests pass; `pnpm py:lint` +
`pnpm py:typecheck` clean (0 errors).

## Live verification

Throwaway Neon branch (forked from default, migrations applied, deleted after) —
relationship-rich real source end-to-end through the real pipeline, no mocks, no
synthetic claims:

- **W1** real GitHub-releases adapter → **rust-lang/rust** release notes (6 real
  docs, live api.github.com) → **W2** normalize (42 chunks) → **W3** real LLM
  extraction (Gemini `gemini-2.5-flash`, live HTTP): **151 claims**, ~1013
  mentions → **W5** embed → **W6** resolve (209 entities, 0 false auto-merges) →
  **link-claim-entities**: 87 claims linked (60 subject + 52 object ends), 25
  fully linked; methods `exact_mention_span` (60) + `embedding_cosine` (52); 190
  ends left NULL (conservative).
- **W7 derive_relationships: 4 relationships** from genuinely-linked real claims
  (`entity_instance_of_concept`: `LazyCell<T,F>` / `assert_matches!` /
  `AssertUnwindSafe<T>` / `Vec::into_raw_parts` → `Stabilized APIs`), each with
  claim_ids + source_document_ids provenance. `write_fact_versions` wrote
  append-only versions; re-run skipped.
- **Adversarial no-false-link:** two distinct live entities both named "Mercury" +
  a "Mercury" claim → left NULL (ambiguity rejected). Control: deprecating one
  left exactly one live → the same claim then linked to the survivor (`exact_name`,
  0.85), never the deprecated row.
- **Idempotency:** link re-run → 0 new / 0 churn; derive re-run → 0 new; fact
  versions → skipped. Throwaway branch deleted after the run.
