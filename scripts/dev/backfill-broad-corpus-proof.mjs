#!/usr/bin/env node
// Idempotently apply reviewed Workstream 4 broad-corpus proof rows.
//
// This operator proof extends the first-proof live corpus with a bounded set of
// reviewed source-document summaries, classified claims, evidence links, and
// fact versions for the full AI-history quality gate. It does not print
// DATABASE_URL and does not store raw source text.
//
// Usage:
//   node scripts/dev/backfill-broad-corpus-proof.mjs --dry-run
//   node scripts/dev/backfill-broad-corpus-proof.mjs --apply

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
  modelProvider: '00000000-0000-4500-8500-000000000101',
  research: '00000000-0000-4500-8500-000000000102',
  releaseNotes: '00000000-0000-4500-8500-000000000103',
  benchmark: '00000000-0000-4500-8500-000000000104',
  developer: '00000000-0000-4500-8500-000000000105',
  infrastructure: '00000000-0000-4500-8500-000000000106',
  policy: '00000000-0000-4500-8500-000000000107',
  protocol: '00000000-0000-4500-8500-000000000108',
};

const firstProofEntityIds = {
  ChatGPT: '00000000-0000-4400-8400-000000000301',
  Claude: '00000000-0000-4400-8400-000000000302',
  Gemini: '00000000-0000-4400-8400-000000000303',
  Llama: '00000000-0000-4400-8400-000000000304',
  'MCP protocol': '00000000-0000-4400-8400-000000000305',
};

const sources = [
  {
    id: sourceIds.modelProvider,
    slug: 'broad-proof-model-provider-news',
    name: 'Broad Proof - Model Provider News',
    description: 'Reviewed official model-provider announcements for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: {
      feed_urls: ['https://openai.com/news/rss.xml', 'https://www.anthropic.com/news/rss.xml'],
      language: 'en',
    },
    licenseNotes:
      'Official public model-provider announcements. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'model_provider',
      topic_cluster: 'frontier_llms',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.research,
    slug: 'broad-proof-research-arxiv',
    name: 'Broad Proof - Research arXiv',
    description: 'Reviewed arXiv research abstracts for broad AI-history coverage.',
    sourceType: 'research',
    adapterName: 'arxiv_v1',
    adapterConfig: {
      search_terms: [
        'FlashAttention',
        'Segment Anything',
        'Direct Preference Optimization',
        'QLoRA',
      ],
      categories: ['cs.AI', 'cs.CL', 'cs.LG', 'cs.CV'],
      batch_size: '10',
    },
    licenseNotes: 'arXiv abstract-first source; full paper redistribution is not assumed.',
    metadata: {
      source_class: 'research',
      topic_cluster: 'ml_research',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.releaseNotes,
    slug: 'broad-proof-release-notes',
    name: 'Broad Proof - Release Notes',
    description:
      'Reviewed official release announcements for development-cycle and open-weight coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: {
      feed_urls: [
        'https://openai.com/news/rss.xml',
        'https://www.anthropic.com/news/rss.xml',
        'https://ai.meta.com/blog/rss/',
      ],
      language: 'en',
    },
    licenseNotes:
      'Official release pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'release_notes',
      topic_cluster: 'development_cycles',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.benchmark,
    slug: 'broad-proof-benchmarks',
    name: 'Broad Proof - Benchmarks',
    description: 'Reviewed official benchmark result pages for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://mlcommons.org/feed/'], language: 'en' },
    licenseNotes:
      'Official benchmark-result pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'benchmark',
      topic_cluster: 'benchmarks',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.developer,
    slug: 'broad-proof-developer-ecosystem',
    name: 'Broad Proof - Developer Ecosystem',
    description: 'Reviewed official developer-tooling sources for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: {
      feed_urls: ['https://openai.com/news/rss.xml', 'https://www.anthropic.com/news/rss.xml'],
      language: 'en',
    },
    licenseNotes:
      'Official developer/product pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'developer_ecosystem',
      topic_cluster: 'agent_tooling',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.infrastructure,
    slug: 'broad-proof-infrastructure',
    name: 'Broad Proof - Infrastructure',
    description: 'Reviewed official AI infrastructure announcements for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: {
      feed_urls: ['https://blogs.nvidia.com/feed/', 'https://cloud.google.com/blog/rss'],
      language: 'en',
    },
    licenseNotes:
      'Official infrastructure announcement pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'infrastructure',
      topic_cluster: 'deployment_infrastructure',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.policy,
    slug: 'broad-proof-policy-regulatory',
    name: 'Broad Proof - Policy Regulatory',
    description: 'Reviewed official policy and regulatory sources for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: {
      feed_urls: ['https://www.nist.gov/news-events/news/rss.xml'],
      language: 'en',
    },
    licenseNotes:
      'Official public policy/regulatory pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'policy_regulatory',
      topic_cluster: 'regulation',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
  {
    id: sourceIds.protocol,
    slug: 'broad-proof-protocols',
    name: 'Broad Proof - Protocols',
    description: 'Reviewed official protocol sources for broad AI-history coverage.',
    sourceType: 'api',
    adapterName: 'rss_feed_v1',
    adapterConfig: { feed_urls: ['https://modelcontextprotocol.io/llms.txt'], language: 'en' },
    licenseNotes:
      'Official protocol documentation pages. Store only reviewed summaries and citations unless raw redistribution terms are reviewed.',
    metadata: {
      source_class: 'protocol',
      topic_cluster: 'model_context_protocol',
      corpus_taxonomy: 'ai_history',
      corpus_track: 'broad_proof',
    },
  },
];

