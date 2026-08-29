'use client';

import { useEffect, useMemo, useRef } from 'react';
import dynamic from 'next/dynamic';
import hljs from 'highlight.js';
import type { FileViewState } from './use-files-tab';
import type { DiffNav } from './diff-editor';
import { isMarkdownPath, languageForFile } from './file-icon';
import { MarkdownPreview } from './markdown-preview';
import { SCROLL_STYLE } from './styles';
import { SCROLL_PERSIST_MS } from './cm-scroll';

// CodeMirror is loaded only when a file is actually edited, keeping it out of
// the panel's initial bundle.
const FileEditor = dynamic(() => import('./file-editor').then((m) => m.FileEditor), {
  ssr: false,
  loading: () => <div className="h-full w-full" style={{ backgroundColor: '#171717' }} />,
});

// The @codemirror/merge diff surface is likewise loaded only when a tab enters
// diff mode.
const DiffEditor = dynamic(() => import('./diff-editor').then((m) => m.DiffEditor), {
  ssr: false,
  loading: () => <div className="h-full w-full" style={{ backgroundColor: '#171717' }} />,
});

// The live-preview markdown editor (CodeMirror + syntax-hiding decorations) is
// loaded only when an editable markdown file is shown in formatted mode.
const MarkdownLiveEditor = dynamic(
  () => import('./markdown-live-editor').then((m) => m.MarkdownLiveEditor),
  {
    ssr: false,
    loading: () => <div className="h-full w-full" style={{ backgroundColor: '#171717' }} />,
  },
);

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

function ErrorMessage({ code }: { code: string }) {
  const messageByCode: Record<string, string> = {
    path_not_found: 'File no longer exists',
    permission_denied: 'Permission denied',
    outside_project: 'Path is outside the project',
    too_large: 'File is too large to preview',
    no_handler: 'Update the daemon on this machine to browse files',
    target_disconnected: 'Machine is offline',
    timeout: 'Request timed out',
    not_connected: 'Not connected',
  };
  return (
    <div className="flex items-center justify-center h-full text-sm text-muted-foreground font-mono px-4 text-center">
      {messageByCode[code] || `Could not load file (${code})`}
    </div>
  );
}

