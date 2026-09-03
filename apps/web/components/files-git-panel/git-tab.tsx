'use client';

import * as React from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Folder,
  FolderOpen,
  GitBranch,
  Loader2,
  Minus,
  Plus,
  Terminal,
  WifiOff,
  X,
} from 'lucide-react';
import type { DiffEntry, SubmoduleEntry } from './use-git-tab';
import type { GitStatusEntry, GitStatusResult } from './rpc';
import { buildChangesTree, type ChangesDirNode } from './changes-tree';
import { diffKey, submoduleFileKey } from './concurrency';
import { SCROLL_STYLE } from './styles';
import { DiffView } from './diff-view';

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

function dirname(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? '' : path.slice(0, i);
}

const DAEMON_UNREACHABLE_CODES = new Set(['target_disconnected', 'timeout', 'unknown', 'rpc_failed']);

function IconCard({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center gap-3">
      <div className="text-muted-foreground">{icon}</div>
      <div className="text-sm text-muted-foreground font-mono leading-relaxed">{children}</div>
    </div>
  );
}

function GitErrorBody({ code }: { code: string }) {
  if (DAEMON_UNREACHABLE_CODES.has(code) || code === 'no_handler') {
    return (
      <IconCard icon={<Terminal className="h-8 w-8" />}>
        Run <code className="px-1.5 py-0.5 rounded bg-muted text-foreground">vicoa daemon</code> to
        <br />
        connect your machine to see git changes.
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
  if (code === 'not_a_repo') {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground font-mono px-4 text-center">
        Not a git repository
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center h-full text-sm text-muted-foreground font-mono px-4 text-center">
      Could not load git status ({code})
    </div>
  );
}

function GitOfflineBanner({ code }: { code: string }) {
  const message = DAEMON_UNREACHABLE_CODES.has(code)
    ? 'Machine offline — showing last loaded status.'
    : code === 'not_connected'
      ? 'Not connected — showing last loaded status.'
      : `Could not refresh (${code}) — showing last loaded status.`;
  return (
    <div className="px-3 py-1.5 text-[11px] font-mono text-amber-900 dark:text-amber-200 bg-amber-100/70 dark:bg-amber-950/30 border-b border-amber-200/60 dark:border-amber-900/40">
      {message}
    </div>
  );
}

/** Everything the nested submodule view needs, bundled so the three levels of
 *  Section/DiffFileSection drilling stay readable. */
export interface SubmoduleView {
  enabled: boolean;
  submodules: Map<string, SubmoduleEntry>;
  submoduleDiffs: Map<string, DiffEntry>;
  expandedSubFiles: Set<string>;
  onToggleSubFile: (sub: string, file: string, staged: boolean) => void;
}

interface GitTabProps {
  status: GitStatusResult | null;
  statusLoading: boolean;
  statusError: string | null;
  diffs: Map<string, DiffEntry>;
  expanded: Set<string>;
  wrapLines: boolean;
  splitView: boolean;
  splitDiffEnabled: boolean;
  /** Render the sections as a folder tree instead of flat rows. */
  treeView: boolean;
  submoduleView: SubmoduleView;
  /** Paths with an in-flight stage/unstage — their row button shows a spinner. */
  pendingPaths: Set<string>;
  /** Last stage/unstage/commit failure (git's own message where available). */
  writeError: string | null;
  committing: boolean;
  commitMessage: string;
  onCommitMessageChange: (next: string) => void;
  onCommit: () => void;
  onDismissWriteError: () => void;
  onToggleExpand: (path: string, staged: boolean) => void;
  onStage: (path: string) => void;
  onUnstage: (path: string) => void;
  /** Open a changed file as an editable diff tab (the filename click). Absent →
   * the filename falls back to toggling the inline preview. */
  onOpenFile?: (path: string, opts?: { newTab?: boolean }) => void;
}

export function GitTab(props: GitTabProps) {
  const {
    status,
    statusLoading,
    statusError,
    diffs,
    expanded,
    wrapLines,
    splitView,
    splitDiffEnabled,
    treeView,
    submoduleView,
    pendingPaths,
    writeError,
    committing,
    commitMessage,
    onCommitMessageChange,
    onCommit,
    onDismissWriteError,
    onToggleExpand,
    onStage,
    onUnstage,
    onOpenFile,
  } = props;

  // Error AND no cached status → full-screen error card. Otherwise show cached
  // status with an offline banner on top.
  if (statusError && !status) return <GitErrorBody code={statusError} />;
  if (!status) {
    return (
      <div className="p-4 space-y-4 animate-pulse">
        <div className="h-2.5 w-48 rounded-full bg-muted" />
        <div className="h-2.5 w-32 rounded-full bg-muted/70" />
        <div className="h-2.5 w-40 rounded-full bg-muted/50" />
        <div className="h-2.5 w-36 rounded-full bg-muted/70" />
        <div className="h-2.5 w-44 rounded-full bg-muted" />
        <div className="h-2.5 w-28 rounded-full bg-muted/50" />
        <div className="h-2.5 w-40 rounded-full bg-muted/70" />
        <div className="h-2.5 w-36 rounded-full bg-muted" />
        <div className="h-2.5 w-48 rounded-full bg-muted/70" />
        <div className="h-2.5 w-32 rounded-full bg-muted/50" />
        <div className="h-2.5 w-44 rounded-full bg-muted/70" />
        <div className="h-2.5 w-28 rounded-full bg-muted" />
      </div>
    );
  }

  const totalChanges = status.staged.length + status.unstaged.length + status.untracked.length;
  const sectionShared = {
    diffs,
    expanded,
    wrapLines,
    splitView,
    splitDiffEnabled,
    treeView,
    submoduleView,
    pendingPaths,
    onToggle: onToggleExpand,
    onOpenFile,
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {statusError && <GitOfflineBanner code={statusError} />}
      {writeError && (
        <div className="flex items-start gap-2 border-b border-red-300 bg-red-100 px-3 py-1.5 text-[11px] font-mono text-red-900 flex-shrink-0 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
          <AlertTriangle className="mt-px h-3.5 w-3.5 flex-shrink-0" />
          <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{writeError}</span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={onDismissWriteError}
            className="flex-shrink-0 text-red-900/70 hover:text-red-900 dark:text-red-200/70 dark:hover:text-red-100"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
      {totalChanges === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground font-mono">
          Workspace has no changes
        </div>
      ) : (
        <>
          {/* The commit box appears once something is staged (the + hover
              action) — no dead disabled UI while there's nothing to commit. */}
          {status.staged.length > 0 && (
            <CommitBox
              message={commitMessage}
              onChange={onCommitMessageChange}
              committing={committing}
              onCommit={onCommit}
            />
          )}
          <div className={`min-h-0 flex-1 overflow-auto ${SCROLL_STYLE}`}>
            <Section title="Staged" entries={status.staged} staged={true}
              {...sectionShared} onStageAction={onUnstage}
            />
            <Section title="Unstaged" entries={status.unstaged} staged={false}
              {...sectionShared} onStageAction={onStage}
            />
            <Section title="Untracked" entries={status.untracked} staged={false}
              {...sectionShared} onStageAction={onStage}
            />
          </div>
        </>
      )}
    </div>
  );
}

/** Commit-message box + button, pinned above the sections. Only rendered while
 *  something is staged. ⌘/Ctrl+Enter in the textarea is the keyboard path. */
function CommitBox({
  message,
  onChange,
  committing,
  onCommit,
}: {
  message: string;
  onChange: (next: string) => void;
  committing: boolean;
  onCommit: () => void;
}) {
  const canCommit = message.trim().length > 0 && !committing;
  return (
    <div className="flex flex-shrink-0 flex-col gap-1.5 border-b border-border px-3 py-2">
      <textarea
        value={message}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && canCommit) {
            e.preventDefault();
            onCommit();
          }
        }}
        placeholder="Commit message"
        rows={message.includes('\n') || message.length > 60 ? 3 : 1}
        className="w-full resize-none rounded bg-foreground/[0.06] px-2 py-1.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 focus:bg-foreground/[0.09] focus:outline-none"
      />
      <button
        type="button"
        disabled={!canCommit}
        onClick={onCommit}
        className="flex items-center justify-center gap-1.5 rounded border border-border bg-foreground/[0.06] px-2 py-1 text-xs font-mono text-foreground hover:bg-foreground/[0.1] disabled:cursor-not-allowed disabled:opacity-40"
      >
        {committing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        Commit
      </button>
    </div>
  );
}

/** Inline branch summary (icon + branch + ahead/behind + upstream). Presentational;
 *  the panel renders it inside the Changes toolbar row. Null status → placeholder. */
export function BranchInfo({ status }: { status: GitStatusResult | null }) {
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs font-mono text-muted-foreground">
      <GitBranch className="h-3.5 w-3.5 flex-shrink-0" />
      <span className="text-foreground truncate">
        {status ? status.branch || '(detached HEAD)' : '…'}
      </span>
      {status && (status.ahead > 0 || status.behind > 0) && (
        <>
          <span>·</span>
          {status.ahead > 0 && <span>{status.ahead}↑</span>}
          {status.behind > 0 && <span>{status.behind}↓</span>}
        </>
      )}
      {status?.upstream && (
        <>
          <span>·</span>
          <span className="truncate">{status.upstream}</span>
        </>
      )}
    </div>
  );
}