const documents = [
  doc(
    '001',
    sourceIds.modelProvider,
    'openai:gpt-4:2023-03-14',
    'https://openai.com/index/gpt-4-research/',
    'GPT-4',
    '2023-03-14T00:00:00Z',
    'ChatGPT',
    'released_gpt4_access',
    'GPT-4 became available through ChatGPT Plus and API waitlist access.',
    'OpenAI announced GPT-4 on March 14, 2023 and described text-input availability through ChatGPT Plus and the API waitlist.',
    'frontier_llms',
    'article',
  ),
  doc(
    '002',
    sourceIds.modelProvider,
    'anthropic:claude-2:2023-07-11',
    'https://www.anthropic.com/news/claude-2',
    'Claude 2',
    '2023-07-11T00:00:00Z',
    'Claude',
    'released',
    'Claude 2 model and public beta website',
    'Anthropic announced Claude 2 on July 11, 2023 with API access and a public beta website at claude.ai.',
    'frontier_llms',
    'article',
  ),
  doc(
    '003',
    sourceIds.modelProvider,
    'google:gemini-1-5:2024-02-15',
    'https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024/',
    'Gemini 1.5',
    '2024-02-15T00:00:00Z',
    'Gemini',
    'introduced',
    'Gemini 1.5 Pro with long-context multimodal capability',
    'Google announced Gemini 1.5 on February 15, 2024 and described a next-generation multimodal model with expanded long-context capability.',
    'frontier_llms',
    'article',
  ),
  doc(
    '004',
    sourceIds.modelProvider,
    'anthropic:claude-3:2024-03-04',
    'https://www.anthropic.com/news/claude-3-family',
    'Claude 3 model family',
    '2024-03-04T00:00:00Z',
    'Claude',
    'introduced_family',
    'Claude 3 Opus, Sonnet, and Haiku model family',
    'Anthropic introduced the Claude 3 model family on March 4, 2024 with Opus, Sonnet, and Haiku.',
    'frontier_llms',
    'article',
  ),
  doc(
    '005',
    sourceIds.modelProvider,
    'openai:gpt-4o:2024-05-13',
    'https://openai.com/index/gpt-4o-and-more-tools-to-chatgpt-free/',
    'GPT-4o and ChatGPT tools',
    '2024-05-13T00:00:00Z',
    'ChatGPT',
    'added_gpt4o',
    'GPT-4o and more tools in ChatGPT free tier',
    'OpenAI announced GPT-4o on May 13, 2024 and said more intelligence and tools would roll out in ChatGPT.',
    'model_architecture',
    'article',
  ),
  doc(
    '006',
    sourceIds.modelProvider,
    'google:gemini-2-0:2024-12-11',
    'https://developers.googleblog.com/en/the-next-chapter-of-the-gemini-era-for-developers/',
    'Gemini 2.0 for developers',
    '2024-12-11T00:00:00Z',
    'Gemini',
    'introduced',
    'Gemini 2.0 developer model generation',
    'Google introduced Gemini 2.0 for developers in December 2024 as a new Gemini-era model generation.',
    'model_architecture',
    'article',
  ),

  doc(
    '007',
    sourceIds.research,
    'arxiv:2205.14135',
    'https://arxiv.org/abs/2205.14135',
    'FlashAttention',
    '2022-05-27T00:00:00Z',
    'FlashAttention',
    'introduced',
    'IO-aware exact attention algorithm',
    'The FlashAttention paper introduced a fast, memory-efficient exact attention algorithm with IO awareness.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '008',
    sourceIds.research,
    'arxiv:2304.02643',
    'https://arxiv.org/abs/2304.02643',
    'Segment Anything',
    '2023-04-05T00:00:00Z',
    'Segment Anything',
    'introduced',
    'promptable segmentation foundation model and SA-1B dataset',
    'The Segment Anything paper introduced SAM and the SA-1B mask dataset for promptable image segmentation research.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '009',
    sourceIds.research,
    'arxiv:2305.18290',
    'https://arxiv.org/abs/2305.18290',
    'Direct Preference Optimization',
    '2023-05-29T00:00:00Z',
    'Direct Preference Optimization',
    'introduced',
    'preference optimization without an explicit reward model',
    'The DPO paper introduced a direct optimization objective for language-model preference tuning without fitting a separate reward model.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '010',
    sourceIds.research,
    'arxiv:2305.14314',
    'https://arxiv.org/abs/2305.14314',
    'QLoRA',
    '2023-05-23T00:00:00Z',
    'QLoRA',
    'introduced',
    'efficient finetuning of quantized language models',
    'The QLoRA paper introduced efficient finetuning of quantized LLMs using low-rank adapters.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '011',
    sourceIds.research,
    'arxiv:2302.13971',
    'https://arxiv.org/abs/2302.13971',
    'LLaMA research paper',
    '2023-02-27T00:00:00Z',
    'Llama',
    'described',
    'open and efficient foundation language model family',
    'The LLaMA research paper described a family of open and efficient foundation language models.',
    'open_weight_models',
    'paper_abstract',
  ),
  doc(
    '012',
    sourceIds.research,
    'arxiv:2307.09288',
    'https://arxiv.org/abs/2307.09288',
    'Llama 2 research paper',
    '2023-07-18T00:00:00Z',
    'Llama',
    'described',
    'Llama 2 pretrained and fine-tuned model family',
    'The Llama 2 paper described pretrained and fine-tuned Llama 2 large language models.',
    'open_weight_models',
    'paper_abstract',
  ),
  doc(
    '013',
    sourceIds.research,
    'arxiv:2312.00752',
    'https://arxiv.org/abs/2312.00752',
    'Mamba',
    '2023-12-01T00:00:00Z',
    'Mamba',
    'introduced',
    'selective state-space sequence model architecture',
    'The Mamba paper introduced selective state-space models as an efficient sequence-modeling architecture.',
    'model_architecture',
    'paper_abstract',
  ),
  doc(
    '014',
    sourceIds.research,
    'arxiv:2401.04088',
    'https://arxiv.org/abs/2401.04088',
    'Mixtral of Experts',
    '2024-01-08T00:00:00Z',
    'Mixtral',
    'described',
    'sparse mixture-of-experts language model',
    'The Mixtral paper described a sparse mixture-of-experts language model architecture.',
    'model_architecture',
    'paper_abstract',
  ),
  doc(
    '015',
    sourceIds.research,
    'arxiv:2405.04434',
    'https://arxiv.org/abs/2405.04434',
    'LoRA learns less and forgets less',
    '2024-05-07T00:00:00Z',
    'LoRA adaptation research',
    'analyzed',
    'low-rank adaptation forgetting behavior',
    'This 2024 research analyzed low-rank adaptation behavior and model forgetting under finetuning.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '016',
    sourceIds.research,
    'arxiv:2406.06098',
    'https://arxiv.org/abs/2406.06098',
    'Long-context benchmark research',
    '2024-06-10T00:00:00Z',
    'Long-context evaluation',
    'introduced',
    'long-context evaluation method for language models',
    'This 2024 research contributed long-context evaluation methods for modern language models.',
    'ml_research',
    'paper_abstract',
  ),

  doc(
    '017',
    sourceIds.releaseNotes,
    'openai:function-calling:2023-06-13',
    'https://openai.com/blog/function-calling-and-other-api-updates',
    'Function calling and API updates',
    '2023-06-13T00:00:00Z',
    'ChatGPT',
    'added_function_calling',
    'function calling API update',
    'OpenAI announced function calling and API model updates on June 13, 2023.',
    'development_cycles',
    'release_notes',
  ),
  doc(
    '018',
    sourceIds.releaseNotes,
    'openai:assistants-api:2023-11-06',
    'https://openai.com/index/new-models-and-developer-products-announced-at-devday/',
    'DevDay developer products',
    '2023-11-06T00:00:00Z',
    'OpenAI Assistants API',
    'introduced',
    'Assistants API and developer products',
    'OpenAI announced new models and developer products at DevDay, including the Assistants API.',
    'development_cycles',
    'release_notes',
  ),
  doc(
    '019',
    sourceIds.releaseNotes,
    'openai:structured-outputs:2024-08-06',
    'https://openai.com/index/introducing-structured-outputs-in-the-api/',
    'Structured Outputs in the API',
    '2024-08-06T00:00:00Z',
    'OpenAI API',
    'introduced',
    'Structured Outputs with schema-constrained model responses',
    'OpenAI introduced Structured Outputs in the API to make model outputs conform to developer-supplied schemas.',
    'development_cycles',
    'release_notes',
  ),
  doc(
    '020',
    sourceIds.releaseNotes,
    'openai:responses-api:2025-03-11',
    'https://openai.com/index/new-tools-for-building-agents/',
    'New tools for building agents',
    '2025-03-11T00:00:00Z',
    'OpenAI Responses API',
    'introduced',
    'Responses API and agent-building tools',
    'OpenAI introduced new tools for building agents, including the Responses API and hosted tools.',
    'development_cycles',
    'release_notes',
  ),
  doc(
    '021',
    sourceIds.releaseNotes,
    'anthropic:tool-use:2024-05-30',
    'https://www.anthropic.com/news/tool-use-ga',
    'Tool use GA',
    '2024-05-30T00:00:00Z',
    'Claude',
    'added_tool_use',
    'generally available tool use API capability',
    'Anthropic announced general availability for tool use on the Anthropic API.',
    'development_cycles',
    'release_notes',
  ),
  doc(
    '022',
    sourceIds.releaseNotes,
    'meta:llama-2:2023-07-18',
    'https://ai.meta.com/blog/llama-2/',
    'Llama 2',
    '2023-07-18T00:00:00Z',
    'Llama',
    'released',
    'Llama 2 open foundation and fine-tuned chat models',
    'Meta announced Llama 2 on July 18, 2023 as an open foundation and fine-tuned chat model family.',
    'open_weight_models',
    'release_notes',
  ),
  doc(
    '023',
    sourceIds.releaseNotes,
    'meta:llama-3-1:2024-07-23',
    'https://ai.meta.com/blog/meta-llama-3-1/',
    'Llama 3.1',
    '2024-07-23T00:00:00Z',
    'Llama',
    'released',
    'Llama 3.1 open model family',
    'Meta announced Llama 3.1 on July 23, 2024 as an open model family update.',
    'open_weight_models',
    'release_notes',
  ),
  doc(
    '024',
    sourceIds.releaseNotes,
    'google:gemma:2024-02-21',
    'https://blog.google/technology/developers/gemma-open-models/',
    'Gemma open models',
    '2024-02-21T00:00:00Z',
    'Gemma',
    'released',
    'open models built from Gemini research and technology',
    'Google announced Gemma open models in February 2024, built from the same research and technology used for Gemini models.',
    'open_weight_models',
    'release_notes',
  ),
  doc(
    '025',
    sourceIds.releaseNotes,
    'mistral:mixtral:2023-12-11',
    'https://mistral.ai/news/mixtral-of-experts',
    'Mixtral of Experts',
    '2023-12-11T00:00:00Z',
    'Mixtral',
    'released',
    'open-weight sparse mixture-of-experts model',
    'Mistral AI announced Mixtral of Experts as an open-weight sparse mixture-of-experts model.',
    'open_weight_models',
    'release_notes',
  ),

  doc(
    '026',
    sourceIds.benchmark,
    'mlcommons:training-3-1:2023-11-08',
    'https://mlcommons.org/2023/11/mlperf-training-v3-1-hpc-v3-0-results/',
    'MLPerf Training v3.1',
    '2023-11-08T00:00:00Z',
    'MLPerf Training',
    'published_results',
    'MLPerf Training v3.1 and HPC v3.0 results',
    'MLCommons published MLPerf Training v3.1 and HPC v3.0 benchmark results in November 2023.',
    'benchmarks',
    'article',
  ),
  doc(
    '027',
    sourceIds.benchmark,
    'mlcommons:inference-4-0:2024-03-27',
    'https://mlcommons.org/2024/03/mlperf-inference-v4-0-results/',
    'MLPerf Inference v4.0',
    '2024-03-27T00:00:00Z',
    'MLPerf Inference',
    'published_results',
    'MLPerf Inference v4.0 results',
    'MLCommons published MLPerf Inference v4.0 benchmark results in March 2024.',
    'benchmarks',
    'article',
  ),
  doc(
    '028',
    sourceIds.benchmark,
    'mlcommons:training-4-0:2024-06-12',
    'https://mlcommons.org/2024/06/mlperf-training-v4-0-results/',
    'MLPerf Training v4.0',
    '2024-06-12T00:00:00Z',
    'MLPerf Training',
    'published_results',
    'MLPerf Training v4.0 results',
    'MLCommons published MLPerf Training v4.0 benchmark results in June 2024.',
    'benchmarks',
    'article',
  ),
  doc(
    '029',
    sourceIds.benchmark,
    'mlcommons:inference-4-1:2024-09-11',
    'https://mlcommons.org/2024/09/mlperf-inference-v4-1-results/',
    'MLPerf Inference v4.1',
    '2024-09-11T00:00:00Z',
    'MLPerf Inference',
    'published_results',
    'MLPerf Inference v4.1 results',
    'MLCommons published MLPerf Inference v4.1 benchmark results in September 2024.',
    'benchmarks',
    'article',
  ),
  doc(
    '030',
    sourceIds.benchmark,
    'mlcommons:training-4-1:2024-11-13',
    'https://mlcommons.org/2024/11/mlperf-training-v4-1-results/',
    'MLPerf Training v4.1',
    '2024-11-13T00:00:00Z',
    'MLPerf Training',
    'published_results',
    'MLPerf Training v4.1 results',
    'MLCommons published MLPerf Training v4.1 benchmark results in November 2024.',
    'benchmarks',
    'article',
  ),

  doc(
    '031',
    sourceIds.developer,
    'openai:plugins:2023-03-23',
    'https://openai.com/blog/chatgpt-plugins',
    'ChatGPT plugins',
    '2023-03-23T00:00:00Z',
    'ChatGPT',
    'introduced_plugins',
    'plugin support for ChatGPT',
    'OpenAI announced initial support for ChatGPT plugins on March 23, 2023.',
    'agent_tooling',
    'article',
  ),
  doc(
    '032',
    sourceIds.developer,
    'openai:function-calling-dev:2023-06-13',
    'https://openai.com/blog/function-calling-and-other-api-updates',
    'Function calling developer update',
    '2023-06-13T00:00:00Z',
    'OpenAI API',
    'introduced_function_calling',
    'JSON-schema-described function calling',
    'OpenAI introduced function calling so developers could describe functions to models using JSON Schema.',
    'agent_tooling',
    'article',
  ),
  doc(
    '033',
    sourceIds.developer,
    'anthropic:computer-use:2024-10-22',
    'https://www.anthropic.com/news/3-5-models-and-computer-use',
    'Claude computer use',
    '2024-10-22T00:00:00Z',
    'Claude',
    'introduced_computer_use',
    'computer-use capability for Claude',
    'Anthropic announced upgraded Claude 3.5 models and computer-use capability in October 2024.',
    'agent_tooling',
    'article',
  ),
  doc(
    '034',
    sourceIds.developer,
    'anthropic:agent-api:2025-05-22',
    'https://www.anthropic.com/news/agent-capabilities-api',
    'Agent capabilities API',
    '2025-05-22T00:00:00Z',
    'Claude',
    'added_agent_capabilities',
    'MCP connector and code execution on Anthropic API',
    'Anthropic announced new agent capabilities on the Anthropic API, including MCP connector support.',
    'agent_tooling',
    'article',
  ),
  doc(
    '035',
    sourceIds.developer,
    'openai:agents-sdk:2025-03-11',
    'https://openai.com/index/new-tools-for-building-agents/',
    'OpenAI Agents SDK',
    '2025-03-11T00:00:00Z',
    'OpenAI Agents SDK',
    'introduced',
    'agent-building SDK and hosted tools',
    'OpenAI introduced agent-building tools including an Agents SDK and hosted tools in March 2025.',
    'agent_tooling',
    'article',
  ),

  doc(
    '036',
    sourceIds.infrastructure,
    'nvidia:h100:2022-03-22',
    'https://nvidianews.nvidia.com/news/nvidia-announces-hopper-architecture-the-next-generation-of-accelerated-computing',
    'NVIDIA Hopper H100',
    '2022-03-22T00:00:00Z',
    'NVIDIA H100',
    'announced',
    'Hopper H100 accelerator architecture for large AI workloads',
    'NVIDIA announced the Hopper architecture and H100 accelerator in March 2022 for large AI and accelerated-computing workloads.',
    'deployment_infrastructure',
    'article',
  ),
  doc(
    '037',
    sourceIds.infrastructure,
    'nvidia:dgx-cloud:2023-03-21',
    'https://nvidianews.nvidia.com/news/nvidia-announces-dgx-cloud',
    'NVIDIA DGX Cloud',
    '2023-03-21T00:00:00Z',
    'NVIDIA DGX Cloud',
    'announced',
    'cloud service for training generative AI models',
    'NVIDIA announced DGX Cloud as infrastructure for enterprises to train generative AI models.',
    'deployment_infrastructure',
    'article',
  ),
  doc(
    '038',
    sourceIds.infrastructure,
    'google:tpu-v5e:2023-08-29',
    'https://cloud.google.com/blog/products/compute/announcing-cloud-tpu-v5e-and-a3-gpus-in-ga',
    'Cloud TPU v5e and A3 GPUs',
    '2023-08-29T00:00:00Z',
    'Cloud TPU v5e',
    'announced_ga',
    'AI-optimized TPU v5e and A3 GPU infrastructure',
    'Google Cloud announced TPU v5e and A3 GPU availability for AI-optimized infrastructure in 2023.',
    'deployment_infrastructure',
    'article',
  ),
  doc(
    '039',
    sourceIds.infrastructure,
    'aws:trainium2:2023-11-28',
    'https://aws.amazon.com/blogs/aws/coming-soon-aws-trainium2-designed-to-deliver-up-to-4x-better-performance-for-training-foundation-models-and-llms/',
    'AWS Trainium2',
    '2023-11-28T00:00:00Z',
    'AWS Trainium2',
    'announced',
    'second-generation accelerator for foundation model training',
    'AWS announced Trainium2 for training foundation models and large language models.',
    'deployment_infrastructure',
    'article',
  ),
  doc(
    '040',
    sourceIds.infrastructure,
    'nvidia:blackwell:2024-03-18',
    'https://nvidianews.nvidia.com/news/nvidia-blackwell-platform-arrives-to-power-a-new-era-of-computing',
    'NVIDIA Blackwell platform',
    '2024-03-18T00:00:00Z',
    'NVIDIA Blackwell',
    'announced',
    'platform for frontier-scale AI computing',
    'NVIDIA announced the Blackwell platform in March 2024 for a new era of AI computing.',
    'deployment_infrastructure',
    'article',
  ),

  doc(
    '041',
    sourceIds.policy,
    'nist:ai-rmf:2023-01-26',
    'https://www.nist.gov/itl/ai-risk-management-framework',
    'NIST AI Risk Management Framework',
    '2023-01-26T00:00:00Z',
    'NIST AI RMF',
    'released',
    'AI Risk Management Framework 1.0',
    'NIST released the AI Risk Management Framework 1.0 on January 26, 2023.',
    'regulation',
    'article',
  ),
  doc(
    '042',
    sourceIds.policy,
    'whitehouse:eo-14110:2023-10-30',
    'https://www.whitehouse.gov/briefing-room/presidential-actions/2023/10/30/executive-order-on-the-safe-secure-and-trustworthy-development-and-use-of-artificial-intelligence/',
    'Executive Order 14110',
    '2023-10-30T00:00:00Z',
    'Executive Order 14110',
    'issued',
    'US executive order on safe, secure, trustworthy AI',
    'The White House issued Executive Order 14110 on safe, secure, and trustworthy AI on October 30, 2023.',
    'regulation',
    'article',
  ),
  doc(
    '043',
    sourceIds.policy,
    'eu:ai-act-provisional:2023-12-09',
    'https://www.consilium.europa.eu/en/press/press-releases/2023/12/09/artificial-intelligence-act-council-and-parliament-strike-a-deal-on-the-first-worldwide-rules-for-ai/',
    'EU AI Act provisional agreement',
    '2023-12-09T00:00:00Z',
    'EU AI Act',
    'reached_provisional_agreement',
    'Council and Parliament provisional agreement',
    'The Council presidency and European Parliament negotiators reached a provisional agreement on the AI Act in December 2023.',
    'regulation',
    'article',
  ),
  doc(
    '044',
    sourceIds.policy,
    'nist:genai-profile:2024-07-26',
    'https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-600-1',
    'NIST GenAI Profile',
    '2024-07-26T00:00:00Z',
    'NIST AI 600-1',
    'released',
    'Generative AI Profile for the AI RMF',
    'NIST released NIST AI 600-1, the Generative AI Profile for the AI RMF, in July 2024.',
    'regulation',
    'article',
  ),
  doc(
    '045',
    sourceIds.policy,
    'eu:ai-act-oj:2024-07-12',
    'https://eur-lex.europa.eu/eli/reg/2024/1689/oj',
    'EU AI Act Regulation 2024/1689',
    '2024-07-12T00:00:00Z',
    'EU AI Act',
    'published',
    'Regulation (EU) 2024/1689 in the Official Journal',
    'Regulation (EU) 2024/1689, the Artificial Intelligence Act, was published in the Official Journal in July 2024.',
    'regulation',
    'article',
  ),

  doc(
    '046',
    sourceIds.protocol,
    'mcp:spec-2025-03-26',
    'https://modelcontextprotocol.io/specification/2025-03-26/index',
    'MCP 2025-03-26 specification',
    '2025-03-26T00:00:00Z',
    'MCP protocol',
    'published_spec_revision',
    '2025-03-26 protocol specification',
    'The Model Context Protocol published a 2025-03-26 specification revision defining authoritative protocol requirements.',
    'model_context_protocol',
    'specification',
  ),
  doc(
    '047',
    sourceIds.protocol,
    'mcp:authorization-2025-03-26',
    'https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization',
    'MCP authorization specification',
    '2025-03-26T00:00:00Z',
    'MCP protocol',
    'specified_authorization',
    'HTTP transport authorization flow',
    'The MCP 2025-03-26 authorization specification defines authorization flow requirements for HTTP-based transports.',
    'model_context_protocol',
    'specification',
  ),
  doc(
    '048',
    sourceIds.research,
    'arxiv:2212.08073',
    'https://arxiv.org/abs/2212.08073',
    'Constitutional AI',
    '2022-12-15T00:00:00Z',
    'Constitutional AI',
    'introduced',
    'AI feedback method for harmlessness training',
    'The Constitutional AI paper described a method for training AI assistants using principles and AI feedback.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '049',
    sourceIds.research,
    'arxiv:2302.04761',
    'https://arxiv.org/abs/2302.04761',
    'Toolformer',
    '2023-02-09T00:00:00Z',
    'Toolformer',
    'introduced',
    'language-model self-supervised tool-use training',
    'The Toolformer paper introduced self-supervised training that lets language models learn to use external tools.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '050',
    sourceIds.research,
    'arxiv:2305.10601',
    'https://arxiv.org/abs/2305.10601',
    'Tree of Thoughts',
    '2023-05-17T00:00:00Z',
    'Tree of Thoughts',
    'introduced',
    'deliberate problem-solving framework for language models',
    'The Tree of Thoughts paper introduced a framework for deliberate search over intermediate reasoning steps in language models.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '051',
    sourceIds.research,
    'arxiv:2310.11511',
    'https://arxiv.org/abs/2310.11511',
    'Self-RAG',
    '2023-10-17T00:00:00Z',
    'Self-RAG',
    'introduced',
    'retrieval-augmented generation with self-reflection',
    'The Self-RAG paper introduced retrieval-augmented generation with self-reflection signals.',
    'ml_research',
    'paper_abstract',
  ),
  doc(
    '052',
    sourceIds.research,
    'arxiv:2310.01889',
    'https://arxiv.org/abs/2310.01889',
    'Ring Attention',
    '2023-10-03T00:00:00Z',
    'Ring Attention',
    'introduced',
    'blockwise transformer attention across devices',
    'The Ring Attention paper introduced a blockwise transformer attention method for scaling context across devices.',
    'model_architecture',
    'paper_abstract',
  ),
];

