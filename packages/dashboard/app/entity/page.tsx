import Link from 'next/link';
import { redirect } from 'next/navigation';

export default async function EntitySearch({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  if (q) redirect(`/entity/${encodeURIComponent(q)}`);
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Find an entity</h1>
      <p className="text-neutral-600 dark:text-neutral-400">
        Enter an entity name on the{' '}
        <Link className="underline" href="/">
          home page
        </Link>
        .
      </p>
    </main>
  );
}
