import Link from 'next/link';
import {
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Panel,
  SourcePolicyNote,
  SubmitButton,
} from '../../../components/ui';
import { safeCitationHref } from '../../../lib/citations';
import { apiClient } from '../../../lib/client';
import { describeError, formatDateTime } from '../../../lib/format';
import { dynamicPageMetadata } from '../../../lib/seo';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const decoded = decodeURIComponent(id);
  return dynamicPageMetadata({
    title: `Claim evidence ${decoded}`,
    description:
      'Claim-level source documents, citation metadata, and source-policy state from Intercal.',
    pathname: `/claim/${encodeURIComponent(decoded)}`,
  });
}

export default async function ClaimPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data: Awaited<ReturnType<ReturnType<typeof apiClient>['getSources']>> | null = null;
  let error: string | null = null;

  try {
    data = await apiClient().getSources({ entity_or_claim_id: id, limit: 25 });
  } catch (e) {
    error = describeError(e);
  }

  return (
    <div className="space-y-6">
      <Link className="text-sm underline" href="/">
        Home
      </Link>
      <PageHeader eyebrow="Claim" title={id}>
        <p>
          Claim-level source documents are read from the canonical sources query. Body text is not
          exposed here.
        </p>
      </PageHeader>

      {error ? <ErrorState title="Claim evidence unavailable" message={error} /> : null}

      <SourcePolicyNote>
        <p>
          Claim source paths expose source-document metadata and outbound citations. Raw source
          bodies remain outside public dashboard routes.
        </p>
      </SourcePolicyNote>

      {data ? (
        <Panel
          title={`${data.sources.length} source document${data.sources.length === 1 ? '' : 's'}`}
        >
          {data.sources.length ? (
            <ul className="space-y-3">
              {data.sources.map((source) => {
                const citationHref = safeCitationHref(source.url);

                return (
                  <li
                    key={source.id}
                    className="rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{source.title ?? 'Untitled source'}</p>
                        <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                          source {source.sourceId}; published {formatDateTime(source.publishedAt)}
                        </p>
                        <p className="mt-1 text-xs text-neutral-500">
                          ingested {formatDateTime(source.ingestedAt)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {citationHref ? (
                          <Link
                            href={citationHref}
                            target="_blank"
                            rel="noreferrer"
                            className="underline"
                          >
                            Open citation
                          </Link>
                        ) : null}
                        <Link
                          href={`/source/${encodeURIComponent(source.id)}`}
                          className="underline"
                        >
                          Source record
                        </Link>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState title="No source documents returned">
              <p>
                This claim currently has no source-document path available from the public query.
              </p>
            </EmptyState>
          )}
        </Panel>
      ) : null}

      <Panel title="Report a claim issue">
        <form action="/feedback" className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <input type="hidden" name="targetType" value="claim" />
          <Field name="targetId" label="Claim id" defaultValue={id} required />
          <SubmitButton>Open feedback</SubmitButton>
        </form>
      </Panel>
    </div>
  );
}
