import {
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Panel,
  SubmitButton,
} from '../../components/ui';
import { apiClient } from '../../lib/client';
import { describeError, formatDateTime, formatPercent } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/freshness');
export const dynamic = 'force-dynamic';

export default async function FreshnessPage({
  searchParams,
}: {
  searchParams: Promise<{ target?: string }>;
}) {
  const params = await searchParams;
  const target = params.target?.trim();
  let data: Awaited<ReturnType<ReturnType<typeof apiClient>['getFreshness']>> | null = null;
  let error: string | null = null;

  if (target) {
    try {
      data = await apiClient().getFreshness({ topic_or_entity: target });
    } catch (e) {
      error = describeError(e);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Freshness" title="Freshness and weak coverage">
        <p>
          Freshness reports distinguish current, stale, thin, and explicit no-data states from the
          shared query layer.
        </p>
      </PageHeader>

      <Panel>
        <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field
            name="target"
            label="Topic or entity"
            defaultValue={target}
            placeholder="MCP protocol"
            required
          />
          <SubmitButton>Check freshness</SubmitButton>
        </form>
      </Panel>

      {error ? <ErrorState title="Freshness query failed" message={error} /> : null}

      {data ? (
        <Panel title={data.target}>
          <dl className="grid gap-4 text-sm md:grid-cols-2 xl:grid-cols-4">
            <div>
              <dt className="font-medium">Coverage</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                {formatPercent(data.coverage)}
              </dd>
            </div>
            <div>
              <dt className="font-medium">Last updated</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                {formatDateTime(data.lastUpdated)}
              </dd>
            </div>
            <div>
              <dt className="font-medium">Last ingested</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                {formatDateTime(data.lastIngestedAt)}
              </dd>
            </div>
            <div>
              <dt className="font-medium">State</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                {data.staleness ?? 'unknown'}
              </dd>
            </div>
          </dl>
        </Panel>
      ) : (
        <EmptyState title="Run a freshness query">
          <p>
            Unknown topics return explicit no-entity/no-source coverage state instead of invented
            facts.
          </p>
        </EmptyState>
      )}
    </div>
  );
}