interface SectionProps {
  title: string;
  entries: GitStatusEntry[];
  staged: boolean;
  diffs: Map<string, DiffEntry>;
  expanded: Set<string>;
  wrapLines: boolean;
  splitView: boolean;
  splitDiffEnabled: boolean;
  treeView: boolean;
  submoduleView: SubmoduleView;
  pendingPaths: Set<string>;
  onToggle: (path: string, staged: boolean) => void;
  /** The row's hover action: unstage for the Staged section, stage otherwise. */
  onStageAction: (path: string) => void;
  onOpenFile?: (path: string, opts?: { newTab?: boolean }) => void;
}

function Section(props: SectionProps) {
  const { title, entries, staged, treeView } = props;
  if (entries.length === 0) return null;
  return (
    <div>
      <div className="sticky top-0 z-10 bg-muted/40 backdrop-blur px-3 py-1.5 text-[11px] text-muted-foreground font-mono">
        {title} · {entries.length}
      </div>
      {treeView ? (
        <SectionTree {...props} />
      ) : (
        entries.map((entry) => (
          <SectionFileRow key={diffKey(entry.path, staged)} entry={entry} section={props} />
        ))
      )}
    </div>
  );
}

/** One file of a Section, flat or inside the tree — wires the shared props
 *  through to DiffFileSection so the two layouts can't drift apart. */
