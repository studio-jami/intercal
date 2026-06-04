/**
 * The shared query-service layer. The REST API and the MCP server both call these — there is
 * one set of query semantics, never two.
 *
 * V1 status: `getEntity`, `getSources`, `getFreshness`, and `searchEvidence` are real reads
 * against the canonical schema. `getDelta` and `verifyClaim` require digest synthesis and
 * contradiction reasoning owned by Plan 03 and raise `NotImplementedError` until then — an
 * honest deferral, not a mock.
 */
import type { components } from '@intercal/shared';
import type { Db } from './db/client.js';
import type { EntitiesTable } from './db/types.js';
import { NotFoundError, NotImplementedError } from './errors.js';
import { mapClaim, mapEntity, mapRelationship, mapSourceDocument } from './mappers.js';

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

async function findEntityRow(db: Db, nameOrId: string): Promise<EntitiesTable | undefined> {
  if (UUID.test(nameOrId)) {
    return db.selectFrom('entities').selectAll().where('id', '=', nameOrId).executeTakeFirst();
  }
  const byName = await db
    .selectFrom('entities')
    .selectAll()
    .where('is_deprecated', '=', false)
    .where((eb) => eb(eb.fn('lower', ['canonical_name']), '=', nameOrId.toLowerCase()))
    .orderBy('importance_score', 'desc')
    .executeTakeFirst();
  if (byName) return byName;

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
    .orderBy('recorded_at', 'desc')
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

export interface FreshnessParams {
  topic_or_entity: string;
}

export async function getFreshness(db: Db, params: FreshnessParams): Promise<S['FreshnessReport']> {
  const entity = await findEntityRow(db, params.topic_or_entity);
  if (entity) {
    return {
      target: entity.canonical_name,
      lastUpdated: entity.last_updated_at.toISOString(),
      staleness: staleness(entity.last_updated_at),
    };
  }
  // Fall back to global ingestion freshness when the target is not a known entity.
  const latest = await db
    .selectFrom('source_documents')
    .select((eb) => eb.fn.max('ingested_at').as('last'))
    .executeTakeFirst();
  const last = (latest?.last as Date | null) ?? null;
  return {
    target: params.topic_or_entity,
    lastIngestedAt: last ? last.toISOString() : undefined,
    staleness: staleness(last),
  };
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

export interface DeltaParams {
  topic: string;
  since_date: string;
  token_budget?: number;
  until_date?: string;
}

export function getDelta(_db: Db, _params: DeltaParams): Promise<S['DeltaResponse']> {
  throw new NotImplementedError(
    'Plan 03 — get_delta: token-budgeted digest synthesis over changed claims/entities since a date.',
  );
}

export interface VerifyClaimParams {
  claim_text: string;
  as_of_date?: string;
  token_budget?: number;
}

export function verifyClaim(
  _db: Db,
  _params: VerifyClaimParams,
): Promise<S['ClaimVerificationResponse']> {
  throw new NotImplementedError(
    'Plan 03 — verify_claim: evidence matching + contradiction reasoning for a free-text claim.',
  );
}
