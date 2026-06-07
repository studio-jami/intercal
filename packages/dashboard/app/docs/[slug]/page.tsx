import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Markdown } from '../../../components/markdown';
import { PageHeader, Panel } from '../../../components/ui';
import { getPublicDoc, getPublicDocs } from '../../../lib/public-docs';

export const dynamic = 'force-static';
export const dynamicParams = false;

export function generateStaticParams() {
  return getPublicDocs().map((page) => ({ slug: page.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = getPublicDoc(slug);
  if (!page) return {};
  return {
    title: `${page.title} - Intercal Docs`,
    description: page.description,
  };
}

export default async function DocsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const docs = getPublicDocs();
  const page = getPublicDoc(slug);
  if (!page) notFound();

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-2">
        <PageHeader eyebrow="Docs" title="Intercal documentation" />
        <nav className="grid gap-1 text-sm">
          {docs.map((item) => (
            <Link
              key={item.slug}
              href={item.href}
              className={`rounded-md border px-3 py-2 hover:bg-neutral-50 dark:hover:bg-neutral-900 ${
                item.slug === page.slug
                  ? 'border-neutral-950 dark:border-neutral-50'
                  : 'border-neutral-200 dark:border-neutral-800'
              }`}
            >
              <span className="block font-medium">{item.title}</span>
              <span className="block text-xs text-neutral-500">{item.description}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <Panel>
        <Markdown markdown={page.markdown} />
      </Panel>
    </div>
  );
}
