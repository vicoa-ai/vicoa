import { updates as updateDocs } from '@/.source/index';

export type UpdateEntry = (typeof updateDocs)[number];

export const updates = updateDocs;

export const UPDATES_BASE_URL = 'https://vicoa.ai';

export interface UpdateFrontmatter {
  title: string;
  description: string;
  /** Short lede shown under the headline, before the body sections. */
  summary: string;
  publishedAt: string;
  updatedAt?: string;
  tags?: string[];
  image?: string;
  imageAlt?: string;
}

export function getUpdateSlug(entry: UpdateEntry): string {
  return entry.info.path.replace(/\.mdx$/, '');
}

const updatesBySlug = new Map(
  updates.map((entry) => [getUpdateSlug(entry), entry] as const)
);

/**
 * fumadocs exposes frontmatter both spread onto the doc and (depending on the
 * build) nested under `frontmatter`. Merge the two the same way the blog does
 * so a build-mode change can't silently drop fields.
 */
export function getUpdateData(entry: UpdateEntry) {
  const raw = entry as any;
  return {
    ...((raw.frontmatter ?? {}) as Record<string, unknown>),
    ...raw,
  } as UpdateFrontmatter & Record<string, unknown>;
}

/** Newest first — the order the changelog is read in. */
export function getAllUpdates(): UpdateEntry[] {
  return Array.from(updates).sort((a, b) => {
    const dateA = new Date(getUpdateData(a).publishedAt || 0).getTime();
    const dateB = new Date(getUpdateData(b).publishedAt || 0).getTime();
    return dateB - dateA;
  });
}

export function getUpdateBySlug(slug: string): UpdateEntry | undefined {
  return updatesBySlug.get(slug);
}

export function getUpdateUrl(entry: UpdateEntry): string {
  return `/updates/${getUpdateSlug(entry)}`;
}

/** Previous (older) and next (newer) entries, for permalink footer nav. */
export function getAdjacentUpdates(entry: UpdateEntry) {
  const all = getAllUpdates();
  const index = all.findIndex((item) => getUpdateSlug(item) === getUpdateSlug(entry));

  return {
    newer: index > 0 ? all[index - 1] : undefined,
    older: index >= 0 && index < all.length - 1 ? all[index + 1] : undefined,
  };
}

/** "Mar 18, 2026" — matches the compact date rail on the index page. */
export function formatUpdateDate(date: string | undefined): string {
  if (!date) return '';

  const parsed = new Date(date);
  if (isNaN(parsed.getTime())) return '';

  return parsed.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/** ISO date for <time dateTime> and structured data. */
export function toIsoDate(date: string | undefined): string | undefined {
  if (!date) return undefined;
  const parsed = new Date(date);
  return isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}
