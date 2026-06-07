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
import { describeError, formatDate } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/search');
export const dynamic = 'force-dynamic';

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ query?: string; from_date?: string; to_date?: string; limit?: string }>;
}) {
  const params = await searchParams;
  const query = params.query?.trim();
  const limit = params.limit ? Number(params.limit) : 20;
  let data: Awaited<ReturnType<ReturnType<typeof apiClient>['searchEvidence']>> | null = null;
  let error: string | null = null;

  if (query) {
    try {
      data = await apiClient().searchEvidence({
        query,
        from_date: params.from_date || undefined,
        to_date: params.to_date || undefined,
        limit,
      });
    } catch (e) {
      error = describeError(e);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Evidence" title="Search source-backed evidence">
        <p>
          Results come from source-document citation metadata and policy-allowed derived snippets.
          Restricted source bodies are not exposed or searched as body text.
        </p>
      </PageHeader>

      <SourcePolicyNote />

      <Panel>
        <form className="grid gap-3 lg:grid-cols-[1fr_12rem_12rem_8rem_auto] lg:items-end">
          <Field
            name="query"
            label="Query"
            defaultValue={query}
            placeholder="MCP protocol"
            required
          />
          <Field name="from_date" label="From" type="date" defaultValue={params.from_date} />
          <Field name="to_date" label="To" type="date" defaultValue={params.to_date} />
          <Field name="limit" label="Limit" type="number" defaultValue={String(limit)} />
          <SubmitButton>Search</SubmitButton>
        </form>
      </Panel>

      {error ? <ErrorState title="Evidence search failed" message={error} /> : null}

      {query && data ? (
        <Panel title={`${data.total} evidence result${data.total === 1 ? '' : 's'}`}>
          {data.hits.length ? (
            <ul className="space-y-3">
              {data.hits.map((hit) => (
                <li
                  key={hit.documentId}
                  className="space-y-2 rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
                >
                  <p className="text-sm">{hit.snippet || 'No policy-allowed snippet available.'}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <EvidenceLink
                      sourceDocumentId={hit.citation.sourceDocumentId}
                      url={hit.citation.url}
                      publishedAt={hit.citation.publishedAt}
                    />
                    <span className="text-xs text-neutral-500">score {hit.score.toFixed(2)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No evidence matched this query">
              <p>Intercal has no matching policy-servable evidence for this search window.</p>
            </EmptyState>
          )}
        </Panel>
      ) : (
        <EmptyState title="Run a query to inspect evidence">
          <p>Try a corpus proof topic such as MCP protocol, MLPerf, or Executive Order 14110.</p>
        </EmptyState>
      )}

      {data?.hits.length ? (
        <p className="text-xs text-neutral-500">
          Newest hit date: {formatDate(data.hits[0]?.citation.publishedAt)}
        </p>
      ) : null}
    </div>
  );
}
