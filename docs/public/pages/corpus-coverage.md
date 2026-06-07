# Corpus And Backfill Coverage

Intercal's target corpus is GPT-era AI history from November 2022 onward: model releases, model cards, lab announcements, research papers, standards, SDK/framework releases, benchmarks, regulation, runtime infrastructure, and selected MediaWiki revisions.

## Current proof status

The current live code has:

- historical adapters behind `SourcePort`;
- reviewed first-proof and broad-corpus seed/catalog scripts;
- quality gates for seeded proof, live first proof, and live full proof;
- query proofs for entity point-in-time reads, freshness, deltas, claim verification, evidence search, contradictions, and source-policy restricted-body behavior.

The broad live proof is a bounded reviewed slice. It is enough to prove machinery and public query paths. It is not continuous full-web saturation and should not be described that way.

## Quality gates

Run gates against a migrated database:

```powershell
node scripts/dev/verify-corpus-quality-gates.mjs seeded-proof
node scripts/dev/verify-corpus-quality-gates.mjs live-first-proof
node scripts/dev/verify-corpus-quality-gates.mjs live-full
```

Seeded mode rolls back probe rows. Live modes require reviewed source rows and backfilled evidence in the target database.

## Backfill posture

Historical backfill uses the same worker path as scheduled ingestion. Operators bound it by source class, date range, source count, document count, and dry-run/apply mode. It must create provenance-bearing source documents, claims, evidence links, and fact versions. It must not insert shortcut facts that bypass the provenance chain.

## Public coverage language

Public coverage claims must stay no broader than the last passing live gate. A passing seeded proof proves the verifier and query machinery only.
