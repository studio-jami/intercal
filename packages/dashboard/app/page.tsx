import Link from 'next/link';
import { Field, PageHeader, Panel, SubmitButton } from '../components/ui';

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
          Query entities, evidence, deltas, claim verification, freshness, and coverage over
          Intercal's temporal corpus. Public pages are read-only: every displayed assertion is tied
          to source-document citations or shown as an explicit unknown.
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

        <Panel title="Operational posture">
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-medium">Canonical reads</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                REST, SDK, MCP, and this app share the same query semantics.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Source policy</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Evidence pages cite URL/title metadata and derived snippets only when policy allows
                them.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Feedback</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Reports create review records; they never mutate canonical facts.
              </dd>
            </div>
          </dl>
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
    </div>
  );
}
