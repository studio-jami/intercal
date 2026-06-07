import Link from 'next/link';
import { Field, PageHeader, Panel, SourcePolicyNote, SubmitButton } from '../../../components/ui';
import { compactId } from '../../../lib/format';
import { dynamicPageMetadata } from '../../../lib/seo';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const decoded = decodeURIComponent(id);
  return dynamicPageMetadata({
    title: `Source record ${compactId(decoded)}`,
    description:
      'Source-document identifier, public citation state, and source-policy explanation without raw body exposure.',
    pathname: `/source/${encodeURIComponent(decoded)}`,
  });
}

export default async function SourceRecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const sourceDocumentId = decodeURIComponent(id);

  return (
    <div className="space-y-6">
      <Link className="text-sm underline" href="/search">
        Evidence search
      </Link>
      <PageHeader eyebrow="Source record" title={compactId(sourceDocumentId)}>
        <p>
          Source documents are public through the entity, claim, delta, verification, and evidence
          paths that cite them. This record preserves the source-document identifier without
          exposing body text.
        </p>
      </PageHeader>

      <SourcePolicyNote />

      <Panel title="Current public state">
        <dl className="grid gap-3 text-sm md:grid-cols-2">
          <div>
            <dt className="font-medium">Source document id</dt>
            <dd className="break-all text-neutral-600 dark:text-neutral-400">{sourceDocumentId}</dd>
          </div>
          <div>
            <dt className="font-medium">Direct lookup</dt>
            <dd className="text-neutral-600 dark:text-neutral-400">
              Available only through cited entity, claim, evidence, delta, and verification results.
            </dd>
          </div>
          <div>
            <dt className="font-medium">Body text</dt>
            <dd className="text-neutral-600 dark:text-neutral-400">
              Not displayed on public dashboard routes.
            </dd>
          </div>
          <div>
            <dt className="font-medium">Coverage state</dt>
            <dd className="text-neutral-600 dark:text-neutral-400">
              Unknown until this document is reached from a contracted evidence path.
            </dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Report a source issue">
        <form action="/feedback" className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <input type="hidden" name="targetType" value="source" />
          <Field
            name="targetId"
            label="Source document id"
            defaultValue={sourceDocumentId}
            required
          />
          <SubmitButton>Open feedback</SubmitButton>
        </form>
      </Panel>
    </div>
  );
}
