#!/usr/bin/env node
// Idempotently apply the reviewed Workstream 4 first-proof corpus rows.
//
// This is an operator backfill for the first live proof only. It creates the full
// provenance chain from reviewed public source rows through source documents,
// claims, claim evidence, and fact versions. It does not print DATABASE_URL.
//
// Usage:
//   node scripts/dev/backfill-first-proof-corpus.mjs --dry-run
//   node scripts/dev/backfill-first-proof-corpus.mjs --apply

import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');
const args = new Set(process.argv.slice(2));
const apply = args.has('--apply');
const json = args.has('--json');

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

const sourceIds = {
  openai: '00000000-0000-4400-8400-000000000101',
  anthropicClaude: '00000000-0000-4400-8400-000000000102',
  geminiResearch: '00000000-0000-4400-8400-000000000103',
  llamaRegistry: '00000000-0000-4400-8400-000000000104',
  metaLlama: '00000000-0000-4400-8400-000000000105',
  anthropicMcp: '00000000-0000-4400-8400-000000000106',
};

const docIds = {
  chatgpt: '00000000-0000-4400-8400-000000000201',
  claude: '00000000-0000-4400-8400-000000000202',
  gemini: '00000000-0000-4400-8400-000000000203',
  llama: '00000000-0000-4400-8400-000000000204',
  mcp: '00000000-0000-4400-8400-000000000205',
  turboDevday: '00000000-0000-4400-8400-000000000206',
  turboModelDocs: '00000000-0000-4400-8400-000000000207',
  llamaMetaNews: '00000000-0000-4400-8400-000000000208',
};

const entityIds = {
  chatgpt: '00000000-0000-4400-8400-000000000301',
  claude: '00000000-0000-4400-8400-000000000302',
  gemini: '00000000-0000-4400-8400-000000000303',
  llama: '00000000-0000-4400-8400-000000000304',
  mcp: '00000000-0000-4400-8400-000000000305',
  turbo: '00000000-0000-4400-8400-000000000306',
};

const claimIds = {
  chatgpt: '00000000-0000-4400-8400-000000000401',
  claude: '00000000-0000-4400-8400-000000000402',
  gemini: '00000000-0000-4400-8400-000000000403',
  llama: '00000000-0000-4400-8400-000000000404',
  mcp: '00000000-0000-4400-8400-000000000405',
  turbo128k: '00000000-0000-4400-8400-000000000406',
  turboAprilCutoff: '00000000-0000-4400-8400-000000000407',
  turboDecemberCutoff: '00000000-0000-4400-8400-000000000408',
};

