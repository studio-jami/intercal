import Link from 'next/link';
import { Markdown } from '../../components/markdown';
import { PageHeader, Panel } from '../../components/ui';
import { getPublicDocs } from '../../lib/public-docs';
import { publicPageMetadata } from '../../lib/seo';

export const metadata = publicPageMetadata('/docs');
export const dynamic = 'force-static';

export default function DocsIndexPage() {
  const docs = getPublicDocs();
  const intro = docs.find((page) => page.slug === 'introduction') ?? docs[0];
  if (!intro) throw new Error('No public docs pages configured.');

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-2">
        <PageHeader eyebrow="Docs" title="Intercal documentation" />
        <nav className="grid gap-1 text-sm">
          {docs.map((page) => (
            <Link
              key={page.slug}
              href={page.href}
              className="rounded-md border border-neutral-200 px-3 py-2 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
            >
              <span className="block font-medium">{page.title}</span>
              <span className="block text-xs text-neutral-500">{page.description}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <Panel>
        <Markdown markdown={intro.markdown} />
      </Panel>
    </div>
  );
}
