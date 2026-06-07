import Link from 'next/link';
import type { ReactNode } from 'react';
import { buildWebsiteJsonLd, publicPageMetadata } from '../lib/seo';
import './globals.css';

export const metadata = publicPageMetadata('/');

const nav = [
  ['AI History', '/ai-history'],
  ['Topics', '/topic'],
  ['Graph', '/graph'],
  ['Search', '/search'],
  ['Docs', '/docs'],
  ['Compare', '/compare'],
  ['Delta', '/delta'],
  ['Verify', '/verify'],
  ['Freshness', '/freshness'],
  ['Coverage', '/coverage'],
  ['Subscriptions', '/subscriptions'],
  ['Feedback', '/feedback'],
  ['Operator', '/operator'],
] as const;

export default function RootLayout({ children }: { children: ReactNode }) {
  const websiteJsonLd = buildWebsiteJsonLd();

  return (
    <html lang="en">
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd) }}
        />
        <div className="min-h-screen">
          <header className="border-b border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950">
            <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
              <Link href="/" className="text-lg font-semibold tracking-tight">
                Intercal
              </Link>
              <nav className="flex flex-wrap gap-1 text-sm text-neutral-600 dark:text-neutral-300">
                {nav.map(([label, href]) => (
                  <Link
                    key={href}
                    href={href}
                    className="rounded-md px-3 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-900"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
