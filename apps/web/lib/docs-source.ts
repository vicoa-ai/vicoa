import { docs, meta } from '@/.source/index';

export type DocEntry = (typeof docs)[number];

export const DEFAULT_DOC_SLUG = 'index';

/** Appended to every docs <title>; frontmatter titles stay unbranded. */
export const DOCS_TITLE_SUFFIX = ' - Vicoa Docs';

export const DOCS_BASE_URL = 'https://vicoa.ai';

export const docsBySlug = new Map(
  docs.map((doc) => {
    const slug = doc.info.path.replace(/\.mdx$/, '');
    return [slug, doc] as const;
  })
);

const metaByFolder = new Map(
  meta
    .filter((entry) => entry.info && entry.info.fullPath)
    // fullPath may be absolute or repo-relative depending on the fumadocs build,
    // so anchor on the content/docs segment rather than the string start.
    .map((entry) => [
      entry.info.fullPath
        .replace(/\/meta\.json$/, '')
        .replace(/^.*content\/docs\/?/, ''),
      entry
    ])
);

/**
 * One canonical slug per page, with `index` stripped — `agents/index` renders at
 * `agents` and the root doc at `''`. Deriving these from the file map rather
 * than from meta.json matters: nested meta files list bare child names, so
 * flattening them used to prerender `/docs/claude-code` as a 404 alongside the
 * real `/docs/agents/claude-code`. The `/index` URLs are handled by a redirect
 * in next.config.ts.
 */
export const staticDocSlugs = Array.from(
  new Set(
    Array.from(docsBySlug.keys()).map((slug) =>
      slug.replace(new RegExp(`(^|/)${DEFAULT_DOC_SLUG}$`), '')
    )
  )
);

export function toDocSlugKey(slug?: string[]) {
  if (!slug || slug.length === 0) {
    return DEFAULT_DOC_SLUG;
  }
  return slug.join('/');
}

export function resolveDoc(slug?: string[]): DocEntry | undefined {
  const key = toDocSlugKey(slug);
  return docsBySlug.get(key) ?? docsBySlug.get(`${key}/${DEFAULT_DOC_SLUG}`);
}

/** Canonical path for a slug: `index` -> /docs, `agents/index` -> /docs/agents. */
export function getDocUrl(slug: string) {
  const canonical = slug.replace(new RegExp(`(^|/)${DEFAULT_DOC_SLUG}$`), '');
  return canonical ? `/docs/${canonical}` : '/docs';
}

/** Frontmatter title without the brand suffix — for sidebars, breadcrumbs, H1s. */
export function getDocName(slug: string) {
  const doc = docsBySlug.get(slug) ?? docsBySlug.get(`${slug}/${DEFAULT_DOC_SLUG}`);
  const title = doc?.title ?? slug.split('/').pop()?.replace(/-/g, ' ') ?? slug;
  return title.replace(new RegExp(`${DOCS_TITLE_SUFFIX}$`), '');
}

/** Branded title for <title> and social cards. */
export function getDocPageTitle(doc: DocEntry) {
  const bare = (doc.title ?? 'Documentation').replace(
    new RegExp(`${DOCS_TITLE_SUFFIX}$`),
    ''
  );
  return `${bare}${DOCS_TITLE_SUFFIX}`;
}

export interface DocCrumb {
  name: string;
  url: string;
}

/** Docs > Agents > Claude Code, resolved through the folder meta.json titles. */
export function getDocBreadcrumbs(slug?: string[]): DocCrumb[] {
  const key = toDocSlugKey(slug);
  const crumbs: DocCrumb[] = [{ name: 'Docs', url: '/docs' }];

  const parts = key.split('/').filter((part) => part !== DEFAULT_DOC_SLUG);

  parts.forEach((_, index) => {
    const prefix = parts.slice(0, index + 1).join('/');
    const folder = metaByFolder.get(prefix) as { title?: string } | undefined;
    crumbs.push({
      name: folder?.title ?? getDocName(prefix),
      url: getDocUrl(prefix)
    });
  });

  return crumbs;
}
