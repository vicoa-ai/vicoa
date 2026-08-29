'use client';

import { ChevronDown, ChevronRight } from 'lucide-react';
import type { CommitEntry } from './rpc';
import type { CommitDiffEntry, CommitFilesEntry } from './use-commits';
import { fileKey } from './use-commits';
import { DiffView } from './diff-view';

function basename(p: string): string {
  const i = p.lastIndexOf('/');
  return i < 0 ? p : p.slice(i + 1);
}
function dirname(p: string): string {
  const i = p.lastIndexOf('/');
  return i < 0 ? '' : p.slice(0, i);
}

/** The inline-expanded body of a commit row: just the list of changed files
 *  (each expands to its diff). Commit metadata lives in the row's hover card. */
export function CommitFiles({
  commit,
  files,
  diffs,
  expandedFiles,
  wrapLines,
  splitView,
  onToggleFile,
}: {
  commit: CommitEntry;
  files: CommitFilesEntry | undefined;
  diffs: Map<string, CommitDiffEntry>;
  expandedFiles: Set<string>;
  wrapLines: boolean;
  splitView: boolean;
  onToggleFile: (commitId: string, path: string) => void;
}) {
  return (
    <div className="border-t border-border/50 bg-black/20">
      {!files || files.loading ? (
        <div className="px-3 py-2 text-xs text-muted-foreground font-mono">Loading…</div>
      ) : files.error ? (
        <div className="px-3 py-2 text-xs text-muted-foreground font-mono">
          Could not load files ({files.error})
        </div>
      ) : (
        files.result?.files.map((f) => {
          const key = fileKey(commit.id, f.path);
          const open = expandedFiles.has(key);
          const diff = diffs.get(key);
          return (
            <div key={f.path} className="border-t border-border/40">
              <button
                type="button"
                onClick={() => onToggleFile(commit.id, f.path)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/30"
              >
                {open ? (
                  <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                )}
                <span className="text-xs font-mono truncate flex-1" title={f.path}>
                  {basename(f.path)}
                </span>
                {dirname(f.path) && (
                  <span className="text-[10px] font-mono text-muted-foreground truncate max-w-[35%]">
                    {dirname(f.path)}
                  </span>
                )}
                <span className="text-[10px] font-mono">
                  <span className="text-emerald-400">+{f.additions}</span>
                  <span className="ml-1 text-red-400">-{f.deletions}</span>
                </span>
              </button>
              {open && (
                <DiffView
                  result={diff?.result ?? null}
                  loading={diff?.loading ?? true}
                  error={diff?.error ?? null}
                  path={f.path}
                  wrapLines={wrapLines}
                  splitView={splitView}
                />
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