function SectionFileRow({
  entry,
  section,
  indent,
  hideDir,
}: {
  entry: GitStatusEntry;
  section: SectionProps;
  indent?: number;
  hideDir?: boolean;
}) {
  const { staged, diffs, expanded, wrapLines, splitView, splitDiffEnabled, submoduleView, pendingPaths, onToggle, onStageAction, onOpenFile } = section;
  const key = diffKey(entry.path, staged);
  return (
    <DiffFileSection
      entry={entry}
      staged={staged}
      isOpen={expanded.has(key)}
      diff={diffs.get(key)}
      submodule={submoduleView.submodules.get(key)}
      submoduleView={submoduleView}
      wrapLines={wrapLines}
      splitView={splitView && splitDiffEnabled}
      pending={pendingPaths.has(entry.path)}
      indent={indent}
      hideDir={hideDir}
      onToggle={() => onToggle(entry.path, staged)}
      onStageAction={() => onStageAction(entry.path)}
      onOpenFile={onOpenFile}
    />
  );
}

const TREE_INDENT = 14;

/** Folder-tree layout of one section. Folders collapse locally (per section);
 *  file rows keep the exact flat-row behavior, just indented. */
function SectionTree(props: SectionProps) {
  const { entries } = props;
  const tree = React.useMemo(() => buildChangesTree(entries), [entries]);
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());
  const toggleDir = (path: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const renderDir = (node: ChangesDirNode, depth: number): React.ReactNode => {
    const isCollapsed = collapsed.has(node.path);
    return (
      <div key={node.path}>
        <button
          type="button"
          onClick={() => toggleDir(node.path)}
          className="flex w-full items-center gap-1.5 py-1 pr-3 text-left text-xs font-mono text-muted-foreground hover:bg-muted/40"
          style={{ paddingLeft: 12 + depth * TREE_INDENT }}
        >
          {isCollapsed ? (
            <ChevronRight className="h-3 w-3 flex-shrink-0" />
          ) : (
            <ChevronDown className="h-3 w-3 flex-shrink-0" />
          )}
          {isCollapsed ? (
            <Folder className="h-3.5 w-3.5 flex-shrink-0" />
          ) : (
            <FolderOpen className="h-3.5 w-3.5 flex-shrink-0" />
          )}
          <span className="truncate" title={node.path}>{node.name}</span>
        </button>
        {!isCollapsed && (
          <>
            {node.dirs.map((d) => renderDir(d, depth + 1))}
            {node.files.map((f) => (
              <SectionFileRow
                key={diffKey(f.path, props.staged)}
                entry={f}
                section={props}
                indent={12 + (depth + 1) * TREE_INDENT}
                hideDir
              />
            ))}
          </>
        )}
      </div>
    );
  };

  return (
    <>
      {tree.dirs.map((d) => renderDir(d, 0))}
      {tree.files.map((f) => (
        <SectionFileRow
          key={diffKey(f.path, props.staged)}
          entry={f}
          section={props}
          hideDir
        />
      ))}
    </>
  );
}