export function FileViewer({
  state,
  wrap,
  markdownSource = false,
  diffSideBySide = false,
  onDraftChange,
  onSave,
  onScrollAnchor,
  onDiffNav,
}: {
  state: FileViewState;
  wrap: boolean;
  markdownSource?: boolean;
  /** In diff mode, lay the editor out as two side-by-side panes instead of the
   * single inline diff. */
  diffSideBySide?: boolean;
  onDraftChange?: (content: string) => void;
  onSave?: () => void;
  /** Report the top scroll anchor of the current surface so the panel can
   * remember it per tab. Wired for the editor, diff and read-only source
   * surfaces; rendered previews (no line mapping) don't participate. */
  onScrollAnchor?: (path: string, line: number, offset: number) => void;
  /** Publishes the diff surface's change-navigation handle to the panel (only
   * meaningful in diff mode; `null` on any other surface / teardown). */
  onDiffNav?: (nav: DiffNav | null) => void;
}) {
  if (state.loading) {
    return (
      <div className="h-full p-3 space-y-2 animate-pulse">
        <div className="h-3 w-48 rounded-full bg-muted" />
        <div className="h-3 w-64 rounded-full bg-muted/70" />
        <div className="h-3 w-40 rounded-full bg-muted/50" />
        <div className="h-3 w-56 rounded-full bg-muted/70" />
        <div className="h-3 w-44 rounded-full bg-muted" />
        <div className="h-3 w-52 rounded-full bg-muted/50" />
        <div className="h-3 w-40 rounded-full bg-muted/70" />
        <div className="h-3 w-60 rounded-full bg-muted" />
        <div className="h-3 w-36 rounded-full bg-muted/70" />
        <div className="h-3 w-48 rounded-full bg-muted/50" />
      </div>
    );
  }
  if (state.error) {
    return <ErrorMessage code={state.error} />;
  }
  const result = state.result;
  if (!result) return <ErrorMessage code="unknown" />;

  if (result.is_binary && result.encoding === 'base64') {
    const ext = state.path.split('.').pop()?.toLowerCase() ?? '';
    const mime =
      ext === 'png' ? 'image/png'
      : ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg'
      : ext === 'gif' ? 'image/gif'
      : ext === 'webp' ? 'image/webp'
      : 'application/octet-stream';
    return (
      <div className={`flex flex-col items-center justify-center h-full p-4 gap-3 overflow-auto ${SCROLL_STYLE}`}>
        <img
          src={`data:${mime};base64,${result.content}`}
          alt={basename(state.path)}
          className="max-w-full max-h-[90%] object-contain"
        />
        <div className="text-xs text-muted-foreground font-mono">{formatBytes(result.size)}</div>
      </div>
    );
  }

  if (result.is_binary) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-sm text-muted-foreground font-mono gap-2">
        <span>Binary file — cannot preview</span>
        <span className="text-xs">{formatBytes(result.size)}</span>
      </div>
    );
  }

  const isSvg = state.path.toLowerCase().endsWith('.svg');
  if (isSvg) {
    return (
      <div className={`flex flex-col items-center justify-center h-full p-4 gap-3 overflow-auto ${SCROLL_STYLE}`}>
        <img
          src={`data:image/svg+xml,${encodeURIComponent(result.content)}`}
          alt={basename(state.path)}
          className="max-w-full max-h-[90%] object-contain"
        />
        <div className="text-xs text-muted-foreground font-mono">{formatBytes(result.size)}</div>
      </div>
    );
  }

  // Diff mode: the editable working-tree-vs-HEAD diff. Takes precedence over the
  // markdown preview (a change is shown as a source diff, not rendered). Falls
  // through to the editor/source surfaces below when the baseline can't back a
  // diff — while loading it shows a skeleton; on error (binary/truncated/old
  // daemon) it just renders the editor so editing keeps working, and the
  // read-only inline diff stays available in the Changes tab.
  if (state.viewMode === 'diff') {
    const base = state.base;
    if (base == null || base.loading) {
      return (
        <div className="h-full p-3 space-y-2 animate-pulse">
          <div className="h-3 w-40 rounded-full bg-muted" />
          <div className="h-3 w-56 rounded-full bg-muted/70" />
          <div className="h-3 w-32 rounded-full bg-muted/50" />
          <div className="h-3 w-48 rounded-full bg-muted/70" />
          <div className="h-3 w-44 rounded-full bg-muted" />
        </div>
      );
    }
    if (base.error === null && state.editing && state.draft != null) {
      return (
        <DiffEditor
          path={state.path}
          original={base.content}
          value={state.draft}
          sideBySide={diffSideBySide}
          wrap={wrap}
          initialScrollLine={state.scrollLine}
          initialScrollOffset={state.scrollOffset}
          onScrollAnchor={onScrollAnchor}
          onDiffNav={onDiffNav}
          onChange={onDraftChange ?? (() => {})}
          onSave={onSave ?? (() => {})}
        />
      );
    }
    // else fall through to the editor (editable) / read-only source below.
  }

  if (isMarkdownPath(basename(state.path)) && !markdownSource) {
    // Editable markdown → the live-preview editor: edit the rendered document in
    // place, no source↔preview toggle. The buffer stays exact markdown, so the
    // same draft/save engine drives it. Non-editable markdown (truncated file /
    // old daemon → no draft) falls back to the read-only rendered preview.
    if (state.editing && state.draft != null) {
      return (
        <MarkdownLiveEditor
          path={state.path}
          value={state.draft}
          wrap={wrap}
          initialScrollLine={state.scrollLine}
          initialScrollOffset={state.scrollOffset}
          onScrollAnchor={onScrollAnchor}
          onChange={onDraftChange ?? (() => {})}
          onSave={onSave ?? (() => {})}
        />
      );
    }
    return (
      <div className="h-full overflow-auto custom-scrollbar">
        <MarkdownPreview content={result.content} />
        {result.truncated && (
          <div className="sticky bottom-0 left-0 right-0 bg-amber-100 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 text-xs px-3 py-2 text-center font-mono">
            Showing first 1.00 MB of {formatBytes(result.size)}
          </div>
        )}
      </div>
    );
  }

  // Source view. In edit mode this is the CodeMirror editor over the draft;
  // otherwise the read-only highlighted table.
  if (state.editing) {
    return (
      <FileEditor
        path={state.path}
        value={state.draft ?? result.content}
        wrap={wrap}
        initialScrollLine={state.scrollLine}
        initialScrollOffset={state.scrollOffset}
        onScrollAnchor={onScrollAnchor}
        onChange={onDraftChange ?? (() => {})}
        onSave={onSave ?? (() => {})}
      />
    );
  }

  return (
    <TextFileBody
      result={result}
      path={state.path}
      wrap={wrap}
      initialScrollLine={state.scrollLine}
      initialScrollOffset={state.scrollOffset}
      onScrollAnchor={onScrollAnchor}
    />
  );
}

