import type { MetadataRoute } from 'next';
import { canonicalUrl, SITE_ORIGIN } from '../lib/seo';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: ['/', '/docs', '/api/openapi.json', '/llms.txt', '/llms-full.txt'],
      disallow: ['/operator', '/subscriptions', '/feedback'],
    },
    sitemap: canonicalUrl('/sitemap.xml'),
    host: SITE_ORIGIN,
  };
}
