import Link from 'next/link';
import { redirect } from 'next/navigation';
import { Field, PageHeader, Panel, SubmitButton } from '../../components/ui';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/entity');

export default async function EntitySearch({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  if (q) redirect(`/entity/${encodeURIComponent(q)}`);
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Entity" title="Find an entity">
        <p>
          Open a resolved entity by name or UUID. Facts render only from canonical query-layer
          responses.
        </p>
      </PageHeader>
      <Panel>
        <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field name="q" label="Entity" placeholder="ChatGPT" required />
          <SubmitButton>Open entity</SubmitButton>
        </form>
      </Panel>
      <p className="text-sm text-neutral-500">
        Return to the{' '}
        <Link className="underline" href="/">
          public overview
        </Link>
        .
      </p>
    </div>
  );
}