const sources = [
  {
    id: sourceIds.openai,
    slug: 'first-proof-openai-news',
    name: 'First Proof - OpenAI News',
    description:
      'Reviewed official OpenAI announcements for ChatGPT and GPT-4 Turbo first-proof coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://openai.com/news/rss.xml'], language: 'en' },
    licenseNotes:
      'Official OpenAI public announcement pages. Store only derived summaries and citations unless terms are reviewed for raw redistribution.',
    rateLimit: 30,
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
  {
    id: sourceIds.anthropicClaude,
    slug: 'first-proof-anthropic-claude-news',
    name: 'First Proof - Anthropic Claude News',
    description: 'Reviewed official Anthropic announcement for Claude first-proof coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://www.anthropic.com/news/rss.xml'], language: 'en' },
    licenseNotes:
      'Official Anthropic public announcement pages. Store only derived summaries and citations unless terms are reviewed for raw redistribution.',
    rateLimit: 30,
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
  {
    id: sourceIds.geminiResearch,
    slug: 'first-proof-gemini-research',
    name: 'First Proof - Gemini Research',
    description: 'Reviewed Gemini technical report source for research-class first-proof coverage.',
    sourceType: 'research',
    adapterName: 'arxiv_v1',
    adapterConfig: {
      search_terms: ['Gemini A Family of Highly Capable Multimodal Models'],
      categories: ['cs.CL', 'cs.AI'],
      batch_size: '10',
    },
    licenseNotes: 'arXiv abstract-first source; full paper redistribution is not assumed.',
    rateLimit: 30,
    metadata: {
      source_class: 'research',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
  {
    id: sourceIds.llamaRegistry,
    slug: 'first-proof-llama-registry',
    name: 'First Proof - Llama Registry',
    description: 'Reviewed Hugging Face registry rows for Meta Llama first-proof coverage.',
    sourceType: 'registry',
    adapterName: 'registry_releases_v1',
    adapterConfig: {
      huggingface_models: ['meta-llama/Meta-Llama-3-8B', 'meta-llama/Meta-Llama-3-70B'],
    },
    licenseNotes:
      'Hugging Face model metadata and model cards have per-model terms; raw redistribution is not assumed.',
    rateLimit: 30,
    metadata: {
      source_class: 'registry',
      topic_cluster: 'open_weight_models',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
  {
    id: sourceIds.metaLlama,
    slug: 'first-proof-meta-llama-news',
    name: 'First Proof - Meta Llama News',
    description: 'Reviewed official Meta Llama announcement for open-weight first-proof coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://ai.meta.com/blog/rss/'], language: 'en' },
    licenseNotes:
      'Official Meta AI public announcement page. Store only derived summaries and citations unless terms are reviewed for raw redistribution.',
    rateLimit: 30,
    metadata: {
      source_class: 'release_notes',
      topic_cluster: 'open_weight_models',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
  {
    id: sourceIds.anthropicMcp,
    slug: 'first-proof-anthropic-mcp-news',
    name: 'First Proof - Anthropic MCP News',
    description:
      'Reviewed official Anthropic announcement for Model Context Protocol first-proof coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://www.anthropic.com/news/rss.xml'], language: 'en' },
    licenseNotes:
      'Official Anthropic public announcement pages. Store only derived summaries and citations unless terms are reviewed for raw redistribution.',
    rateLimit: 30,
    metadata: {
      source_class: 'protocol',
      topic_cluster: 'model_context_protocol',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
    },
  },
];

const documents = [
  {
    id: docIds.chatgpt,
    sourceId: sourceIds.openai,
    externalId: 'openai:chatgpt:2022-11-30',
    url: 'https://openai.com/index/chatgpt/',
    title: 'Introducing ChatGPT',
    publishedAt: '2022-11-30T00:00:00Z',
    documentType: 'article',
    text: 'Reviewed source summary: OpenAI introduced ChatGPT on November 30, 2022 as a conversational AI research release. ChatGPT belongs to the frontier LLMs timeline after November 2022.',
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://openai.com/index/chatgpt/',
    },
  },
  {
    id: docIds.claude,
    sourceId: sourceIds.anthropicClaude,
    externalId: 'anthropic:claude:2023-03-14',
    url: 'https://www.anthropic.com/news/introducing-claude',
    title: 'Introducing Claude',
    publishedAt: '2023-03-14T00:00:00Z',
    documentType: 'article',
    text: 'Reviewed source summary: Anthropic introduced Claude on March 14, 2023 as an AI assistant. Claude belongs to the frontier LLMs timeline after March 2023.',
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://www.anthropic.com/news/introducing-claude',
    },
  },
  {
    id: docIds.gemini,
    sourceId: sourceIds.geminiResearch,
    externalId: 'arxiv:2312.11805',
    url: 'https://arxiv.org/abs/2312.11805',
    title: 'Gemini: A Family of Highly Capable Multimodal Models',
    publishedAt: '2023-12-19T00:00:00Z',
    documentType: 'paper_abstract',
    text: 'Reviewed source summary: the Gemini technical report describes Gemini as a family of highly capable multimodal models. Gemini belongs to the frontier LLMs timeline after December 2023.',
    metadata: {
      source_class: 'research',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://arxiv.org/abs/2312.11805',
    },
  },
  {
    id: docIds.llama,
    sourceId: sourceIds.llamaRegistry,
    externalId: 'meta-llama:llama-3:2024-04-18',
    url: 'https://ai.meta.com/blog/meta-llama-3/',
    title: 'Introducing Meta Llama 3',
    publishedAt: '2024-04-18T00:00:00Z',
    documentType: 'api_record',
    text: 'Reviewed source summary: Meta introduced Llama 3 on April 18, 2024 as the next generation of its openly available large language model family. Llama belongs to the open-weight models timeline.',
    metadata: {
      source_class: 'registry',
      topic_cluster: 'open_weight_models',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://ai.meta.com/blog/meta-llama-3/',
    },
  },
  {
    id: docIds.mcp,
    sourceId: sourceIds.anthropicMcp,
    externalId: 'anthropic:mcp:2024-11-25',
    url: 'https://www.anthropic.com/news/model-context-protocol',
    title: 'Introducing the Model Context Protocol',
    publishedAt: '2024-11-25T00:00:00Z',
    documentType: 'article',
    text: 'Reviewed source summary: Anthropic introduced and open-sourced the Model Context Protocol on November 25, 2024. The MCP protocol connects AI assistants to tools, systems, and data sources.',
    metadata: {
      source_class: 'protocol',
      topic_cluster: 'model_context_protocol',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://www.anthropic.com/news/model-context-protocol',
    },
  },
  {
    id: docIds.turboDevday,
    sourceId: sourceIds.openai,
    externalId: 'openai:devday:gpt-4-turbo:2023-11-06',
    url: 'https://openai.com/index/new-models-and-developer-products-announced-at-devday/',
    title: 'New models and developer products announced at DevDay',
    publishedAt: '2023-11-06T00:00:00Z',
    documentType: 'release_notes',
    text: 'Reviewed source summary: OpenAI announced GPT-4 Turbo at DevDay on November 6, 2023 with a 128k context window and an April 2023 knowledge cutoff.',
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url:
        'https://openai.com/index/new-models-and-developer-products-announced-at-devday/',
    },
  },
  {
    id: docIds.turboModelDocs,
    sourceId: sourceIds.openai,
    externalId: 'openai:model-docs:gpt-4-turbo:2024-04-09',
    url: 'https://platform.openai.com/docs/models/gpt-4-turbo',
    title: 'GPT-4 Turbo model documentation',
    publishedAt: '2024-04-09T00:00:00Z',
    documentType: 'api_record',
    text: 'Reviewed source summary: OpenAI model documentation lists GPT-4 Turbo with a 128,000 token context window, model identifier gpt-4-turbo-2024-04-09, and a December 2023 knowledge cutoff.',
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://platform.openai.com/docs/models/gpt-4-turbo',
    },
  },
  {
    id: docIds.llamaMetaNews,
    sourceId: sourceIds.metaLlama,
    externalId: 'meta:llama-3:2024-04-18',
    url: 'https://ai.meta.com/blog/meta-llama-3/',
    title: 'Introducing Meta Llama 3',
    publishedAt: '2024-04-18T00:00:00Z',
    documentType: 'release_notes',
    text: 'Reviewed source summary: Meta announced Llama 3 on April 18, 2024. This release-note source backs the open-weight model timeline for first-proof coverage.',
    metadata: {
      source_class: 'release_notes',
      topic_cluster: 'open_weight_models',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      reviewed_source_url: 'https://ai.meta.com/blog/meta-llama-3/',
    },
  },
];

