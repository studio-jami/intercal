import { sql } from 'kysely';
import type { Db } from './db/client.js';

export type ObservabilityTable =
  | 'observability_source_health'
  | 'observability_failed_jobs'
  | 'observability_pipeline_metrics'
  | 'observability_usage_latency'
  | 'observability_freshness'
  | 'observability_provider_consumption';

export const OBSERVABILITY_VIEW_NAMES = [
  'observability_source_health',
  'observability_failed_jobs',
  'observability_pipeline_metrics',
  'observability_usage_latency',
  'observability_freshness',
  'observability_provider_consumption',
] as const satisfies readonly ObservabilityTable[];

export interface ObservabilitySnapshot {
  sourceHealth: unknown[];
  pipelineMetrics: unknown[];
  usageLatency: unknown[];
  freshness: unknown[];
  failedJobs: unknown[];
  providerConsumption: unknown[];
}

async function selectView(db: Db, view: ObservabilityTable, limit: number): Promise<unknown[]> {
  const result = await sql`SELECT * FROM ${sql.ref(view)} LIMIT ${limit}`.execute(db);
  return result.rows;
}

export async function queryObservabilitySnapshot(
  db: Db,
  options: { limit?: number } = {},
): Promise<ObservabilitySnapshot> {
  const limit = Math.max(1, Math.min(options.limit ?? 50, 500));
  const [sourceHealth, pipelineMetrics, usageLatency, freshness, failedJobs, providerConsumption] =
    await Promise.all([
      selectView(db, 'observability_source_health', limit),
      selectView(db, 'observability_pipeline_metrics', limit),
      selectView(db, 'observability_usage_latency', limit),
      selectView(db, 'observability_freshness', limit),
      selectView(db, 'observability_failed_jobs', limit),
      selectView(db, 'observability_provider_consumption', limit),
    ]);

  return {
    sourceHealth,
    pipelineMetrics,
    usageLatency,
    freshness,
    failedJobs,
    providerConsumption,
  };
}
