import {
  evaluateCorpusQualityReport,
  FULL_AI_HISTORY_CORPUS_QUALITY_CONFIG,
  queryCorpusQualityReport,
} from '@intercal/core';
import { EmptyState, ErrorState, PageHeader, Panel } from '../../components/ui';
import { dashboardDb } from '../../lib/db';
import { formatDateTime } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/coverage');
export const dynamic = 'force-dynamic';

export default async function CoveragePage() {
  let data: Awaited<ReturnType<typeof queryCorpusQualityReport>> | null = null;
  let error: string | null = null;

  try {
    data = await queryCorpusQualityReport(dashboardDb(), FULL_AI_HISTORY_CORPUS_QUALITY_CONFIG);
  } catch (e) {
    error = e instanceof Error ? e.message : 'Unknown error';
  }

  const evaluation = data
    ? evaluateCorpusQualityReport(data, FULL_AI_HISTORY_CORPUS_QUALITY_CONFIG)
    : null;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Coverage" title="Corpus quality gate">
        <p>
          Public coverage language is bounded by the live corpus quality report. This page reads the
          same gate used by Workstream 4 and reports failed checks as coverage gaps.
        </p>
      </PageHeader>

      {error ? <ErrorState title="Coverage report unavailable" message={error} /> : null}

      {data && evaluation ? (
        <>
          <Panel
            title={evaluation.passed ? 'Full AI-history gate passed' : 'Coverage gaps remain'}
            aside={`generated ${formatDateTime(data.generatedAt)}`}
          >
            <dl className="grid gap-4 text-sm md:grid-cols-2 xl:grid-cols-5">
              <Metric label="Active claims" value={String(data.activeClaimCount)} />
              <Metric label="Evidenced claims" value={String(data.evidencedActiveClaimCount)} />
              <Metric label="Citations" value={String(data.citationCount)} />
              <Metric label="Open contradictions" value={String(data.openContradictionCount)} />
              <Metric label="Open reviews" value={String(data.openReviewRecordCount)} />
            </dl>
          </Panel>

          <Panel title="Gate checks">
            <ul className="grid gap-2 md:grid-cols-2">
              {evaluation.checks.map((check) => (
                <li
                  key={check.key}
                  className="rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-medium">{check.label}</p>
                    <span
                      className={
                        check.passed
                          ? 'text-emerald-700 dark:text-emerald-300'
                          : 'text-amber-700 dark:text-amber-300'
                      }
                    >
                      {check.passed ? 'passed' : 'gap'}
                    </span>
                  </div>
                  <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                    expected {check.expected}; actual {check.actual}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <MetricList title="Source classes" rows={data.sourceClasses} />
            <MetricList title="Topic clusters" rows={data.topicClusters} />
          </div>
        </>
      ) : !error ? (
        <EmptyState title="No coverage report available">
          <p>The database connection did not return a corpus quality report.</p>
        </EmptyState>
      ) : null}
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

function MetricList({ title, rows }: { title: string; rows: { key: string; count: number }[] }) {
  return (
    <Panel title={title}>
      {rows.length ? (
        <ul className="space-y-2 text-sm">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center justify-between gap-3">
              <span>{row.key}</span>
              <span className="text-neutral-500">{row.count}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No rows reported" />
      )}
    </Panel>
  );
}