const entities = [
  {
    id: entityIds.chatgpt,
    typeId: 'product',
    name: 'ChatGPT',
    description: 'OpenAI conversational AI product in the GPT-era AI-history corpus.',
    firstSeenAt: '2022-11-30T00:00:00Z',
    lastUpdatedAt: '2023-03-01T00:00:00Z',
    importance: 0.9,
  },
  {
    id: entityIds.claude,
    typeId: 'product',
    name: 'Claude',
    description: 'Anthropic AI assistant in the GPT-era AI-history corpus.',
    firstSeenAt: '2023-03-14T00:00:00Z',
    lastUpdatedAt: '2024-03-01T00:00:00Z',
    importance: 0.88,
  },
  {
    id: entityIds.gemini,
    typeId: 'product',
    name: 'Gemini',
    description: 'Google multimodal model family in the GPT-era AI-history corpus.',
    firstSeenAt: '2023-12-06T00:00:00Z',
    lastUpdatedAt: '2024-02-15T00:00:00Z',
    importance: 0.87,
  },
  {
    id: entityIds.llama,
    typeId: 'technical_artifact',
    name: 'Llama',
    description: 'Meta open-weight model family in the GPT-era AI-history corpus.',
    firstSeenAt: '2023-02-24T00:00:00Z',
    lastUpdatedAt: '2024-04-18T00:00:00Z',
    importance: 0.86,
  },
  {
    id: entityIds.mcp,
    typeId: 'technical_artifact',
    name: 'MCP protocol',
    description: 'Model Context Protocol in the GPT-era AI-history corpus.',
    firstSeenAt: '2024-11-25T00:00:00Z',
    lastUpdatedAt: '2024-11-25T00:00:00Z',
    importance: 0.8,
  },
  {
    id: entityIds.turbo,
    typeId: 'technical_artifact',
    name: 'GPT-4 Turbo',
    description: 'OpenAI GPT-4 Turbo model in the GPT-era AI-history corpus.',
    firstSeenAt: '2023-11-06T00:00:00Z',
    lastUpdatedAt: '2024-04-09T00:00:00Z',
    importance: 0.83,
  },
];

