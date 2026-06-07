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

export const metadata = publicPageMetadata('/compare');
export const dynamic = 'force-dynamic';

type Delta = Awaited<ReturnType<ReturnType<typeof apiClient>['getDelta']>>;
type Freshness = Awaited<ReturnType<ReturnType<typeof apiClient>['getFreshness']>>;

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ left?: string; right?: string; since_date?: string }>;
}) {
  const params = await searchParams;
  const left = params.left?.trim();
  const right = params.right?.trim();
  const since = params.since_date || '2023-01-01';
  let leftResult: TopicSnapshot | null = null;
  let rightResult: TopicSnapshot | null = null;
  let error: string | null = null;

  if (left && right) {
    try {
      const client = apiClient();
      const [leftDelta, leftFreshness, rightDelta, rightFreshness] = await Promise.all([
        client.getDelta({
          topic: left,
          since_date: new Date(since).toISOString(),
          token_budget: 600,
        }),
        client.getFreshness({ topic_or_entity: left }),
        client.getDelta({
          topic: right,
          since_date: new Date(since).toISOString(),
          token_budget: 600,
        }),
        client.getFreshness({ topic_or_entity: right }),
      ]);
      leftResult = { delta: leftDelta, freshness: leftFreshness };
      rightResult = { delta: rightDelta, freshness: rightFreshness };
    } catch (e) {
      error = describeError(e);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Comparison" title="Compare topic change and coverage">
        <p>
          Compare two cited delta briefings with freshness and coverage states from the shared query
          layer.
        </p>
      </PageHeader>

      <Panel>
        <form className="grid gap-3 lg:grid-cols-[1fr_1fr_12rem_auto] lg:items-end">
          <Field name="left" label="Left topic" defaultValue={left} placeholder="GPT-4" required />
          <Field
            name="right"
            label="Right topic"
            defaultValue={right}
            placeholder="Claude"
            required
          />
          <Field name="since_date" label="Since" type="date" defaultValue={since} required />
          <SubmitButton>Compare</SubmitButton>
        </form>
      </Panel>

      {error ? <ErrorState title="Comparison failed" message={error} /> : null}

      {leftResult && rightResult ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <TopicPanel title={left ?? 'Left topic'} snapshot={leftResult} />
          <TopicPanel title={right ?? 'Right topic'} snapshot={rightResult} />
        </div>
      ) : (
        <EmptyState title="Run a comparison">
          <p>Try GPT-4 and Claude since 2023-01-01 to compare cited changes and coverage.</p>
        </EmptyState>
      )}
    </div>
  );
}

interface TopicSnapshot {
  delta: Delta;
  freshness: Freshness;
}

function TopicPanel({ title, snapshot }: { title: string; snapshot: TopicSnapshot }) {
  const topClaims = snapshot.delta.changedClaims.slice(0, 4);
  return (
    <Panel title={title} aside={`since ${formatDate(snapshot.delta.since)}`}>
      <dl className="mb-4 grid gap-3 text-sm sm:grid-cols-3">
        <Metric label="Changed claims" value={String(snapshot.delta.changedClaims.length)} />
        <Metric label="Coverage" value={formatPercent(snapshot.freshness.coverage)} />
        <Metric label="Freshness" value={snapshot.freshness.staleness ?? 'unknown'} />
      </dl>
      {topClaims.length ? (
        <ul className="space-y-3 text-sm">
          {topClaims.map((claim) => (
            <li
              key={claim.id}
              className="space-y-2 rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
            >
              <p>{claim.normalizedText}</p>
              <div className="flex flex-wrap gap-2">
                {claim.evidence.length ? (
                  claim.evidence.map((citation) => (
                    <EvidenceLink key={citation.sourceDocumentId} {...citation} />
                  ))
                ) : (
                  <span className="text-xs text-neutral-500">Evidence path unavailable.</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No changed claims returned" />
      )}
    </Panel>
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
