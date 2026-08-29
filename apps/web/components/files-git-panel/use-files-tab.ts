'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { FileEntry, ReadFileResult } from './rpc';
import {
  rpcListFiles,
  rpcReadFile,
  rpcStatFile,
  rpcWriteFile,
  rpcGitShowFile,
  isWriteConflict,
} from './rpc';
import { loadExpansion, saveExpansion, loadFileTabs, saveFileTabs } from './panel-storage';
import { ancestorPaths } from './tree';
import { RpcError } from '@/lib/ws-client';
import {
  indexOfTab,
  withLoadingTab,
  replacePreviewSlot,
  patchTab,
  removeTab,
  nextActiveAfterClose,
  type OpenFile,
  type DiffBase,
  type DiffBaseRef,
} from './file-tabs';

// The viewer imports this name; keep it as an alias of the tab shape.
export type FileViewState = OpenFile;

/** How often open editable tabs are stat-polled for an on-disk change. */
const POLL_MS = 2500;
/** Debounce before an autosave fires after the last keystroke. */
const AUTOSAVE_MS = 1000;
/** localStorage key for the (global) autosave preference. */
const AUTOSAVE_KEY = 'vicoa:files:autosave';
/** localStorage key for the (global) diff-baseline preference: which revision a
 *  freshly opened diff compares against — `'HEAD'` (default) or the staged
 *  `'index'`. Remembered across sessions so the last HEAD-vs-staged choice
 *  sticks. */
const DIFF_BASE_REF_KEY = 'vicoa:files:diff-base-ref';

interface UseFilesTabArgs {
  machineId: string | null;
  cwd: string | null;
  instanceId: string;
}

interface UseFilesTabApi {
  listings: Map<string, FileEntry[] | null>;
  expanded: Set<string>;
  listingErrors: Map<string, string>;
  rootError: string | null;
  openFiles: OpenFile[];
  activeFilePath: string | null;
  activeFile: OpenFile | null;
  toggleDir: (path: string) => void;
  revealDir: (dirPath: string) => void;
  /** Open (or focus) a file tab. `opts.mode` picks the initial surface — the
   * Changes list passes `'diff'` to open the editable diff; the Files tree omits
   * it, so a new tab defaults to `'edit'` and an already-open tab keeps its mode.
   * `opts.preview` (single click) reuses the one preview slot; omitting it (double
   * click) opens/commits a permanent tab. */
  openFile: (path: string, opts?: { mode?: 'edit' | 'diff'; preview?: boolean }) => void;
  activateFile: (path: string | null) => void;
  /** Remember the top scroll anchor of a tab (line + sub-line px offset), so
   * re-showing it (or reopening the session) restores the scroll position. */
  setScrollAnchor: (path: string, line: number, offset: number) => void;
  closeFileTab: (path: string) => void;
  refreshAll: () => void;
  /** Flip a tab between the plain editor and the editable diff; lazily loads the
   * baseline the first time diff is shown. */
  setViewMode: (path: string, mode: 'edit' | 'diff') => void;
  /** Switch the diff baseline (HEAD ⇄ staged index) for a tab and reload it.
   * Only meaningful for a file with staged changes. */
  setDiffBaseRef: (path: string, baseRef: DiffBaseRef) => void;
  // ── Editing ──
  /** Autosave preference (default off). The engine honours it; the UI toggle is
   * currently hidden, but the option is kept for a future settings surface. */
  autosaveEnabled: boolean;
  setAutosaveEnabled: (on: boolean) => void;
  updateDraft: (path: string, content: string) => void;
  saveFile: (path: string, opts?: { force?: boolean }) => void;
  /** Replace the buffer with the current on-disk content (banner "Reload"). */
  reloadFromDisk: (path: string) => void;
}