const claims = [
  {
    id: claimIds.chatgpt,
    entityId: entityIds.chatgpt,
    subject: 'ChatGPT',
    predicate: 'released',
    object: 'frontier LLM public interface',
    normalized: 'ChatGPT is part of the frontier LLMs timeline after November 2022.',
    validFrom: '2022-11-30T00:00:00Z',
    confidence: 0.95,
    docId: docIds.chatgpt,
    topicCluster: 'frontier_llms',
  },
  {
    id: claimIds.claude,
    entityId: entityIds.claude,
    subject: 'Claude',
    predicate: 'released',
    object: 'frontier LLM assistant',
    normalized: 'Claude is part of the frontier LLMs timeline after March 2023.',
    validFrom: '2023-03-14T00:00:00Z',
    confidence: 0.94,
    docId: docIds.claude,
    topicCluster: 'frontier_llms',
  },
  {
    id: claimIds.gemini,
    entityId: entityIds.gemini,
    subject: 'Gemini',
    predicate: 'released',
    object: 'frontier multimodal model family',
    normalized: 'Gemini is part of the frontier LLMs timeline after December 2023.',
    validFrom: '2023-12-06T00:00:00Z',
    confidence: 0.93,
    docId: docIds.gemini,
    topicCluster: 'frontier_llms',
  },
  {
    id: claimIds.llama,
    entityId: entityIds.llama,
    subject: 'Llama',
    predicate: 'released',
    object: 'open-weight model family',
    normalized: 'Llama is an open-weight model family in the frontier LLMs timeline.',
    validFrom: '2024-04-18T00:00:00Z',
    confidence: 0.92,
    docId: docIds.llama,
    topicCluster: 'open_weight_models',
  },
  {
    id: claimIds.mcp,
    entityId: entityIds.mcp,
    subject: 'MCP protocol',
    predicate: 'introduced',
    object: 'agent tooling protocol',
    normalized: 'MCP protocol connects models to tools and context.',
    validFrom: '2024-11-25T00:00:00Z',
    confidence: 0.91,
    docId: docIds.mcp,
    topicCluster: 'model_context_protocol',
  },
  {
    id: claimIds.turbo128k,
    entityId: entityIds.turbo,
    subject: 'GPT-4 Turbo',
    predicate: 'supports_context_window',
    object: '128k context window',
    normalized: 'GPT-4 Turbo supports a 128k context window.',
    validFrom: '2023-11-06T00:00:00Z',
    confidence: 0.96,
    docId: docIds.turboDevday,
    topicCluster: 'frontier_llms',
  },
  {
    id: claimIds.turboAprilCutoff,
    entityId: entityIds.turbo,
    subject: 'GPT-4 Turbo',
    predicate: 'has_knowledge_cutoff',
    object: 'April 2023',
    normalized: 'GPT-4 Turbo had an April 2023 knowledge cutoff when announced at DevDay.',
    validFrom: '2023-11-06T00:00:00Z',
    validUntil: '2024-04-09T00:00:00Z',
    confidence: 0.9,
    docId: docIds.turboDevday,
    topicCluster: 'frontier_llms',
    contradictionStatus: 'has_contradiction',
  },
  {
    id: claimIds.turboDecemberCutoff,
    entityId: entityIds.turbo,
    subject: 'GPT-4 Turbo',
    predicate: 'has_knowledge_cutoff',
    object: 'December 2023',
    normalized: 'GPT-4 Turbo 2024-04-09 has a December 2023 knowledge cutoff.',
    validFrom: '2024-04-09T00:00:00Z',
    confidence: 0.9,
    docId: docIds.turboModelDocs,
    topicCluster: 'frontier_llms',
    contradictionStatus: 'has_contradiction',
  },
];

function hashText(text) {
  return `first-proof:${createHash('sha256').update(text).digest('hex')}`;
}

