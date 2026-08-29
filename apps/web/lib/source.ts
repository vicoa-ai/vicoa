import { meta } from '@/.source/index';
import {
  DEFAULT_DOC_SLUG,
  docsBySlug,
  getDocName as toName,
  getDocUrl as toUrl
} from '@/lib/docs-source';

// Find meta entries for folders
const metaByFolder = new Map(
  meta
    .filter((entry) => entry.info && entry.info.fullPath)
    .map((entry) => [entry.info.fullPath.replace(/\/meta\.json$/, '').replace(/^content\/docs\//, ''), entry])
);

function buildTree() {
  // Find root meta (the main docs meta.json)
  const rootMeta = Array.from(metaByFolder.values()).find(m =>
    m.info?.fullPath?.endsWith('docs/meta.json')
  );

  if (!rootMeta || !(rootMeta as any).pages) {
    // Fallback to all docs if no meta found
    return Array.from(docsBySlug.keys())
      .map(slug => ({
        type: 'page' as const,
        name: toName(slug),
        url: toUrl(slug)
      }));
  }

  const rootPages = (rootMeta as any).pages;

  return rootPages.map((slug: string) => {
    // Check if this is a folder with its own meta
    const folderMeta = Array.from(metaByFolder.values()).find(m =>
      m.info?.fullPath?.endsWith(`/${slug}/meta.json`)
    );

    if (folderMeta && (folderMeta as any).pages) {
      // This is a folder - create a folder node with children
      const folderPages = (folderMeta as any).pages;
      return {
        type: 'folder' as const,
        name: (folderMeta as any).title || toName(slug),
        index: {
          type: 'page' as const,
          name: (folderMeta as any).title || toName(slug),
          // Link the canonical /docs/agents, not the /docs/agents/index alias.
          url: toUrl(slug)
        },
        children: folderPages
          .filter((childSlug: string) => childSlug !== DEFAULT_DOC_SLUG)
          .map((childSlug: string) => ({
            type: 'page' as const,
            name: toName(`${slug}/${childSlug}`),
            url: toUrl(`${slug}/${childSlug}`)
          }))
      };
    } else {
      // This is a regular page
      return {
        type: 'page' as const,
        name: toName(slug),
        url: toUrl(slug)
      };
    }
  });
}

const children = buildTree();

export const pageTree = {
  name: 'Documentation',
  children
};
