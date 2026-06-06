/**
 * Corpus quality gate verifier.
 *
 * Usage:
 *   node scripts/dev/verify-corpus-quality-gates.mjs seeded-proof [--json]
 *   node scripts/dev/verify-corpus-quality-gates.mjs live-first-proof [--json]
 *   node scripts/dev/verify-corpus-quality-gates.mjs live-full [--json]
 *
 * `seeded-proof` writes rollback-scoped proof rows and exercises the same core query functions
 * used by REST/MCP. It requires `pnpm --filter @intercal/core build` first so plain node can load
 * the package without a TypeScript runtime.
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');

const mode = process.argv[2]?.startsWith('--')
  ? 'seeded-proof'
  : (process.argv[2] ?? 'seeded-proof');
const json = process.argv.includes('--json');
const databaseUrl = loadDatabaseUrl();

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envPath = join(repoRoot, '.env');
  if (!existsSync(envPath)) return undefined;
  for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*DATABASE_URL\s*=\s*(.+?)\s*$/);
    if (match) return match[1].replace(/^["']|["']$/g, '');
  }
  return undefined;
}

if (!databaseUrl) {
  console.error(
    'DATABASE_URL is required in the environment or local .env. The value is not printed by this script.',
  );
  process.exit(2);
}

async function loadCore() {
  try {
    return await import(new URL('../../packages/core/dist/index.js', import.meta.url).href);
  } catch (error) {
    console.error('Unable to load packages/core/dist/index.js.');
    console.error('Run: pnpm --filter @intercal/core build');
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(2);
  }
}

const core = await loadCore();
const db = core.createDb(databaseUrl);
const { sql } = core;

const firstProofConfig = core.FIRST_PROOF_CORPUS_QUALITY_CONFIG;
const fullConfig = core.FULL_AI_HISTORY_CORPUS_QUALITY_CONFIG;

const IDS = {
  sources: {
    openai: '00000000-0000-4000-8000-000000000101',
    anthropic: '00000000-0000-4000-8000-000000000102',
    google: '00000000-0000-4000-8000-000000000103',
    meta: '00000000-0000-4000-8000-000000000104',
    mcp: '00000000-0000-4000-8000-000000000105',
    openaiRelease: '00000000-0000-4000-8000-000000000106',
  },
  docs: {
    chatgpt: '00000000-0000-4000-8000-000000000201',
    claude: '00000000-0000-4000-8000-000000000202',
    gemini: '00000000-0000-4000-8000-000000000203',
    llama: '00000000-0000-4000-8000-000000000204',
    mcp: '00000000-0000-4000-8000-000000000205',
    turbo: '00000000-0000-4000-8000-000000000206',
  },
  entities: {
    chatgpt: '00000000-0000-4000-8000-000000000301',
    claude: '00000000-0000-4000-8000-000000000302',
    gemini: '00000000-0000-4000-8000-000000000303',
    llama: '00000000-0000-4000-8000-000000000304',
    mcp: '00000000-0000-4000-8000-000000000305',
    turbo: '00000000-0000-4000-8000-000000000306',
  },
  claims: {
    chatgpt: '00000000-0000-4000-8000-000000000401',
    claude: '00000000-0000-4000-8000-000000000402',
    gemini: '00000000-0000-4000-8000-000000000403',
    llama: '00000000-0000-4000-8000-000000000404',
    mcp: '00000000-0000-4000-8000-000000000405',
    turbo128k: '00000000-0000-4000-8000-000000000406',
    turbo1m: '00000000-0000-4000-8000-000000000407',
  },
};

function logResult(payload) {
  if (json) {
    console.log(JSON.stringify(payload, null, 2));
    return;
  }
  console.log(`mode: ${payload.mode}`);
  console.log(`passed: ${payload.passed}`);
  for (const check of payload.evaluation.checks) {
    const mark = check.passed ? 'PASS' : 'FAIL';
    console.log(`[${mark}] ${check.label}: expected ${check.expected}; actual ${check.actual}`);
  }
  if (payload.queryProofs) {
    for (const proof of payload.queryProofs) {
      console.log(`[${proof.passed ? 'PASS' : 'FAIL'}] ${proof.name}: ${proof.detail}`);
    }
  }
}

async function seedProof(tx) {
  await sql`
    INSERT INTO sources (id, slug, name, source_type, adapter_name, metadata, redistribution_allowed, summary_allowed, citation_only)
    VALUES
      (${IDS.sources.openai}, 'w4-proof-openai', 'Workstream 4 proof OpenAI', 'api', 'proof_seed_v1', '{"source_class":"model_provider"}', true, true, false),
      (${IDS.sources.anthropic}, 'w4-proof-anthropic', 'Workstream 4 proof Anthropic', 'api', 'proof_seed_v1', '{"source_class":"model_provider"}', true, true, false),
      (${IDS.sources.google}, 'w4-proof-google', 'Workstream 4 proof Google', 'api', 'proof_seed_v1', '{"source_class":"research"}', true, true, false),
      (${IDS.sources.meta}, 'w4-proof-meta', 'Workstream 4 proof Meta', 'registry', 'proof_seed_v1', '{"source_class":"registry"}', true, true, false),
      (${IDS.sources.mcp}, 'w4-proof-mcp', 'Workstream 4 proof MCP', 'release_notes', 'proof_seed_v1', '{"source_class":"protocol"}', true, true, false),
      (${IDS.sources.openaiRelease}, 'w4-proof-openai-release-notes', 'Workstream 4 proof OpenAI release notes', 'release_notes', 'proof_seed_v1', '{"source_class":"release_notes"}', true, true, false)
  `.execute(tx);

  await sql`
    INSERT INTO source_documents
      (id, source_id, content_hash, external_id, url, title, published_at, cleaned_text, document_type, metadata, redistribution_allowed, summary_allowed, citation_only)
    VALUES
      (${IDS.docs.chatgpt}, ${IDS.sources.openai}, 'w4-proof-chatgpt', 'chatgpt', 'https://example.invalid/chatgpt', 'ChatGPT launch proof', '2022-11-30T00:00:00Z', 'ChatGPT became a frontier LLM public interface in late 2022.', 'article', '{"source_class":"model_provider"}', true, true, false),
      (${IDS.docs.claude}, ${IDS.sources.anthropic}, 'w4-proof-claude', 'claude', 'https://example.invalid/claude', 'Claude proof', '2023-03-14T00:00:00Z', 'Claude entered the frontier LLM timeline in March 2023.', 'article', '{"source_class":"model_provider"}', true, true, false),
      (${IDS.docs.gemini}, ${IDS.sources.google}, 'w4-proof-gemini', 'gemini', 'https://example.invalid/gemini', 'Gemini proof', '2023-12-06T00:00:00Z', 'Gemini is a frontier LLM family with multimodal releases.', 'paper_abstract', '{"source_class":"research"}', true, true, false),
      (${IDS.docs.llama}, ${IDS.sources.meta}, 'w4-proof-llama', 'llama', 'https://example.invalid/llama', 'Llama proof', '2024-04-18T00:00:00Z', 'Llama is an open-weight model family in the AI-history corpus.', 'api_record', '{"source_class":"registry"}', true, true, false),
      (${IDS.docs.mcp}, ${IDS.sources.mcp}, 'w4-proof-mcp', 'mcp', 'https://example.invalid/mcp', 'MCP protocol proof', '2024-11-25T00:00:00Z', 'The MCP protocol connects models to tools and context.', 'release_notes', '{"source_class":"protocol"}', true, true, false),
      (${IDS.docs.turbo}, ${IDS.sources.openaiRelease}, 'w4-proof-turbo', 'gpt-4-turbo', 'https://example.invalid/gpt-4-turbo', 'GPT-4 Turbo context proof', '2023-11-06T00:00:00Z', 'GPT-4 Turbo supports a 128k context window, not a 1M context window.', 'release_notes', '{"source_class":"release_notes"}', true, true, false)
  `.execute(tx);

  await sql`
    INSERT INTO entities (id, type_id, canonical_name, description, current_state, importance_score, first_seen_at, last_updated_at)
    VALUES
      (${IDS.entities.chatgpt}, 'product', 'ChatGPT', 'Workstream 4 rollback proof entity', '{}', 0.90, '2022-11-30T00:00:00Z', '2023-03-01T00:00:00Z'),
      (${IDS.entities.claude}, 'product', 'Claude', 'Workstream 4 rollback proof entity', '{}', 0.88, '2023-03-14T00:00:00Z', '2024-03-01T00:00:00Z'),
      (${IDS.entities.gemini}, 'product', 'Gemini', 'Workstream 4 rollback proof entity', '{}', 0.87, '2023-12-06T00:00:00Z', '2024-02-15T00:00:00Z'),
      (${IDS.entities.llama}, 'technical_artifact', 'Llama', 'Workstream 4 rollback proof entity', '{}', 0.86, '2023-02-24T00:00:00Z', '2024-04-18T00:00:00Z'),
      (${IDS.entities.mcp}, 'technical_artifact', 'MCP protocol', 'Workstream 4 rollback proof entity', '{}', 0.80, '2024-11-25T00:00:00Z', '2024-11-25T00:00:00Z'),
      (${IDS.entities.turbo}, 'technical_artifact', 'GPT-4 Turbo', 'Workstream 4 rollback proof entity', '{}', 0.83, '2023-11-06T00:00:00Z', '2023-11-06T00:00:00Z')
  `.execute(tx);

  await sql`
    INSERT INTO claims
      (id, subject_entity_id, subject_text, predicate, object_text, normalized_text, valid_from, extractor, extraction_confidence, source_document_ids, contradiction_status, metadata, created_at, updated_at)
    VALUES
      (${IDS.claims.chatgpt}, ${IDS.entities.chatgpt}, 'ChatGPT', 'released', 'frontier LLM public interface', 'ChatGPT is part of the frontier LLMs timeline after November 2022.', '2022-11-30T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.95, ARRAY[${IDS.docs.chatgpt}]::uuid[], 'none', '{"topic_cluster":"frontier_llms"}', '2023-03-02T00:00:00Z', '2023-03-02T00:00:00Z'),
      (${IDS.claims.claude}, ${IDS.entities.claude}, 'Claude', 'released', 'frontier LLM assistant', 'Claude is part of the frontier LLMs timeline after March 2023.', '2023-03-14T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.94, ARRAY[${IDS.docs.claude}]::uuid[], 'none', '{"topic_cluster":"frontier_llms"}', '2023-03-15T00:00:00Z', '2023-03-15T00:00:00Z'),
      (${IDS.claims.gemini}, ${IDS.entities.gemini}, 'Gemini', 'released', 'frontier LLM family', 'Gemini is part of the frontier LLMs timeline after December 2023.', '2023-12-06T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.93, ARRAY[${IDS.docs.gemini}]::uuid[], 'none', '{"topic_cluster":"frontier_llms"}', '2024-02-15T00:00:00Z', '2024-02-15T00:00:00Z'),
      (${IDS.claims.llama}, ${IDS.entities.llama}, 'Llama', 'released', 'open-weight model family', 'Llama is an open-weight model family in the frontier LLMs timeline.', '2024-04-18T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.92, ARRAY[${IDS.docs.llama}]::uuid[], 'none', '{"topic_cluster":"open_weight_models"}', '2024-04-18T00:00:00Z', '2024-04-18T00:00:00Z'),
      (${IDS.claims.mcp}, ${IDS.entities.mcp}, 'MCP protocol', 'introduced', 'agent tooling protocol', 'MCP protocol connects models to tools and context.', '2024-11-25T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.91, ARRAY[${IDS.docs.mcp}]::uuid[], 'none', '{"topic_cluster":"model_context_protocol"}', '2024-11-25T00:00:00Z', '2024-11-25T00:00:00Z'),
      (${IDS.claims.turbo128k}, ${IDS.entities.turbo}, 'GPT-4 Turbo', 'supports_context_window', '128k context window', 'GPT-4 Turbo supports a 128k context window.', '2023-11-06T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.96, ARRAY[${IDS.docs.turbo}]::uuid[], 'none', '{"topic_cluster":"frontier_llms"}', '2023-11-06T00:00:00Z', '2023-11-06T00:00:00Z'),
      (${IDS.claims.turbo1m}, ${IDS.entities.turbo}, 'GPT-4 Turbo', 'supports_context_window', '1M context window', 'GPT-4 Turbo supports a 1M context window.', '2023-11-06T00:00:00Z', 'workstream_4_seeded_quality_gate', 0.20, ARRAY[${IDS.docs.turbo}]::uuid[], 'has_contradiction', '{"topic_cluster":"frontier_llms"}', '2023-11-07T00:00:00Z', '2023-11-07T00:00:00Z')
  `.execute(tx);

  for (const [claimId, docId] of [
    [IDS.claims.chatgpt, IDS.docs.chatgpt],
    [IDS.claims.claude, IDS.docs.claude],
    [IDS.claims.gemini, IDS.docs.gemini],
    [IDS.claims.llama, IDS.docs.llama],
    [IDS.claims.mcp, IDS.docs.mcp],
    [IDS.claims.turbo128k, IDS.docs.turbo],
    [IDS.claims.turbo1m, IDS.docs.turbo],
  ]) {
    await sql`
      INSERT INTO claim_evidence (claim_id, document_id, support_strength, confidence, quote_excerpt)
      VALUES (${claimId}, ${docId}, 'supports', 1.0, 'Workstream 4 rollback-scoped proof citation')
    `.execute(tx);
  }

  await sql`
    INSERT INTO claim_contradictions (claim_a_id, claim_b_id, detection_method, confidence, description)
    VALUES (${IDS.claims.turbo128k}, ${IDS.claims.turbo1m}, 'rule', 0.95, 'Rollback proof: changed context-window claim must surface contradiction state.')
  `.execute(tx);

  await sql`
    INSERT INTO review_records (target_type, target_id, concern_type, summary, status)
    VALUES ('coverage', 'workstream-4-seeded-proof', 'missing_coverage', 'Rollback proof review-needed rate gate row.', 'received')
  `.execute(tx);

  for (const [entityId, claimId, docId] of [
    [IDS.entities.chatgpt, IDS.claims.chatgpt, IDS.docs.chatgpt],
    [IDS.entities.claude, IDS.claims.claude, IDS.docs.claude],
    [IDS.entities.gemini, IDS.claims.gemini, IDS.docs.gemini],
    [IDS.entities.llama, IDS.claims.llama, IDS.docs.llama],
    [IDS.entities.mcp, IDS.claims.mcp, IDS.docs.mcp],
    [IDS.entities.turbo, IDS.claims.turbo128k, IDS.docs.turbo],
  ]) {
    await sql`
      INSERT INTO fact_versions (fact_subject_type, fact_subject_id, payload, valid_from, recorded_at, source_document_ids, claim_ids, confidence, produced_by)
      VALUES ('entity', ${entityId}, '{}', '2023-03-01T00:00:00Z', now(), ARRAY[${docId}]::uuid[], ARRAY[${claimId}]::uuid[], 0.95, 'workstream_4_seeded_quality_gate')
    `.execute(tx);
  }
}

function proof(name, passed, detail) {
  return { name, passed, detail };
}

async function runQueryProofs(tx) {
  const proofs = [];
  async function addProof(name, run) {
    try {
      const result = await run();
      proofs.push(proof(name, result.passed, result.detail));
    } catch (error) {
      proofs.push(proof(name, false, error instanceof Error ? error.message : String(error)));
    }
  }

  await addProof('get_entity ChatGPT as_of', async () => {
    const asOf = '2023-03-01T00:00:00Z';
    const entity = await core.getEntity(tx, {
      name_or_id: 'ChatGPT',
      at_date: asOf,
    });
    const asOfTime = new Date(asOf).getTime();
    const factsInWindow = entity.facts.every((fact) => {
      const validFromOk = !fact.validFrom || new Date(fact.validFrom).getTime() <= asOfTime;
      const validUntilOk = !fact.validUntil || new Date(fact.validUntil).getTime() > asOfTime;
      return validFromOk && validUntilOk;
    });
    return {
      passed: entity.entity.displayName === 'ChatGPT' && entity.facts.length > 0 && factsInWindow,
      detail: `${entity.entity.displayName}; facts=${entity.facts.length}; factsInWindow=${factsInWindow}`,
    };
  });

  await addProof('get_freshness MCP protocol', async () => {
    const freshness = await core.getFreshness(tx, { topic_or_entity: 'MCP protocol' });
    return { passed: freshness.coverage > 0, detail: `coverage=${freshness.coverage}` };
  });

  await addProof('get_delta frontier LLMs', async () => {
    const delta = await core.getDelta(tx, {
      topic: 'frontier LLMs',
      since_date: '2023-03-01T00:00:00Z',
      token_budget: 300,
    });
    return {
      passed: delta.changedClaims.length >= 4 && delta.summary.citations.length > 0,
      detail: `claims=${delta.changedClaims.length}; citations=${delta.summary.citations.length}`,
    };
  });

  await addProof('verify_claim point-in-time before evidence', async () => {
    const before = await core.verifyClaim(tx, {
      claim_text: 'GPT-4 Turbo supports a 128k context window',
      as_of_date: '2023-10-01T00:00:00Z',
    });
    return { passed: before.verdict === 'unverified', detail: `verdict=${before.verdict}` };
  });

  await addProof('verify_claim point-in-time after evidence', async () => {
    const after = await core.verifyClaim(tx, {
      claim_text: 'GPT-4 Turbo supports a 128k context window',
      as_of_date: '2024-04-01T00:00:00Z',
    });
    return {
      passed: after.verdict !== 'unverified' && after.supportingEvidence.length > 0,
      detail: `verdict=${after.verdict}; supporting=${after.supportingEvidence.length}; contradicting=${after.contradictingEvidence.length}`,
    };
  });

  await addProof('verify_claim adversarial stale/wrong value', async () => {
    const adversarial = await core.verifyClaim(tx, {
      claim_text: 'GPT-4 Turbo supports a 1M context window',
      as_of_date: '2024-04-01T00:00:00Z',
    });
    return {
      passed: adversarial.verdict !== 'supported',
      detail: `verdict=${adversarial.verdict}`,
    };
  });

  await addProof('search_evidence MCP protocol', async () => {
    const evidence = await core.searchEvidence(tx, {
      query: 'MCP protocol',
      from_date: '2024-01-01T00:00:00Z',
      to_date: '2026-06-06T00:00:00Z',
    });
    return { passed: evidence.hits.length > 0, detail: `hits=${evidence.hits.length}` };
  });
  return proofs;
}

async function runLive(selectedMode) {
  const config = selectedMode === 'live-full' ? fullConfig : firstProofConfig;
  const report = await core.queryCorpusQualityReport(db, config);
  const evaluation = core.evaluateCorpusQualityReport(report, config);
  const queryProofs = selectedMode === 'live-first-proof' ? await runQueryProofs(db) : [];
  return {
    mode: selectedMode,
    passed: evaluation.passed && queryProofs.every((item) => item.passed),
    report,
    evaluation,
    queryProofs,
  };
}

const rollbackSentinel = new Error('ROLLBACK_WORKSTREAM_4_SEEDED_PROOF');

try {
  let result;
  if (mode === 'seeded-proof') {
    try {
      await db
        .transaction()
        .setIsolationLevel('serializable')
        .execute(async (tx) => {
          await seedProof(tx);
          const report = await core.queryCorpusQualityReport(tx, firstProofConfig);
          const evaluation = core.evaluateCorpusQualityReport(report, firstProofConfig);
          const queryProofs = await runQueryProofs(tx);
          result = {
            mode,
            passed: evaluation.passed && queryProofs.every((item) => item.passed),
            report,
            evaluation,
            queryProofs,
          };
          throw rollbackSentinel;
        });
    } catch (error) {
      if (error !== rollbackSentinel) throw error;
    }
    const residue = await db
      .selectFrom('sources')
      .select((eb) => eb.fn.count('id').as('count'))
      .where('slug', 'like', 'w4-proof-%')
      .executeTakeFirst();
    const residueCount = Number(residue?.count ?? 0);
    result.queryProofs.push(
      proof(
        'seeded proof rollback cleanup',
        residueCount === 0,
        `residual proof sources=${residueCount}`,
      ),
    );
    result.passed = result.passed && residueCount === 0;
  } else if (mode === 'live-first-proof' || mode === 'live-full') {
    result = await runLive(mode);
  } else {
    console.error(`Unknown mode: ${mode}`);
    process.exit(2);
  }

  logResult(result);
  process.exitCode = result.passed ? 0 : 1;
} finally {
  await db.destroy();
}