async function upsertSources(client) {
  for (const source of sources) {
    await client.query(
      `
      INSERT INTO sources (
        id, slug, name, description, source_type, adapter_name, adapter_config,
        run_cadence_seconds, license_spdx, redistribution_allowed, summary_allowed,
        citation_only, license_notes, rate_limit_requests_per_minute, is_active,
        is_paused, metadata
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7::jsonb,
        NULL, NULL, false, true,
        false, $8, $9, true,
        false, $10::jsonb
      )
      ON CONFLICT (slug) DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        source_type = EXCLUDED.source_type,
        adapter_name = EXCLUDED.adapter_name,
        adapter_config = EXCLUDED.adapter_config,
        redistribution_allowed = EXCLUDED.redistribution_allowed,
        summary_allowed = EXCLUDED.summary_allowed,
        citation_only = EXCLUDED.citation_only,
        license_notes = EXCLUDED.license_notes,
        rate_limit_requests_per_minute = EXCLUDED.rate_limit_requests_per_minute,
        is_active = EXCLUDED.is_active,
        is_paused = EXCLUDED.is_paused,
        metadata = EXCLUDED.metadata,
        updated_at = now()
      `,
      [
        source.id,
        source.slug,
        source.name,
        source.description,
        source.sourceType,
        source.adapterName,
        JSON.stringify(source.adapterConfig),
        source.licenseNotes,
        source.rateLimit,
        JSON.stringify(source.metadata),
      ],
    );
  }
}

async function upsertDocuments(client) {
  for (const document of documents) {
    await client.query(
      `
      INSERT INTO source_documents (
        id, source_id, content_hash, external_id, url, title, language, published_at,
        cleaned_text, content_length, document_type, redistribution_allowed,
        summary_allowed, citation_only, metadata
      ) VALUES (
        $1, $2, $3, $4, $5, $6, 'en', $7::timestamptz,
        $8, $9, $10, false,
        true, false, $11::jsonb
      )
      ON CONFLICT (id) DO UPDATE SET
        source_id = EXCLUDED.source_id,
        external_id = EXCLUDED.external_id,
        url = EXCLUDED.url,
        title = EXCLUDED.title,
        published_at = EXCLUDED.published_at,
        cleaned_text = EXCLUDED.cleaned_text,
        content_length = EXCLUDED.content_length,
        document_type = EXCLUDED.document_type,
        redistribution_allowed = EXCLUDED.redistribution_allowed,
        summary_allowed = EXCLUDED.summary_allowed,
        citation_only = EXCLUDED.citation_only,
        metadata = EXCLUDED.metadata
      `,
      [
        document.id,
        document.sourceId,
        hashText(document.text),
        document.externalId,
        document.url,
        document.title,
        document.publishedAt,
        document.text,
        Buffer.byteLength(document.text, 'utf8'),
        document.documentType,
        JSON.stringify(document.metadata),
      ],
    );
  }
}

async function upsertEntities(client) {
  for (const entity of entities) {
    await client.query(
      `
      INSERT INTO entities (
        id, type_id, canonical_name, description, current_state, importance_score,
        first_seen_at, last_updated_at, metadata
      ) VALUES (
        $1, $2, $3, $4, '{}'::jsonb, $5,
        $6::timestamptz, $7::timestamptz, $8::jsonb
      )
      ON CONFLICT (id) DO UPDATE SET
        type_id = EXCLUDED.type_id,
        canonical_name = EXCLUDED.canonical_name,
        description = EXCLUDED.description,
        importance_score = EXCLUDED.importance_score,
        first_seen_at = EXCLUDED.first_seen_at,
        last_updated_at = EXCLUDED.last_updated_at,
        metadata = EXCLUDED.metadata,
        updated_at = now()
      `,
      [
        entity.id,
        entity.typeId,
        entity.name,
        entity.description,
        entity.importance,
        entity.firstSeenAt,
        entity.lastUpdatedAt,
        JSON.stringify({ corpus_track: 'first_proof' }),
      ],
    );
    await client.query(
      `
      INSERT INTO entity_aliases (entity_id, alias, alias_type, language, is_primary)
      VALUES ($1, $2, 'name', 'en', true)
      ON CONFLICT DO NOTHING
      `,
      [entity.id, entity.name],
    );
  }
}

