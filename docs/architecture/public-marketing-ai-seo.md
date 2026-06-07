# Public Marketing And AI SEO

Intercal's public marketing surface is part of the product app because the public claims depend on
the same docs, REST, MCP, and corpus coverage state. This doc records the source-owned SEO surface;
the live Next app and tests remain executable truth.

## Owned routes

- `/` describes Intercal as a provenance-backed temporal knowledge substrate and links to the
  product routes that already read the shared query layer.
- `/ai-history` is the crawlable public explanation page for agents and search systems. It includes
  copyable summary text, canonical query examples, MCP/REST/docs surface pointers, and a non-blocking
  Jami Studio hook.
- `/sitemap.xml`, `/robots.txt`, canonical metadata, OpenGraph/Twitter metadata, JSON-LD, and the
  share-image route are owned in `packages/dashboard`.

## Claim Boundaries

Marketing copy must stay bounded by implemented behavior:

- It may describe source documents to claims to entities to typed temporal relationships to
  append-only fact versions.
- It may describe cutoff deltas, claim verification as of a date, provenance, freshness, coverage,
  REST, SDK, and MCP because those surfaces exist in the live app/contracts.
- It must describe corpus breadth as a bounded reviewed AI-history proof unless the live corpus
  quality gates prove broader continuous coverage.
- It must not imply that the future Jami Studio site is live or required. Links/copy hooks are
  non-blocking context only.

## Drift Checks

Route and metadata expectations are tested in `packages/dashboard/lib/seo.test.ts`. Public docs and
route inventory remain checked by `pnpm docs:check`.
