import Link from 'next/link';
import { Field, PageHeader, Panel, SubmitButton } from '../components/ui';
import { canonicalExamples, publicPageMetadata, publicSummaryText } from '../lib/seo';

export const metadata = publicPageMetadata('/');

export default function HomePage() {
  const surfaces: { title: string; href: string; body: string }[] = [
    {
      title: 'Search evidence',
      href: '/search',
      body: 'Find source-backed evidence by query and date range.',
    },
    {
      title: 'Topic explorer',
      href: '/topic',
      body: 'Inspect a topic timeline with freshness and evidence.',
    },
    {
      title: 'Graph timeline',
      href: '/graph',
      body: 'View cited claims, entities, confidence, contradictions, and source origins.',
    },
    {
      title: 'Compare topics',
      href: '/compare',
      body: 'Compare two topics by cited change volume, freshness, and coverage.',
    },
    {
      title: 'Delta briefing',
      href: '/delta',
      body: 'Ask what changed about a topic after a cutoff date.',
    },
    {
      title: 'Verify claim',
      href: '/verify',
      body: 'Check a claim against cited support and contradictions.',
    },
    {
      title: 'Freshness',
      href: '/freshness',
      body: 'See recency, coverage, and explicit no-data states.',
    },
    {
      title: 'Coverage',
      href: '/coverage',
      body: 'Review the public corpus-quality gate snapshot.',
    },
    {
      title: 'Docs',
      href: '/docs',
      body: 'Read source-owned docs, generated OpenAPI guidance, and AI-friendly exports.',
    },
    {
      title: 'Subscriptions',
      href: '/subscriptions',
      body: 'Manage authenticated change notifications without mutating graph state.',
    },
    {
      title: 'Operator',
      href: '/operator',
      body: 'Auth-gated source health, reviews, usage, budget, and audit state.',
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Public knowledge experience" title="Provenance-backed AI history">
        <p>
          Intercal is a temporal knowledge substrate for agents and LLM apps: source documents
          become claims, resolved entities, typed temporal relationships, and append-only bitemporal
          fact versions served over MCP and REST.
        </p>
      </PageHeader>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Panel title="Start with an entity">
          <form action="/entity" className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <Field
              name="q"
              label="Entity"
              placeholder="ChatGPT, Claude, Gemini, Llama, MCP protocol"
            />
            <SubmitButton>Open entity</SubmitButton>
          </form>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            {['ChatGPT', 'Claude', 'Gemini', 'Llama', 'MCP protocol'].map((name) => (
              <Link
                key={name}
                href={`/entity/${encodeURIComponent(name)}`}
                className="rounded border border-neutral-200 px-2 py-1 underline dark:border-neutral-800"
              >
                {name}
              </Link>
            ))}
          </div>
        </Panel>

        <Panel title="What the public surface answers">
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-medium">Cutoff deltas</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Ask what changed about a topic after a date with cited changed claims.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Claim verification</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Check whether a claim was supported or contradicted as of a date.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Provenance</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Public pages cite source-document paths or display explicit coverage states.
              </dd>
            </div>
          </dl>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Copyable public role">
          <pre className="whitespace-pre-wrap text-sm leading-6 text-neutral-700 dark:text-neutral-300">
            {publicSummaryText}
          </pre>
        </Panel>
        <Panel title="Canonical examples">
          <ul className="grid gap-2 text-sm">
            {canonicalExamples.map((example) => (
              <li
                key={example.href}
                className="flex flex-col gap-1 rounded border border-neutral-200 p-2 dark:border-neutral-800"
              >
                <Link href={example.href} className="font-medium underline">
                  {example.label}
                </Link>
                <span className="text-neutral-600 dark:text-neutral-400">
                  {example.description}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {surfaces.map(({ title, href, body }) => (
          <Link
            key={href}
            href={href}
            className="rounded-md border border-neutral-200 p-4 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
          >
            <h2 className="font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">{body}</p>
          </Link>
        ))}
      </section>

      <Panel title="Jami Studio">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Intercal can be linked from a future Jami Studio public site, but this product surface
          does not depend on <code>www.jami.studio</code> being live. This repo owns Intercal's
          product, docs, REST, OpenAPI, MCP, and AI-readable exports.
        </p>
      </Panel>
    </div>
  );
}
