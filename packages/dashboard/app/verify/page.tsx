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
import { describeError, formatPercent } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/verify');
export const dynamic = 'force-dynamic';

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ claim_text?: string; as_of_date?: string; token_budget?: string }>;
}) {
  const params = await searchParams;
  const claimText = params.claim_text?.trim();
  const tokenBudget = params.token_budget ? Number(params.token_budget) : 800;
  let data: Awaited<ReturnType<ReturnType<typeof apiClient>['verifyClaim']>> | null = null;
  let error: string | null = null;

  if (claimText) {
    try {
      data = await apiClient().verifyClaim({
        claim_text: claimText,
        as_of_date: params.as_of_date ? new Date(params.as_of_date).toISOString() : undefined,
        token_budget: tokenBudget,
      });
    } catch (e) {
      error = describeError(e);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Claims" title="Verify a claim">
        <p>
          Verification is deterministic and citation-backed. Unsupported claims return unverified or
          contradicted rather than invented support.
        </p>
      </PageHeader>

      <Panel>
        <form className="grid gap-3 lg:grid-cols-[1fr_12rem_9rem_auto] lg:items-end">
          <Field
            name="claim_text"
            label="Claim"
            defaultValue={claimText}
            placeholder="GPT-4 Turbo supports a 128k context window"
            required
          />
          <Field name="as_of_date" label="As of" type="date" defaultValue={params.as_of_date} />
          <Field
            name="token_budget"
            label="Token budget"
            type="number"
            defaultValue={String(tokenBudget)}
          />
          <SubmitButton>Verify</SubmitButton>
        </form>
      </Panel>

      {error ? <ErrorState title="Verification failed" message={error} /> : null}

      {data ? (
        <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
          <Panel title="Verdict">
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="font-medium">State</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">{data.verdict}</dd>
              </div>
              <div>
                <dt className="font-medium">Confidence</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {formatPercent(data.confidence.score)} by {data.confidence.method}
                </dd>
              </div>
              <div>
                <dt className="font-medium">As-of date</dt>
                <dd className="text-neutral-600 dark:text-neutral-400">
                  {data.asOf ?? 'current valid state'}
                </dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Evidence path">
            <div className="space-y-4">
              <EvidenceList title="Supporting evidence" citations={data.supportingEvidence} />
              <EvidenceList title="Contradicting evidence" citations={data.contradictingEvidence} />
            </div>
          </Panel>
        </div>
      ) : (
        <EmptyState title="Run a claim verification">
          <p>
            Try the GPT-4 Turbo 128k claim or the adversarial 1M-context claim from the quality
            gate.
          </p>
        </EmptyState>
      )}
    </div>
  );
}

function EvidenceList({
  title,
  citations,
}: {
  title: string;
  citations: { sourceDocumentId: string; url?: string; publishedAt?: string }[];
}) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {citations.length ? (
        <div className="flex flex-wrap gap-2">
          {citations.map((citation) => (
            <EvidenceLink key={citation.sourceDocumentId} {...citation} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-neutral-500">No cited evidence on this side.</p>
      )}
    </section>
  );
}
