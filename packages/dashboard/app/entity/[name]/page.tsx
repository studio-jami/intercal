import { IntercalApiError } from '@intercal/sdk';
import Link from 'next/link';
import { apiClient } from '../../../lib/client';

type EntityResponse = Awaited<ReturnType<ReturnType<typeof apiClient>['getEntity']>>;

export default async function EntityPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const decoded = decodeURIComponent(name);

  let data: EntityResponse | null = null;
  let errorMessage: string | null = null;
  try {
    data = await apiClient().getEntity({ name_or_id: decoded });
  } catch (e) {
    errorMessage =
      e instanceof IntercalApiError
        ? `${e.code}: ${e.message}`
        : e instanceof Error
          ? e.message
          : 'Unknown error';
  }

  return (
    <main className="space-y-6">
      <Link className="text-sm underline" href="/">
        ← Home
      </Link>

      {errorMessage ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">No data for “{decoded}”.</p>
          <p className="text-sm">{errorMessage}</p>
        </div>
      ) : data ? (
        <article className="space-y-6">
          <header className="space-y-1">
            <p className="text-xs uppercase tracking-wide text-neutral-500">{data.entity.type}</p>
            <h1 className="text-3xl font-semibold">{data.entity.displayName}</h1>
            {data.entity.aliases?.length ? (
              <p className="text-sm text-neutral-500">aka {data.entity.aliases.join(', ')}</p>
            ) : null}
          </header>

          <section>
            <h2 className="mb-2 text-lg font-medium">Facts</h2>
            {data.facts?.length ? (
              <ul className="space-y-2">
                {data.facts.map((f) => (
                  <li
                    key={f.id}
                    className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
                  >
                    <p>{f.normalizedText}</p>
                    <p className="text-xs text-neutral-500">
                      confidence {Math.round(f.confidence.score * 100)}% · {f.evidence.length}{' '}
                      source(s) · recorded {new Date(f.recordedAt).toLocaleDateString()}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-500">No recorded facts yet (explicit unknown).</p>
            )}
          </section>

          <section className="text-sm text-neutral-500">
            {data.relationships?.length ?? 0} relationship(s) ·{' '}
            {data.freshness.lastUpdated
              ? `updated ${data.freshness.staleness ?? ''} ago`
              : 'freshness unknown'}
          </section>
        </article>
      ) : null}
    </main>
  );
}
