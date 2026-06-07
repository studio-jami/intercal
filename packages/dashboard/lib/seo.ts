import type { Metadata, MetadataRoute } from 'next';

export const SITE_ORIGIN = 'https://intercal.jami.studio';
export const SITE_NAME = 'Intercal';
export const SHARE_IMAGE_PATH = '/opengraph-image';
export const SHARE_IMAGE_ALT = 'Intercal temporal knowledge substrate for cited AI-history queries';

export const canonicalExamples = [
  {
    label: 'Verify a claim as of a date',
    href: '/verify?claim_text=GPT-4%20Turbo%20supports%20a%20128k%20context%20window&as_of_date=2024-04-01',
    description: 'Check a claim against dated supporting and contradicting evidence.',
  },
  {
    label: 'Ask for a cutoff delta',
    href: '/delta?topic=frontier%20LLMs&since_date=2023-03-01',
    description: 'Return cited changes after a cutoff, with a bounded token budget.',
  },
  {
    label: 'Open a public topic',
    href: '/topic/frontier%20LLMs',
    description: 'Inspect freshness, evidence search, and a cited topic timeline.',
  },
  {
    label: 'Open an entity',
    href: '/entity/MCP%20protocol',
    description: 'Read entity facts, relationships, freshness, and evidence paths.',
  },
] as const;

export const publicSummaryText = [
  'Intercal is an open, provenance-backed temporal knowledge substrate for agents and LLM apps.',
  'It turns source documents into claims, resolved entities, typed temporal relationships, and append-only bitemporal fact versions.',
  'Use it to ask what changed after a cutoff date, verify a claim as of a date, inspect provenance, and connect agents over same-origin MCP and REST.',
  'Public coverage is bounded by the reviewed AI-history corpus gates and every surfaced fact must cite evidence or show an explicit coverage state.',
].join(' ');

const noindexRoutes = new Set(['/subscriptions', '/feedback', '/operator']);

export const publicRouteMetadata = {
  '/': {
    title: 'Intercal',
    description:
      'A provenance-backed temporal knowledge substrate for AI-history deltas, claim verification, evidence search, MCP, and REST.',
  },
  '/ai-history': {
    title: 'AI history substrate',
    description:
      'Crawlable explanation of Intercal as a cited AI-history substrate for cutoff deltas, claim verification, provenance, MCP, and REST.',
  },
  '/entity': {
    title: 'Entity lookup',
    description:
      'Open public entity pages with cited facts, relationships, freshness, and evidence paths.',
  },
  '/topic': {
    title: 'Topic explorer',
    description:
      'Open topic pages that combine freshness, evidence search, and cited cutoff timelines.',
  },
  '/graph': {
    title: 'Graph timeline',
    description:
      'Explore cited claim, entity, confidence, contradiction, and source-origin overlays.',
  },
  '/search': {
    title: 'Evidence search',
    description:
      'Search policy-servable source-document evidence with citation metadata and dated filters.',
  },
  '/compare': {
    title: 'Topic comparison',
    description:
      'Compare two AI-history topics by cited change volume, freshness, and coverage state.',
  },
  '/delta': {
    title: 'Cutoff delta briefing',
    description:
      'Ask what changed about a topic after a cutoff date using cited claims and a token budget.',
  },
  '/verify': {
    title: 'Claim verification',
    description: 'Verify a claim as of a date against supporting and contradicting evidence.',
  },
  '/freshness': {
    title: 'Freshness',
    description: 'Inspect recency, coverage, and explicit no-data states for a topic or entity.',
  },
  '/coverage': {
    title: 'Corpus coverage',
    description:
      'Review the current AI-history corpus quality gate and its public coverage limits.',
  },
  '/subscriptions': {
    title: 'Subscriptions',
    description:
      'Manage authenticated change notifications without mutating canonical graph state.',
  },
  '/feedback': {
    title: 'Feedback',
    description: 'Report public evidence or claim issues into audited review records.',
  },
  '/operator': {
    title: 'Operator console',
    description: 'Auth-gated source health, reviews, usage, budget, and audit state.',
  },
  '/docs': {
    title: 'Documentation',
    description:
      'Source-owned Intercal docs, generated OpenAPI guidance, MCP examples, and AI exports.',
  },
} as const;

export type PublicStaticRoute = keyof typeof publicRouteMetadata;