async function upsertClaims(client) {
  for (const claim of claims) {
    const metadata = {
      topic_cluster: claim.topicCluster,
      corpus_taxonomy: 'ai_history',
      corpus_track: 'first_proof',
      source_class: documents.find((document) => document.id === claim.docId)?.metadata
        .source_class,
      reviewed_backfill: 'scripts/dev/backfill-first-proof-corpus.mjs',
    };
    await client.query(
      `
      INSERT INTO claims (
        id, subject_entity_id, subject_text, predicate, object_text, qualifiers,
        normalized_text, raw_quote, raw_spans, valid_from, valid_until, extractor,
        extraction_confidence, source_document_ids, contradiction_status, status,
        metadata
      ) VALUES (
        $1, $2, $3, $4, $5, '{}'::jsonb,
        $6, NULL, $7::jsonb, $8::timestamptz, $9::timestamptz, 'reviewed_first_proof_backfill',
        $10, ARRAY[$11::uuid], $12, 'active',
        $13::jsonb
      )
      ON CONFLICT (id) DO UPDATE SET
        subject_entity_id = EXCLUDED.subject_entity_id,
        subject_text = EXCLUDED.subject_text,
        predicate = EXCLUDED.predicate,
        object_text = EXCLUDED.object_text,
        normalized_text = EXCLUDED.normalized_text,
        raw_quote = EXCLUDED.raw_quote,
        raw_spans = EXCLUDED.raw_spans,
        valid_from = EXCLUDED.valid_from,
        valid_until = EXCLUDED.valid_until,
        extractor = EXCLUDED.extractor,
        extraction_confidence = EXCLUDED.extraction_confidence,
        source_document_ids = EXCLUDED.source_document_ids,
        contradiction_status = EXCLUDED.contradiction_status,
        status = EXCLUDED.status,
        metadata = EXCLUDED.metadata,
        updated_at = now()
      `,
      [
        claim.id,
        claim.entityId,
        claim.subject,
        claim.predicate,
        claim.object,
        claim.normalized,
        JSON.stringify([{ document_id: claim.docId, char_start: null, char_end: null }]),
        claim.validFrom,
        claim.validUntil ?? null,
        claim.confidence,
        claim.docId,
        claim.contradictionStatus ?? 'none',
        JSON.stringify(metadata),
      ],
    );
    await client.query(
      `
      INSERT INTO claim_evidence (
        claim_id, document_id, support_strength, confidence, char_offset_start,
        char_offset_end, quote_excerpt
      ) VALUES ($1, $2, 'supports', $3, NULL, NULL, NULL)
      ON CONFLICT (claim_id, document_id) DO UPDATE SET
        support_strength = EXCLUDED.support_strength,
        confidence = EXCLUDED.confidence,
        char_offset_start = EXCLUDED.char_offset_start,
        char_offset_end = EXCLUDED.char_offset_end,
        quote_excerpt = EXCLUDED.quote_excerpt
      `,
      [claim.id, claim.docId, claim.confidence],
    );
  }
}

async function upsertContradictions(client) {
  await client.query(
    `
    INSERT INTO claim_contradictions (
      claim_a_id, claim_b_id, detection_method, confidence, description, resolution_status
    ) VALUES (
      $1, $2, 'human', 0.9,
      'Reviewed first-proof stale-data pair: GPT-4 Turbo knowledge-cutoff claim changed between the DevDay preview and the 2024-04-09 model documentation.',
      'open'
    )
    ON CONFLICT (claim_a_id, claim_b_id) DO UPDATE SET
      detection_method = EXCLUDED.detection_method,
      confidence = EXCLUDED.confidence,
      description = EXCLUDED.description,
      resolution_status = EXCLUDED.resolution_status
    `,
    [claimIds.turboAprilCutoff, claimIds.turboDecemberCutoff],
  );
}

async function insertFactVersions(client) {
  for (const entity of entities) {
    const claim = claims.find((item) => item.entityId === entity.id);
    if (!claim) continue;
    const factId = `00000000-0000-4400-8400-000000000${String(500 + entities.indexOf(entity) + 1).padStart(3, '0')}`;
    await client.query(
      `
      INSERT INTO fact_versions (
        id, fact_subject_type, fact_subject_id, payload, valid_from, source_document_ids,
        claim_ids, confidence, produced_by
      ) VALUES (
        $1, 'entity', $2, $3::jsonb, $4::timestamptz, ARRAY[$5::uuid],
        ARRAY[$6::uuid], $7, 'reviewed_first_proof_backfill'
      )
      ON CONFLICT (id) DO NOTHING
      `,
      [
        factId,
        entity.id,
        JSON.stringify({ canonical_name: entity.name, corpus_track: 'first_proof' }),
        claim.validFrom,
        claim.docId,
        claim.id,
        claim.confidence,
      ],
    );
  }
}

