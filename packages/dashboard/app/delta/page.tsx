import {
  EmptyState,
  ErrorState,
  EvidenceLink,
  Field,
  PageHeader,
  Panel,
  SubmitButton,
} from '../../components/ui';
import { apiClient } from '../../lib/client';
import { describeError, formatDate, formatPercent } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/delta');
export const dynamic = 'force-dynamic';

export default async function DeltaPage({
  searchParams,
}: {
  searchParams: Promise<{
    topic?: string;
    since_date?: string;
    until_date?: string;
    token_budget?: string;
  }>;
}) {
  const params = await searchParams;
  const topic = params.topic?.trim();
  const since = params.since_date || '2023-01-01';
  const tokenBudget = params.token_budget ? Number(params.token_budget) : 800;
  let data: Awaited<ReturnType<ReturnType<typeof apiClient>['getDelta']>> | null = null;
  let error: string | null = null;

  if (topic) {
    try {
      data = await apiClient().getDelta({
        topic,
        since_date: new Date(since).toISOString(),
        until_date: params.until_date ? new Date(params.until_date).toISOString() : undefined,
        token_budget: tokenBudget,
      });
    } catch (e) {
      error = describeError(e);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Briefing" title="Delta briefing">
        <p>
          Ask what changed about a topic after a cutoff. Digest lines and changed claims are backed
          by source-document citations.
        </p>
      </PageHeader>

      <Panel>
        <form className="grid gap-3 lg:grid-cols-[1fr_12rem_12rem_9rem_auto] lg:items-end">
          <Field
            name="topic"
            label="Topic"
            defaultValue={topic}
            placeholder="frontier LLMs"
            required
          />
          <Field name="since_date" label="Since" type="date" defaultValue={since} required />
          <Field name="until_date" label="Until" type="date" defaultValue={params.until_date} />
          <Field
            name="token_budget"
            label="Token budget"
            type="number"
            defaultValue={String(tokenBudget)}
          />
          <SubmitButton>Brief</SubmitButton>
        </form>
      </Panel>

      {error ? <ErrorState title="Delta query failed" message={error} /> : null}

      {data ? (
        <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel
            title={data.topic}
            aside={`${formatDate(data.since)} to ${data.until ? formatDate(data.until) : 'now'}`}
          >
            <pre className="whitespace-pre-wrap text-sm leading-6">{data.summary.content}</pre>
            <div className="mt-4 flex flex-wrap gap-2">
              {data.summary.citations.length ? (
                data.summary.citations.map((citation) => (
                  <EvidenceLink key={citation.sourceDocumentId} {...citation} />
                ))
              ) : (
                <span className="text-sm text-neutral-500">
                  No citations because no changes were recorded.
                </span>
              )}
            </div>
          </Panel>

          <Panel title="Coverage state">
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="font-medium">Changed claims</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {data.changedClaims.length}
                </dd>
              </div>
              <div>
                <dt className="font-medium">Changed entities</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {data.changedEntities.length}
                </dd>
              </div>
              <div>
                <dt className="font-medium">Confidence</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {formatPercent(data.confidence.score)}
                </dd>
              </div>
              <div>
                <dt className="font-medium">Freshness</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {data.freshness.staleness ?? 'unknown'}
                </dd>
              </div>
            </dl>
          </Panel>
        </div>
      ) : (
        <EmptyState title="Run a delta query">
          <p>Try frontier LLMs since 2023-03-01 or MLPerf since 2023-01-01.</p>
        </EmptyState>
      )}
    </div>
  );
}
