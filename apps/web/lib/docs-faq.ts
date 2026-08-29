import { readFileSync } from 'node:fs';
import path from 'node:path';
import { cache } from 'react';

export interface FaqEntry {
  question: string;
  answer: string;
}

const FAQ_PATH = 'content/docs/faq.mdx';

/** Schema.org answers must be plain text — flatten the markdown we allow in the FAQ. */
function toPlainText(markdown: string) {
  return markdown
    .replace(/```[\s\S]*?```/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Reads faq.mdx and pairs each `## Question` with the prose beneath it. Runs at
 * build time (the docs routes are fully prerendered), so the JSON-LD is baked
 * into the static HTML and nothing touches the filesystem at request time.
 */
export const getFaqEntries = cache((): FaqEntry[] => {
  let raw: string;

  try {
    raw = readFileSync(path.join(process.cwd(), FAQ_PATH), 'utf8');
  } catch {
    // Content missing from the build context — ship the page without FAQ schema
    // rather than failing the render.
    return [];
  }

  const body = raw
    .replace(/^---\n[\s\S]*?\n---\n/, '')
    // Drop fenced code first so a shell comment like `## note` can't split a section.
    .replace(/```[\s\S]*?```/g, '');
  const entries: FaqEntry[] = [];

  // Split on H2s only; H3s stay part of the answer they belong to.
  const sections = body.split(/^## /m).slice(1);

  for (const section of sections) {
    const newline = section.indexOf('\n');
    if (newline === -1) continue;

    const question = section.slice(0, newline).trim();
    const answer = toPlainText(section.slice(newline));

    if (question && answer) {
      entries.push({ question, answer });
    }
  }

  return entries;
});
