import { redirect } from 'next/navigation';
import {
  EmptyState,
  Field,
  PageHeader,
  Panel,
  SelectField,
  SubmitButton,
} from '../../components/ui';
import { apiClient } from '../../lib/client';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/feedback');
export const dynamic = 'force-dynamic';

async function submitFeedbackAction(formData: FormData) {
  'use server';

  const targetType = String(formData.get('targetType') ?? '');
  const targetId = String(formData.get('targetId') ?? '').trim();
  const concernType = String(formData.get('concernType') ?? '');
  const summary = String(formData.get('summary') ?? '').trim();
  const details = String(formData.get('details') ?? '').trim();
  let destination: string;

  try {
    const response = await apiClient().submitFeedback({
      targetType: targetType as 'entity' | 'claim' | 'source' | 'digest' | 'freshness' | 'coverage',
      targetId,
      concernType: concernType as
        | 'incorrect'
        | 'outdated'
        | 'missing_evidence'
        | 'missing_coverage'
        | 'source_quality'
        | 'contradiction'
        | 'other',
      summary,
      ...(details ? { details } : {}),
    });
    destination = `/feedback?submitted=${encodeURIComponent(response.review.id)}`;
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Unknown error';
    destination = `/feedback?error=${encodeURIComponent(message)}`;
  }
  redirect(destination);
}

export default async function FeedbackPage({
  searchParams,
}: {
  searchParams: Promise<{
    submitted?: string;
    error?: string;
    targetType?: string;
    targetId?: string;
  }>;
}) {
  const params = await searchParams;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Review input" title="Report a public data issue">
        <p>
          Feedback creates an audited review record for operators. It does not change entities,
          claims, sources, relationships, or fact versions.
        </p>
      </PageHeader>

      {params.submitted ? (
        <Panel title="Feedback received">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Review record {params.submitted} was created and queued for operator review.
          </p>
        </Panel>
      ) : null}

      {params.error ? (
        <EmptyState title="Feedback could not be submitted">
          <p>{params.error}</p>
        </EmptyState>
      ) : null}

      <Panel title="Submit a review record">
        <form action={submitFeedbackAction} className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-3">
            <SelectField
              label="Target type"
              name="targetType"
              defaultValue={params.targetType ?? 'coverage'}
            >
              <option value="entity">Entity</option>
              <option value="claim">Claim</option>
              <option value="source">Source</option>
              <option value="digest">Digest</option>
              <option value="freshness">Freshness</option>
              <option value="coverage">Coverage</option>
            </SelectField>
            <Field
              name="targetId"
              label="Target id or topic"
              defaultValue={params.targetId ?? 'full-ai-history'}
              placeholder="UUID, topic, or coverage key"
              required
            />
            <SelectField label="Concern" name="concernType" defaultValue="missing_coverage">
              <option value="incorrect">Incorrect</option>
              <option value="outdated">Outdated</option>
              <option value="missing_evidence">Missing evidence</option>
              <option value="missing_coverage">Missing coverage</option>
              <option value="source_quality">Source quality</option>
              <option value="contradiction">Contradiction</option>
              <option value="other">Other</option>
            </SelectField>
          </div>
          <Field
            name="summary"
            label="Summary"
            placeholder="Short operator-readable issue"
            required
          />
          <label className="grid gap-1 text-sm">
            <span className="font-medium">Details</span>
            <textarea
              name="details"
              rows={5}
              className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
            />
          </label>
          <div>
            <SubmitButton>Submit feedback</SubmitButton>
          </div>
        </form>
      </Panel>
    </div>
  );
}
