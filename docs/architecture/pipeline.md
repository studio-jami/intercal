# Knowledge Pipeline

How source documents become provenance-backed, bitemporal knowledge. The pipeline is the
Python side (`services/*`); it writes canonical data to Postgres through repositories. Deep
algorithm bodies are implemented in Plan 02 — the foundation provides the structure, ports, and
job entrypoints.

## Stages

```
source → ingest → normalize → extract (mentions, claims) → resolve (entities, relationships)
       → fact versions → embeddings → synthesis (digests, freshness, notifications)
```

| Stage | Service | Jobs | Writes |
| --- | --- | --- | --- |
| Ingest | `intercal-ingest` | `ingest_source`, `normalize_document`, `score_source_health`, `cleanup_expired_cache` | `sources`, `ingestion_runs`, `source_documents`, `document_chunks` |
| Extract | `intercal-extract` | `extract_mentions`, `extract_claims` | `mentions`, `claims`, `claim_evidence` |
| Resolve | `intercal-resolve` | `resolve_entities`, `derive_relationships`, `write_fact_versions` | `entities`, `entity_resolution_candidates`, `entity_merge_events`, `relationships`, `fact_versions` |
| Embed | (in `intercal-shared` ports, invoked per stage) | embeddings via `EmbeddingsPort` | `document_embeddings`, `chunk_embeddings`, `entity_embeddings`, `claim_embeddings` |
| Synthesize | `intercal-synthesize` | `build_digest`, `recompute_freshness`, `notify_subscribers` | `digests`, freshness state, subscription deliveries |

## Invariants (enforced in schema; see [`data-model.md`](data-model.md))

- **Idempotency:** re-running a job must not duplicate documents, claims, relationships, or fact
  versions. `source_documents.content_hash` is globally unique.
- **Provenance:** every claim used in a public answer traces to `claim_evidence` →
  `source_documents`. Relationships and fact versions are *derived from claims*, not free-floating.
- **Conservative resolution:** false non-merges are acceptable; false merges are corruption.
  Merges go through `entity_resolution_candidates` and are reversible via `entity_merge_events`.
- **Roles/offices are separate entities**, not aliases for their occupants (historical correctness).
- **Bitemporal facts:** `valid_from`/`valid_until` (world time) vs `recorded_at` (transaction
  time); fact history is append-only.
- **Source policy:** `redistribution_allowed` / `citation_only` on sources and documents gate
  what may be stored or exposed, before broad ingestion.

## Execution / scheduling

Jobs run as portable CLI entrypoints (`python -m intercal_<service> <job>`), invoked locally,
by a GitHub Actions scheduled workflow (zero-cost on the public repo), by Modal, or by cron —
all behind the `SchedulerPort`. See [`../../scripts/workers/README.md`](../../scripts/workers/README.md).
