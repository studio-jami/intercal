/**
 * The shared query-service layer. The REST API and the MCP server both call these — there is
 * one set of query semantics, never two.
 *
 * V1 status: every V1 read — `getEntity`, `getSources`, `getFreshness`, `searchEvidence`,
 * `getDelta`, and `verifyClaim` — is a real read against the canonical schema. The two synthesis
 * bodies live in dedicated modules (`delta.ts`, `verify.ts`) and this file stays a thin dispatch so
 * the REST and MCP surfaces call one set of semantics.
 */
import type { components } from '@intercal/shared';
import type { Db } from './db/client.js';
import type { EntitiesTable } from './db/types.js';
import { buildDelta, type DeltaParams } from './delta.js';
import { NotFoundError } from './errors.js';
import { assembleFreshness, type FreshnessParams } from './freshness.js';
import { mapClaim, mapEntity, mapRelationship, mapSourceDocument } from './mappers.js';
import { buildVerification, type VerifyClaimParams } from './verify.js';

type S = components['schemas'];

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const clampLimit = (n: number | undefined, def = 20) => Math.min(100, Math.max(1, n ?? def));

function staleness(from: Date | null): string | undefined {
  if (!from) return undefined;
  const days = Math.floor((Date.now() - from.getTime()) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return '1 day';
  return `${days} days`;
}

/**
 * Resolve a UUID that may point to a deprecated (merged-away) entity.
 *
 * Decision (W1): when an agent holds a UUID for an entity that has been merged,
 * silently serving the deprecated row as canonical is wrong — it would expose a
 * stale, non-authoritative record with no indication it has been superseded.
 * The right behaviour for an append-only substrate is to be transparent:
 *   - Follow `merged_into_id` up to the surviving (non-deprecated) entity and
 *     return that, so callers automatically get the current canonical record.
 *   - If the chain is unexpectedly broken (survivor missing or also deprecated),
 *     throw `NotFoundError` with the `mergedIntoId` detail so the caller can log
 *     or surface it — never silently return a stale row.
 *
 * We cap the follow-chain at 5 hops to guard against corrupt cycles.
 */
async function resolveIfMerged(db: Db, row: EntitiesTable): Promise<EntitiesTable> {
  let current = row;
  const MAX_HOPS = 5;
  for (let hop = 0; hop < MAX_HOPS; hop++) {
    if (!current.is_deprecated || !current.merged_into_id) return current;
    const survivor = await db
      .selectFrom('entities')
      .selectAll()
      .where('id', '=', current.merged_into_id)
      .executeTakeFirst();
    if (!survivor) {
      throw new NotFoundError(
        `Entity ${row.id} was merged but the survivor entity ${current.merged_into_id} no longer exists.`,
        { mergedIntoId: current.merged_into_id },
      );
    }
    current = survivor;
  }
  // Survived the loop: either we reached a non-deprecated node (returned above)
  // or we hit MAX_HOPS, implying a corrupt cycle.
  if (current.is_deprecated) {
    throw new NotFoundError(
      `Entity ${row.id} merge chain did not resolve to a live entity within ${MAX_HOPS} hops.`,
      { mergedIntoId: current.merged_into_id ?? undefined },
    );
  }
  return current;
}

async function findEntityRow(db: Db, nameOrId: string): Promise<EntitiesTable | undefined> {
  if (UUID.test(nameOrId)) {
    const row = await db
      .selectFrom('entities')
      .selectAll()
      .where('id', '=', nameOrId)
      .executeTakeFirst();
    if (!row) return undefined;
    // Transparently resolve merged-away IDs to their survivor.
    return resolveIfMerged(db, row);
  }
  const byName = await db
    .selectFrom('entities')
    .selectAll()
    .where('is_deprecated', '=', false)
    .where((eb) => eb(eb.fn('lower', ['canonical_name']), '=', nameOrId.toLowerCase()))
    .orderBy('importance_score', 'desc')
    .executeTakeFirst();
  if (byName) return byName;

  // Alias lookup: guard against aliases that have been re-parented to a deprecated entity
  // (can occur transiently during a merge reversal or data-quality correction).
  const alias = await db
    .selectFrom('entity_aliases')
    .select('entity_id')
    .where((eb) => eb(eb.fn('lower', ['alias']), '=', nameOrId.toLowerCase()))
    .executeTakeFirst();
  if (!alias) return undefined;
  return db
    .selectFrom('entities')
    .selectAll()
    .where('id', '=', alias.entity_id)
    .where('is_deprecated', '=', false)
    .executeTakeFirst();
}

export interface EntityParams {
  name_or_id: string;
  at_date?: string;
  token_budget?: number;
}

export async function getEntity(db: Db, params: EntityParams): Promise<S['EntityResponse']> {
  const row = await findEntityRow(db, params.name_or_id);
  if (!row) throw new NotFoundError(`No entity found for "${params.name_or_id}"`);

  const [aliases, externalIds] = await Promise.all([
    db.selectFrom('entity_aliases').selectAll().where('entity_id', '=', row.id).execute(),
    db.selectFrom('entity_external_ids').selectAll().where('entity_id', '=', row.id).execute(),
  ]);

  let relQuery = db
    .selectFrom('relationships')
    .selectAll()
    .where('is_deprecated', '=', false)
    .where((eb) =>
      eb.or([eb('subject_entity_id', '=', row.id), eb('object_entity_id', '=', row.id)]),
    );
  if (params.at_date) {
    const at = new Date(params.at_date);
    relQuery = relQuery
      .where((eb) => eb.or([eb('valid_from', 'is', null), eb('valid_from', '<=', at)]))
      .where((eb) => eb.or([eb('valid_until', 'is', null), eb('valid_until', '>', at)]));
  }
  const relationships = await relQuery.orderBy('recorded_at', 'desc').limit(100).execute();

  const facts = await db
    .selectFrom('claims')
    .selectAll()
    .where('subject_entity_id', '=', row.id)
    .where('status', '=', 'active')
    // claims has no recorded_at column; created_at is the claim's transaction time.
    .orderBy('created_at', 'desc')
    .limit(25)
    .execute();

  return {
    entity: mapEntity(row, aliases, externalIds),
    asOf: params.at_date,
    relationships: relationships.map(mapRelationship),
    facts: facts.map(mapClaim),
    freshness: {
      target: row.canonical_name,
      lastUpdated: row.last_updated_at.toISOString(),
      staleness: staleness(row.last_updated_at),
    },
  };
}

export interface SourcesParams {
  entity_or_claim_id: string;
  limit?: number;
}

export async function getSources(db: Db, params: SourcesParams): Promise<S['SourcesResponse']> {
  const id = params.entity_or_claim_id;
  let docIds: string[] = [];

  const claim = UUID.test(id)
    ? await db
        .selectFrom('claims')
        .select('source_document_ids')
        .where('id', '=', id)
        .executeTakeFirst()
    : undefined;

  if (claim) {
    docIds = claim.source_document_ids;
  } else {
    const claims = await db
      .selectFrom('claims')
      .select('source_document_ids')
      .where((eb) => eb.or([eb('subject_entity_id', '=', id), eb('object_entity_id', '=', id)]))
      .limit(500)
      .execute();
    docIds = [...new Set(claims.flatMap((c) => c.source_document_ids))];
  }

  if (docIds.length === 0) return { sources: [] };
  const docs = await db
    .selectFrom('source_documents')
    .selectAll()
    .where('id', 'in', docIds)
    .orderBy('published_at', 'desc')
    .limit(clampLimit(params.limit))
    .execute();
  return { sources: docs.map(mapSourceDocument) };
}

export type { FreshnessParams };

/**
 * "What does Intercal know about X, how fresh is it, and where is coverage weak?" (Plan 03 W7).
 *
 * This is the fetch layer: it resolves the target and gathers the REAL substrate signals (entity
 * transaction-time recency, newest fact version, active-claim count, how many of those claims have
 * CANONICAL `claim_evidence` [the coverage = evidence-depth numerator], and distinct backing
 * documents [the single-source breadth warning]), then delegates to the pure `assembleFreshness` for
 * the coverage +
 * staleness/gap logic. Same split as delta.ts (`buildDelta` + `assembleDigest`) so the policy is
 * unit-testable without a DB. Honesty-first: an unresolved topic or a claim-less entity is reported
 * as an explicit gap (coverage 0), never as invented coverage. See freshness.ts for the metric
 * rationale (coverage is evidence depth, corpus-growth invariant — not a distinct/corpus ratio).
 */
export async function getFreshness(db: Db, params: FreshnessParams): Promise<S['FreshnessReport']> {
  const entity = await findEntityRow(db, params.topic_or_entity);
  if (!entity) {
    // Unknown topic: explicit no-data. Report only the corpus's overall ingest recency.
    const latest = await db
      .selectFrom('source_documents')
      .select((eb) => eb.fn.max('ingested_at').as('last'))
      .executeTakeFirst();
    const lastIngestedAt = (latest?.last as Date | null) ?? null;
    return assembleFreshness({ kind: 'unknown', topic: params.topic_or_entity, lastIngestedAt });
  }

  // Active claims about the entity (subject OR object) — the corroboration base. Evidence is read
  // from the CANONICAL `claim_evidence` join table, NOT the denormalized `claims.source_document_ids`
  // array. The schema (db/migrations/0013) declares `source_document_ids` a "denormalized fast
  // lookup" and `claim_evidence` the canonical link, and the AGENTS.md provenance invariant ("every
  // public fact must trace to claim evidence → source documents") is defined on `claim_evidence`.
  // The two are written by separate, non-transactional statements in the extract pipeline
  // (services/extract: INSERT claims, then INSERT claim_evidence), so they CAN diverge; a coverage
  // metric whose whole purpose is provenance honesty must read the authoritative table. (Verified
  // identical in current prod data, so this is robustness, not a live correction.)
  //
  // Per active claim we get: whether it has ≥1 canonical evidence row (the coverage = evidence-depth
  // numerator) and the union of distinct evidence documents (the corroboration-breadth signal).
  const claimRows = await db
    .selectFrom('claims')
    .leftJoin('claim_evidence', 'claim_evidence.claim_id', 'claims.id')
    .select(['claims.id as claim_id', 'claim_evidence.document_id as document_id'])
    .where('claims.status', '=', 'active')
    .where((eb) =>
      eb.or([
        eb('claims.subject_entity_id', '=', entity.id),
        eb('claims.object_entity_id', '=', entity.id),
      ]),
    )
    .execute();
  const evidencedClaimIds = new Set<string>();
  const allClaimIds = new Set<string>();
  const distinctSources = new Set<string>();
  for (const row of claimRows) {
    allClaimIds.add(row.claim_id);
    if (row.document_id) {
      evidencedClaimIds.add(row.claim_id);
      distinctSources.add(row.document_id);
    }
  }
  const activeClaimCount = allClaimIds.size;
  const evidencedClaimCount = evidencedClaimIds.size;

  // Newest fact-version transaction time for this subject (the authoritative append-only change
  // axis) — the only remaining DB signal the assembler needs beyond the claims fetch above.
  const latestFv = await db
    .selectFrom('fact_versions')
    .select((eb) => eb.fn.max('recorded_at').as('latest'))
    .where('fact_subject_type', '=', 'entity')
    .where('fact_subject_id', '=', entity.id)
    .executeTakeFirst();

  return assembleFreshness({
    kind: 'entity',
    canonicalName: entity.canonical_name,
    lastUpdatedAt: entity.last_updated_at,
    latestFactVersionAt: (latestFv?.latest as Date | null) ?? null,
    activeClaimCount,
    evidencedClaimCount,
    distinctSourceCount: distinctSources.size,
  });
}

export interface EvidenceParams {
  query: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
}

export async function searchEvidence(
  db: Db,
  params: EvidenceParams,
): Promise<S['EvidenceResponse']> {
  const pattern = `%${params.query}%`;
  let q = db
    .selectFrom('source_documents')
    .selectAll()
    .where((eb) => eb.or([eb('title', 'ilike', pattern), eb('cleaned_text', 'ilike', pattern)]));
  if (params.from_date) q = q.where('published_at', '>=', new Date(params.from_date));
  if (params.to_date) q = q.where('published_at', '<=', new Date(params.to_date));

  const rows = await q.orderBy('published_at', 'desc').limit(clampLimit(params.limit)).execute();

  const hits = rows.map((row) => {
    const titleHit = row.title?.toLowerCase().includes(params.query.toLowerCase()) ?? false;
    // Respect source policy: no body snippet for citation-only documents.
    let snippet = '';
    if (!row.citation_only && row.cleaned_text) {
      const idx = row.cleaned_text.toLowerCase().indexOf(params.query.toLowerCase());
      const start = idx >= 0 ? Math.max(0, idx - 80) : 0;
      snippet = row.cleaned_text.slice(start, start + 240).trim();
    } else if (row.title) {
      snippet = row.title;
    }
    return {
      documentId: row.id,
      snippet,
      score: titleHit ? 1 : 0.5,
      citation: {
        sourceDocumentId: row.id,
        ...(row.url ? { url: row.url } : {}),
        ...(row.published_at ? { publishedAt: row.published_at.toISOString() } : {}),
      },
    };
  });

  return { hits, total: hits.length };
}

export type { DeltaParams };

/**
 * "What changed since my cutoff." Returns a compact, token-bounded, fully-cited digest over the
 * claims/entities/relationships whose TRANSACTION time (the bitemporal "when Intercal recorded
 * it" axis) falls in `(since_date, until_date]`, scoped to `topic`.
 *
 * The body lives in `delta.ts`; this stays a thin dispatch like the other query functions so the
 * REST and MCP surfaces call one set of semantics. See `delta.ts` for the design rationale
 * (deterministic assembly, ranking, token-budget trimming, citation/confidence/freshness).
 */
export function getDelta(db: Db, params: DeltaParams): Promise<S['DeltaResponse']> {
  return buildDelta(db, params);
}

export type { VerifyClaimParams };

/**
 * Verify a free-text claim against the substrate: a deterministic, fully-cited verdict
 * (supported / partially_supported / contradicted / unverified) with supporting and contradicting
 * evidence, confidence, and point-in-time (`as_of_date`) bitemporal evaluation.
 *
 * The body lives in `verify.ts`; this stays a thin dispatch like the other query functions so the
 * REST and MCP surfaces call one set of semantics. See `verify.ts` for the design rationale
 * (deterministic evidence match + contradiction reasoning, point-in-time, token budget, citation
 * and confidence derivation).
 */
export function verifyClaim(
  db: Db,
  params: VerifyClaimParams,
): Promise<S['ClaimVerificationResponse']> {
  return buildVerification(db, params);
}
