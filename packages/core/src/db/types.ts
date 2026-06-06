/**
 * Kysely table interfaces for the tables the query layer reads.
 *
 * SQL-first migrations in `db/` are authoritative. This interface mirrors them for typed
 * reads only and is regenerable with `kysely-codegen` against a live database. It is NOT a
 * schema source of truth — never use it to create or alter tables.
 *
 * pg returns `numeric` as a string and `timestamptz` as a JS `Date`; types reflect that.
 */

import type { ColumnType, Generated } from 'kysely';

type Json = unknown;

/** A timestamptz column that the DB defaults (now()) on insert/update — optional on insert. */
type DefaultedTimestamp = ColumnType<Date, Date | undefined, Date>;

export interface EntitiesTable {
  id: string;
  type_id: string;
  canonical_name: string;
  description: string | null;
  current_state: Json;
  importance_score: string; // numeric
  first_seen_at: Date;
  last_updated_at: Date;
  is_deprecated: boolean;
  merged_into_id: string | null;
  // Set when is_deprecated = true (merge/duplicate/error/split).
  deprecated_at: Date | null;
  deprecation_reason: string | null;
}

export interface EntityAliasesTable {
  id: string;
  entity_id: string;
  alias: string;
  alias_type: string;
  language: string;
  is_primary: boolean;
}

export interface EntityExternalIdsTable {
  id: string;
  entity_id: string;
  namespace: string;
  external_id: string;
  url: string | null;
}

export interface RelationshipsTable {
  id: string;
  type_id: string;
  subject_entity_id: string;
  object_entity_id: string;
  valid_from: Date | null;
  valid_until: Date | null;
  recorded_at: Date;
  confidence: string; // numeric
  source_document_ids: string[];
  claim_ids: string[];
  is_active: boolean;
  is_deprecated: boolean;
}

export interface ClaimsTable {
  id: string;
  subject_entity_id: string | null;
  subject_text: string;
  predicate: string;
  object_entity_id: string | null;
  object_text: string;
  qualifiers: Json;
  normalized_text: string;
  raw_quote: string | null;
  valid_from: Date | null;
  valid_until: Date | null;
  extraction_confidence: string; // numeric
  source_document_ids: string[];
  contradiction_status: string;
  status: string;
  // claims has no dedicated transaction-time column (unlike relationships/fact_versions).
  // created_at is the row's transaction time — when Intercal recorded the claim — and is the
  // source for the contract's required Claim.recordedAt. updated_at tracks last mutation.
  created_at: Date;
  updated_at: Date;
}

export interface ClaimEvidenceTable {
  id: string;
  claim_id: string;
  document_id: string;
  // 'supports' | 'partially_supports' | 'contradicts' | 'neutral'.
  support_strength: string;
  confidence: string; // numeric
  char_offset_start: number | null;
  char_offset_end: number | null;
  quote_excerpt: string | null;
  created_at: Date;
}

export interface ClaimContradictionsTable {
  id: string;
  claim_a_id: string;
  claim_b_id: string;
  // 'rule' | 'model' | 'human' — how the contradiction was detected.
  detection_method: string;
  confidence: string; // numeric
  description: string | null;
  // 'open' | 'resolved' | 'dismissed' — only 'open' rows are live contradictions.
  resolution_status: string;
  resolved_claim_id: string | null;
  resolved_at: Date | null;
  resolved_by: string | null;
  created_at: Date;
}

export interface FactVersionsTable {
  id: string;
  // 'entity' | 'relationship' | 'claim' — what the version describes (polymorphic FK).
  fact_subject_type: string;
  fact_subject_id: string;
  // JSON snapshot of the subject's state at this version.
  payload: Json;
  valid_from: Date | null;
  valid_until: Date | null;
  // recorded_at is the transaction-time axis: when Intercal recorded this version. Immutable.
  recorded_at: Date;
  source_document_ids: string[];
  claim_ids: string[];
  confidence: string | null; // numeric
  // is_current = false marks a superseded historical version.
  is_current: boolean;
  // Set on the OLD row when a newer version supersedes it (append-only correction).
  superseded_by_id: string | null;
  superseded_at: Date | null;
  produced_by: string;
}

export interface SourceDocumentsTable {
  id: string;
  source_id: string;
  content_hash: string;
  external_id: string | null;
  url: string | null;
  title: string | null;
  language: string;
  published_at: Date | null;
  ingested_at: Date;
  cleaned_text: string | null;
  document_type: string | null;
  redistribution_allowed: boolean;
  citation_only: boolean;
}

export interface SourcesTable {
  id: string;
  slug: string;
  name: string;
  is_active: boolean;
  last_run_at: Date | null;
  reliability_score: string | null;
}

export interface IngestionRunsTable {
  id: string;
  source_id: string;
  status: string;
  started_at: Date | null;
  finished_at: Date | null;
}

/**
 * API keys (db/migrations/0020_api_keys.sql). ONLY the hash is stored — the raw key is shown once
 * at issuance and never persisted. `scopes` is a jsonb array of scope strings. A key is usable only
 * when `is_active = true`, `revoked_at IS NULL`, and (`expires_at IS NULL OR expires_at > now()`).
 */
export interface ApiKeysTable {
  id: Generated<string>;
  name: string;
  key_prefix: string;
  key_hash: string;
  // jsonb string[] — written as a JSON string on insert, read as a parsed array.
  scopes: ColumnType<string[], string, string>;
  owner_type: Generated<string>; // 'user' | 'service' | 'system'
  owner_id: string | null;
  requests_per_minute: number | null;
  requests_per_day: number | null;
  is_active: Generated<boolean>;
  expires_at: Date | null;
  last_used_at: Date | null;
  revoked_at: Date | null;
  revoked_by: string | null;
  revocation_reason: string | null;
  metadata: ColumnType<Json, string, string>;
  created_at: DefaultedTimestamp;
  updated_at: DefaultedTimestamp;
}

/**
 * Usage events (db/migrations/0021_usage_events.sql). Operational per-request records consumed by
 * Plan 04 W6 observability. No PII beyond the key id and (optionally) anonymized caller context.
 */
export interface UsageEventsTable {
  id: Generated<string>;
  api_key_id: string | null;
  tool_name: string;
  request_id: string | null;
  status_code: number | null;
  latency_ms: number | null;
  error_code: string | null;
  token_budget: number | null;
  tokens_used: number | null;
  entity_count: number | null;
  claim_count: number | null;
  document_count: number | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: DefaultedTimestamp;
}

export interface Database {
  entities: EntitiesTable;
  entity_aliases: EntityAliasesTable;
  entity_external_ids: EntityExternalIdsTable;
  relationships: RelationshipsTable;
  claims: ClaimsTable;
  claim_evidence: ClaimEvidenceTable;
  claim_contradictions: ClaimContradictionsTable;
  fact_versions: FactVersionsTable;
  source_documents: SourceDocumentsTable;
  sources: SourcesTable;
  ingestion_runs: IngestionRunsTable;
  api_keys: ApiKeysTable;
  usage_events: UsageEventsTable;
}
