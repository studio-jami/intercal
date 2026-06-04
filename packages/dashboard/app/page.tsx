import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Intercal</h1>
        <p className="text-neutral-600 dark:text-neutral-400">
          An open, provenance-backed <strong>temporal knowledge substrate</strong> for agents and
          LLM applications. Source documents become claims, resolved entities, typed temporal
          relationships, and append-only fact versions — queryable by date, topic, entity, claim,
          confidence, and token budget over MCP and REST.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Explore an entity</h2>
        <form action="/entity" className="flex gap-2">
          <input
            name="q"
            placeholder="e.g. OpenAI"
            className="flex-1 rounded-md border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <button
            type="submit"
            className="rounded-md bg-neutral-900 px-4 py-2 text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Look up
          </button>
        </form>
        <p className="text-sm text-neutral-500">
          Try a sample like{' '}
          <Link className="underline" href="/entity/OpenAI">
            /entity/OpenAI
          </Link>
          . Every displayed fact is evidence-linked or shown as an explicit unknown.
        </p>
      </section>

      <footer className="border-t border-neutral-200 pt-6 text-sm text-neutral-500 dark:border-neutral-800">
        Read-only public experience. Canonical data is never mutated here. The full graph, timeline,
        briefing, and operator surfaces are delivered in the interactive-experience plan.
      </footer>
    </main>
  );
}
