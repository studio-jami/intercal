import { redirect } from 'next/navigation';
import { Field, PageHeader, Panel, SubmitButton } from '../../components/ui';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/topic');

export default async function TopicSearch({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  if (q) redirect(`/topic/${encodeURIComponent(q)}`);
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Topic" title="Open a topic explorer">
        <p>
          Topic pages compose freshness, evidence search, and delta timelines around one public
          query.
        </p>
      </PageHeader>
      <Panel>
        <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field name="q" label="Topic" placeholder="frontier LLMs" required />
          <SubmitButton>Open topic</SubmitButton>
        </form>
      </Panel>
    </div>
  );
}
