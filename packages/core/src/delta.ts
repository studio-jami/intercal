/**
 * `getDelta` body — the "what changed since my cutoff" digest (Plan 03 W5).
 *
 * DESIGN: deterministic, not LLM-synthesised. The contract's `DeltaResponse` carries the change
 * set *structurally* — `changedClaims: Claim[]` (each with its own `evidence: Citation[]` and
 * `confidence`), `changedEntities: EntitySummary[]`, and a `summary: Digest` whose `content` is a
 * short prose lede plus a citation-numbered list of the actual changes. Every asserted line in the
 * digest is built from a real row and is traceable to a source document, so there is nothing to
 * fabricate. We deliberately do NOT call an LLM here:
 *   - No LLM client exists in `packages/core`, and adding provider logic past the port boundary
 *     would violate the adapter rule (AGENTS.md "Hard rules").
 *   - The steering for this workstream prefers a correct, deterministic, fully-cited digest over an
 *     uncited LLM blob. Optional provider-backed prose polishing is a later seam: it would sit
 *     behind `LlmPort` and may only rephrase content that is already grounded in these citations —
 *     it can never introduce an un-cited assertion.
 *
 * TEMPORAL AXIS: "what changed since the cutoff" means TRANSACTION time — when Intercal *recorded*
 * the change — not world/valid time. Claims use `created_at` (their transaction-time column;
 * `claims` has no `recorded_at`); relationships and fact_versions use `recorded_at`. The window is
 * `(since, until]`.
 *
 * CHANGE UNITS: the substrate's canonical change record is the append-only `fact_versions` table
 * (Plan 02 W7) — a new version (or a supersession of an older one) recorded in the window is a real
 * change even when the underlying entity row is older. The contract's `DeltaResponse` has no
 * fact-version field, so we map fact-version changes into the shape it does carry: the version's
 * subject entity joins `changedEntities` (windowed on the version's `recorded_at`, NOT only on the
 * entity's `last_updated_at`, which is written earlier in the pipeline and would miss the version),
 * its supersession/new-assertion counts are reported in the digest lede, and its backing source
 * documents are rolled into the digest citations. Changed entities are also still detected via
 * `last_updated_at`; the two signals are unioned and deduped by id so a change is never double-counted.
 *
 * TOKEN BUDGET: the response is bounded to `token_budget` (default from resource-budget profiles).
 * Items are ranked most-important first — recency (newer transaction time), then confidence, then
 * evidence weight — and trimmed until the estimated token cost fits. The digest reports exactly
 * what was included vs omitted so a budget-trimmed answer is never silently lossy.
 */
import type { components } from '@intercal/shared';
import type { Db } from './db/client.js';
import type {
  ClaimsTable,
  EntitiesTable,
  FactVersionsTable,
  RelationshipsTable,
} from './db/types.js';
import { mapClaim, mapEntity, mapRelationship } from './mappers.js';

type S = components['schemas'];
type Claim = S['Claim'];
type Citation = S['Citation'];
type EntitySummary = S['EntitySummary'];

export interface DeltaParams {
  topic: string;
  since_date: string;
  token_budget?: number;
  until_date?: string;
}

// Token-budget profiles. The contract's `token_budget` is an explicit override; absent that we
// default to the "standard" profile. These map to the resource-budget doc's notion of compact /
// standard / expanded delivery sizes (docs/operations/resource-budget.md).
const DEFAULT_TOKEN_BUDGET = 1500;
const MIN_TOKEN_BUDGET = 200;
const MAX_TOKEN_BUDGET = 8000;

// ~4 chars/token is the standard rough heuristic for English text; deterministic and provider-free.
// We over-estimate slightly (round up) so a budgeted response never overshoots in practice.
const estimateTokens = (text: string): number => Math.ceil(text.length / 4);

function clampBudget(n: number | undefined): number {
  const v = n ?? DEFAULT_TOKEN_BUDGET;
  if (!Number.isFinite(v)) return DEFAULT_TOKEN_BUDGET;
  return Math.min(MAX_TOKEN_BUDGET, Math.max(MIN_TOKEN_BUDGET, Math.floor(v)));
}