function TextFileBody({
  result,
  path,
  wrap,
  initialScrollLine,
  initialScrollOffset,
  onScrollAnchor,
}: {
  result: NonNullable<FileViewState['result']>;
  path: string;
  wrap: boolean;
  initialScrollLine?: number;
  initialScrollOffset?: number;
  onScrollAnchor?: (path: string, line: number, offset: number) => void;
}) {
  const lines = result.content.split('\n');
  const language = languageForFile(basename(path));
  const scrollRef = useRef<HTMLDivElement>(null);
  const onScrollAnchorRef = useRef(onScrollAnchor);
  onScrollAnchorRef.current = onScrollAnchor;

  const highlighted = useMemo(() => {
    if (!language) return null;
    if (!hljs.getLanguage(language)) return null;
    try {
      return lines.map((line) => hljs.highlight(line, { language, ignoreIllegals: true }).value);
    } catch {
      return null;
    }
  }, [lines, language]);

  // Restore the last anchor for this file, then remember it as the user scrolls.
  // Keyed on `path` so switching files re-applies the new tab's anchor; the top
  // line is read from the row under the container's top edge (each row carries
  // its 1-based line via `data-line`), plus how far it's scrolled above.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (initialScrollLine && initialScrollLine > 1) {
      const row = el.querySelector<HTMLElement>(`[data-line="${initialScrollLine}"]`);
      if (row) {
        el.scrollTop =
          row.getBoundingClientRect().top -
          el.getBoundingClientRect().top +
          el.scrollTop +
          (initialScrollOffset ?? 0);
      }
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    let pending: { line: number; offset: number } | null = null;
    const readTopAnchor = (): { line: number; offset: number } | null => {
      const rect = el.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + 4, rect.top + 1);
      const rowEl = hit?.closest<HTMLElement>('[data-line]');
      const line = rowEl ? Number(rowEl.dataset.line) : NaN;
      if (!Number.isFinite(line)) return null;
      const offset = rowEl ? Math.max(0, Math.round(rect.top - rowEl.getBoundingClientRect().top)) : 0;
      return { line, offset };
    };
    const onScroll = () => {
      // Read on the current (still-old) DOM immediately; debounce only the report
      // so a scroll-then-switch flushes the right value for the right file.
      const anchor = readTopAnchor();
      if (anchor == null) return;
      pending = anchor;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (pending != null) {
          onScrollAnchorRef.current?.(path, pending.line, pending.offset);
          pending = null;
        }
      }, SCROLL_PERSIST_MS);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      clearTimeout(timer);
      el.removeEventListener('scroll', onScroll);
      if (pending != null) onScrollAnchorRef.current?.(path, pending.line, pending.offset);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  return (
    <div ref={scrollRef} className={`h-full overflow-auto font-mono text-xs ${SCROLL_STYLE}`}>
      <table className="w-full border-separate border-spacing-0">
        <tbody>
          {lines.map((line, idx) => (
            <tr key={idx} data-line={idx + 1}>
              <td className="w-[3.5rem] min-w-[3.5rem] text-right pr-3 select-none text-muted-foreground/70 sticky left-0 bg-[#171717] tabular-nums align-top">
                {idx + 1}
              </td>
              <td className={wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}>
                {highlighted ? (
                  <span
                    className="hljs-line"
                    dangerouslySetInnerHTML={{ __html: highlighted[idx] || '&nbsp;' }}
                  />
                ) : (
                  <span>{line || ' '}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.truncated && (
        <div className="sticky bottom-0 left-0 right-0 bg-amber-100 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 text-xs px-3 py-2 text-center font-mono">
          Showing first 1.00 MB of {formatBytes(result.size)}
        </div>
      )}
    </div>
  );
}
