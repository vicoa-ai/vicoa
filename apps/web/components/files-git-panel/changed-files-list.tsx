'use client';

import * as React from 'react';
import type { GitStatusResult, GitStatusEntry } from './rpc';
import { FileTypeIcon } from './file-type-icon';
import { gitStatusColor, gitStatusLetter } from './files-tab';
import { SCROLL_STYLE } from './styles';

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

function dirname(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? '' : path.slice(0, i);
}

/** De-duped, ordered list of changed files (staged → unstaged → untracked),
 *  skipping the trailing-slash directory rows git emits for embedded repos. */
export function changedFileEntries(status: GitStatusResult | null): GitStatusEntry[] {
  const seen = new Set<string>();
  const out: GitStatusEntry[] = [];
  for (const list of [status?.staged, status?.unstaged, status?.untracked]) {
    for (const e of list ?? []) {
      if (e.path.endsWith('/') || seen.has(e.path)) continue;
      seen.add(e.path);
      out.push(e);
    }
  }
  return out;
}

/** A compact list of the working tree's changed files, for switching between
 *  diffs without leaving the file view. Clicking a row opens its diff; the
 *  active file is highlighted. Deleted files have no working copy to edit, so
 *  they're shown but not openable. */
export function ChangedFilesList({
  status,
  activePath,
  onOpenFile,
}: {
  status: GitStatusResult | null;
  activePath: string | null;
  /** Single click opens a preview diff; `{ newTab: true }` (double click) a
   * permanent tab. */
  onOpenFile: (path: string, opts?: { newTab?: boolean }) => void;
}) {
  const entries = React.useMemo(() => changedFileEntries(status), [status]);

  if (entries.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-sm text-muted-foreground font-mono">
        No changes
      </div>
    );
  }

  return (
    <div className={`min-h-0 flex-1 overflow-auto py-1 ${SCROLL_STYLE}`}>
      {entries.map((e) => {
        const name = basename(e.path);
        const dir = dirname(e.path);
        const active = e.path === activePath;
        const canOpen = e.status !== 'D';
        return (
          <button
            key={e.path}
            type="button"
            onClick={() => canOpen && onOpenFile(e.path)}
            onDoubleClick={() => canOpen && onOpenFile(e.path, { newTab: true })}
            disabled={!canOpen}
            title={e.path}
            className={`flex w-full items-center gap-2 px-3 py-1 text-left text-xs font-mono hover:bg-muted/40 ${
              active ? 'bg-muted/50' : ''
            } ${canOpen ? '' : 'cursor-default opacity-60'}`}
          >
            <FileTypeIcon fileName={name} size={14} />
            <span className={`truncate ${gitStatusColor(e.status)}`}>{name}</span>
            {dir ? (
              <span className="min-w-0 flex-1 truncate text-muted-foreground/60">{dir}</span>
            ) : (
              <span className="flex-1" />
            )}
            <span className="flex-shrink-0 text-[10px]">
              <span className="text-emerald-600 dark:text-emerald-400">+{e.additions}</span>
              <span className="ml-1 text-red-600 dark:text-red-400">-{e.deletions}</span>
            </span>
            <span className={`flex-shrink-0 text-[10px] ${gitStatusColor(e.status)}`}>
              {gitStatusLetter(e.status)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