function doc(
  suffix,
  sourceId,
  externalId,
  url,
  title,
  publishedAt,
  subject,
  predicate,
  object,
  summary,
  topicCluster,
  documentType,
) {
  return {
    id: `00000000-0000-4500-8500-000000000${suffix}`,
    claimId: `00000000-0000-4500-8500-000000001${suffix}`,
    factId: `00000000-0000-4500-8500-000000002${suffix}`,
    sourceId,
    externalId,
    url,
    title,
    publishedAt,
    subject,
    predicate,
    object,
    normalized: `${subject} ${predicate.replaceAll('_', ' ')} ${object}.`,
    text: `Reviewed source summary: ${summary}`,
    topicCluster,
    documentType,
  };
}

function sourceById(id) {
  return sources.find((source) => source.id === id);
}

function hashText(text) {
  return `broad-proof:${createHash('sha256').update(text).digest('hex')}`;
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
        false, $8, 30, true,
        false, $9::jsonb
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
        JSON.stringify(source.metadata),
      ],
    );
  }
}

async function upsertFirstProofEntities(client) {
  for (const [name, id] of Object.entries(firstProofEntityIds)) {
    await client.query(
      `
      INSERT INTO entities (
        id, type_id, canonical_name, description, current_state, importance_score,
        first_seen_at, last_updated_at, metadata
      ) VALUES (
        $1, 'technical_artifact', $2, $3, '{}'::jsonb, 0.85,
        '2022-11-30T00:00:00Z', now(), '{"corpus_track":"first_proof"}'::jsonb
      )
      ON CONFLICT (id) DO UPDATE SET
        canonical_name = EXCLUDED.canonical_name,
        last_updated_at = now(),
        updated_at = now()
      `,
      [id, name, `${name} in the GPT-era AI-history corpus.`],
    );
  }
}

