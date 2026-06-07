import Link from 'next/link';
import type { ReactNode } from 'react';

type Block =
  | { type: 'heading'; level: number; text: string; key: string }
  | { type: 'paragraph'; text: string; key: string }
  | { type: 'list'; ordered: boolean; items: string[]; key: string }
  | { type: 'code'; language: string; code: string; key: string }
  | { type: 'rule'; key: string };

function isListLine(line: string): boolean {
  return /^(- |\d+\. )/.test(line);
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    const key = `${index}-${line.slice(0, 12)}`;

    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith('```')) {
      const language = line.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index]?.startsWith('```')) {
        code.push(lines[index] ?? '');
        index += 1;
      }
      index += 1;
      blocks.push({ type: 'code', language, code: code.join('\n'), key });
      continue;
    }

    if (line.trim() === '---') {
      blocks.push({ type: 'rule', key });
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const marker = heading[1] ?? '#';
      const text = heading[2] ?? '';
      blocks.push({
        type: 'heading',
        level: marker.length,
        text,
        key,
      });
      index += 1;
      continue;
    }

    if (isListLine(line)) {
      const ordered = /^\d+\. /.test(line);
      const items: string[] = [];
      while (index < lines.length && isListLine(lines[index] ?? '')) {
        items.push((lines[index] ?? '').replace(/^(- |\d+\. )/, ''));
        index += 1;
      }
      blocks.push({ type: 'list', ordered, items, key });
      continue;
    }

    const paragraph: string[] = [line.trim()];
    index += 1;
    while (
      index < lines.length &&
      lines[index]?.trim() &&
      !lines[index]?.startsWith('```') &&
      !/^(#{1,3})\s+/.test(lines[index] ?? '') &&
      !isListLine(lines[index] ?? '') &&
      lines[index]?.trim() !== '---'
    ) {
      paragraph.push((lines[index] ?? '').trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraph.join(' '), key });
  }

  return blocks;
}

function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let match: RegExpExecArray | null = pattern.exec(text);
  while (match) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const matchedText = match[0];
    if (matchedText.startsWith('`')) {
      parts.push(
        <code
          key={`${match.index}-code`}
          className="rounded bg-neutral-100 px-1 py-0.5 text-[0.95em] dark:bg-neutral-900"
        >
          {matchedText.slice(1, -1)}
        </code>,
      );
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(matchedText);
      if (link) {
        const href = link[2] ?? '';
        const label = link[1] ?? href;
        const external = /^https?:\/\//.test(href);
        parts.push(
          <Link
            key={`${match.index}-link`}
            href={href}
            className="underline"
            target={external ? '_blank' : undefined}
            rel={external ? 'noreferrer' : undefined}
          >
            {label}
          </Link>,
        );
      }
    }
    last = match.index + matchedText.length;
    match = pattern.exec(text);
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ markdown }: { markdown: string }) {
  const blocks = parseBlocks(markdown);
  return (
    <article className="space-y-4 text-sm leading-6 text-neutral-700 dark:text-neutral-300">
      {blocks.map((block) => {
        if (block.type === 'heading') {
          if (block.level === 1) {
            return (
              <h1
                key={block.key}
                className="text-2xl font-semibold text-neutral-950 dark:text-white"
              >
                {block.text}
              </h1>
            );
          }
          if (block.level === 2) {
            return (
              <h2
                key={block.key}
                className="pt-2 text-lg font-semibold text-neutral-950 dark:text-white"
              >
                {block.text}
              </h2>
            );
          }
          return (
            <h3 key={block.key} className="font-semibold text-neutral-950 dark:text-white">
              {block.text}
            </h3>
          );
        }
        if (block.type === 'paragraph') {
          return <p key={block.key}>{inline(block.text)}</p>;
        }
        if (block.type === 'list') {
          const List = block.ordered ? 'ol' : 'ul';
          return (
            <List key={block.key} className="ml-5 list-outside space-y-1">
              {block.items.map((item) => (
                <li key={item} className={block.ordered ? 'list-decimal' : 'list-disc'}>
                  {inline(item)}
                </li>
              ))}
            </List>
          );
        }
        if (block.type === 'code') {
          return (
            <pre
              key={block.key}
              className="overflow-x-auto rounded-md bg-neutral-950 p-4 text-xs text-neutral-50"
            >
              <code data-language={block.language || undefined}>{block.code}</code>
            </pre>
          );
        }
        return <hr key={block.key} className="border-neutral-200 dark:border-neutral-800" />;
      })}
    </article>
  );
}
