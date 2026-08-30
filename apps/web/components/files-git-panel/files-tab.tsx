'use client';

import * as React from 'react';
import { ChevronRight, Folder, FolderOpen, Loader2, Search, Terminal, WifiOff, X } from 'lucide-react';
import { flattenTree, type TreeRow } from './tree';
import { FileTypeIcon } from './file-type-icon';
import { rankFileMatches } from './file-search';
import type { FileEntry } from './rpc';
import { SCROLL_STYLE } from './styles';

interface FilesTabProps {
  listings: Map<string, FileEntry[] | null>;
  expanded: Set<string>;
  rootError: string | null;
  onToggleDir: (path: string) => void;
  /** Single click opens a preview tab; `{ newTab: true }` (double click) opens
   * a permanent tab. */
  onOpenFile: (path: string, opts?: { newTab?: boolean }) => void;
  /** Project-relative paths of files with unsaved edits — shown with a dot. */
  dirtyPaths?: Set<string>;
  /** Project-relative path → git status letter, coloring changed file rows. */
  statuses?: Map<string, string>;
  /** Folders containing a git change — tinted so changes show while collapsed. */
  changedDirs?: Set<string>;
}

/** Text color for a git status letter (VSCode convention). `''` = no change. */
export function gitStatusColor(status: string | undefined): string {
  switch (status) {
    case 'A':
    case '??':
      return 'text-emerald-600 dark:text-emerald-400';
    case 'M':
    case 'T':
      return 'text-amber-600 dark:text-amber-400';
    case 'D':
      return 'text-red-600 dark:text-red-400';
    case 'R':
    case 'C':
      return 'text-sky-600 dark:text-sky-400';
    case 'U':
      return 'text-orange-600 dark:text-orange-400';
    default:
      return '';
  }
}

/** The single-letter badge shown at the row's right edge (untracked → U). */
export function gitStatusLetter(status: string): string {
  return status === '??' ? 'U' : status.charAt(0);
}

function rowIcon(row: TreeRow): React.ReactElement {
  if (row.type === 'dir') {
    return row.expanded ? <FolderOpen className="h-4 w-4 text-muted-foreground" /> : <Folder className="h-4 w-4 text-muted-foreground" />;
  }
  return <FileTypeIcon fileName={row.name} size={16} />;
}

const DAEMON_UNREACHABLE = new Set(['target_disconnected', 'timeout', 'unknown', 'rpc_failed']);

function IconCard({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center gap-3">
      <div className="text-muted-foreground">{icon}</div>
      <div className="text-sm text-muted-foreground font-mono leading-relaxed">{children}</div>
    </div>
  );
}

function errorCard(code: string, verb: 'browse files' | 'see git changes') {
  if (DAEMON_UNREACHABLE.has(code) || code === 'no_handler') {
    return (
      <IconCard icon={<Terminal className="h-8 w-8" />}>
        Run <code className="px-1.5 py-0.5 rounded bg-muted text-foreground">vicoa daemon</code> to
        <br />
        connect your machine to {verb}.
      </IconCard>
    );
  }
  if (code === 'not_connected') {
    return (
      <IconCard icon={<WifiOff className="h-8 w-8" />}>
        Not connected, reconnecting…
      </IconCard>
    );
  }
  const messages: Record<string, string> = {
    path_not_found: 'Project directory not found.',
    permission_denied: 'Permission denied.',
    outside_project: 'Path is outside the project.',
  };
  return (
    <div className="flex items-center justify-center h-full text-sm text-muted-foreground font-mono px-4 text-center">
      {messages[code] || `Could not load files (${code}).`}
    </div>
  );
}

function OfflineBanner({ code }: { code: string }) {
  const message = DAEMON_UNREACHABLE.has(code)
    ? 'Machine offline — showing last loaded files.'
    : code === 'not_connected'
      ? 'Not connected — showing last loaded files.'
      : `Could not refresh (${code}) — showing last loaded files.`;
  return (
    <div className="px-3 py-1.5 text-[11px] font-mono text-amber-900 dark:text-amber-200 bg-amber-100/70 dark:bg-amber-950/30 border-b border-amber-200/60 dark:border-amber-900/40">
      {message}
    </div>
  );
}

/** Search row pinned above the tree: filter the project index by file name. */
export function FileSearchRow({
  query,
  onChange,
}: {
  query: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="flex flex-shrink-0 items-center gap-1.5 border-b border-border/60 px-3 py-1.5">
      <Search className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
      <input
        value={query}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && query) {
            event.stopPropagation();
            onChange('');
          }
        }}
        placeholder="Search files"
        data-file-search
        className="min-w-0 flex-1 bg-transparent text-xs font-mono outline-none placeholder:text-muted-foreground/50"
      />
      {query && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange('')}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function fileIconFor(name: string): React.ReactElement {
  return <FileTypeIcon fileName={name} size={16} />;
}

/**
 * Renders `text` with the characters at `indices` (relative to `text`)
 * emphasised — used to show which characters a fuzzy query matched.
 */
