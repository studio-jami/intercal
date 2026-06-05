/**
 * Kysely table interfaces for the tables the query layer reads.
 *
 * SQL-first migrations in `db/` are authoritative. This interface mirrors them for typed
 * reads only and is regenerable with `kysely-codegen` against a live database. It is NOT a
 * schema source of truth — never use it to create or alter tables.
 *
 * pg returns `numeric` as a string and `timestamptz` as a JS `Date`; types reflect that.
 */

type Json = unknown;

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

export interface Database {
  entities: EntitiesTable;
  entity_aliases: EntityAliasesTable;
  entity_external_ids: EntityExternalIdsTable;
  relationships: RelationshipsTable;
  claims: ClaimsTable;
  fact_versions: FactVersionsTable;
  source_documents: SourceDocumentsTable;
  sources: SourcesTable;
  ingestion_runs: IngestionRunsTable;
}
