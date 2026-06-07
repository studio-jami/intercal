import {
  EmptyState,
  ErrorState,
  EvidenceLink,
  Field,
  PageHeader,
  Panel,
  SourcePolicyNote,
  SubmitButton,
} from '../../components/ui';
import { apiClient } from '../../lib/client';
import { compactId, describeError, formatDate, formatPercent } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/graph');
export const dynamic = 'force-dynamic';

export default async function GraphPage({
  searchParams,
}: {
  searchParams: Promise<{ topic?: string; since_date?: string; until_date?: string }>;
}) {
  const params = await searchParams;
  const topic = params.topic?.trim();
  const since = params.since_date || '2023-01-01';
  const client = apiClient();
  let data: Awaited<ReturnType<typeof client.getDelta>> | null = null;
  let error: string | null = null;

  if (topic) {
    try {
      data = await client.getDelta({
        topic,
        since_date: new Date(since).toISOString(),
        until_date: params.until_date ? new Date(params.until_date).toISOString() : undefined,
        token_budget: 1200,
      });
    } catch (e) {
      error = describeError(e);
    }
  }

  const citations = data
    ? [
        ...new Map(
          data.changedClaims.flatMap((claim) => claim.evidence).map((c) => [c.sourceDocumentId, c]),
        ).values(),
      ]
    : [];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Graph and timeline" title="Explore cited changes">
        <p>
          Inspect topic changes over time with confidence, contradiction, and source-origin
          overlays. Every node is a returned claim, entity, or cited source-document id.
        </p>
      </PageHeader>

      <Panel>
        <form className="grid gap-3 lg:grid-cols-[1fr_12rem_12rem_auto] lg:items-end">
          <Field
            name="topic"
            label="Topic"
            defaultValue={topic}
            placeholder="MCP protocol"
            required
          />
          <Field name="since_date" label="Since" type="date" defaultValue={since} required />
          <Field name="until_date" label="Until" type="date" defaultValue={params.until_date} />
          <SubmitButton>Render graph</SubmitButton>
        </form>
      </Panel>

      <SourcePolicyNote />

      {error ? <ErrorState title="Graph query failed" message={error} /> : null}

      {data ? (
        <>
          <div className="grid gap-4 xl:grid-cols-[1.4fr_0.6fr]">
            <Panel
              title={`Timeline for ${data.topic}`}
              aside={`${formatDate(data.since)} to ${data.until ? formatDate(data.until) : 'now'}`}
            >
              {data.changedClaims.length ? (
                <ol className="relative space-y-4 border-l border-neutral-200 pl-4 text-sm dark:border-neutral-800">
                  {data.changedClaims.map((claim) => (
                    <li key={claim.id} className="space-y-2">
                      <div className="-ml-[1.35rem] size-3 rounded-full border border-neutral-400 bg-white dark:bg-neutral-950" />
                      <div className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <p>{claim.normalizedText}</p>
                          <span className="text-xs text-neutral-500">
                            {formatDate(claim.validFrom ?? claim.recordedAt)}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <span className="rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-800">
                            confidence {formatPercent(claim.confidence.score)}
                          </span>
                          <span className="rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-800">
                            contradiction {claim.contradiction}
                          </span>
                          <span className="rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-800">
                            status {claim.status}
                          </span>
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
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <EmptyState title="No changed claims in this window" />
              )}
            </Panel>

            <Panel title="Overlay counts">
              <dl className="grid gap-3 text-sm">
                <Metric label="Changed claims" value={String(data.changedClaims.length)} />
                <Metric label="Changed entities" value={String(data.changedEntities.length)} />
                <Metric label="Source documents" value={String(citations.length)} />
                <Metric label="Aggregate confidence" value={formatPercent(data.confidence.score)} />
                <Metric label="Freshness" value={data.freshness.staleness ?? 'unknown'} />
              </dl>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Entity nodes">
              {data.changedEntities.length ? (
                <ul className="space-y-2 text-sm">
                  {data.changedEntities.map((entity) => (
                    <li
                      key={entity.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-800"
                    >
                      <span>
                        {entity.displayName}{' '}
                        <span className="text-neutral-500">({entity.type})</span>
                      </span>
                      <span className="text-xs text-neutral-500">{compactId(entity.id)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No changed entities returned" />
              )}
            </Panel>

            <Panel title="Source-origin nodes">
              {citations.length ? (
                <ul className="space-y-2 text-sm">
                  {citations.map((citation) => (
                    <li key={citation.sourceDocumentId}>
                      <EvidenceLink {...citation} />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No source-origin citations returned" />
              )}
            </Panel>
          </div>
        </>
      ) : (
        <EmptyState title="Run a graph query">
          <p>Try MCP protocol or frontier LLMs with a November 2022 onward window.</p>
        </EmptyState>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium">{label}</dt>
      <dd className="text-neutral-600 dark:text-neutral-400">{value}</dd>
    </div>
  );
}
