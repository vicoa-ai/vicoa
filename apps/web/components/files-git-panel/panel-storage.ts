// The persisted, always-present panel tabs. Terminal tabs are dynamic
// (managed in files-git-panel.tsx / terminal-sessions.tsx, desktop-only) and
// never a value of PanelTab; their *layout* (which tabs, at which cwd) is
// persisted separately as part of the per-session workspace layout below, so
// it can be restored on relaunch as fresh shells.
export type PanelTab = 'files' | 'git';

export interface PanelState {
  /** @deprecated Per-session now — see {@link PanelSessionView}. Kept on the
   *  global state only so the legacy load/save round-trip stays stable; the
   *  panel hook no longer reads it. */
  open: boolean;
  width: number;
  lastTab: PanelTab;
  /** @deprecated Per-session now — see {@link PanelSessionView}. */
  maximized: boolean;
  /** Terminal-dock height (px) when a session's panel is split. A global
   *  preference like `width`; whether a session IS split lives on
   *  {@link PanelSessionView}. */
  splitHeight: number;
}

export const DEFAULT_PANEL_STATE: PanelState = {
  open: false,
  width: 400,
  lastTab: 'files',
  maximized: false,
  splitHeight: 280,
};

export const MIN_PANEL_WIDTH = 300;
export const MAX_PANEL_WIDTH_RATIO = 0.6;
export const MIN_SPLIT_HEIGHT = 120;

export function clampPanelWidth(width: number, viewport: number): number {
  if (!Number.isFinite(width)) return DEFAULT_PANEL_STATE.width;
  const max = viewport * MAX_PANEL_WIDTH_RATIO;
  if (width < MIN_PANEL_WIDTH) return MIN_PANEL_WIDTH;
  if (width > max) return max;
  return width;
}

const KEY_OPEN = 'files-panel-open';
const KEY_WIDTH = 'files-panel-width';
const KEY_TAB = 'files-panel-tab';
const KEY_MAXIMIZED = 'files-panel-maximized';
const KEY_SPLIT_HEIGHT = 'files-panel-split-height';

export function loadPanelState(storage: Storage): PanelState {
  const openRaw = storage.getItem(KEY_OPEN);
  const widthRaw = storage.getItem(KEY_WIDTH);
  const tabRaw = storage.getItem(KEY_TAB);
  const maximizedRaw = storage.getItem(KEY_MAXIMIZED);
  const splitHeightRaw = storage.getItem(KEY_SPLIT_HEIGHT);

  const width = widthRaw === null ? DEFAULT_PANEL_STATE.width : Number(widthRaw);
  const splitHeight =
    splitHeightRaw === null ? DEFAULT_PANEL_STATE.splitHeight : Number(splitHeightRaw);
  // Only the fixed tabs are persisted. Any other value (including a legacy
  // 'terminal' from an older build) falls back to 'files'.
  const lastTab: PanelTab = tabRaw === 'git' ? 'git' : 'files';
  return {
    open: openRaw === 'true',
    width: Number.isFinite(width) ? width : DEFAULT_PANEL_STATE.width,
    lastTab,
    maximized: maximizedRaw === 'true',
    splitHeight: Number.isFinite(splitHeight)
      ? Math.max(MIN_SPLIT_HEIGHT, splitHeight)
      : DEFAULT_PANEL_STATE.splitHeight,
  };
}

export function savePanelState(storage: Storage, patch: Partial<PanelState>): void {
  if (patch.open !== undefined) storage.setItem(KEY_OPEN, String(patch.open));
  if (patch.width !== undefined) storage.setItem(KEY_WIDTH, String(patch.width));
  if (patch.lastTab !== undefined) storage.setItem(KEY_TAB, patch.lastTab);
  if (patch.maximized !== undefined) storage.setItem(KEY_MAXIMIZED, String(patch.maximized));
  if (patch.splitHeight !== undefined) storage.setItem(KEY_SPLIT_HEIGHT, String(patch.splitHeight));
}

// ---------------------------------------------------------------------------
// Per-session panel view (open + focus). Whether the panel is open and whether
// it's maximized into the focus overlay is *view state that belongs to each
// session*: opening or focusing one session must not change another, and
// returning to a session restores how you left it. That's different from
// `width` / `lastTab`, which are global preferences shared across sessions.
// Keyed by instanceId; the default (closed, not focused) is stored as an absent
// key, so a session you've never touched starts as chat-only.
// ---------------------------------------------------------------------------

