import Link from 'next/link';
import { PageHeader, Panel } from '../../components/ui';
import { canonicalExamples, publicPageMetadata, publicSummaryText } from '../../lib/seo';

export const metadata = publicPageMetadata('/ai-history');
export const dynamic = 'force-static';

export default function AiHistoryPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="AI history substrate" title="Cited temporal knowledge for agents">
        <p>
          Intercal is built for questions that depend on time: what changed after a cutoff, whether
          a claim was supported as of a date, where a fact came from, and how fresh the public
          corpus is. The public surface is crawlable, but every product claim stays bounded by the
          live query layer and corpus quality gates.
        </p>
      </PageHeader>

      <Panel title="Copyable public summary">
        <pre className="whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-3 text-sm leading-6 text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
          {publicSummaryText}
        </pre>
      </Panel>

      <section className="grid gap-4 lg:grid-cols-2">
        <Panel title="What Intercal answers">
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-medium">Cutoff deltas</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Ask what changed about a topic after a date, then inspect cited changed claims.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Claim verification as of a date</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Check support and contradiction evidence against dated public graph state.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Provenance and source policy</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Public pages expose citation metadata and policy-allowed derived snippets, not raw
                restricted source bodies.
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Agent and app surfaces">
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-medium">MCP</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Agents connect to the same-origin Streamable HTTP endpoint at <code>/api/mcp</code>.
              </dd>
            </div>
            <div>
              <dt className="font-medium">REST and OpenAPI</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Applications call <code>/api/v1/*</code> and read the generated OpenAPI contract at{' '}
                <code>/api/openapi.json</code>.
              </dd>
            </div>
            <div>
              <dt className="font-medium">AI-readable docs</dt>
              <dd className="text-neutral-600 dark:text-neutral-400">
                Source-owned docs are rendered at <code>/docs</code> and exported through{' '}
                <code>/llms.txt</code> and <code>/llms-full.txt</code>.
              </dd>
            </div>
          </dl>
        </Panel>
      </section>

      <Panel title="Canonical public examples">
        <ul className="grid gap-3 md:grid-cols-2">
          {canonicalExamples.map((example) => (
            <li
              key={example.href}
              className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
            >
              <Link href={example.href} className="font-medium underline">
                {example.label}
              </Link>
              <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                {example.description}
              </p>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Jami Studio hook">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          A future Jami Studio public site can link to Intercal as one of the studio's open
          knowledge substrates. Intercal does not require <code>www.jami.studio</code> to be live;
          this repository owns only the Intercal product, docs, REST, and MCP surface.
        </p>
      </Panel>
    </div>
  );
}
