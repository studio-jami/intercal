import { describe, expect, it } from 'vitest';
import robots from '../app/robots';
import sitemap from '../app/sitemap';
import {
  buildSitemapEntries,
  buildWebsiteJsonLd,
  canonicalUrl,
  dynamicPageMetadata,
  publicPageMetadata,
  publicRouteMetadata,
  SHARE_IMAGE_PATH,
  SITE_ORIGIN,
} from './seo';

describe('dashboard public SEO', () => {
  it('builds canonical URLs on the official Intercal domain', () => {
    expect(canonicalUrl('/delta')).toBe(`${SITE_ORIGIN}/delta`);
    expect(canonicalUrl('verify')).toBe(`${SITE_ORIGIN}/verify`);
  });

  it('declares canonical metadata and share images for every static public route', () => {
    for (const route of Object.keys(publicRouteMetadata) as (keyof typeof publicRouteMetadata)[]) {
      const metadata = publicPageMetadata(route);

      expect(metadata.description).toBe(publicRouteMetadata[route].description);
      expect(metadata.alternates?.canonical).toBe(canonicalUrl(route));
      expect(metadata.openGraph?.url).toBe(canonicalUrl(route));
      expect(JSON.stringify(metadata.openGraph?.images)).toContain(SHARE_IMAGE_PATH);
    }
  });

  it('marks auth and operator workflow routes as noindex', () => {
    expect(publicPageMetadata('/operator').robots).toMatchObject({ index: false, follow: false });
    expect(publicPageMetadata('/subscriptions').robots).toMatchObject({
      index: false,
      follow: false,
    });
    expect(publicPageMetadata('/feedback').robots).toMatchObject({ index: false, follow: false });
    expect(publicPageMetadata('/ai-history').robots).toMatchObject({ index: true, follow: true });
  });

  it('builds dynamic route metadata without losing the canonical path', () => {
    const metadata = dynamicPageMetadata({
      title: 'MCP protocol topic timeline',
      description: 'Topic explanation',
      pathname: '/topic/MCP%20protocol',
    });

    expect(metadata.title).toBe('MCP protocol topic timeline | Intercal');
    expect(metadata.alternates?.canonical).toBe(`${SITE_ORIGIN}/topic/MCP%20protocol`);
    expect(JSON.stringify(metadata.openGraph)).toContain('article');
  });

  it('serves a sitemap with product, docs, and example entity/topic routes', () => {
    const urls = new Set(sitemap().map((entry) => entry.url));

    expect(urls.has(canonicalUrl('/'))).toBe(true);
    expect(urls.has(canonicalUrl('/ai-history'))).toBe(true);
    expect(urls.has(canonicalUrl('/docs/introduction'))).toBe(true);
    expect(urls.has(canonicalUrl('/entity/MCP%20protocol'))).toBe(true);
    expect(urls.has(canonicalUrl('/topic/frontier%20LLMs'))).toBe(true);
    expect(urls.has(canonicalUrl('/operator'))).toBe(false);
  });

  it('keeps sitemap generation deterministic for supplied docs', () => {
    expect(buildSitemapEntries([{ href: '/docs/test' }]).map((entry) => entry.url)).toContain(
      canonicalUrl('/docs/test'),
    );
  });

  it('serves robots policy for crawlable docs and non-crawlable operator workflows', () => {
    const config = robots();

    expect(config.sitemap).toBe(canonicalUrl('/sitemap.xml'));
    expect(config.host).toBe(SITE_ORIGIN);
    expect(JSON.stringify(config.rules)).toContain('/operator');
    expect(JSON.stringify(config.rules)).toContain('/api/openapi.json');
  });

  it('emits structured data for website, software, corpus, and API surfaces', () => {
    const graph = buildWebsiteJsonLd()['@graph'].map((item) => item['@type']);

    expect(graph).toContain('WebSite');
    expect(graph).toContain('SoftwareApplication');
    expect(graph).toContain('Dataset');
    expect(graph).toContain('WebAPI');
  });
});