export interface PanelSessionView {
  open: boolean;
  maximized: boolean;
  /** Split layout: the session's terminals live in an always-visible dock
   *  stacked with the files/changes area, instead of being ordinary tabs. */
  split: boolean;
  /** Dock stacked above the files area instead of below it. */
  splitTop: boolean;
}

export const DEFAULT_PANEL_SESSION_VIEW: PanelSessionView = {
  open: false,
  maximized: false,
  split: false,
  splitTop: false,
};

function sessionViewKey(instanceId: string): string {
  return `files-panel-view:${instanceId}`;
}

export function loadPanelSessionView(storage: Storage, instanceId: string): PanelSessionView {
  const raw = storage.getItem(sessionViewKey(instanceId));
  if (raw === null) return DEFAULT_PANEL_SESSION_VIEW;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return DEFAULT_PANEL_SESSION_VIEW;
    const obj = parsed as Record<string, unknown>;
    return {
      open: obj.open === true,
      maximized: obj.maximized === true,
      split: obj.split === true,
      splitTop: obj.splitTop === true,
    };
  } catch {
    return DEFAULT_PANEL_SESSION_VIEW;
  }
}

export function savePanelSessionView(
  storage: Storage,
  instanceId: string,
  view: PanelSessionView,
): void {
  // The default (chat-only) is the absence of a key — keeps storage tidy and
  // guarantees a never-touched session always starts closed.
  if (!view.open && !view.maximized && !view.split && !view.splitTop) {
    storage.removeItem(sessionViewKey(instanceId));
    return;
  }
  try {
    storage.setItem(sessionViewKey(instanceId), JSON.stringify(view));
  } catch {
    // QuotaExceeded or similar — persistence is best-effort.
  }
}

function expansionKey(instanceId: string): string {
  return `files-panel-expansion:${instanceId}`;
}

export function loadExpansion(storage: Storage, instanceId: string): Set<string> {
  const raw = storage.getItem(expansionKey(instanceId));
  if (raw === null) return new Set();
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is string => typeof v === 'string'));
  } catch {
    return new Set();
  }
}

export function saveExpansion(storage: Storage, instanceId: string, paths: Set<string>): void {
  storage.setItem(expansionKey(instanceId), JSON.stringify(Array.from(paths)));
}

// ---------------------------------------------------------------------------
// Per-session workspace layout (desktop only): open file tabs + terminal tabs.
//
// Restored on relaunch — files re-read from disk, terminals re-spawned as fresh
// shells at their saved cwd (the shell *process* cannot survive an app quit, so
// scrollback and running commands are not preserved; this restores the layout).
// Terminals and files use separate keys because different hooks own them (the
// global TerminalSessionsProvider vs the per-session useFilesTab) and a shared
// key would let one hook's write clobber the other's.
// ---------------------------------------------------------------------------

// Bound the persisted layout so a runaway session can't bloat localStorage.
const MAX_PERSISTED_TERMINALS = 16; // matches the daemon's DEFAULT_MAX_SESSIONS
const MAX_PERSISTED_FILES = 50;

export interface PersistedTerminal {
  cwd: string;
  machineId: string;
}

export interface SavedTerminals {
  terminals: PersistedTerminal[];
  /** Index into `terminals` of the active tab (-1 = a fixed panel tab). */
  activeIndex: number;
}

export const EMPTY_SAVED_TERMINALS: SavedTerminals = { terminals: [], activeIndex: -1 };

export interface SavedFileTab {
  /** Project-relative path. */
  path: string;
  /** Which surface the tab was showing, so a diff reopens as a diff on reload. */
  viewMode: 'edit' | 'diff';
  /** The 1-based line last at the top of the viewport, so reopening the tab (or
   *  the whole session) restores where the user was, not the top of the file.
   *  Absent when never scrolled past the top. */
  scrollLine?: number;
  /** Pixels of `scrollLine` scrolled above the viewport's top edge, so the
   *  restore lands sub-line accurate rather than a line off. */
  scrollOffset?: number;
}

export interface SavedFileTabs {
  /** Open file tabs, in tab order. */
  openFiles: SavedFileTab[];
  activeFile: string | null;
}

export const EMPTY_SAVED_FILE_TABS: SavedFileTabs = { openFiles: [], activeFile: null };

function terminalsKey(instanceId: string): string {
  return `files-panel-terminals:${instanceId}`;
}

function fileTabsKey(instanceId: string): string {
  return `files-panel-filetabs:${instanceId}`;
}

