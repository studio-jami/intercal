# db/

This directory owns Intercal's SQL schema: forward-only migration files and idempotent seed files.

The database is the product's canonical source of truth. Migrations and constraints are not hidden behind ORM abstractions.

---

## Directory layout

```
db/
  migrations/   Forward-only .sql files applied in filename order
  seeds/        Idempotent .sql files for stable reference vocabularies
  README.md     This file
```

---

## Running migrations

The migration runner is `scripts/dev/migrate.mjs`. Use the root-level pnpm scripts:

| Command | What it does |
|---|---|
| `pnpm db:migrate:clean` | Drops and recreates the target database, then applies all migrations in order |
| `pnpm db:migrate:seeded` | Same as clean, but also runs all seed files after migrations |
| `pnpm db:check` | Applies migrations without dropping; reports drift from the current schema |

The runner reads `DATABASE_URL` from the environment (`.env` or shell). See `docs/operations/development.md` for local setup.

---

## Migration convention

- Files are numbered with four zero-padded digits: `0001_extensions.sql`, `0002_entity_types.sql`, etc.
- Each file is pure, idempotent-safe SQL: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE EXTENSION IF NOT EXISTS`.
- Files are applied in strict filename order by the runner.
- Each file should be focused on a single logical concern (one table group or one schema change).

### Forward-fix policy (no down-migrations)

There are no rollback scripts. The policy is **forward-fix only**:

- Mistakes are corrected by writing a new migration that alters or drops the incorrect object.
- Never modify a migration file that has already been applied to any environment. Create a new numbered file instead.
- This keeps the migration log as a faithful record of schema history and avoids the unreliability of rollback scripts on production data.

If a migration is applied and found to be wrong before the schema reaches a shared environment, it may be deleted and replaced — but only if it has never been applied outside the developer's local database.

---

## Seed convention

- Seed files live in `db/seeds/` and are numbered separately from migrations.
- Every seed must be idempotent: `INSERT ... ON CONFLICT DO NOTHING`.
- Seeds populate stable vocabularies only: `entity_types` and `relationship_types`.
- Application data is never seeded here; use fixture scripts in `scripts/fixtures/` for test data.

---

## Bitemporal model

Intercal uses two independent time axes, required for reliable cutoff-gap queries:

| Column | Meaning |
|---|---|
| `valid_from` / `valid_until` | When the fact is or was **true in the world**. `valid_until = NULL` = open interval (still true). |
| `recorded_at` | When Intercal **learned or recorded** it. |

These are independent:
- A historical fact (e.g. valid 1990–2000) may be recorded today (`recorded_at = now()`).
- A fact recorded today may later be corrected by inserting a new version — never updating the old row.

The `fact_versions` table is the primary bitemporal store. Append-only: never `UPDATE` or `DELETE` existing rows. Corrections insert a new row and set `superseded_by_id` on the old one.

---

## Role / Office separation

Roles (`entity_types.id = 'role'`) and offices (`entity_types.id = 'office'`) are **separate entity types**, not aliases for their current holder.

- "CEO of OpenAI" is an entity of type `role`, not an alias for the current person holding it.
- "US Secretary of State" is an entity of type `office`.
- Temporal occupancy is modeled as a `relationship` with type `person_holds_role` or `person_holds_office`, with `valid_from` and `valid_until` recording the term.

This is a hard architectural requirement for historical correctness. Never add a person's name as an alias for a role/office entity.

---

## Embeddings: model, dim, and vector-space safety

Every embedding row carries:

| Column | Purpose |
|---|---|
| `model` | The exact versioned model name used to produce the vector (e.g. `bge-small-en-v1.5`) |
| `dim` | The number of dimensions (e.g. `384`) |

**Critical rule:** Vectors from different models or different dimensions represent different vector spaces and **must not be mixed in the same HNSW index**.

The default embedding model is `bge-small-en-v1.5` (384 dims), stored as `halfvec(384)`.

If a different-dimension model is adopted (e.g. `bge-base-en-v1.5` at 768 dims), a **new migration must add a new column or table** — the existing `halfvec(384)` columns cannot accept 768-dim vectors.

`halfvec` uses 2-byte floats, halving index size vs `vector` (4-byte floats) at no material recall loss for cosine similarity search.

HNSW indexes are created with `halfvec_cosine_ops`:

```sql
CREATE INDEX ON chunk_embeddings USING hnsw (embedding halfvec_cosine_ops);
```

---

## Table summary

For full responsibility descriptions and invariants, see `docs/architecture/data-model.md`.

| Migration | Tables |
|---|---|
| `0001_extensions.sql` | pgcrypto, vector extensions |
| `0002_entity_types.sql` | `entity_types` |
| `0003_relationship_types.sql` | `relationship_types` |
| `0004_sources.sql` | `sources` |
| `0005_ingestion_runs.sql` | `ingestion_runs` |
| `0006_source_documents.sql` | `source_documents` |
| `0007_document_chunks.sql` | `document_chunks` |
| `0008_entities.sql` | `entities` |
| `0009_entity_aliases.sql` | `entity_aliases` |
| `0010_entity_external_ids.sql` | `entity_external_ids` |
| `0011_entity_resolution.sql` | `entity_resolution_candidates`, `entity_merge_events` |
| `0012_mentions.sql` | `mentions` |
| `0013_claims.sql` | `claims`, `claim_evidence`, `claim_contradictions` |
| `0014_relationships.sql` | `relationships` |
| `0015_fact_versions.sql` | `fact_versions` |
| `0016_embeddings.sql` | `document_embeddings`, `chunk_embeddings`, `entity_embeddings`, `claim_embeddings` |
| `0017_topics.sql` | `topics`, `topic_memberships` |
| `0018_digests.sql` | `digests` |
| `0019_subscriptions.sql` | `subscriptions` |
| `0020_api_keys.sql` | `api_keys` |
| `0021_usage_events.sql` | `usage_events` |
| `0022_audit_events.sql` | `audit_events` |
| `0023_source_documents_normalized.sql` | source document normalized-content fields |
| `0024_embeddings_version_and_fts.sql` | embedding version metadata and full-text search indexes |
| `0025_source_documents_summary_policy.sql` | source document summary-policy snapshot |
| `0026_audit_events_append_only.sql` | `audit_events` UPDATE/DELETE enforcement |
| `0027_audit_events_forbid_truncate.sql` | `audit_events` TRUNCATE enforcement |
| `0028_review_records.sql` | `review_records` |
| `0029_subscription_notifications.sql` | `subscription_notifications`, `subscription_delivery_logs` |
