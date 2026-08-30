import type { ReadFileResult } from './rpc';

/** The baseline ("original") side of the diff view, loaded lazily the first
 * time a tab enters diff mode. Which revision it holds is the tab's
 * {@link OpenFile.baseRef}: `HEAD` (all uncommitted changes) or the staged
 * index blob (unstaged changes only). `content` is `''` for a file not present
 * at the ref (a new/untracked file — an all-added diff). `error` is set when the
 * baseline can't back an editable diff (binary/truncated/old daemon without the
 * `git-base` capability), and the viewer then falls back to the read-only
 * inline diff. */
export interface DiffBase {
  loading: boolean;
  content: string;
  error: string | null;
}

/** Which git revision the diff's read-only baseline is taken from:
 * - `'HEAD'` — the committed version, so the diff shows every uncommitted change
 *   (staged + unstaged). The default.
 * - `'index'` — the staged blob (`git show :<path>`), so the diff shows only the
 *   *unstaged* edits on top of what's staged. Only meaningful when the file has
 *   staged changes; otherwise the index equals HEAD and the two are identical. */
export type DiffBaseRef = 'HEAD' | 'index';

/** One open file tab and its (lazily loaded) content state. */
export interface OpenFile {
  path: string;
  loading: boolean;
  result: ReadFileResult | null;
  error: string | null;
  // ── View mode (orthogonal to the fetch/editing state below) ──
  /** Which surface the tab shows: the plain editor (`'edit'`), or the
   * working-tree-vs-HEAD diff (`'diff'`, editable). Defaults to `'edit'`;
   * `'diff'` when opened from the Changes list. */
  viewMode: 'edit' | 'diff';
  /** The baseline for diff mode; `null` until first requested. */
  base: DiffBase | null;
  /** Which revision {@link base} is diffed against. Defaults to `'HEAD'`; the
   * toolbar's staged-file toggle flips it to `'index'`. */
  baseRef: DiffBaseRef;
  /** A transient "preview" tab (opened by a single click). At most one exists;
   * the next single-click reuses its slot. A double-click, or editing it, makes
   * it permanent (`preview: false`). Shown in italic in the tab strip. */
  preview: boolean;
  // ── Editing state (orthogonal to the fetch lifecycle above) ──
  /** Edit mode is on for this tab: the source view is an editor, not read-only. */
  editing: boolean;
  /** In-progress buffer while editing; `null` when not editing. */
  draft: string | null;
  /** `draft` differs from the last loaded/saved content. Drives the tab dot. */
  dirty: boolean;
  /** A write is in flight. */
  saving: boolean;
  /** Last hard save error code (permission/offline/…); `null` when clear. */
  saveError: string | null;
  /** The `content_hash` the draft is based on — the conflict base sent on save,
   * and the yardstick the poll compares against to spot an on-disk change. */
  baseHash: string | null;
  /** The file changed on disk under an unsaved edit (poll or conflict); shows
   * the reload/overwrite banner. */
  externalChange: boolean;
  // ── Scroll memory (orthogonal to everything above) ──
  /** The 1-based line last at the top of the viewport, and how far (px) it was
   * scrolled above the top edge. Restored when the tab is re-shown or the session
   * is reopened; `undefined` until the tab is scrolled (see cm-scroll.ts).
   * Persisted per session via {@link SavedFileTab}. */
  scrollLine?: number;
  scrollOffset?: number;
}

/** The view-mode + editing fields of a freshly-opened (view-only) tab. */
export function blankEditState(): Pick<
  OpenFile,
  | 'viewMode'
  | 'base'
  | 'baseRef'
  | 'preview'
  | 'editing'
  | 'draft'
  | 'dirty'
  | 'saving'
  | 'saveError'
  | 'baseHash'
  | 'externalChange'
> {
  return {
    viewMode: 'edit',
    base: null,
    baseRef: 'HEAD',
    preview: false,
    editing: false,
    draft: null,
    dirty: false,
    saving: false,
    saveError: null,
    baseHash: null,
    externalChange: false,
  };
}

/** A tab is editable — and its daemon supports writing — exactly when the last
 * read returned a string `content_hash` (absent on old daemons; `null` for
 * binary/truncated files). This is the single gate for the Edit affordance. */
export function isEditable(tab: OpenFile | null | undefined): boolean {
  return typeof tab?.result?.content_hash === 'string';
}

export function indexOfTab(tabs: OpenFile[], path: string): number {
  return tabs.findIndex((t) => t.path === path);
}

/** Append a loading placeholder for `path`, or reset an existing tab to loading.
 * An existing tab's editing state is carried over so a background refetch never
 * discards an unsaved edit (callers also skip refetching dirty tabs). */
export function withLoadingTab(tabs: OpenFile[], path: string): OpenFile[] {
  const i = indexOfTab(tabs, path);
  if (i < 0) {
    return [...tabs, { path, loading: true, result: null, error: null, ...blankEditState() }];
  }
  const next = tabs.slice();
  const prev = next[i];
  next[i] = {
    path,
    loading: true,
    result: null,
    error: null,
    // View mode + baseline survive a background refetch (the revision hasn't
    // moved), same as the editing state below.
    viewMode: prev.viewMode,
    base: prev.base,
    baseRef: prev.baseRef,
    preview: prev.preview,
    editing: prev.editing,
    draft: prev.draft,
    dirty: prev.dirty,
    saving: prev.saving,
    saveError: prev.saveError,
    baseHash: prev.baseHash,
    externalChange: prev.externalChange,
    // Scroll position survives a background refetch — the doc is the same file.
    scrollLine: prev.scrollLine,
    scrollOffset: prev.scrollOffset,
  };
  return next;
}

/** Reuse the preview slot: replace the tab at `oldPath` (in place, same tab
 *  order) with a fresh loading preview tab for `newPath`. Returns the input
 *  unchanged if `oldPath` is gone. */
export function replacePreviewSlot(
  tabs: OpenFile[],
  oldPath: string,
  newPath: string,
): OpenFile[] {
  const i = indexOfTab(tabs, oldPath);
  if (i < 0) return tabs;
  const next = tabs.slice();
  next[i] = {
    path: newPath,
    loading: true,
    result: null,
    error: null,
    ...blankEditState(),
    preview: true,
  };
  return next;
}

/** Merge `patch` into the tab for `path`. Returns the input unchanged if the
 *  tab was closed mid-flight (so a late RPC result can't resurrect it). */
export function patchTab(
  tabs: OpenFile[],
  path: string,
  patch: Partial<Omit<OpenFile, 'path'>>,
): OpenFile[] {
  const i = indexOfTab(tabs, path);
  if (i < 0) return tabs;
  const next = tabs.slice();
  next[i] = { ...next[i], ...patch, path };
  return next;
}

export function removeTab(tabs: OpenFile[], path: string): OpenFile[] {
  return tabs.filter((t) => t.path !== path);
}

/**
 * Which tab is active after closing `closingPath`. Closing an inactive tab
 * leaves the active one; closing the active tab picks the left neighbor, else
 * the right neighbor, else null (nothing left). `tabs` must still contain
 * `closingPath` (call before removing it).
 */
export function nextActiveAfterClose(
  tabs: OpenFile[],
  activePath: string | null,
  closingPath: string,
): string | null {
  if (closingPath !== activePath) return activePath;
  const i = indexOfTab(tabs, closingPath);
  if (i < 0) return activePath;
  if (tabs.length <= 1) return null;
  return i - 1 >= 0 ? tabs[i - 1].path : tabs[i + 1].path;
}
