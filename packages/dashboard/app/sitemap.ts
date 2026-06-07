import type { MetadataRoute } from 'next';
import { getPublicDocs } from '../lib/public-docs';
import { buildSitemapEntries } from '../lib/seo';

export default function sitemap(): MetadataRoute.Sitemap {
  return buildSitemapEntries(getPublicDocs().map((page) => ({ href: page.href })));
}
