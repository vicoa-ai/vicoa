'use client';

import { useMemo } from 'react';
import hljs from 'highlight.js';
import type { DiffHunk, GitDiffResult } from './rpc';
import { hunkToRows, type DiffRow } from './diff-lines';
import { alignHunk, type SplitPair } from './diff-align';
import { languageForFile } from './file-icon';
import { SCROLL_STYLE } from './styles';
import { diffLineBackgroundClass } from '@/components/ui/message-markdown-utils';

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

/** Renders a single file's diff (hunks, unified or split) with the shared
 *  loading / error / binary / empty states. Used by the working-tree Changes
 *  tab and the commit-history file diffs alike. */
export function DiffView({
  result,
  loading,
  error,
  path,
  wrapLines,
  splitView,
}: {
  result: GitDiffResult | null;
  loading: boolean;
  error: string | null;
  path: string;
  wrapLines: boolean;
  splitView: boolean;
}) {
  if (loading) {
    return (
      <div className="p-3 space-y-2 animate-pulse">
        <div className="h-3 w-48 rounded-full bg-muted" />
        <div className="h-3 w-32 rounded-full bg-muted/70" />
        <div className="h-3 w-40 rounded-full bg-muted/50" />
        <div className="h-3 w-36 rounded-full bg-muted/70" />
        <div className="h-3 w-44 rounded-full bg-muted" />
        <div className="h-3 w-28 rounded-full bg-muted/50" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="px-3 py-4 text-xs text-muted-foreground font-mono">
        Could not load diff ({error})
      </div>
    );
  }
  if (!result) {
    return <div className="px-3 py-4 text-xs text-muted-foreground font-mono">Loading…</div>;
  }

  if (result.is_binary) {
    return (
      <div className="px-3 py-3 text-xs font-mono text-muted-foreground">
        Binary file changed
        {result.old_size !== undefined &&
          result.new_size !== undefined &&
          ` · ${result.old_size} B → ${result.new_size} B`}
      </div>
    );
  }

  if (result.hunks.length === 0) {
    return <div className="px-3 py-3 text-xs font-mono text-muted-foreground">No changes</div>;
  }

  const language = languageForFile(basename(path));

  return (
    <div>
      {result.hunks.map((hunk, idx) => (
        <HunkRender
          key={idx}
          hunk={hunk}
          language={language}
          wrapLines={wrapLines}
          splitView={splitView}
        />
      ))}
      {result.truncated && (
        <div className="bg-amber-100 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 text-[11px] px-3 py-1.5 font-mono">
          Diff truncated — open on desktop for the rest.
        </div>
      )}
    </div>
  );
}

function HunkRender({
  hunk,
  language,
  wrapLines,
  splitView,
}: {
  hunk: DiffHunk;
  language: string | null;
  wrapLines: boolean;
  splitView: boolean;
}) {
  const aligned = useMemo(() => alignHunk(hunkToRows(hunk)), [hunk]);
  return (
    <div>
      <div className="px-3 py-1 text-[10px] font-mono text-muted-foreground bg-muted/30">
        {hunk.header}
      </div>
      {splitView ? (
        <SplitHunkBody pairs={aligned.split} language={language} wrapLines={wrapLines} />
      ) : (
        <UnifiedHunkBody rows={aligned.unified} language={language} wrapLines={wrapLines} />
      )}
    </div>
  );
}

function highlightLine(content: string, language: string | null): string | null {
  if (!language || !hljs.getLanguage(language)) return null;
  try {
    return hljs.highlight(content, { language, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
}

function lineClass(kind: DiffRow['kind']): string {
  return diffLineBackgroundClass(kind);
}

/** The brighter background for the words that actually changed within a paired
 *  add/remove line — layered over the line's lighter tint from `lineClass`. */
function segmentClass(kind: DiffRow['kind']): string {
  if (kind === 'add') return 'bg-green-200/80 dark:bg-green-700/60 rounded-[2px]';
  if (kind === 'remove') return 'bg-red-200/80 dark:bg-red-700/60 rounded-[2px]';
  return '';
}

/** Line body: word-level highlighted spans when the row was paired (`segments`),
 *  otherwise the syntax-highlighted whole line. */
function LineContent({ row, language }: { row: DiffRow; language: string | null }) {
  if (row.segments) {
    return (
      <>
        {row.segments.map((seg, i) =>
          seg.changed ? (
            <span key={i} className={segmentClass(row.kind)}>
              {seg.text}
            </span>
          ) : (
            <span key={i}>{seg.text}</span>
          ),
        )}
      </>
    );
  }
  const html = highlightLine(row.content, language);
  return html ? (
    <span dangerouslySetInnerHTML={{ __html: html || '&nbsp;' }} />
  ) : (
    <span>{row.content || ' '}</span>
  );
}

function UnifiedHunkBody({
  rows,
  language,
  wrapLines,
}: {
  rows: DiffRow[];
  language: string | null;
  wrapLines: boolean;
}) {
  return (
    <div className="font-mono text-[11px]">
      {rows.map((row, i) => (
        <div key={i} className={`flex ${lineClass(row.kind)}`}>
          <div className="w-10 min-w-10 text-right pr-1 select-none text-muted-foreground/60 tabular-nums">
            {row.oldNo ?? ''}
          </div>
          <div className="w-10 min-w-10 text-right pr-2 select-none text-muted-foreground/60 tabular-nums">
            {row.newNo ?? ''}
          </div>
          <div className="w-4 text-center select-none text-muted-foreground/60">
            {row.kind === 'add' ? '+' : row.kind === 'remove' ? '-' : ' '}
          </div>
          <div
            className={`flex-1 ${wrapLines ? 'whitespace-pre-wrap break-words' : `whitespace-pre overflow-x-auto ${SCROLL_STYLE}`}`}
          >
            <LineContent row={row} language={language} />
          </div>
        </div>
      ))}
    </div>
  );
}

function SplitHunkBody({
  pairs,
  language,
  wrapLines,
}: {
  pairs: SplitPair[];
  language: string | null;
  wrapLines: boolean;
}) {
  return (
    <div className="font-mono text-[11px] flex">
      <div className="flex-1 min-w-0 border-r border-border/40">
        {pairs.map((p, idx) => (
          <SplitCell key={`l${idx}`} row={p.left} side="old" language={language} wrapLines={wrapLines} />
        ))}
      </div>
      <div className="flex-1 min-w-0">
        {pairs.map((p, idx) => (
          <SplitCell key={`r${idx}`} row={p.right} side="new" language={language} wrapLines={wrapLines} />
        ))}
      </div>
    </div>
  );
}

function SplitCell({
  row,
  side,
  language,
  wrapLines,
}: {
  row: DiffRow | null;
  side: 'old' | 'new';
  language: string | null;
  wrapLines: boolean;
}) {
  if (!row) return <div className="h-[1em] bg-muted/20" />;
  return (
    <div className={`flex ${lineClass(row.kind)}`}>
      <div className="w-10 min-w-10 text-right pr-2 select-none text-muted-foreground/60 tabular-nums">
        {side === 'old' ? (row.oldNo ?? '') : (row.newNo ?? '')}
      </div>
      <div
        className={`flex-1 ${wrapLines ? 'whitespace-pre-wrap break-words' : `whitespace-pre overflow-x-auto ${SCROLL_STYLE}`}`}
      >
        <LineContent row={row} language={language} />
      </div>
    </div>
  );
}
