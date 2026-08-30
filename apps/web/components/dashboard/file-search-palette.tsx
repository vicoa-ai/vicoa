'use client';

/**
 * FileSearchPalette — the ⌘P "quick open a file" overlay (VS Code's ⌘P).
 *
 * A modal sibling of the ⌘K {@link SearchPalette}, but scoped to one session's
 * workspace: it fuzzy-searches the live project file index (the same list the
 * `@`-mention autocomplete and the Files panel search use) and opens the chosen
 * file in the files/git panel. Ranking is client-side (fzf-style subsequence
 * match via `rankFileMatches`); the index itself comes off the session's daemon
 * through `useFileMentions`, so this is only meaningful while the machine is
 * online — the instance page gates the ⌘P shortcut on that.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFileMentions } from '@/lib/hooks/use-file-mentions';
import { rankFileMatches } from '@/components/files-git-panel/file-search';
import { FileTypeIcon } from '@/components/files-git-panel/file-type-icon';

const RESULT_CAP = 200;

interface FileSearchPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Machine hosting the project; drives the live index fetch. */
  machineId: string | null;
  /** Absolute project root — the key the file index is cached under. */
  projectPath: string | undefined;
  /** Open the picked file (project-relative path) in the files panel. */
  onOpenFile: (path: string) => void;
}

interface FileRow {
  path: string;
  /** Character indices into `path` that the query matched, for highlighting. */
  positions: number[];
}

function splitPath(path: string): { base: string; dir: string } {
  const slash = path.lastIndexOf('/');
  if (slash < 0) return { base: path, dir: '' };
  return { base: path.slice(slash + 1), dir: path.slice(0, slash) };
}

/**
 * Render `text` with the characters at `indices` emphasised — shows which
 * characters the fuzzy query matched. Mirrors the Files panel's highlighter.
 */
function HighlightChars({ text, indices }: { text: string; indices: Set<number> }) {
  if (indices.size === 0) return <>{text}</>;
  const nodes: React.ReactNode[] = [];
  let run = '';
  let runMatched = false;
  const flush = (key: number) => {
    if (!run) return;
    nodes.push(
      runMatched ? (
        <span key={key} className="font-semibold text-foreground">
          {run}
        </span>
      ) : (
        <React.Fragment key={key}>{run}</React.Fragment>
      ),
    );
    run = '';
  };
  for (let i = 0; i < text.length; i++) {
    const matched = indices.has(i);
    if (matched !== runMatched && run) flush(i);
    runMatched = matched;
    run += text[i];
  }
  flush(text.length);
  return <>{nodes}</>;
}

export function FileSearchPalette({
  open,
  onOpenChange,
  machineId,
  projectPath,
  onOpenFile,
}: FileSearchPaletteProps) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // Only fetch the (potentially large) index while the palette is open.
  const { files, isLoading } = useFileMentions({
    projectPath,
    machineId,
    enabled: open,
  });

  // The index lists folders (trailing slash) ahead of files for `@`-mentions;
  // a file finder can't open a folder, so drop them.
  const paths = useMemo(
    () => files.map((f) => f.path).filter((p) => !p.endsWith('/')),
    [files],
  );
  const trimmed = query.trim();

  // Empty query shows the "type to search" hint rather than an arbitrary slice
  // of the index — there's no recency signal that would make a default list
  // meaningful, so ranking only kicks in once the user types.
  const rows = useMemo<FileRow[]>(() => {
    if (!trimmed) return [];
    return rankFileMatches(paths, trimmed, RESULT_CAP).map((m) => ({
      path: m.path,
      positions: m.positions,
    }));
  }, [paths, trimmed]);

  // Reset transient state whenever the palette closes.
  useEffect(() => {
    if (open) return;
    setQuery('');
    setActiveIndex(0);
  }, [open]);

  // Keep the active row in range as the result set changes under it.
  useEffect(() => {
    setActiveIndex((current) => (rows.length === 0 ? 0 : Math.min(current, rows.length - 1)));
  }, [rows]);

  useEffect(() => {
    const row = listRef.current?.querySelector(`[data-file-index="${activeIndex}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  // Capture-phase Escape so the palette closes ahead of other overlay handlers.
  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      onOpenChange(false);
    };
    document.addEventListener('keydown', onEsc, true);
    return () => document.removeEventListener('keydown', onEsc, true);
  }, [open, onOpenChange]);

  const pick = useCallback(
    (path: string) => {
      onOpenChange(false);
      onOpenFile(path);
    },
    [onOpenChange, onOpenFile],
  );

  const onInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((current) => (rows.length === 0 ? 0 : (current + 1) % rows.length));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((current) =>
          rows.length === 0 ? 0 : (current - 1 + rows.length) % rows.length,
        );
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const row = rows[activeIndex];
        if (row) pick(row.path);
      }
    },
    [rows, activeIndex, pick],
  );

  if (!open) return null;

  const showIndexing = isLoading && paths.length === 0;
  const showTypeHint = !showIndexing && !trimmed;
  const showNoMatches = !showIndexing && !!trimmed && rows.length === 0;

  return (
    <div className="fixed inset-0 z-50">
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search files"
        className="fixed left-1/2 top-[15%] w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="Search files by name…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
          />
          <kbd className="hidden shrink-0 rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline-block">
            esc
          </kbd>
        </div>

        <div
          ref={listRef}
          className="custom-scrollbar max-h-[min(400px,50vh)] overflow-y-auto overflow-x-hidden p-2"
        >
          {showIndexing && (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Indexing files…
            </div>
          )}

          {showTypeHint && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              Type to search for files
            </div>
          )}

          {showNoMatches && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              No matching files.
            </div>
          )}

          {rows.map((row, i) => {
            const active = activeIndex === i;
            const { base, dir } = splitPath(row.path);
            const baseStart = row.path.length - base.length;
            // Positions index the full path; shift the basename hits local.
            const baseIndices = new Set(
              row.positions.filter((p) => p >= baseStart).map((p) => p - baseStart),
            );
            return (
              <button
                key={row.path}
                type="button"
                data-file-index={i}
                title={row.path}
                onMouseMove={() => setActiveIndex(i)}
                onClick={() => pick(row.path)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm outline-none cursor-pointer',
                  active && 'bg-accent',
                )}
              >
                <FileTypeIcon fileName={base} size={16} />
                <span className="min-w-0 flex-1 truncate">
                  <HighlightChars text={base} indices={baseIndices} />
                </span>
                {dir && (
                  <span className="min-w-0 max-w-[45%] shrink-0 truncate pl-3 text-right text-xs text-muted-foreground/70">
                    {dir}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3 border-t px-4 py-2 text-[11px] text-muted-foreground">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
        </div>
      </div>
    </div>
  );
}