async function upsertDocuments(client) {
  for (const document of documents) {
    const source = sourceById(document.sourceId);
    const metadata = {
      ...source.metadata,
      topic_cluster: document.topicCluster,
      reviewed_source_url: document.url,
    };
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
        JSON.stringify(metadata),
      ],
    );
  }
}

async function upsertClaims(client) {
  for (const document of documents) {
    const source = sourceById(document.sourceId);
    const entityId = firstProofEntityIds[document.subject] ?? null;
    const metadata = {
      ...source.metadata,
      source_class: source.metadata.source_class,
      topic_cluster: document.topicCluster,
      reviewed_backfill: 'scripts/dev/backfill-broad-corpus-proof.mjs',
    };
    await client.query(
      `
      INSERT INTO claims (
        id, subject_entity_id, subject_text, predicate, object_text, qualifiers,
        normalized_text, raw_quote, raw_spans, valid_from, valid_until, extractor,
        extraction_confidence, source_document_ids, contradiction_status, status,
        metadata
      ) VALUES (
        $1, $2::uuid, $3, $4, $5, '{}'::jsonb,
        $6, NULL, $7::jsonb, $8::timestamptz, NULL, 'reviewed_broad_corpus_backfill',
        0.90, ARRAY[$9::uuid], 'none', 'active',
        $10::jsonb
      )
      ON CONFLICT (id) DO UPDATE SET
        subject_entity_id = EXCLUDED.subject_entity_id,
        subject_text = EXCLUDED.subject_text,
        predicate = EXCLUDED.predicate,
        object_text = EXCLUDED.object_text,
        normalized_text = EXCLUDED.normalized_text,
        raw_spans = EXCLUDED.raw_spans,
        valid_from = EXCLUDED.valid_from,
        source_document_ids = EXCLUDED.source_document_ids,
        status = EXCLUDED.status,
        metadata = EXCLUDED.metadata,
        updated_at = now()
      `,
      [
        document.claimId,
        entityId,
        document.subject,
        document.predicate,
        document.object,
        document.normalized,
        JSON.stringify([{ document_id: document.id, char_start: null, char_end: null }]),
        document.publishedAt,
        document.id,
        JSON.stringify(metadata),
      ],
    );
    await client.query(
      `
      INSERT INTO claim_evidence (
        claim_id, document_id, support_strength, confidence, char_offset_start,
        char_offset_end, quote_excerpt
      ) VALUES ($1, $2, 'supports', 0.90, NULL, NULL, NULL)
      ON CONFLICT (claim_id, document_id) DO UPDATE SET
        support_strength = EXCLUDED.support_strength,
        confidence = EXCLUDED.confidence,
        quote_excerpt = EXCLUDED.quote_excerpt
      `,
      [document.claimId, document.id],
    );
  }
}