export const sitemapExampleRoutes = [
  '/entity/ChatGPT',
  '/entity/Claude',
  '/entity/Gemini',
  '/entity/Llama',
  '/entity/MCP%20protocol',
  '/topic/frontier%20LLMs',
  '/topic/MCP%20protocol',
  '/topic/AI%20regulation',
] as const;

export function canonicalUrl(pathname: string): string {
  const path = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${SITE_ORIGIN}${path}`;
}

export function publicPageMetadata(pathname: PublicStaticRoute): Metadata {
  const route = publicRouteMetadata[pathname];
  const title = route.title === SITE_NAME ? SITE_NAME : `${route.title} | ${SITE_NAME}`;
  const description = route.description;
  const canonical = canonicalUrl(pathname);
  const index = !noindexRoutes.has(pathname);

  return {
    metadataBase: new URL(SITE_ORIGIN),
    title,
    description,
    applicationName: SITE_NAME,
    alternates: { canonical },
    openGraph: {
      title,
      description,
      url: canonical,
      siteName: SITE_NAME,
      type: 'website',
      images: [{ url: SHARE_IMAGE_PATH, width: 1200, height: 630, alt: SHARE_IMAGE_ALT }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [SHARE_IMAGE_PATH],
    },
    robots: index
      ? { index: true, follow: true }
      : { index: false, follow: false, googleBot: { index: false, follow: false } },
  };
}

export function dynamicPageMetadata({
  title,
  description,
  pathname,
}: {
  title: string;
  description: string;
  pathname: string;
}): Metadata {
  const canonical = canonicalUrl(pathname);
  const fullTitle = `${title} | ${SITE_NAME}`;
  return {
    metadataBase: new URL(SITE_ORIGIN),
    title: fullTitle,
    description,
    alternates: { canonical },
    openGraph: {
      title: fullTitle,
      description,
      url: canonical,
      siteName: SITE_NAME,
      type: 'article',
      images: [{ url: SHARE_IMAGE_PATH, width: 1200, height: 630, alt: SHARE_IMAGE_ALT }],
    },
    twitter: {
      card: 'summary_large_image',
      title: fullTitle,
      description,
      images: [SHARE_IMAGE_PATH],
    },
    robots: { index: true, follow: true },
  };
}

export function buildWebsiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${SITE_ORIGIN}/#website`,
        name: SITE_NAME,
        url: SITE_ORIGIN,
        description: publicRouteMetadata['/'].description,
        inLanguage: 'en',
      },
      {
        '@type': 'SoftwareApplication',
        '@id': `${SITE_ORIGIN}/#software`,
        name: SITE_NAME,
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'Web',
        url: SITE_ORIGIN,
        description:
          'Open temporal knowledge substrate for cited AI-history deltas, claim verification, provenance, REST, and MCP.',
      },
      {
        '@type': 'Dataset',
        '@id': `${SITE_ORIGIN}/#ai-history-corpus`,
        name: 'Intercal AI-history corpus',
        url: canonicalUrl('/coverage'),
        description:
          'A bounded, reviewed GPT-era AI-history corpus surfaced with provenance, freshness, and coverage states.',
        isAccessibleForFree: true,
      },
      {
        '@type': 'WebAPI',
        '@id': `${SITE_ORIGIN}/api#webapi`,
        name: 'Intercal REST and MCP API',
        url: canonicalUrl('/api/openapi.json'),
        documentation: canonicalUrl('/docs'),
        description:
          'Same-origin REST, generated OpenAPI, and MCP surfaces over the shared Intercal query layer.',
      },
    ],
  };
}

export function buildSitemapEntries(docs: { href: string }[] = []): MetadataRoute.Sitemap {
  const staticRoutes = (Object.keys(publicRouteMetadata) as PublicStaticRoute[]).filter(
    (route) => !noindexRoutes.has(route),
  );
  const routeEntries = [...staticRoutes, ...sitemapExampleRoutes].map((route) => ({
    url: canonicalUrl(route),
    changeFrequency: route === '/' ? ('daily' as const) : ('weekly' as const),
    priority: route === '/' ? 1 : route.startsWith('/docs') ? 0.7 : 0.8,
  }));
  const docEntries = docs.map((doc) => ({
    url: canonicalUrl(doc.href),
    changeFrequency: 'weekly' as const,
    priority: 0.7,
  }));

  return [...routeEntries, ...docEntries];
}
