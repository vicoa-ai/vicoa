import type { Metadata } from 'next';

/**
 * Canonical origin for the marketing/docs site. The root layout's
 * `metadataBase` resolves relative paths against this, so pages pass a
 * root-relative path ('/features') and get an absolute canonical + og:url.
 */
export const SITE_URL = 'https://vicoa.ai';

/**
 * Derive `alternates.canonical` and `openGraph.url` from a single source — the
 * page's own path — so the two can never drift apart again.
 *
 * Next.js *overwrites* (does not deep-merge) metadata fields between route
 * segments. A page that sets only one of canonical/og:url therefore silently
 * inherits the root layout's homepage value for the other, which is the C1
 * canonical bug (some pages canonicalised to the homepage, others emitted an
 * og:url pointing at the homepage). Routing both through this helper removes
 * that whole failure class: pass the path once, get both fields wired to it.
 *
 * Any `alternates`/`openGraph` fields the caller also sets (RSS `types`, og
 * images, etc.) are preserved; only `canonical` and `url` are forced from
 * `path`.
 *
 * @param path Root-relative page path, e.g. `/features`. Resolved to an
 *   absolute URL by the root layout's `metadataBase`.
 */
export function pageMetadata(path: string, meta: Metadata = {}): Metadata {
  return {
    ...meta,
    alternates: { ...meta.alternates, canonical: path },
    openGraph: { ...meta.openGraph, url: path },
  };
}
