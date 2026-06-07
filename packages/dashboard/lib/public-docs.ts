import { publicDocMarkdown, publicDocsManifest } from './public-docs.gen';

export interface PublicDocPage {
  slug: string;
  title: string;
  description: string;
  source: string;
}

export interface PublicDocsManifest {
  title: string;
  baseUrl: string;
  pages: PublicDocPage[];
  dashboardRoutes: string[];
  api: {
    openapiSource: string;
    publicOpenapiRoute: string;
    mcpRoute: string;
  };
  exports: {
    index: string;
    full: string;
  };
}

export interface PublicDoc extends PublicDocPage {
  href: string;
  markdown: string;
}

export function getPublicDocsManifest(): PublicDocsManifest {
  return publicDocsManifest;
}

export function getPublicDocs(): PublicDoc[] {
  const manifest = getPublicDocsManifest();
  const markdownBySlug: Record<string, string> = publicDocMarkdown;
  return manifest.pages.map((page) => ({
    ...page,
    href: `/docs/${page.slug}`,
    markdown: markdownBySlug[page.slug] ?? '',
  }));
}

export function getPublicDoc(slug: string): PublicDoc | null {
  return getPublicDocs().find((page) => page.slug === slug) ?? null;
}

export function buildLlmsIndex(): string {
  const manifest = getPublicDocsManifest();
  const lines = [
    '# Intercal',
    '',
    'Intercal is an open, provenance-backed temporal knowledge substrate for agents and LLM apps. It serves public docs, REST, generated OpenAPI, and MCP from https://intercal.jami.studio.',
    '',
    '## Docs',
    '',
    `- [Docs home](${manifest.baseUrl}/docs): ${manifest.title}`,
    ...manifest.pages.map(
      (page) => `- [${page.title}](${manifest.baseUrl}/docs/${page.slug}): ${page.description}`,
    ),
    '',
    '## Machine-readable surfaces',
    '',
    `- [OpenAPI](${manifest.baseUrl}${manifest.api.publicOpenapiRoute})`,
    `- [MCP](${manifest.baseUrl}${manifest.api.mcpRoute})`,
    `- [Full docs export](${manifest.baseUrl}/llms-full.txt)`,
  ];
  return `${lines.join('\n')}\n`;
}

export function buildLlmsFull(): string {
  const manifest = getPublicDocsManifest();
  const docs = getPublicDocs();
  const sections = docs.map((page) => page.markdown).join('\n\n---\n\n');
  return `${[
    '# Intercal',
    '',
    'Intercal is an open, provenance-backed temporal knowledge substrate for agents and LLM apps. It serves public docs, REST, generated OpenAPI, and MCP from https://intercal.jami.studio.',
    '',
    `Source exports are generated from ${manifest.pages.length} source-owned pages listed in docs/public/manifest.json.`,
    '',
    '---',
    '',
    sections,
  ].join('\n')}\n`;
}