function staleness(from: Date | null): string | undefined {
  if (!from) return undefined;
  const days = Math.floor((Date.now() - from.getTime()) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return '1 day';
  return `${days} days`;
}

/**
 * Resolve a free-text `topic` to the set of entity IDs it names (canonical name OR alias, exact,
 * case-insensitive). Returns an empty array when the topic is not a known entity — the delta then
 * falls back to a text match over the claim columns, so a topic like "WebCrypto" that was never
 * resolved to an entity still surfaces its changed claims.
 */
async function resolveTopicEntityIds(db: Db, topic: string): Promise<string[]> {
  const lower = topic.toLowerCase();
  const [byName, byAlias] = await Promise.all([
    db
      .selectFrom('entities')
      .select('id')
      .where('is_deprecated', '=', false)
      .where((eb) => eb(eb.fn('lower', ['canonical_name']), '=', lower))
      .execute(),
    db
      .selectFrom('entity_aliases')
      .select('entity_id')
      .where((eb) => eb(eb.fn('lower', ['alias']), '=', lower))
      .execute(),
  ]);
  const ids = new Set<string>();
  for (const r of byName) ids.add(r.id);
  for (const r of byAlias) ids.add(r.entity_id);
  return [...ids];
}

/** Cost (in estimated tokens) of rendering one claim as a digest bullet, including its citation. */
function claimLineCost(claim: Claim, index: number): number {
  return estimateTokens(renderClaimLine(claim, index));
}

/** One human-readable, citation-numbered line for a changed claim. */
function renderClaimLine(claim: Claim, index: number): string {
  const when = claim.recordedAt.slice(0, 10);
  const subject = claim.subject?.trim() || claim.normalizedText;
  const body = claim.normalizedText?.trim() || `${subject} ${claim.predicate} ${claim.object}`;
  const conf = claim.confidence ? ` (confidence ${claim.confidence.score.toFixed(2)})` : '';
  return `${index}. [${when}] ${body}${conf}`;
}

/**
 * Rank changed claims most-important first for budget trimming:
 *   1. recency of transaction time (newer first) — "what changed" leads with the latest,
 *   2. extraction confidence (higher first),
 *   3. evidence weight (more citing documents first).
 * Deterministic total order (ties broken by id) so the same query is byte-stable.
 */
function rankClaims(a: ClaimsTable, b: ClaimsTable): number {
  const t = b.created_at.getTime() - a.created_at.getTime();
  if (t !== 0) return t;
  const c = Number(b.extraction_confidence) - Number(a.extraction_confidence);
  if (c !== 0) return c;
  const e = (b.source_document_ids?.length ?? 0) - (a.source_document_ids?.length ?? 0);
  if (e !== 0) return e;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

export async function buildDelta(db: Db, params: DeltaParams): Promise<S['DeltaResponse']> {
  const since = new Date(params.since_date);
  const until = params.until_date ? new Date(params.until_date) : undefined;
  const budget = clampBudget(params.token_budget);

  const topicEntityIds = await resolveTopicEntityIds(db, params.topic);
  const pattern = `%${params.topic}%`;

  // ── Changed claims: transaction time (created_at) in (since, until], scoped to topic ──
  // Scope = claims about a resolved topic entity OR whose text mentions the topic. We pull a
  // generous candidate cap (200) ordered newest-first, then rank + budget-trim in memory; the cap
  // bounds DB work while the budget bounds the response.
  let claimQuery = db
    .selectFrom('claims')
    .selectAll()
    .where('status', '=', 'active')
    .where('created_at', '>', since)
    .where((eb) => {
      const scopes = [
        eb('subject_text', 'ilike', pattern),
        eb('object_text', 'ilike', pattern),
        eb('normalized_text', 'ilike', pattern),
      ];
      if (topicEntityIds.length > 0) {
        scopes.push(eb('subject_entity_id', 'in', topicEntityIds));
        scopes.push(eb('object_entity_id', 'in', topicEntityIds));
      }
      return eb.or(scopes);
    });
  if (until) claimQuery = claimQuery.where('created_at', '<=', until);
  const claimRows = (await claimQuery.orderBy('created_at', 'desc').limit(200).execute()).sort(
    rankClaims,
  );

  // ── Changed relationships: recorded_at in (since, until], touching a topic entity ──
  let relRows: RelationshipsTable[] = [];
  if (topicEntityIds.length > 0) {
    let relQuery = db
      .selectFrom('relationships')
      .selectAll()
      .where('is_deprecated', '=', false)
      .where('recorded_at', '>', since)
      .where((eb) =>
        eb.or([
          eb('subject_entity_id', 'in', topicEntityIds),
          eb('object_entity_id', 'in', topicEntityIds),
        ]),
      );
    if (until) relQuery = relQuery.where('recorded_at', '<=', until);
    relRows = await relQuery.orderBy('recorded_at', 'desc').limit(50).execute();
  }

  // ── Fact-version changes: the canonical "change" unit (Plan 02 W7). ──────────────────────────
  // fact_versions is the append-only bitemporal record of what Intercal believes; a NEW version
  // recorded in (since, until] is a real change even when the underlying entity row's
  // last_updated_at predates the cutoff (the version is written as the FINAL pipeline stage, so its
  // recorded_at is reliably >= the entity's last_updated_at — confirmed in production). Scoping
  // changed entities ONLY on last_updated_at therefore silently drops fact-version-level changes,
  // including supersessions. We window on the version's transaction time (recorded_at) instead.
  const factSubjectScope = new Set<string>(topicEntityIds);
  for (const c of claimRows) {
    if (c.subject_entity_id) factSubjectScope.add(c.subject_entity_id);
    if (c.object_entity_id) factSubjectScope.add(c.object_entity_id);
  }
  let factVersionRows: FactVersionsTable[] = [];
  if (factSubjectScope.size > 0) {
    let fvQuery = db
      .selectFrom('fact_versions')
      .selectAll()
      .where('fact_subject_type', '=', 'entity')
      .where('fact_subject_id', 'in', [...factSubjectScope])
      .where('recorded_at', '>', since);
    if (until) fvQuery = fvQuery.where('recorded_at', '<=', until);
    factVersionRows = await fvQuery.orderBy('recorded_at', 'desc').limit(200).execute();
  }

  // ── Changed entities: union of (a) entities whose last_updated_at moved in the window and
  // (b) entities that had a fact version recorded in the window (the authoritative change record).
  // Deduped by id in the assembler so a change is never double-counted. EntitySummary is compact by
  // contract (id/type/displayName), so these are cheap and we include all of them.
  const entityIdsInPlay = new Set<string>(factSubjectScope);
  for (const fv of factVersionRows) entityIdsInPlay.add(fv.fact_subject_id);
  let entityRows: EntitiesTable[] = [];
  if (entityIdsInPlay.size > 0) {
    // Pull every in-scope live entity touched in the window by EITHER signal. We filter to the
    // window-or-fact-version set in the assembler; fetching the candidates here keeps one round-trip.
    const fvSubjectIds = new Set(factVersionRows.map((fv) => fv.fact_subject_id));
    let entQuery = db
      .selectFrom('entities')
      .selectAll()
      .where('is_deprecated', '=', false)
      .where('id', 'in', [...entityIdsInPlay])
      .where((eb) => {
        const touched = eb('last_updated_at', '>', since);
        // An entity with a fact version in the window is changed even if last_updated_at is older.
        if (fvSubjectIds.size > 0) {
          return eb.or([touched, eb('id', 'in', [...fvSubjectIds])]);
        }
        return touched;
      });
    if (until) entQuery = entQuery.where('last_updated_at', '<=', until);
    entityRows = await entQuery.orderBy('last_updated_at', 'desc').limit(100).execute();
  }

  // ── Citations need url + publishedAt; fetch the source docs backing the candidate change set
  // once, then the pure assembler picks the ones backing the INCLUDED items. ───────────────────
  const allDocIds = new Set<string>();
  for (const c of claimRows) for (const id of c.source_document_ids) allDocIds.add(id);
  for (const r of relRows) for (const id of r.source_document_ids) allDocIds.add(id);
  for (const fv of factVersionRows) for (const id of fv.source_document_ids) allDocIds.add(id);
  const docMeta =
    allDocIds.size > 0
      ? await db
          .selectFrom('source_documents')
          .select(['id', 'url', 'published_at'])
          .where('id', 'in', [...allDocIds])
          .execute()
      : [];

  return assembleDigest({
    params,
    since,
    until,
    budget,
    topicEntityIds,
    claimRows,
    relRows,
    entityRows,
    factVersionRows,
    docMeta,
  });
}

/** Source-document provenance needed to build digest-level citations. */
export interface DocMeta {
  id: string;
  url: string | null;
  published_at: Date | null;
}

/** Inputs to the pure digest assembler — the already-fetched, topic-scoped, window-filtered rows. */
export interface AssembleInput {
  params: DeltaParams;
  since: Date;
  until: Date | undefined;
  budget: number;
  topicEntityIds: string[];
  claimRows: ClaimsTable[];
  relRows: RelationshipsTable[];
  entityRows: EntitiesTable[];
  /** Fact-version rows recorded in the window (the canonical change unit; may be empty). */
  factVersionRows?: FactVersionsTable[];
  docMeta: DocMeta[];
}

/**
 * Pure, DB-free assembly of the `DeltaResponse` from fetched rows: rank → token-budget trim →
 * cite → score → render. Separated from `buildDelta` so the budget/citation/confidence/freshness
 * logic is unit-testable without a live database. `claimRows` is expected pre-sorted by
 * `rankClaims` (newest/most-confident first); we sort defensively so the function is total.
 */
export function assembleDigest(input: AssembleInput): S['DeltaResponse'] {
  const { params, since, until, budget, topicEntityIds, entityRows, docMeta } = input;
  const claimRows = [...input.claimRows].sort(rankClaims);
  const relRows = input.relRows;
  const factVersionRows = input.factVersionRows ?? [];

  // ── Fact-version changes (the canonical bitemporal change unit). ──────────────────────────────
  // A row recorded in the window that is NO LONGER current (is_current = false) was CLOSED in the
  // window — i.e. a supersession event happened: a newer version replaced it. A current row in the
  // window for a subject WITHOUT such a closed predecessor is a freshly recorded assertion. We
  // classify from the in-window rows alone (no extra query) and never double-count a subject.
  const supersededSubjectIds = new Set<string>();
  for (const fv of factVersionRows) {
    if (!fv.is_current || fv.superseded_by_id) supersededSubjectIds.add(fv.fact_subject_id);
  }
  const supersessionCount = factVersionRows.filter(
    (fv) => !fv.is_current || fv.superseded_by_id,
  ).length;
  // New assertions: current rows whose subject was not also superseded in-window.
  const newAssertionSubjectIds = new Set<string>();
  for (const fv of factVersionRows) {
    if (fv.is_current && !fv.superseded_by_id && !supersededSubjectIds.has(fv.fact_subject_id)) {
      newAssertionSubjectIds.add(fv.fact_subject_id);
    }
  }
  const newAssertionCount = newAssertionSubjectIds.size;

  // ── Lede (built before trimming so its real token cost can be reserved exactly). ─────────────
  // The lede uses only window-fixed totals (claimRows.length, relationship + fact-version counts),
  // so it does not depend on how many lines survive the budget trim.
  const sinceLabel = params.since_date.slice(0, 10);
  const scopeNote =
    topicEntityIds.length > 0
      ? `${topicEntityIds.length} resolved entit${topicEntityIds.length === 1 ? 'y' : 'ies'}`
      : 'text match (topic not a resolved entity)';
  const factVersionNote = (() => {
    const parts: string[] = [];
    if (supersessionCount > 0) {
      parts.push(`${supersessionCount} fact${supersessionCount === 1 ? '' : 's'} superseded`);
    }
    if (newAssertionCount > 0) {
      parts.push(
        `${newAssertionCount} new fact version${newAssertionCount === 1 ? '' : 's'} recorded`,
      );
    }
    return parts.join(', ');
  })();
  const changedRelationships = relRows.map(mapRelationship);
  const hasAnyChange =
    claimRows.length > 0 || changedRelationships.length > 0 || factVersionRows.length > 0;
  let lede: string;
  if (!hasAnyChange) {
    lede = `No recorded changes about "${params.topic}" since ${sinceLabel}.`;
  } else {
    const extras: string[] = [];
    if (changedRelationships.length > 0) {
      extras.push(
        `${changedRelationships.length} relationship change${changedRelationships.length === 1 ? '' : 's'}`,
      );
    }
    if (factVersionNote) extras.push(factVersionNote);
    lede =
      `${claimRows.length} claim change${claimRows.length === 1 ? '' : 's'} recorded about "${params.topic}" since ${sinceLabel}` +
      (extras.length > 0 ? ` (plus ${extras.join(', ')})` : '') +
      `; scope: ${scopeNote}.`;
  }

  // ── Token-budget trimming ──────────────────────────────────────────────────────────────────
  // Reserve the lede's MEASURED cost plus a small footer allowance; spend the rest on ranked claim
  // lines. Each accepted claim contributes its mapped Claim (with evidence) to changedClaims and its
  // line to the digest content; we stop when the next line would exceed the budget. Reserving the
  // real lede cost (not a fixed guess) guarantees the rendered content never exceeds the budget.
  const FOOTER_RESERVE = 40; // tokens for the included/omitted footer line
  const leadReserve = estimateTokens(lede) + FOOTER_RESERVE;
  let spent = leadReserve;
  const includedClaims: ClaimsTable[] = [];
  const lines: string[] = [];
  for (const row of claimRows) {
    const mapped = mapClaim(row);
    const cost = claimLineCost(mapped, includedClaims.length + 1);
    if (spent + cost > budget) break;
    spent += cost;
    includedClaims.push(row);
    lines.push(renderClaimLine(mapped, includedClaims.length));
  }
  const omittedClaims = claimRows.length - includedClaims.length;

  const changedClaims: Claim[] = includedClaims.map(mapClaim);
  const changedEntities: EntitySummary[] = entityRows.map((e) => {
    const summary = mapEntity(e, [], []);
    return { id: summary.id, type: summary.type, displayName: summary.displayName };
  });

  // ── Citations: aggregate the source documents backing the INCLUDED items, enriched with
  // url + publishedAt so every digest line is traceable to real provenance. (Claim.evidence
  // already carries the per-claim sourceDocumentId; this is the digest-level roll-up.) ──────────
  const citedDocIds = new Set<string>();
  for (const c of includedClaims) for (const id of c.source_document_ids) citedDocIds.add(id);
  for (const r of relRows) for (const id of r.source_document_ids) citedDocIds.add(id);
  // Fact-version provenance is real change-evidence: roll its backing docs into the digest citations
  // so the supersession/new-assertion note in the lede is itself traceable, never an un-cited claim.
  for (const fv of factVersionRows) for (const id of fv.source_document_ids) citedDocIds.add(id);
  const docById = new Map(docMeta.map((d) => [d.id, d]));
  const citations: Citation[] = [...citedDocIds].map((id) => {
    const d = docById.get(id);
    return {
      sourceDocumentId: id,
      ...(d?.url ? { url: d.url } : {}),
      ...(d?.published_at ? { publishedAt: d.published_at.toISOString() } : {}),
    };
  });

  // ── Confidence: the mean extraction confidence of the included claims, method-labelled so the
  // caller knows it is an aggregate over evidence, not a single model score. Empty change set →
  // confidence 0 (nothing to assert). ─────────────────────────────────────────────────────────
  const confidenceScore =
    includedClaims.length === 0
      ? 0
      : includedClaims.reduce((sum, c) => sum + Number(c.extraction_confidence), 0) /
        includedClaims.length;

  // ── Freshness: newest transaction time across the changed set; coverage = fraction of changed
  // claims we could fit in the budget. ────────────────────────────────────────────────────────
  let latestChange = claimRows.reduce<Date | null>(
    (max, c) => (max === null || c.created_at > max ? c.created_at : max),
    null,
  );
  // A fact-version recorded after the newest claim is the freshest transaction-time change.
  for (const fv of factVersionRows) {
    if (latestChange === null || fv.recorded_at > latestChange) latestChange = fv.recorded_at;
  }
  const coverage = claimRows.length === 0 ? 1 : includedClaims.length / claimRows.length;
  const freshness: S['FreshnessReport'] = {
    target: params.topic,
    lastUpdated: latestChange ? latestChange.toISOString() : undefined,
    coverage,
    staleness: staleness(latestChange),
  };

  // ── Digest content: the pre-built deterministic prose lede + the citation-numbered change lines +
  // a footer that reports exactly what was included vs trimmed. Nothing here is un-cited. ─────────
  const footerParts: string[] = [];
  if (omittedClaims > 0) {
    footerParts.push(
      `${includedClaims.length} of ${claimRows.length} changes shown within the ${budget}-token budget; ${omittedClaims} omitted (most-recent/most-confident first).`,
    );
  } else if (includedClaims.length > 0) {
    footerParts.push(`All ${includedClaims.length} changes fit within the ${budget}-token budget.`);
  }
  const content = [lede, ...lines, footerParts.join(' ')].filter((s) => s.length > 0).join('\n');

  return {
    topic: params.topic,
    since: since.toISOString(),
    ...(until ? { until: until.toISOString() } : {}),
    summary: {
      topicOrEntity: params.topic,
      tokenBudget: budget,
      content,
      citations,
      freshness,
      generatedAt: new Date().toISOString(),
    },
    changedClaims,
    changedEntities,
    confidence: { score: confidenceScore, method: 'aggregate_extraction' },
    freshness,
  };
}
