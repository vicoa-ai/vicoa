import type { GitStatusEntry } from './rpc';

/**
 * One folder level of a Changes section rendered as a tree. Single-child
 * directory chains are compressed VSCode-style — a folder with no files of its
 * own and exactly one subfolder folds into it, so `name` may span several
 * segments ("src/app/api") while `path` is always the full prefix.
 */
export interface ChangesDirNode {
  name: string;
  path: string;
  dirs: ChangesDirNode[];
  files: GitStatusEntry[];
}

interface MutableNode {
  name: string;
  path: string;
  dirs: Map<string, MutableNode>;
  files: GitStatusEntry[];
}

function compress(node: MutableNode, isRoot: boolean): ChangesDirNode {
  let current = node;
  if (!isRoot) {
    while (current.files.length === 0 && current.dirs.size === 1) {
      const child = current.dirs.values().next().value as MutableNode;
      current = { ...child, name: `${current.name}/${child.name}` };
    }
  }
  const dirs = Array.from(current.dirs.values())
    .map((d) => compress(d, false))
    .sort((a, b) => a.name.localeCompare(b.name));
  return { name: current.name, path: current.path, dirs, files: current.files };
}

/**
 * Group a section's entries by directory. File order within a folder is
 * preserved from `entries` (git's own ordering); folders sort alphabetically.
 * A trailing-slash entry (an untracked embedded repo git won't descend into)
 * stays a leaf row named after its last segment, exactly like the flat list.
 */
export function buildChangesTree(entries: GitStatusEntry[]): ChangesDirNode {
  const root: MutableNode = { name: '', path: '', dirs: new Map(), files: [] };
  for (const entry of entries) {
    const parts = entry.path.split('/').filter(Boolean);
    if (parts.length === 0) continue;
    let node = root;
    for (const part of parts.slice(0, -1)) {
      let child = node.dirs.get(part);
      if (!child) {
        child = {
          name: part,
          path: node.path ? `${node.path}/${part}` : part,
          dirs: new Map(),
          files: [],
        };
        node.dirs.set(part, child);
      }
      node = child;
    }
    node.files.push(entry);
  }
  return compress(root, true);
}