export function loadTerminals(storage: Storage, instanceId: string): SavedTerminals {
  const raw = storage.getItem(terminalsKey(instanceId));
  if (raw === null) return EMPTY_SAVED_TERMINALS;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return EMPTY_SAVED_TERMINALS;
    const obj = parsed as Record<string, unknown>;
    const terminals = Array.isArray(obj.terminals)
      ? obj.terminals
          .filter(
            (t): t is { cwd: string; machineId: string } =>
              typeof t === 'object' &&
              t !== null &&
              typeof (t as Record<string, unknown>).cwd === 'string' &&
              typeof (t as Record<string, unknown>).machineId === 'string',
          )
          .map((t) => ({ cwd: t.cwd, machineId: t.machineId }))
          .slice(0, MAX_PERSISTED_TERMINALS)
      : [];
    const activeIndex =
      typeof obj.activeIndex === 'number' &&
      obj.activeIndex >= 0 &&
      obj.activeIndex < terminals.length
        ? obj.activeIndex
        : -1;
    return { terminals, activeIndex };
  } catch {
    return EMPTY_SAVED_TERMINALS;
  }
}

export function saveTerminals(storage: Storage, instanceId: string, saved: SavedTerminals): void {
  if (saved.terminals.length === 0) {
    storage.removeItem(terminalsKey(instanceId));
    return;
  }
  try {
    storage.setItem(
      terminalsKey(instanceId),
      JSON.stringify({
        terminals: saved.terminals.slice(0, MAX_PERSISTED_TERMINALS),
        activeIndex: saved.activeIndex,
      }),
    );
  } catch {
    // QuotaExceeded or similar — persistence is best-effort.
  }
}

export function loadFileTabs(storage: Storage, instanceId: string): SavedFileTabs {
  const raw = storage.getItem(fileTabsKey(instanceId));
  if (raw === null) return EMPTY_SAVED_FILE_TABS;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return EMPTY_SAVED_FILE_TABS;
    const obj = parsed as Record<string, unknown>;
    // Accept both the legacy `string[]` layout (defaults to edit mode) and the
    // current `{ path, viewMode }[]` so an existing saved layout still restores.
    const openFiles: SavedFileTab[] = Array.isArray(obj.openFiles)
      ? obj.openFiles
          .map((e): SavedFileTab | null => {
            if (typeof e === 'string') return { path: e, viewMode: 'edit' };
            if (e !== null && typeof e === 'object') {
              const rec = e as Record<string, unknown>;
              if (typeof rec.path === 'string') {
                const scrollLine =
                  typeof rec.scrollLine === 'number' &&
                  Number.isFinite(rec.scrollLine) &&
                  rec.scrollLine > 1
                    ? Math.floor(rec.scrollLine)
                    : undefined;
                const scrollOffset =
                  scrollLine !== undefined &&
                  typeof rec.scrollOffset === 'number' &&
                  Number.isFinite(rec.scrollOffset) &&
                  rec.scrollOffset > 0
                    ? Math.floor(rec.scrollOffset)
                    : undefined;
                return {
                  path: rec.path,
                  viewMode: rec.viewMode === 'diff' ? 'diff' : 'edit',
                  ...(scrollLine !== undefined ? { scrollLine } : {}),
                  ...(scrollOffset !== undefined ? { scrollOffset } : {}),
                };
              }
            }
            return null;
          })
          .filter((t): t is SavedFileTab => t !== null)
          .slice(0, MAX_PERSISTED_FILES)
      : [];
    const paths = openFiles.map((f) => f.path);
    const activeFile =
      typeof obj.activeFile === 'string' && paths.includes(obj.activeFile)
        ? obj.activeFile
        : null;
    return { openFiles, activeFile };
  } catch {
    return EMPTY_SAVED_FILE_TABS;
  }
}

export function saveFileTabs(storage: Storage, instanceId: string, saved: SavedFileTabs): void {
  if (saved.openFiles.length === 0) {
    storage.removeItem(fileTabsKey(instanceId));
    return;
  }
  try {
    storage.setItem(
      fileTabsKey(instanceId),
      JSON.stringify({
        openFiles: saved.openFiles.slice(0, MAX_PERSISTED_FILES),
        activeFile: saved.activeFile,
      }),
    );
  } catch {
    // QuotaExceeded or similar — persistence is best-effort.
  }
}

/** Drop every persisted trace of a session (used when it is archived/deleted). */
export function clearWorkspaceLayout(storage: Storage, instanceId: string): void {
  storage.removeItem(terminalsKey(instanceId));
  storage.removeItem(fileTabsKey(instanceId));
  storage.removeItem(expansionKey(instanceId));
  storage.removeItem(sessionViewKey(instanceId));
}
