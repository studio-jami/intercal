import Link from 'next/link';
import { EmptyState, ErrorState, EvidenceLink, PageHeader, Panel } from '../../../components/ui';
import { apiClient } from '../../../lib/client';
import { describeError, formatDate, formatPercent } from '../../../lib/format';
import { dynamicPageMetadata } from '../../../lib/seo';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const topic = decodeURIComponent(name);
  return dynamicPageMetadata({
    title: `${topic} topic timeline`,
    description: `Crawlable topic page for ${topic} with freshness, evidence search, and cited cutoff deltas from Intercal.`,
    pathname: `/topic/${encodeURIComponent(topic)}`,
  });
}

export default async function TopicPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const topic = decodeURIComponent(name);
  const since = '2023-01-01T00:00:00.000Z';

  const client = apiClient();
  const [freshnessResult, deltaResult, evidenceResult] = await Promise.allSettled([
    client.getFreshness({ topic_or_entity: topic }),
    client.getDelta({ topic, since_date: since, token_budget: 700 }),
    client.searchEvidence({ query: topic, limit: 8 }),
  ]);

  const freshness = freshnessResult.status === 'fulfilled' ? freshnessResult.value : null;
  const delta = deltaResult.status === 'fulfilled' ? deltaResult.value : null;
  const evidence = evidenceResult.status === 'fulfilled' ? evidenceResult.value : null;
  const errors = [freshnessResult, deltaResult, evidenceResult]
    .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    .map((result) => describeError(result.reason));

  return (
    <div className="space-y-6">
      <Link className="text-sm underline" href="/topic">
        Topics
      </Link>
      <PageHeader eyebrow="Topic explorer" title={topic}>
        <p>
          A compact timeline and evidence view assembled from existing V1 queries. Missing sections
          are explicit coverage states, not inferred data.
        </p>
      </PageHeader>

      {errors.map((error) => (
        <ErrorState key={error} title="Topic query gap" message={error} />
      ))}

      <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <Panel title="Freshness and coverage">
          {freshness ? (
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="font-medium">Coverage</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {formatPercent(freshness.coverage)}
                </dd>
              </div>
              <div>
                <dt className="font-medium">State</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {freshness.staleness ?? 'unknown'}
                </dd>
              </div>
            </dl>
          ) : (
            <EmptyState title="Freshness unavailable" />
          )}
        </Panel>

        <Panel title="Timeline since 2023-01-01">
          {delta?.changedClaims.length ? (
            <ol className="space-y-3 text-sm">
              {delta.changedClaims.map((claim) => (
                <li
                  key={claim.id}
                  className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p>{claim.normalizedText}</p>
                    <span className="text-neutral-500">{formatDate(claim.recordedAt)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {claim.evidence.length ? (
                      claim.evidence.map((citation) => (
                        <EvidenceLink key={citation.sourceDocumentId} {...citation} />
                      ))
                    ) : (
                      <span className="text-xs text-neutral-500">
                        Evidence path unavailable for this returned claim.
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="No changed claims in this window" />
          )}
        </Panel>
      </div>

      <Panel title="Evidence search">
        {evidence?.hits.length ? (
          <ul className="space-y-3">
            {evidence.hits.map((hit) => (
              <li
                key={hit.documentId}
                className="rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800"
              >
                <p>{hit.snippet || 'No policy-allowed snippet available.'}</p>
                <div className="mt-2">
                  <EvidenceLink {...hit.citation} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No evidence hits returned" />
        )}
      </Panel>
    </div>
  );
}
