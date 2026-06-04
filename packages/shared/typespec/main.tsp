import "@typespec/http";
import "@typespec/openapi3";
import "@typespec/json-schema";

using Http;
using TypeSpec.JsonSchema;

/**
 * Intercal public contract — the single source of truth.
 * TypeSpec compiles to OpenAPI 3.1 + JSON Schema; TS types and Pydantic models are generated
 * from those. Do not hand-edit generated artifacts.
 */
@service(#{ title: "Intercal API" })
@server("http://localhost:8787", "Local development")
@jsonSchema
namespace Intercal;

// ───────────────────────── Vocabularies ─────────────────────────

enum EntityType {
  person,
  organization,
  place,
  role,
  office,
  product,
  event,
  concept,
  legislation,
  technical_artifact,
  source,
  dataset,
  jurisdiction,
}

enum ClaimStatus {
  proposed,
  active,
  retracted,
  superseded,
}

enum ContradictionState {
  none,
  contested,
  contradicted,
}

enum RelationshipStatus {
  active,
  ended,
  proposed,
}

enum VerificationVerdict {
  supported,
  partially_supported,
  contradicted,
  unverified,
}

// ───────────────────────── Shared value types ─────────────────────────

@doc("A confidence score in [0,1] with the method that produced it.")
model Confidence {
  @minValue(0) @maxValue(1) score: float32;
  method?: string;
}

@doc("A pointer to evidence in a source document. Every public fact must be citable.")
model Citation {
  sourceDocumentId: string;
  quote?: string;
  url?: string;
  publishedAt?: utcDateTime;
}

@doc("An external identifier for an entity (e.g. a Wikidata QID).")
model ExternalId {
  system: string;
  id: string;
}

@doc("How fresh Intercal's knowledge is for a target.")
model FreshnessReport {
  target: string;
  lastUpdated?: utcDateTime;
  lastIngestedAt?: utcDateTime;
  @doc("Fraction of expected sources currently covered, in [0,1].")
  @minValue(0)
  @maxValue(1)
  coverage?: float32;
  staleness?: string;
}

// ───────────────────────── Core primitives ─────────────────────────

@doc("A canonical thing: person, org, place, role/office, product, event, concept, etc.")
model Entity {
  id: string;
  type: EntityType;
  displayName: string;
  aliases?: string[];
  externalIds?: ExternalId[];
  importance?: float32;
  firstSeen?: utcDateTime;
  lastUpdated?: utcDateTime;
  @doc("Denormalized current state; derived from fact versions, not a source of truth.")
  state?: unknown;
}

@doc("A compact entity reference used in deltas and lists.")
model EntitySummary {
  id: string;
  type: EntityType;
  displayName: string;
}

@doc("An atomic factual assertion extracted from source documents.")
model Claim {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  qualifiers?: unknown;
  normalizedText: string;
  @doc("When the claim is/was true in the world (bitemporal valid time).")
  validFrom?: utcDateTime;
  validUntil?: utcDateTime;
  @doc("When Intercal recorded the claim (bitemporal transaction time).")
  recordedAt: utcDateTime;
  confidence: Confidence;
  status: ClaimStatus;
  contradiction: ContradictionState;
  evidence: Citation[];
}

@doc("A typed temporal edge between entities, derived from claims and evidence.")
model Relationship {
  id: string;
  type: string;
  fromEntityId: string;
  toEntityId: string;
  validFrom?: utcDateTime;
  validUntil?: utcDateTime;
  recordedAt: utcDateTime;
  confidence: Confidence;
  status: RelationshipStatus;
  sourceDocumentIds: string[];
}

@doc("Immutable ingested evidence.")
model SourceDocument {
  id: string;
  sourceId: string;
  title?: string;
  url?: string;
  publishedAt?: utcDateTime;
  ingestedAt: utcDateTime;
  language?: string;
  contentHash: string;
  license?: string;
}

@doc("A token-budgeted synthesis built from evidence and graph state. A delivery artifact, not canonical.")
model Digest {
  topicOrEntity: string;
  tokenBudget?: int32;
  content: string;
  citations: Citation[];
  freshness: FreshnessReport;
  generatedAt: utcDateTime;
}

// ───────────────────────── Tool inputs (V1) ─────────────────────────
// These models double as the MCP tool input JSON Schemas and the REST query bindings.

model DeltaQuery {
  @doc("Topic, entity, or claim subject to compute changes for.")
  @query
  topic: string;

  @doc("Return changes recorded since this date (e.g. a model cutoff).")
  @query
  since_date: utcDateTime;

  @query token_budget?: int32;
  @query until_date?: utcDateTime;
}

model EntityQuery {
  @query name_or_id: string;
  @doc("Point-in-time read: entity state as of this date.")
  @query
  at_date?: utcDateTime;
  @query token_budget?: int32;
}

model EvidenceQuery {
  @query query: string;
  @query from_date?: utcDateTime;
  @query to_date?: utcDateTime;
  @query @minValue(1) @maxValue(100) limit?: int32;
}

model VerifyClaimQuery {
  @query claim_text: string;
  @query as_of_date?: utcDateTime;
  @query token_budget?: int32;
}

model SourcesQuery {
  @query entity_or_claim_id: string;
  @query @minValue(1) @maxValue(100) limit?: int32;
}

model FreshnessQuery {
  @query topic_or_entity: string;
}

// ───────────────────────── Tool responses (V1) ─────────────────────────

model DeltaResponse {
  topic: string;
  since: utcDateTime;
  until?: utcDateTime;
  summary: Digest;
  changedClaims: Claim[];
  changedEntities: EntitySummary[];
  confidence: Confidence;
  freshness: FreshnessReport;
}

model EntityResponse {
  entity: Entity;
  asOf?: utcDateTime;
  relationships?: Relationship[];
  facts?: Claim[];
  freshness: FreshnessReport;
}

model EvidenceHit {
  documentId: string;
  snippet: string;
  @minValue(0) score: float32;
  citation: Citation;
}

model EvidenceResponse {
  hits: EvidenceHit[];
  total: int32;
}

model ClaimVerificationResponse {
  claimText: string;
  verdict: VerificationVerdict;
  confidence: Confidence;
  supportingEvidence: Citation[];
  contradictingEvidence: Citation[];
  asOf?: utcDateTime;
}

model SourcesResponse {
  sources: SourceDocument[];
}

@error
@doc("A structured API/tool error.")
model ApiError {
  code: string;
  message: string;
  details?: unknown;
}

// ───────────────────────── Operations (V1 surface) ─────────────────────────

@tag("knowledge")
@route("/v1/delta")
@get
@doc("What changed about a topic since a date, with evidence, confidence, and a token-budgeted summary.")
op getDelta(...DeltaQuery): DeltaResponse | ApiError;

@tag("knowledge")
@route("/v1/entity")
@get
@doc("Entity state, relationships, and fact history, optionally at a point in time.")
op getEntity(...EntityQuery): EntityResponse | ApiError;

@tag("knowledge")
@route("/v1/evidence")
@get
@doc("Search source-grounded evidence by query, date range, and sources.")
op searchEvidence(...EvidenceQuery): EvidenceResponse | ApiError;

@tag("knowledge")
@route("/v1/claims/verify")
@get
@doc("Verify a claim against recorded evidence as of a date.")
op verifyClaim(...VerifyClaimQuery): ClaimVerificationResponse | ApiError;

@tag("knowledge")
@route("/v1/sources")
@get
@doc("List the source documents backing an entity or claim.")
op getSources(...SourcesQuery): SourcesResponse | ApiError;

@tag("knowledge")
@route("/v1/freshness")
@get
@doc("Report how fresh Intercal's knowledge is for a topic or entity.")
op getFreshness(...FreshnessQuery): FreshnessReport | ApiError;