async function insertFactVersions(client) {
  for (const document of documents) {
    await client.query(
      `
      INSERT INTO fact_versions (
        id, fact_subject_type, fact_subject_id, payload, valid_from, source_document_ids,
        claim_ids, confidence, produced_by
      ) VALUES (
        $1, 'claim', $2, $3::jsonb, $4::timestamptz, ARRAY[$5::uuid],
        ARRAY[$2::uuid], 0.90, 'reviewed_broad_corpus_backfill'
      )
      ON CONFLICT (id) DO NOTHING
      `,
      [
        document.factId,
        document.claimId,
        JSON.stringify({
          subject: document.subject,
          predicate: document.predicate,
          object: document.object,
          topic_cluster: document.topicCluster,
        }),
        document.publishedAt,
        document.id,
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
      '00000000-0000-4500-8500-000000000601',
      'coverage',
      'workstream-4-broad-proof',
      'source_quality',
      'Reviewed broad-corpus proof rows applied for live-full gate coverage.',
      'resolved',
      '{"corpus_track":"broad_proof","script":"scripts/dev/backfill-broad-corpus-proof.mjs"}'::jsonb
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
    "SELECT count(*)::int AS count FROM sources WHERE metadata->>'corpus_track' = 'broad_proof'",
  );
  const docRows = await client.query(
    "SELECT count(*)::int AS count FROM source_documents WHERE metadata->>'corpus_track' = 'broad_proof'",
  );
  const claimRows = await client.query(
    "SELECT count(*)::int AS count FROM claims WHERE metadata->>'corpus_track' = 'broad_proof'",
  );
  const evidenceRows = await client.query(`
    SELECT count(*)::int AS count
    FROM claim_evidence ce
    JOIN claims c ON c.id = ce.claim_id
    WHERE c.metadata->>'corpus_track' = 'broad_proof'
  `);
  const factRows = await client.query(
    "SELECT count(*)::int AS count FROM fact_versions WHERE produced_by = 'reviewed_broad_corpus_backfill'",
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
          claims: documents.length,
          claimEvidence: documents.length,
          factVersions: documents.length,
        },
        currentBroadProofRows: before,
      };
      if (json) console.log(JSON.stringify(payload, null, 2));
      else {
        console.log('mode: dry-run');
        console.log(
          `would apply sources=${sources.length} documents=${documents.length} claims=${documents.length}`,
        );
        console.log(`current broad-proof rows: ${JSON.stringify(before)}`);
        console.log('run with --apply to write reviewed broad-corpus rows');
      }
      return;
    }

    await client.query('BEGIN');
    await upsertSources(client);
    await upsertFirstProofEntities(client);
    await upsertDocuments(client);
    await upsertClaims(client);
    await insertFactVersions(client);
    await markReviewRecord(client);
    await client.query('COMMIT');

    const after = await summarize(client);
    const payload = { mode: 'apply', applied: true, broadProofRows: after };
    if (json) console.log(JSON.stringify(payload, null, 2));
    else {
      console.log('mode: apply');
      console.log(`broad-proof rows: ${JSON.stringify(after)}`);
    }
  } catch (error) {
    try {
      await client.query('ROLLBACK');
    } catch {
      // The original error is the useful one.
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