function HighlightedName({ text, indices }: { text: string; indices: Set<number> }) {
  if (indices.size === 0) return <>{text}</>;
  const nodes: React.ReactNode[] = [];
  let run = '';
  let runMatched = false;
  const flush = (key: number) => {
    if (!run) return;
    nodes.push(
      runMatched ? (
        <span key={key} className="text-foreground font-semibold">
          {run}
        </span>
      ) : (
        <span key={key}>{run}</span>
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

/** Flat result list for a filename search over the project index. */
export function FileSearchResults({
  files,
  query,
  loading,
  onOpenFile,
}: {
  files: string[];
  query: string;
  loading: boolean;
  onOpenFile: (path: string, opts?: { newTab?: boolean }) => void;
}) {
  const matches = React.useMemo(() => rankFileMatches(files, query), [files, query]);

  if (loading && files.length === 0) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground font-mono">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Indexing files…
      </div>
    );
  }
  if (matches.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground font-mono">
        No matching files
      </div>
    );
  }
  return (
    <div className={`min-h-0 flex-1 overflow-auto py-1 ${SCROLL_STYLE}`}>
      {matches.map(({ path, positions }) => {
        const slash = path.lastIndexOf('/');
        const baseStart = slash + 1;
        const base = slash < 0 ? path : path.slice(baseStart);
        const dir = slash < 0 ? '' : path.slice(0, slash);
        // Positions are into the full path; shift the basename hits local.
        const baseIndices = new Set(
          positions.filter((p) => p >= baseStart).map((p) => p - baseStart),
        );
        return (
          <button
            key={path}
            type="button"
            onClick={() => onOpenFile(path)}
            onDoubleClick={() => onOpenFile(path, { newTab: true })}
            title={path}
            className="flex w-full items-center gap-2 px-3 py-1 text-left text-xs font-mono hover:bg-muted/40"
          >
            {fileIconFor(base)}
            <span className="truncate">
              <HighlightedName text={base} indices={baseIndices} />
            </span>
            {dir && <span className="min-w-0 truncate text-muted-foreground/60">{dir}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function FilesTab({
  listings,
  expanded,
  rootError,
  onToggleDir,
  onOpenFile,
  dirtyPaths,
  statuses,
  changedDirs,
}: FilesTabProps) {
  const rootListing = listings.get('');
  const hasCachedRoot = Array.isArray(rootListing);

  // Error AND no cached content → full-screen error card.
  if (rootError && !hasCachedRoot) {
    return errorCard(rootError, 'browse files');
  }

  if (rootListing === undefined || rootListing === null) {
    return (
      <div className="p-4 space-y-4 animate-pulse">
        <div className="h-2.5 w-40 rounded-full bg-muted" />
        <div className="h-2.5 w-32 rounded-full bg-muted/70" />
        <div className="h-2.5 w-44 rounded-full bg-muted" />
        <div className="h-2.5 w-28 rounded-full bg-muted/70" />
        <div className="h-2.5 w-48 rounded-full bg-muted/50" />
        <div className="h-2.5 w-36 rounded-full bg-muted/70" />
        <div className="h-2.5 w-40 rounded-full bg-muted" />
        <div className="h-2.5 w-24 rounded-full bg-muted/50" />
        <div className="h-2.5 w-44 rounded-full bg-muted/70" />
        <div className="h-2.5 w-32 rounded-full bg-muted" />
        <div className="h-2.5 w-48 rounded-full bg-muted/50" />
        <div className="h-2.5 w-28 rounded-full bg-muted/70" />
        <div className="h-2.5 w-40 rounded-full bg-muted/50" />
        <div className="h-2.5 w-36 rounded-full bg-muted" />
      </div>
    );
  }

  const rows = flattenTree(listings, expanded);
  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground font-mono">
        Empty directory
      </div>
    );
  }

  return (
    <div className={`h-full overflow-auto py-2 ${SCROLL_STYLE}`}>
      {rootError && <OfflineBanner code={rootError} />}
      {rows.map((row) => {
        // Changed files get the status color + a right-edge letter; folders that
        // contain a change get a subtle tint so it shows while collapsed.
        const fileStatus = row.type === 'file' ? statuses?.get(row.path) : undefined;
        const nameColor =
          fileStatus !== undefined
            ? gitStatusColor(fileStatus)
            : row.type === 'dir' && changedDirs?.has(row.path)
              ? 'text-amber-700/80 dark:text-amber-300/70'
              : '';
        return (
          <button
            key={row.path}
            type="button"
            onClick={() => row.type === 'dir' ? onToggleDir(row.path) : onOpenFile(row.path)}
            onDoubleClick={
              row.type === 'file' ? () => onOpenFile(row.path, { newTab: true }) : undefined
            }
            className="flex items-center w-full px-3 py-1 text-xs font-mono hover:bg-muted/40 text-left"
            style={{ paddingLeft: 12 + row.depth * 14 }}
          >
            {row.type === 'dir' ? (
              <ChevronRight
                className={`h-3 w-3 text-muted-foreground mr-1 transition-transform ${
                  row.expanded ? 'rotate-90' : ''
                }`}
              />
            ) : (
              <span className="inline-block w-3 mr-1" />
            )}
            <span className="mr-2">{rowIcon(row)}</span>
            <span className={`truncate flex-1 ${nameColor}`}>{row.name}</span>
            {fileStatus !== undefined && (
              <span className={`ml-2 flex-shrink-0 text-[10px] ${gitStatusColor(fileStatus)}`}>
                {gitStatusLetter(fileStatus)}
              </span>
            )}
            {row.type === 'file' && dirtyPaths?.has(row.path) && (
              <span className="ml-2 h-1 w-1 flex-shrink-0 rounded-full bg-foreground/60" />
            )}
            {row.type === 'dir' && row.loading && (
              <span className="ml-2 inline-block h-3 w-3 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground animate-spin" />
            )}
          </button>
        );
      })}
    </div>
  );
}