async function markReviewRecord(client) {
  await client.query(
    `
    INSERT INTO review_records (
      id, target_type, target_id, concern_type, summary, status, metadata
    ) VALUES (
      '00000000-0000-4400-8400-000000000601',
      'coverage',
      'workstream-4-first-proof',
      'source_quality',
      'Reviewed first-proof source rows applied; continue broad-corpus expansion review.',
      'resolved',
      '{"corpus_track":"first_proof","script":"scripts/dev/backfill-first-proof-corpus.mjs"}'::jsonb
    )
    ON CONFLICT (id) DO UPDATE SET
      status = EXCLUDED.status,
      metadata = EXCLUDED.metadata,
      resolved_at = COALESCE(review_records.resolved_at, now()),
      updated_at = now()
    `,
  );
}

async function summarize(client) {
  const sourceRows = await client.query(
    "SELECT count(*)::int AS count FROM sources WHERE metadata->>'corpus_track' = 'first_proof'",
  );
  const docRows = await client.query(
    "SELECT count(*)::int AS count FROM source_documents WHERE metadata->>'corpus_track' = 'first_proof'",
  );
  const claimRows = await client.query(
    "SELECT count(*)::int AS count FROM claims WHERE metadata->>'corpus_track' = 'first_proof'",
  );
  const evidenceRows = await client.query(`
    SELECT count(*)::int AS count
    FROM claim_evidence ce
    JOIN claims c ON c.id = ce.claim_id
    WHERE c.metadata->>'corpus_track' = 'first_proof'
  `);
  const factRows = await client.query(
    "SELECT count(*)::int AS count FROM fact_versions WHERE produced_by = 'reviewed_first_proof_backfill'",
  );
  return {
    sources: sourceRows.rows[0].count,
    sourceDocuments: docRows.rows[0].count,
    claims: claimRows.rows[0].count,
    claimEvidence: evidenceRows.rows[0].count,
    factVersions: factRows.rows[0].count,
  };
}

async function main() {
  const databaseUrl = loadDatabaseUrl();
  if (!databaseUrl) {
    console.error('DATABASE_URL is required. The value is not printed by this script.');
    process.exit(2);
  }

  const pg = (await import('pg')).default;
  const client = new pg.Client({ connectionString: databaseUrl });
  await client.connect();

  try {
    if (!apply) {
      const before = await summarize(client);
      const payload = {
        mode: 'dry-run',
        wouldApply: {
          sources: sources.length,
          sourceDocuments: documents.length,
          entities: entities.length,
          claims: claims.length,
          claimEvidence: claims.length,
          contradictions: 1,
          factVersions: entities.length,
        },
        currentFirstProofRows: before,
      };
      if (json) console.log(JSON.stringify(payload, null, 2));
      else {
        console.log('mode: dry-run');
        console.log(
          `would apply sources=${sources.length} documents=${documents.length} claims=${claims.length}`,
        );
        console.log(`current first-proof rows: ${JSON.stringify(before)}`);
        console.log('run with --apply to write reviewed first-proof corpus rows');
      }
      return;
    }

    await client.query('BEGIN');
    await upsertSources(client);
    await upsertDocuments(client);
    await upsertEntities(client);
    await upsertClaims(client);
    await upsertContradictions(client);
    await insertFactVersions(client);
    await markReviewRecord(client);
    await client.query('COMMIT');

    const after = await summarize(client);
    const payload = { mode: 'apply', applied: true, firstProofRows: after };
    if (json) console.log(JSON.stringify(payload, null, 2));
    else {
      console.log('mode: apply');
      console.log(`first-proof rows: ${JSON.stringify(after)}`);
    }
  } catch (error) {
    try {
      await client.query('ROLLBACK');
    } catch {
      // Ignore rollback failures; the original error is the useful one.
    }
    throw error;
  } finally {
    await client.end();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