export function useFilesTab(args: UseFilesTabArgs): UseFilesTabApi {
  const { machineId, cwd, instanceId } = args;
  const [listings, setListings] = useState<Map<string, FileEntry[] | null>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [listingErrors, setListingErrors] = useState<Map<string, string>>(new Map());
  const [rootError, setRootError] = useState<string | null>(null);
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const [autosaveEnabled, setAutosaveEnabledState] = useState(false);
  // Restore runs once per session; `hydratedInstance` (state, not a ref) gates
  // persistence so the save effect never fires until the restored tabs have
  // actually landed — otherwise it would read the empty pre-restore list and
  // wipe the saved layout in the same commit that schedules the restore.
  const restoredRef = useRef<string | null>(null);
  const [hydratedInstance, setHydratedInstance] = useState<string | null>(null);
  const machineIdRef = useRef(machineId);
  const cwdRef = useRef(cwd);
  const openFilesRef = useRef(openFiles);
  const listingsRef = useRef(listings);
  const activeFilePathRef = useRef(activeFilePath);
  const autosaveEnabledRef = useRef(autosaveEnabled);
  // Remembered HEAD-vs-staged diff baseline (a global preference, like autosave).
  // A ref, not state: it only seeds new diff tabs, so it needs no re-render, and
  // reading localStorage post-mount keeps SSR output stable.
  const preferredBaseRefRef = useRef<DiffBaseRef>('HEAD');
  machineIdRef.current = machineId;
  cwdRef.current = cwd;
  openFilesRef.current = openFiles;
  listingsRef.current = listings;
  activeFilePathRef.current = activeFilePath;
  autosaveEnabledRef.current = autosaveEnabled;
  // Pending autosave timers and in-flight/queued save bookkeeping, keyed by
  // path. Refs (not state) — they must survive re-renders without triggering one.
  const autosaveTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const savingPaths = useRef<Set<string>>(new Set());
  const resavePaths = useRef<Set<string>>(new Set());
  // `saveFile` schedules itself (autosave, resave-after-inflight) via this ref
  // to sidestep the useCallback self-reference bootstrap problem.
  const saveFileRef = useRef<(path: string, opts?: { force?: boolean }) => void>(() => {});

  // Hydrate expansion state when instance changes.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    setExpanded(loadExpansion(window.localStorage, instanceId));
  }, [instanceId]);

  const persistExpansion = useCallback(
    (next: Set<string>) => {
      if (typeof window !== 'undefined') {
        saveExpansion(window.localStorage, instanceId, next);
      }
    },
    [instanceId],
  );

  const fetchListing = useCallback(
    async (path: string): Promise<void> => {
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return;
      // Only flag "in-flight = null" when there's no cached array. A refresh
      // over an existing listing keeps the array visible until the new one
      // arrives, so a failed refresh doesn't wipe out last-good data.
      setListings((prev) => {
        const existing = prev.get(path);
        if (Array.isArray(existing)) return prev;
        const next = new Map(prev);
        next.set(path, null);
        return next;
      });
      try {
        const result = await rpcListFiles(mId, c, path);
        setListings((prev) => {
          const next = new Map(prev);
          next.set(path, result.entries);
          return next;
        });
        setListingErrors((prev) => {
          if (!prev.has(path)) return prev;
          const next = new Map(prev);
          next.delete(path);
          return next;
        });
        if (path === '') setRootError(null);
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'unknown';
        setListings((prev) => {
          const next = new Map(prev);
          // Drop the null placeholder; preserve any cached array.
          if (next.get(path) === null) next.delete(path);
          return next;
        });
        if (path === '') {
          setRootError(code);
        } else {
          setListingErrors((prev) => {
            const next = new Map(prev);
            next.set(path, code);
            return next;
          });
        }
      }
    },
    [],
  );

  // Reset cached state and kick off a root listing whenever the target
  // machine/cwd changes. Merged into one effect so the reset's `setListings`
  // is guaranteed to apply before the fetch decision (splitting them caused
  // the fetch closure to read a stale `listings.has('')` from the previous
  // session and skip fetching, leaving the tree stuck on a skeleton).
  useEffect(() => {
    // Tabs are being wiped — drop any pending autosave timers / save bookkeeping
    // so they can't fire against the previous session's paths.
    for (const timer of autosaveTimers.current.values()) clearTimeout(timer);
    autosaveTimers.current.clear();
    savingPaths.current.clear();
    resavePaths.current.clear();
    setListings(new Map());
    setListingErrors(new Map());
    setRootError(null);
    setOpenFiles([]);
    setActiveFilePath(null);
    // Re-arm the once-per-session restore so it re-runs after this clear. Under
    // React StrictMode (dev) the mount effects fire twice — reset → restore →
    // reset → restore — and without re-arming, the second reset would wipe the
    // just-restored tabs while the second restore skipped (its ref still set),
    // leaving an empty list that then gets persisted over the saved layout. This
    // surfaced once the panel started unmounting on a session switch.
    restoredRef.current = null;
    if (machineId && cwd) {
      void fetchListing('');
    }
    // `instanceId` is included so switching to another session that happens to
    // share the same machine/cwd still clears the previous session's tabs
    // before its own restore runs (otherwise the two would merge).
  }, [machineId, cwd, instanceId, fetchListing]);

  const toggleDir = useCallback(
    (path: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        const wasExpanded = next.has(path);
        if (wasExpanded) {
          next.delete(path);
        } else {
          next.add(path);
        }
        persistExpansion(next);
        if (!wasExpanded) {
          void fetchListing(path);
        }
        return next;
      });
    },
    [fetchListing, persistExpansion],
  );

  // Expand the tree from the root down to `dirPath`, fetching any ancestor
  // listing not already cached. Idempotent — never collapses. Backs the
  // breadcrumb's "open this folder in the drawer" click.
  const revealDir = useCallback(
    (dirPath: string) => {
      const prefixes = ancestorPaths(dirPath);
      if (prefixes.length === 0) return;
      setExpanded((prev) => {
        const next = new Set(prev);
        for (const p of prefixes) next.add(p);
        persistExpansion(next);
        return next;
      });
      for (const p of prefixes) {
        if (!Array.isArray(listingsRef.current.get(p))) void fetchListing(p);
      }
    },
    [persistExpansion, fetchListing],
  );

  // Read `path`'s contents into its (already-created loading) tab. Split out of
  // fetchFile so the preview-slot replacement can reuse the fetch without
  // re-appending a tab. A late result for a closed tab is dropped by patchTab.
  const loadFileContent = useCallback(async (path: string) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    try {
      const result = await rpcReadFile(mId, c, path);
      // Editable text files (the daemon returned a hash) open ready to edit —
      // no mode switch. Binary/truncated/old-daemon files stay read-only.
      const editable = typeof result.content_hash === 'string';
      setOpenFiles((prev) =>
        patchTab(prev, path, {
          loading: false,
          result,
          error: null,
          baseHash: result.content_hash ?? null,
          editing: editable,
          draft: editable ? result.content : null,
          dirty: false,
          externalChange: false,
          saveError: null,
        }),
      );
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setOpenFiles((prev) => patchTab(prev, path, { loading: false, result: null, error: code }));
    }
  }, []);

  // Append (or reset) `path`'s tab to a loading placeholder, then load it.
  // `mode` sets the tab's view mode when given (a first open picks the surface;
  // a plain refetch omits it so the current mode is preserved). `preview` marks
  // a freshly-appended tab as a preview.
  const fetchFile = useCallback(
    async (
      path: string,
      mode?: 'edit' | 'diff',
      preview?: boolean,
      scrollLine?: number,
      scrollOffset?: number,
    ) => {
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return;
      setOpenFiles((prev) => {
        let next = withLoadingTab(prev, path);
        if (mode) next = patchTab(next, path, { viewMode: mode });
        if (preview) next = patchTab(next, path, { preview: true });
        // Seed the restored scroll position so the surface opens where it was
        // left (survives the async content load via patchTab's merge).
        if (scrollLine != null) next = patchTab(next, path, { scrollLine, scrollOffset });
        return next;
      });
      await loadFileContent(path);
    },
    [loadFileContent],
  );

  // Load the diff baseline for `path` into `tab.base` (the diff's read-only
  // "original"). The revision is the tab's `baseRef` — `HEAD` (default) or the
  // staged index blob (`''` → `git show :<path>`); `baseRefArg` overrides it so
  // a just-requested flip fetches the new ref without waiting for the state
  // commit. A path absent at the ref (a new/untracked file, or nothing staged)
  // resolves to an empty baseline; binary/truncated/old-daemon responses set
  // `base.error` so the viewer falls back to the read-only inline diff.
  const fetchBase = useCallback(async (path: string, baseRefArg?: DiffBaseRef) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    const baseRef =
      baseRefArg ?? openFilesRef.current.find((t) => t.path === path)?.baseRef ?? 'HEAD';
    const ref = baseRef === 'index' ? '' : 'HEAD';
    setOpenFiles((prev) => patchTab(prev, path, { base: { loading: true, content: '', error: null } }));
    try {
      const res = await rpcGitShowFile(mId, c, path, ref);
      let base: DiffBase;
      if (res.not_in_ref) {
        base = { loading: false, content: '', error: null };
      } else if (res.is_binary || res.truncated || typeof res.content !== 'string') {
        base = { loading: false, content: '', error: 'unsupported' };
      } else {
        base = { loading: false, content: res.content, error: null };
      }
      setOpenFiles((prev) => patchTab(prev, path, { base }));
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setOpenFiles((prev) => patchTab(prev, path, { base: { loading: false, content: '', error: code } }));
    }
  }, []);

  // Fetch the baseline unless it's already loading or successfully loaded.
  // A previously-errored baseline is retried.
  const ensureBase = useCallback(
    (path: string) => {
      const base = openFilesRef.current.find((t) => t.path === path)?.base;
      if (base && (base.loading || base.error === null)) return;
      // A tab's first diff load adopts the user's remembered HEAD-vs-staged
      // preference (index == HEAD for an unstaged file, so this is a no-op
      // there). A retry after an error keeps whatever ref the tab is on.
      if (base == null && preferredBaseRefRef.current !== 'HEAD') {
        const baseRef = preferredBaseRefRef.current;
        setOpenFiles((prev) => patchTab(prev, path, { baseRef }));
        void fetchBase(path, baseRef);
        return;
      }
      void fetchBase(path);
    },
    [fetchBase],
  );

  // Clear a tab's pending-save bookkeeping (autosave timer + in-flight/queued
  // save flags) without touching the tab list — used when a tab is closed or
  // when its preview slot is reused for another file.
  const clearTabBookkeeping = useCallback((path: string) => {
    const timer = autosaveTimers.current.get(path);
    if (timer) {
      clearTimeout(timer);
      autosaveTimers.current.delete(path);
    }
    savingPaths.current.delete(path);
    resavePaths.current.delete(path);
  }, []);

  // Open a file as a tab (or focus it if already open).
  //  - `opts.mode` picks the surface: the Changes list/switcher pass `'diff'`;
  //    the tree omits it (new tab → 'edit', existing tab keeps its mode).
  //  - `opts.preview` (single click) reuses the one preview slot: a clean
  //    preview tab is replaced in place, so browsing files doesn't pile up tabs.
  //    A non-preview open (double click) opens/commits a permanent tab.
  // Skips the refetch when the tab already holds a successful result.
  const openFile = useCallback(
    (
      path: string,
      opts?: {
        mode?: 'edit' | 'diff';
        preview?: boolean;
        scrollLine?: number;
        scrollOffset?: number;
      },
    ) => {
      const mode = opts?.mode;
      const preview = opts?.preview ?? false;
      // Only used when opening a *fresh* tab (session restore) — an already-open
      // tab keeps whatever scroll position it currently has.
      const scrollLine = opts?.scrollLine;
      const scrollOffset = opts?.scrollOffset;
      setActiveFilePath(path);
      const tabs = openFilesRef.current;
      const existing = tabs.find((t) => t.path === path);
      if (existing) {
        const patch: Partial<Omit<OpenFile, 'path'>> = {};
        if (mode && existing.viewMode !== mode) patch.viewMode = mode;
        if (!preview && existing.preview) patch.preview = false; // double-click promotes
        if (Object.keys(patch).length > 0) setOpenFiles((prev) => patchTab(prev, path, patch));
        if ((mode ?? existing.viewMode) === 'diff') ensureBase(path);
        if (existing.result && !existing.error) return;
        void fetchFile(path);
        return;
      }
      if (preview) {
        const prevPreview = tabs.find((t) => t.preview);
        if (prevPreview && !prevPreview.dirty) {
          // Reuse the clean preview slot in place (keeps tab order stable).
          clearTabBookkeeping(prevPreview.path);
          setOpenFiles((prev) => {
            let next = replacePreviewSlot(prev, prevPreview.path, path);
            if (mode) next = patchTab(next, path, { viewMode: mode });
            return next;
          });
          void loadFileContent(path);
          if (mode === 'diff') ensureBase(path);
          return;
        }
        if (prevPreview && prevPreview.dirty) {
          // Protect unsaved edits: promote the dirty preview, open a new one.
          setOpenFiles((prev) => patchTab(prev, prevPreview.path, { preview: false }));
        }
        void fetchFile(path, mode ?? 'edit', true, scrollLine, scrollOffset);
        if (mode === 'diff') ensureBase(path);
        return;
      }
      void fetchFile(path, mode ?? 'edit', false, scrollLine, scrollOffset);
      if (mode === 'diff') ensureBase(path);
    },
    [fetchFile, loadFileContent, ensureBase, clearTabBookkeeping],
  );

  const setViewMode = useCallback(
    (path: string, mode: 'edit' | 'diff') => {
      setOpenFiles((prev) => patchTab(prev, path, { viewMode: mode }));
      if (mode === 'diff') ensureBase(path);
    },
    [ensureBase],
  );

  // Flip which revision the diff is compared against (HEAD ⇄ staged index) and
  // reload the baseline for the new ref. Passing `baseRef` through to fetchBase
  // avoids reading the not-yet-committed tab state. The choice is also remembered
  // globally, so the next diff a user opens starts on the same baseline.
  const setDiffBaseRef = useCallback(
    (path: string, baseRef: DiffBaseRef) => {
      preferredBaseRefRef.current = baseRef;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(DIFF_BASE_REF_KEY, baseRef);
      }
      setOpenFiles((prev) => patchTab(prev, path, { baseRef }));
      void fetchBase(path, baseRef);
    },
    [fetchBase],
  );

  const activateFile = useCallback((path: string | null) => setActiveFilePath(path), []);

  // Remember the top scroll anchor of a tab's surface (reported by the viewer as
  // the user scrolls). Kept on the tab so it persists per session and restores
  // when the tab is re-shown. A no-op when unchanged, so the stream of scroll
  // reports doesn't churn state or re-persist needlessly. At the top of the file
  // (line 1) the anchor is cleared so a fresh open starts at the top.
  const setScrollAnchor = useCallback((path: string, line: number, offset: number) => {
    setOpenFiles((prev) => {
      const i = indexOfTab(prev, path);
      if (i < 0) return prev;
      const nextLine = line > 1 ? line : undefined;
      const nextOffset = nextLine !== undefined && offset > 0 ? offset : undefined;
      if (prev[i].scrollLine === nextLine && prev[i].scrollOffset === nextOffset) return prev;
      const next = prev.slice();
      next[i] = { ...next[i], scrollLine: nextLine, scrollOffset: nextOffset };
      return next;
    });
  }, []);

  const closeFileTab = useCallback(
    (path: string) => {
      clearTabBookkeeping(path);
      setActiveFilePath((prev) => nextActiveAfterClose(openFilesRef.current, prev, path));
      setOpenFiles((prev) => removeTab(prev, path));
    },
    [clearTabBookkeeping],
  );

  const refreshAll = useCallback(() => {
    if (!machineId || !cwd) return;
    void fetchListing('');
    for (const path of expanded) {
      void fetchListing(path);
    }
    // Never refetch a tab that's mid-edit — it would blow away the unsaved
    // buffer. The poll keeps editing tabs fresh via a non-destructive path.
    if (activeFilePath) {
      const at = openFilesRef.current.find((t) => t.path === activeFilePath);
      if (!at?.editing) void fetchFile(activeFilePath);
      // Diff tabs leave the working side alone (unsaved edits), but the baseline
      // may have moved (a commit, or a stage/unstage when comparing against the
      // index), so refresh the diff's "original" for the tab's current ref.
      if (at?.viewMode === 'diff') void fetchBase(activeFilePath);
    }
  }, [machineId, cwd, fetchListing, expanded, activeFilePath, fetchFile, fetchBase]);

  // ── Editing engine ────────────────────────────────────────────────────────

  const clearAutosaveTimer = useCallback((path: string) => {
    const timer = autosaveTimers.current.get(path);
    if (timer) {
      clearTimeout(timer);
      autosaveTimers.current.delete(path);
    }
  }, []);

  // Persisted (global) autosave + diff-baseline preferences.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    setAutosaveEnabledState(window.localStorage.getItem(AUTOSAVE_KEY) === '1');
    const storedBaseRef = window.localStorage.getItem(DIFF_BASE_REF_KEY);
    if (storedBaseRef === 'index' || storedBaseRef === 'HEAD') {
      preferredBaseRefRef.current = storedBaseRef;
    }
  }, []);
  const setAutosaveEnabled = useCallback((on: boolean) => {
    setAutosaveEnabledState(on);
    autosaveEnabledRef.current = on;
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(AUTOSAVE_KEY, on ? '1' : '0');
    }
  }, []);

  const updateDraft = useCallback((path: string, content: string) => {
    setOpenFiles((prev) => {
      const i = indexOfTab(prev, path);
      if (i < 0 || !prev[i].editing) return prev;
      const t = prev[i];
      const dirty = content !== (t.result?.content ?? '');
      // Editing a preview tab commits it — otherwise the next single-click would
      // discard the unsaved change by reusing its slot.
      const preview = t.preview && !dirty;
      if (t.draft === content && t.dirty === dirty && t.preview === preview) return prev;
      const next = prev.slice();
      next[i] = { ...t, draft: content, dirty, preview };
      return next;
    });
    if (autosaveEnabledRef.current) {
      clearAutosaveTimer(path);
      autosaveTimers.current.set(
        path,
        setTimeout(() => {
          autosaveTimers.current.delete(path);
          saveFileRef.current(path);
        }, AUTOSAVE_MS),
      );
    }
  }, [clearAutosaveTimer]);

  const saveFile = useCallback(
    async (path: string, opts?: { force?: boolean }) => {
      const force = opts?.force ?? false;
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return;
      const tab = openFilesRef.current.find((t) => t.path === path);
      if (!tab || !tab.editing || tab.draft == null) return;
      // Nothing to write unless there are unsaved edits — but a forced save
      // (banner "Overwrite") always goes through.
      if (!force && !tab.dirty) return;
      // Coalesce concurrent saves: one in flight, at most one queued.
      if (savingPaths.current.has(path)) {
        resavePaths.current.add(path);
        return;
      }
      savingPaths.current.add(path);
      clearAutosaveTimer(path); // an explicit save preempts the pending autosave
      const sent = tab.draft;
      const base = tab.baseHash;
      setOpenFiles((prev) => patchTab(prev, path, { saving: true, saveError: null }));
      try {
        const res = await rpcWriteFile(mId, c, path, sent, base, force);
        if (isWriteConflict(res)) {
          setOpenFiles((prev) => patchTab(prev, path, { saving: false, externalChange: true }));
          return;
        }
        setOpenFiles((prev) => {
          const i = indexOfTab(prev, path);
          if (i < 0) return prev;
          const t = prev[i];
          const next = prev.slice();
          const newResult: ReadFileResult | null = t.result
            ? { ...t.result, content: sent, size: res.size, content_hash: res.content_hash }
            : t.result;
          next[i] = {
            ...t,
            result: newResult,
            baseHash: res.content_hash,
            saving: false,
            saveError: null,
            externalChange: false,
            // Keystrokes may have landed while the write was in flight.
            dirty: t.draft !== sent,
          };
          return next;
        });
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'unknown';
        setOpenFiles((prev) => patchTab(prev, path, { saving: false, saveError: code }));
      } finally {
        savingPaths.current.delete(path);
        if (resavePaths.current.has(path)) {
          resavePaths.current.delete(path);
          saveFileRef.current(path, { force });
        }
      }
    },
    [clearAutosaveTimer],
  );
  // Keep the ref pointing at the latest closure for self-scheduling.
  saveFileRef.current = (path, opts) => {
    void saveFile(path, opts);
  };

  // Non-destructive reload: take the current on-disk content into the tab
  // (used by the poll for clean tabs and the banner's "Reload"). No loading
  // skeleton — the content simply refreshes in place.
  const quietReload = useCallback(async (path: string) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    try {
      const result = await rpcReadFile(mId, c, path);
      setOpenFiles((prev) => {
        const i = indexOfTab(prev, path);
        if (i < 0) return prev;
        const t = prev[i];
        const next = prev.slice();
        const base = result.content_hash ?? null;
        next[i] = t.editing
          ? { ...t, result, error: null, loading: false, baseHash: base, draft: result.content, dirty: false, externalChange: false }
          : { ...t, result, error: null, loading: false, baseHash: base, externalChange: false };
        return next;
      });
    } catch {
      // Transient (offline / momentarily gone) — leave state; the poll retries.
    }
  }, []);

  // Poll open editable tabs for an on-disk change the user should know about.
  const pollOpenFiles = useCallback(async () => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    const active = activeFilePathRef.current;
    for (const t of openFilesRef.current) {
      if (t.baseHash == null || t.loading || t.saving) continue;
      // Only the tabs that care: any editing tab, plus the active viewer.
      if (!t.editing && t.path !== active) continue;
      let stat;
      try {
        stat = await rpcStatFile(mId, c, t.path);
      } catch {
        continue; // transient/deleted — retry next round
      }
      if (stat.content_hash === t.baseHash) continue; // unchanged (incl. our own save)
      if (t.editing && t.dirty) {
        setOpenFiles((prev) => patchTab(prev, t.path, { externalChange: true }));
      } else {
        void quietReload(t.path); // clean viewer / untouched edit → take disk
      }
    }
  }, [quietReload]);

  useEffect(() => {
    const id = setInterval(() => void pollOpenFiles(), POLL_MS);
    return () => clearInterval(id);
  }, [pollOpenFiles]);

  // Clear all pending autosave timers on unmount.
  useEffect(() => {
    const timers = autosaveTimers.current;
    return () => {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
    };
  }, []);

  // Restore persisted file tabs once per session (desktop). Declared after the
  // reset effect above, so it runs later in the same effect flush and the
  // reset's `setOpenFiles([])` doesn't undo the reopened tabs. A file that no
  // longer exists on disk reopens as an error tab (existing fetchFile path).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!machineId || !cwd) return;
    if (restoredRef.current === instanceId) return;
    restoredRef.current = instanceId;
    const saved = loadFileTabs(window.localStorage, instanceId);
    if (saved.openFiles.length > 0) {
      // Reopen each tab in its saved surface so a diff reopens as a diff (which
      // also refetches its HEAD baseline via openFile's diff path).
      for (const tab of saved.openFiles)
        openFile(tab.path, {
          mode: tab.viewMode,
          scrollLine: tab.scrollLine,
          scrollOffset: tab.scrollOffset,
        });
      if (saved.activeFile) activateFile(saved.activeFile);
    }
    // Flip the persistence gate in a *later* commit (a state change forces a
    // re-render), by which point the reopened tabs have committed.
    setHydratedInstance(instanceId);
  }, [instanceId, machineId, cwd, openFile, activateFile]);

  // Persist open file tabs — gated on hydration so the empty pre-restore list
  // is never written over the saved layout.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (hydratedInstance !== instanceId) return;
    saveFileTabs(window.localStorage, instanceId, {
      openFiles: openFiles.map((f) => ({
        path: f.path,
        viewMode: f.viewMode,
        ...(f.scrollLine != null ? { scrollLine: f.scrollLine } : {}),
        ...(f.scrollOffset != null ? { scrollOffset: f.scrollOffset } : {}),
      })),
      activeFile: activeFilePath,
    });
  }, [openFiles, activeFilePath, hydratedInstance, instanceId]);

  const activeFile = activeFilePath
    ? openFiles.find((f) => f.path === activeFilePath) ?? null
    : null;

  return {
    listings,
    expanded,
    listingErrors,
    rootError,
    openFiles,
    activeFilePath,
    activeFile,
    toggleDir,
    revealDir,
    openFile,
    activateFile,
    setScrollAnchor,
    closeFileTab,
    refreshAll,
    setViewMode,
    setDiffBaseRef,
    autosaveEnabled,
    setAutosaveEnabled,
    updateDraft,
    saveFile: (path: string, opts?: { force?: boolean }) => saveFileRef.current(path, opts),
    reloadFromDisk: quietReload,
  };
}