function DiffFileSection({
  entry,
  staged,
  isOpen,
  diff,
  submodule,
  submoduleView,
  wrapLines,
  splitView,
  pending,
  indent,
  hideDir,
  onToggle,
  onStageAction,
  onOpenFile,
}: {
  entry: GitStatusEntry;
  staged: boolean;
  isOpen: boolean;
  diff: DiffEntry | undefined;
  submodule: SubmoduleEntry | undefined;
  submoduleView: SubmoduleView;
  wrapLines: boolean;
  splitView: boolean;
  /** A stage/unstage for this path is in flight — spinner instead of +/−. */
  pending: boolean;
  /** Tree mode: left padding of the header row (flat rows use the px-3 default). */
  indent?: number;
  /** Tree mode: the folder shows the location, so drop the dir label. */
  hideDir?: boolean;
  onToggle: () => void;
  /** Hover action: stage (unstaged/untracked rows) or unstage (staged rows). */
  onStageAction: () => void;
  onOpenFile?: (path: string, opts?: { newTab?: boolean }) => void;
}) {
  const name = basename(entry.path);
  const dir = dirname(entry.path);
  const asSubmodule = submoduleView.enabled && entry.is_submodule === true;
  // A deleted file has no working copy to edit, and submodule rows aren't
  // openable as a single-file diff — those fall back to toggling the preview.
  const canOpen = !!onOpenFile && entry.status !== 'D' && !entry.is_submodule;
  return (
    // No separator between plain rows — an open diff gets a bottom edge so the
    // hunks don't bleed into the next file.
    <div className={isOpen ? 'border-b border-border/50' : undefined}>
      <div
        className="group/row w-full sticky top-7 z-[5] flex items-center gap-2 pr-3 py-2 bg-panel hover:bg-muted/40"
        style={{ paddingLeft: indent ?? 12 }}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-label={isOpen ? 'Collapse diff' : 'Expand diff'}
          className="flex-shrink-0 text-muted-foreground hover:text-foreground"
        >
          {isOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>
        <button
          type="button"
          onClick={canOpen ? () => onOpenFile!(entry.path) : onToggle}
          onDoubleClick={canOpen ? () => onOpenFile!(entry.path, { newTab: true }) : undefined}
          title={canOpen ? `Open ${entry.path}` : entry.path}
          className="min-w-0 flex-1 text-left"
        >
          <span className="text-xs font-mono truncate block hover:underline">{name}</span>
        </button>
        {entry.is_submodule && (
          <span className="text-[9px] font-mono uppercase tracking-wide text-muted-foreground border border-border/60 rounded px-1 py-px flex-shrink-0">
            submodule
          </span>
        )}
        {dir && !hideDir && (
          <span className="text-[10px] font-mono text-muted-foreground truncate max-w-[40%]">
            {dir}
          </span>
        )}
        <span className="text-[10px] font-mono flex-shrink-0">
          <span className="text-emerald-600 dark:text-emerald-400">+{entry.additions}</span>
          <span className="ml-1 text-red-600 dark:text-red-400">-{entry.deletions}</span>
        </span>
        {pending ? (
          <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin text-muted-foreground" />
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onStageAction();
            }}
            aria-label={staged ? `Unstage ${entry.path}` : `Stage ${entry.path}`}
            title={staged ? 'Unstage file' : 'Stage file'}
            className="flex-shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-muted-foreground/20 hover:text-foreground focus-visible:opacity-100 group-hover/row:opacity-100"
          >
            {staged ? <Minus className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
      {isOpen && (
        <div className="border-t border-border/50">
          {asSubmodule ? (
            <SubmoduleBody
              sub={entry.path}
              submodule={submodule}
              view={submoduleView}
              wrapLines={wrapLines}
              splitView={splitView}
            />
          ) : (
            <DiffView
              result={diff?.result ?? null}
              loading={diff?.loading ?? true}
              error={diff?.error ?? null}
              path={entry.path}
              wrapLines={wrapLines}
              splitView={splitView}
            />
          )}
        </div>
      )}
    </div>
  );
}

function submoduleErrorMessage(code: string): string {
  // No `no_handler` case: this reuses `git-status`, which every daemon serves.
  if (code === 'not_a_repo') return 'Submodule is not checked out on this machine';
  if (DAEMON_UNREACHABLE_CODES.has(code)) return 'Machine offline';
  return `Could not load submodule changes (${code})`;
}

/** The gitlink expanded into the submodule's *active* changes — its own
 *  working-tree status, same staged/unstaged/untracked split the parent gets.
 *  Replaces the "Subproject commit a..b" body, which says nothing useful. */
function SubmoduleBody({
  sub,
  submodule,
  view,
  wrapLines,
  splitView,
}: {
  sub: string;
  submodule: SubmoduleEntry | undefined;
  view: SubmoduleView;
  wrapLines: boolean;
  splitView: boolean;
}) {
  if (!submodule || submodule.loading) {
    return (
      <div className="px-4 py-3 space-y-2 animate-pulse">
        <div className="h-2 w-40 rounded-full bg-muted" />
        <div className="h-2 w-56 rounded-full bg-muted/70" />
        <div className="h-2 w-32 rounded-full bg-muted/50" />
      </div>
    );
  }
  if (submodule.error) {
    return (
      <div className="px-4 py-3 text-[11px] font-mono text-muted-foreground">
        {submoduleErrorMessage(submodule.error)}
      </div>
    );
  }
  const result = submodule.result;
  if (!result) return null;

  const sections: Array<{ title: string; entries: GitStatusEntry[]; staged: boolean }> = [
    { title: 'Staged', entries: result.staged, staged: true },
    { title: 'Unstaged', entries: result.unstaged, staged: false },
    { title: 'Untracked', entries: result.untracked, staged: false },
  ];
  const total = result.staged.length + result.unstaged.length + result.untracked.length;

  // A clean submodule worktree still shows as changed in the parent — that
  // means the parent's pin no longer matches the submodule's HEAD. Say so,
  // otherwise "no changes" inside a row the parent calls modified reads as a bug.
  if (total === 0) {
    return (
      <div className="px-4 py-3 text-[11px] font-mono text-muted-foreground leading-relaxed">
        No uncommitted changes in this submodule.
        <br />
        The parent repo records a different commit than{' '}
        <span className="text-foreground">{result.branch || 'HEAD'}</span> — commit in the parent to
        update the pointer.
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 py-1.5 flex items-center gap-2 text-[10px] font-mono text-muted-foreground bg-muted/20">
        <GitBranch className="h-3 w-3 flex-shrink-0" />
        <span className="text-foreground truncate">{result.branch || '(detached HEAD)'}</span>
        <span>·</span>
        <span>{total} changed</span>
      </div>
      {sections.map(({ title, entries, staged }) =>
        entries.length === 0 ? null : (
          <div key={title}>
            <div className="px-4 py-1 text-[10px] font-mono text-muted-foreground/80 bg-muted/10">
              {title} · {entries.length}
            </div>
            {entries.map((file) => {
              const key = submoduleFileKey(sub, file.path, staged);
              const isOpen = view.expandedSubFiles.has(key);
              const diff = view.submoduleDiffs.get(key);
              return (
                <div key={key}>
                  <button
                    type="button"
                    onClick={() => view.onToggleSubFile(sub, file.path, staged)}
                    className="w-full flex items-center gap-2 pl-7 pr-3 py-1.5 text-left hover:bg-muted/40"
                  >
                    {isOpen ? (
                      <ChevronDown className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                    ) : (
                      <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                    )}
                    <span className="text-[11px] font-mono truncate flex-1" title={file.path}>
                      {basename(file.path)}
                    </span>
                    {dirname(file.path) && (
                      <span className="text-[10px] font-mono text-muted-foreground truncate max-w-[45%]">
                        {dirname(file.path)}
                      </span>
                    )}
                    <span className="text-[10px] font-mono flex-shrink-0">
                      <span className="text-emerald-600 dark:text-emerald-400">
                        +{file.additions}
                      </span>
                      <span className="ml-1 text-red-600 dark:text-red-400">-{file.deletions}</span>
                    </span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-border/40">
                      <DiffView
                        result={diff?.result ?? null}
                        loading={diff?.loading ?? true}
                        error={diff?.error ?? null}
                        path={file.path}
                        wrapLines={wrapLines}
                        splitView={splitView}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ),
      )}
    </div>
  );
}
