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
import { compactId } from '../../lib/format';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/subscriptions');
export const dynamic = 'force-dynamic';

type TargetKind = 'topic' | 'entity' | 'relationship' | 'claim_pattern';

async function createSubscriptionAction(formData: FormData) {
  'use server';

  const apiKey = String(formData.get('apiKey') ?? '').trim();
  const kind = String(formData.get('kind') ?? 'topic') as TargetKind;
  const targetValue = String(formData.get('targetValue') ?? '').trim();
  const deliveryMethod = String(formData.get('deliveryMethod') ?? 'polling') as
    | 'polling'
    | 'webhook';
  const webhookUrl = String(formData.get('webhookUrl') ?? '').trim();
  const minImportance = Number(formData.get('minImportance') ?? 0);
  const tokenBudget = Number(formData.get('tokenBudget') ?? 800);
  let destination: string;

  try {
    const response = await apiClient({ apiKey }).createSubscription({
      target: targetFor(kind, targetValue),
      deliveryMethod,
      ...(webhookUrl ? { webhookUrl } : {}),
      minImportance,
      tokenBudget,
    });
    destination = `/subscriptions?created=${encodeURIComponent(response.subscription.id)}`;
  } catch (e) {
    destination = `/subscriptions?error=${encodeURIComponent(describeActionError(e))}`;
  }
  redirect(destination);
}

async function pollSubscriptionAction(formData: FormData) {
  'use server';

  const apiKey = String(formData.get('apiKey') ?? '').trim();
  const subscriptionId = String(formData.get('subscriptionId') ?? '').trim();
  const limit = Number(formData.get('limit') ?? 20);
  let destination: string;

  try {
    const response = await apiClient({ apiKey }).pollSubscriptionNotifications({
      subscriptionId,
      limit,
    });
    destination = `/subscriptions?polled=${response.notifications.length}`;
  } catch (e) {
    destination = `/subscriptions?error=${encodeURIComponent(describeActionError(e))}`;
  }
  redirect(destination);
}

async function deleteSubscriptionAction(formData: FormData) {
  'use server';

  const apiKey = String(formData.get('apiKey') ?? '').trim();
  const subscriptionId = String(formData.get('subscriptionId') ?? '').trim();
  let destination: string;

  try {
    const response = await apiClient({ apiKey }).deleteSubscription({ subscriptionId });
    destination = `/subscriptions?deleted=${encodeURIComponent(response.subscription.id)}`;
  } catch (e) {
    destination = `/subscriptions?error=${encodeURIComponent(describeActionError(e))}`;
  }
  redirect(destination);
}

export default async function SubscriptionsPage({
  searchParams,
}: {
  searchParams: Promise<{ created?: string; deleted?: string; polled?: string; error?: string }>;
}) {
  const params = await searchParams;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Subscriptions" title="Manage change notifications">
        <p>
          Authenticated subscription actions use the existing REST subscription endpoints and audit
          path. They create delivery records only; canonical graph data is unchanged.
        </p>
      </PageHeader>

      {params.created ? (
        <Panel title="Subscription created">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Created subscription {compactId(params.created)}. Store the full id in your client or
            operator record before polling or deleting it.
          </p>
        </Panel>
      ) : null}

      {params.deleted ? (
        <Panel title="Subscription deactivated">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Deactivated subscription {compactId(params.deleted)}.
          </p>
        </Panel>
      ) : null}

      {params.polled ? (
        <Panel title="Poll completed">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            {params.polled} pending notification{params.polled === '1' ? '' : 's'} returned and
            marked delivered by the API.
          </p>
        </Panel>
      ) : null}

      {params.error ? (
        <EmptyState title="Subscription action failed">
          <p>{params.error}</p>
        </EmptyState>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel title="Create subscription">
          <form action={createSubscriptionAction} className="grid gap-4">
            <Field name="apiKey" label="API key" type="password" required />
            <div className="grid gap-3 md:grid-cols-2">
              <SelectField label="Target kind" name="kind" defaultValue="topic">
                <option value="topic">Topic id</option>
                <option value="entity">Entity id</option>
                <option value="relationship">Relationship type id</option>
                <option value="claim_pattern">Claim pattern</option>
              </SelectField>
              <Field
                name="targetValue"
                label="Target value"
                placeholder="UUID or claim-pattern text"
                required
              />
              <SelectField label="Delivery" name="deliveryMethod" defaultValue="polling">
                <option value="polling">Polling</option>
                <option value="webhook">Webhook</option>
              </SelectField>
              <Field name="webhookUrl" label="Webhook URL" placeholder="https://example.com/hook" />
              <Field name="minImportance" label="Min importance" type="number" defaultValue="0" />
              <Field name="tokenBudget" label="Token budget" type="number" defaultValue="800" />
            </div>
            <div>
              <SubmitButton>Create</SubmitButton>
            </div>
          </form>
        </Panel>

        <div className="grid gap-4">
          <Panel title="Poll notifications">
            <form action={pollSubscriptionAction} className="grid gap-3">
              <Field name="apiKey" label="API key" type="password" required />
              <Field name="subscriptionId" label="Subscription id" required />
              <Field name="limit" label="Limit" type="number" defaultValue="20" />
              <div>
                <SubmitButton>Poll</SubmitButton>
              </div>
            </form>
          </Panel>

          <Panel title="Delete subscription">
            <form action={deleteSubscriptionAction} className="grid gap-3">
              <Field name="apiKey" label="API key" type="password" required />
              <Field name="subscriptionId" label="Subscription id" required />
              <div>
                <SubmitButton>Delete</SubmitButton>
              </div>
            </form>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function targetFor(kind: TargetKind, value: string) {
  switch (kind) {
    case 'topic':
      return { kind, topicId: value };
    case 'entity':
      return { kind, entityId: value };
    case 'relationship':
      return { kind, relationshipTypeId: value };
    case 'claim_pattern':
      return { kind, claimPattern: { text: value } };
  }
}

function describeActionError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}
