#!/usr/bin/env node

// Live source-policy snippet-gate verification (Plan 04 W2).
//
// Proves, against a REAL database, that `searchEvidence` honors the source-policy snapshot
// columns on `source_documents` (migration 0025 `summary_allowed` + 0006 `citation_only`):
//   - fully-permissive (citation_only=false, summary_allowed=true)  → body snippet emitted
//   - summary_allowed=false                                          → title-only (no body)
//   - citation_only=true                                             → title-only (no body)
//
// All test rows are inserted inside a transaction that is ALWAYS rolled back, so this is safe to
// run against the production branch: nothing is persisted. NEVER prints DATABASE_URL.
//
// Usage: DATABASE_URL=<neon-url> node scripts/dev/verify-source-policy.mjs

import { createDb, searchEvidence } from '@intercal/core';

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  console.error('[verify-source-policy] DATABASE_URL is required.');
  process.exit(2);
}

const db = createDb(databaseUrl);

let pass = 0;
let fail = 0;
function check(name, cond, extra = '') {
  if (cond) {
    pass++;
    console.log(`  ok   ${name}`);
  } else {
    fail++;
    console.log(`  FAIL ${name} ${extra}`);
  }
}

const MARKER = `zzpolicyprobe${Date.now()}`;
const BODY = `Sensitive ${MARKER} body text that must never leak past policy.`;

try {
  // Confirm the 0025 column exists live before exercising the gate.
  const col = await db
    .selectFrom('source_documents')
    .select('summary_allowed')
    .limit(1)
    .execute()
    .then(
      () => true,
      () => false,
    );
  check('migration 0025 summary_allowed column present', col);

  await db
    .transaction()
    .setIsolationLevel('serializable')
    .execute(async (trx) => {
      // Disposable source (rolled back).
      const source = await trx
        .insertInto('sources')
        .values({
          slug: `policy-probe-${Date.now()}`,
          name: 'Source policy probe',
          source_type: 'manual',
          adapter_name: 'manual',
          adapter_config: JSON.stringify({}),
        })
        .returning('id')
        .executeTakeFirstOrThrow();

      const mk = async (label, citation_only, summary_allowed) => {
        const row = await trx
          .insertInto('source_documents')
          .values({
            source_id: source.id,
            content_hash: `${MARKER}-${label}`,
            title: `Title ${MARKER} ${label}`,
            cleaned_text: BODY,
            citation_only,
            summary_allowed,
            published_at: new Date(),
          })
          .returning('id')
          .executeTakeFirstOrThrow();
        return row.id;
      };

      const permissiveId = await mk('permissive', false, true);
      const noSummaryId = await mk('nosummary', false, false);
      const citeOnlyId = await mk('citeonly', true, true);

      const res = await searchEvidence(trx, { query: MARKER, limit: 50 });
      const byId = new Map(res.hits.map((h) => [h.documentId, h]));

      const permissive = byId.get(permissiveId);
      check(
        'permissive source emits a body snippet (not just the title)',
        !!permissive &&
          permissive.snippet.includes('body text') &&
          !permissive.snippet.startsWith('Title '),
        permissive ? `snippet=${JSON.stringify(permissive.snippet)}` : 'missing hit',
      );

      const noSummary = byId.get(noSummaryId);
      check(
        'summary_allowed=false → title-only, no body leak',
        !!noSummary && !noSummary.snippet.includes('body text'),
        noSummary ? `snippet=${JSON.stringify(noSummary.snippet)}` : 'missing hit',
      );

      const citeOnly = byId.get(citeOnlyId);
      check(
        'citation_only=true → title-only, no body leak',
        !!citeOnly && !citeOnly.snippet.includes('body text'),
        citeOnly ? `snippet=${JSON.stringify(citeOnly.snippet)}` : 'missing hit',
      );

      // Always roll back: no probe data persists.
      throw new Error('__rollback__');
    })
    .catch((err) => {
      if (err?.message !== '__rollback__') throw err;
    });

  // Prove the rollback worked — no probe rows remain.
  const leftover = await db
    .selectFrom('source_documents')
    .select('id')
    .where('content_hash', 'like', `${MARKER}%`)
    .execute();
  check(
    'all probe rows rolled back (none persisted)',
    leftover.length === 0,
    `found=${leftover.length}`,
  );
} finally {
  await db.destroy();
}

console.log(`\n[verify-source-policy] ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
