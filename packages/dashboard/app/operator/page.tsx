import { queryAuditEvents, queryObservabilitySnapshot } from '@intercal/core';
import { headers } from 'next/headers';
import { EmptyState, Field, PageHeader, Panel, SubmitButton } from '../../components/ui';
import { dashboardDb } from '../../lib/db';
import { compactId, formatDateTime } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/operator');
export const dynamic = 'force-dynamic';

export default async function OperatorPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const params = await searchParams;
  const configuredToken = process.env.OPERATOR_DASHBOARD_TOKEN;
  const headerToken = (await headers()).get('x-operator-token') ?? undefined;
  const suppliedToken = headerToken ?? params.token;
  const authorized = Boolean(configuredToken && suppliedToken && suppliedToken === configuredToken);

  if (!authorized) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Operator" title="Auth-gated operations console">
          <p>
            This surface reads source health, ingestion runs, feedback, audit events, usage, budget,
            and coverage state. An operator credential is required to render live rows.
          </p>
        </PageHeader>
        <Panel title="Locked">
          <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <Field name="token" label="Operator token" type="password" required />
            <SubmitButton>Unlock</SubmitButton>
          </form>
          <p className="mt-3 text-sm text-neutral-500">
            Access is unavailable without an active operator credential.
          </p>
        </Panel>
      </div>
    );
  }

  const db = dashboardDb();
  const [observability, auditEvents, reviewRecords] = await Promise.all([
    queryObservabilitySnapshot(db, { limit: 20 }),
    queryAuditEvents(db, { limit: 20 }),
    db.selectFrom('review_records').selectAll().orderBy('created_at', 'desc').limit(20).execute(),
  ]);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Operator" title="Operations console">
        <p>Read-only operational state. Public graph data is not mutated from this route.</p>
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-2">
        <TablePanel title="Source health" rows={observability.sourceHealth} />
        <TablePanel title="Ingestion and failed jobs" rows={observability.failedJobs} />
        <TablePanel title="Usage and latency" rows={observability.usageLatency} />
        <TablePanel title="Provider budget consumption" rows={observability.providerConsumption} />
        <TablePanel title="Freshness rollup" rows={observability.freshness} />
        <TablePanel title="Pipeline metrics" rows={observability.pipelineMetrics} />
      </div>

      <Panel title="Feedback and review records">
        {reviewRecords.length ? (
          <ul className="space-y-2 text-sm">
            {reviewRecords.map((record) => (
              <li
                key={record.id}
                className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">
                    {record.concern_type} on {record.target_type}
                  </p>
                  <span className="text-neutral-500">{record.status}</span>
                </div>
                <p className="mt-1 text-neutral-600 dark:text-neutral-400">{record.summary}</p>
                <p className="mt-1 text-xs text-neutral-500">
                  {compactId(record.id)} created {formatDateTime(record.created_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No review records found" />
        )}
      </Panel>

      <Panel title="Recent audit events">
        {auditEvents.length ? (
          <ul className="space-y-2 text-sm">
            {auditEvents.map((event) => (
              <li
                key={event.id}
                className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{event.action}</p>
                  <span className="text-neutral-500">{event.severity}</span>
                </div>
                <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                  {event.targetType} {compactId(event.targetId)} by {event.actorType}{' '}
                  {compactId(event.actorId)}
                </p>
                <p className="mt-1 text-xs text-neutral-500">{formatDateTime(event.createdAt)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No audit events found" />
        )}
      </Panel>
    </div>
  );
}

function TablePanel({ title, rows }: { title: string; rows: unknown[] }) {
  const records = rows.filter(
    (row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object',
  );
  const columns = [...new Set(records.flatMap((row) => Object.keys(row)))].slice(0, 6);
  return (
    <Panel title={title}>
      {records.length && columns.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-xs">
            <thead className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-2 py-2 font-medium">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((row, index) => (
                <tr key={index} className="border-b border-neutral-100 dark:border-neutral-900">
                  {columns.map((column) => (
                    <td key={column} className="max-w-48 truncate px-2 py-2">
                      {String(row[column] ?? 'unknown')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No rows available" />
      )}
    </Panel>
  );
}
