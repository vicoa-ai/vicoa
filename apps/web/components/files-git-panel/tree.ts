import type { FileEntry } from './rpc';

export function joinPath(dir: string, name: string): string {
  if (!dir) return name;
  return `${dir}/${name}`;
}

export function parentPath(path: string): string {
  const i = path.lastIndexOf('/');
  if (i < 0) return '';
  return path.slice(0, i);
}

/**
 * Root-first directory prefixes of `dirPath`. 'a/b/c' -> ['a','a/b','a/b/c'];
 * '' -> []; 'a' -> ['a']. Empty segments (leading/trailing/double slashes) are
 * dropped. Used to expand the tree from the root down to a nested directory.
 */
export function ancestorPaths(dirPath: string): string[] {
  const parts = dirPath.split('/').filter((p) => p.length > 0);
  const out: string[] = [];
  let acc = '';
  for (const p of parts) {
    acc = acc ? `${acc}/${p}` : p;
    out.push(acc);
  }
  return out;
}

export type TreeRow =
  | {
      path: string;
      name: string;
      type: 'dir';
      depth: number;
      expanded: boolean;
      loading: boolean;
    }
  | {
      path: string;
      name: string;
      type: 'file';
      depth: number;
      size: number;
    };

type Listings = Map<string, FileEntry[] | null | undefined>;

export function flattenTree(listings: Listings, expanded: Set<string>): TreeRow[] {
  const out: TreeRow[] = [];

  const walk = (dirPath: string, depth: number): void => {
    const entries = listings.get(dirPath);
    if (!entries) return;
    for (const entry of entries) {
      const childPath = joinPath(dirPath, entry.name);
      if (entry.type === 'dir') {
        const isExpanded = expanded.has(childPath);
        const childListing = listings.get(childPath);
        const loading = isExpanded && (childListing === undefined || childListing === null);
        out.push({
          path: childPath,
          name: entry.name,
          type: 'dir',
          depth,
          expanded: isExpanded,
          loading,
        });
        if (isExpanded && Array.isArray(childListing)) {
          walk(childPath, depth + 1);
        }
      } else {
        out.push({
          path: childPath,
          name: entry.name,
          type: 'file',
          depth,
          size: entry.size ?? 0,
        });
      }
    }
  };

  walk('', 0);
  return out;
}
