import { IntercalApiError } from '@intercal/sdk';
import Link from 'next/link';
import { EmptyState, EvidenceLink, PageHeader, Panel } from '../../../components/ui';
import { apiClient } from '../../../lib/client';
import { formatDate, formatPercent } from '../../../lib/format';
import { dynamicPageMetadata } from '../../../lib/seo';

type EntityResponse = Awaited<ReturnType<ReturnType<typeof apiClient>['getEntity']>>;

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const decoded = decodeURIComponent(name);
  return dynamicPageMetadata({
    title: `${decoded} entity evidence`,
    description: `Cited facts, relationships, freshness, and evidence paths for ${decoded} in the Intercal temporal knowledge substrate.`,
    pathname: `/entity/${encodeURIComponent(decoded)}`,
  });
}

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
    <div className="space-y-6">
      <Link className="text-sm underline" href="/">
        Home
      </Link>

      {errorMessage ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">No data for “{decoded}”.</p>
          <p className="text-sm">{errorMessage}</p>
        </div>
      ) : data ? (
        <article className="space-y-6">
          <PageHeader eyebrow={data.entity.type} title={data.entity.displayName}>
            {data.entity.aliases?.length ? (
              <p className="text-sm text-neutral-500">aka {data.entity.aliases.join(', ')}</p>
            ) : null}
            <p>
              {data.facts?.length ?? 0} fact{(data.facts?.length ?? 0) === 1 ? '' : 's'} and{' '}
              {data.relationships?.length ?? 0} relationship
              {(data.relationships?.length ?? 0) === 1 ? '' : 's'} returned from the shared query
              layer.
            </p>
          </PageHeader>

          <Panel title="Facts">
            {data.facts?.length ? (
              <ul className="space-y-2">
                {data.facts.map((f) => (
                  <li
                    key={f.id}
                    className="space-y-2 rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <p>{f.normalizedText}</p>
                      <Link className="text-sm underline" href={`/claim/${f.id}`}>
                        Evidence
                      </Link>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {f.evidence.length ? (
                        f.evidence.map((citation) => (
                          <EvidenceLink key={citation.sourceDocumentId} {...citation} />
                        ))
                      ) : (
                        <span className="text-sm text-neutral-500">Evidence path unavailable.</span>
                      )}
                    </div>
                    <p className="text-xs text-neutral-500">
                      confidence {formatPercent(f.confidence.score)} by {f.confidence.method} ·
                      recorded {formatDate(f.recordedAt)} · contradiction {f.contradiction}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No recorded facts">
                <p>This is an explicit unknown state for the selected entity.</p>
              </EmptyState>
            )}
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Freshness">
              <dl className="grid gap-2 text-sm">
                <div>
                  <dt className="font-medium">Last updated</dt>
                  <dd className="text-neutral-600 dark:text-neutral-400">
                    {formatDate(data.freshness.lastUpdated)}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium">State</dt>
                  <dd className="text-neutral-600 dark:text-neutral-400">
                    {data.freshness.staleness ?? 'unknown'}
                  </dd>
                </div>
              </dl>
            </Panel>
            <Panel title="Relationships">
              {data.relationships?.length ? (
                <ul className="space-y-2 text-sm">
                  {data.relationships.map((relationship) => (
                    <li
                      key={relationship.id}
                      className="rounded border border-neutral-200 p-2 dark:border-neutral-800"
                    >
                      {relationship.fromEntityId} {relationship.type} {relationship.toEntityId}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No relationships returned" />
              )}
            </Panel>
          </div>
        </article>
      ) : null}
    </div>
  );
}
