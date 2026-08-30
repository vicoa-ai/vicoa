'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { GitDiffResult, GitStatusResult } from './rpc';
import { rpcGitCommit, rpcGitDiff, rpcGitStage, rpcGitStatus, rpcGitUnstage } from './rpc';
import { ConcurrencyQueue, diffKey, submoduleCwd, submoduleFileKey } from './concurrency';
import { RpcError } from '@/lib/ws-client';

interface UseGitTabArgs {
  machineId: string | null;
  cwd: string | null;
}

export interface DiffEntry {
  key: string;
  path: string;
  staged: boolean;
  loading: boolean;
  result: GitDiffResult | null;
  error: string | null;
  /** Set only for diffs of a file *inside* a submodule: the submodule's path in
   * the parent repo. Needed to re-fetch, since `path` is submodule-relative. */
  sub?: string;
}

/** A submodule row expanded into the submodule's own working-tree status —
 *  its *active* changes (HEAD vs worktree), not everything committed since the
 *  parent last bumped the pin. */
export interface SubmoduleEntry {
  key: string;
  path: string;
  loading: boolean;
  result: GitStatusResult | null;
  error: string | null;
}

interface UseGitTabApi {
  status: GitStatusResult | null;
  statusLoading: boolean;
  statusError: string | null;
  diffs: Map<string, DiffEntry>;
  expanded: Set<string>;
  hideWhitespace: boolean;
  wrapLines: boolean;
  splitView: boolean;
  /** Render the changed-file sections as a folder tree instead of a flat list.
   *  A persisted global preference, like the diff toggles. */
  treeView: boolean;
  expandSubmodules: boolean;
  submodules: Map<string, SubmoduleEntry>;
  submoduleDiffs: Map<string, DiffEntry>;
  expandedSubFiles: Set<string>;
  /** Paths with an in-flight stage/unstage — their row buttons disable. */
  pendingPaths: Set<string>;
  /** Last stage/unstage/commit failure, human-readable. Cleared on the next
   *  attempt (or explicitly). */
  writeError: string | null;
  committing: boolean;
  /** Commit-message draft. Lives here (not in the tab component) so it
   *  survives switching to Files/terminals and back; cleared on commit. */
  commitMessage: string;
  setCommitMessage: (next: string) => void;
  toggleHideWhitespace: () => void;
  toggleWrap: () => void;
  toggleSplitView: () => void;
  setSplitView: (next: boolean) => void;
  toggleTreeView: () => void;
  toggleExpandSubmodules: () => void;
  toggleExpand: (path: string, staged: boolean) => void;
  toggleSubFile: (sub: string, file: string, staged: boolean) => void;
  stagePath: (path: string) => void;
  unstagePath: (path: string) => void;
  /** Commit the staged files. Resolves true on success (callers clear the
   *  message box); failures land in `writeError`. */
  commit: (message: string) => Promise<boolean>;
  clearWriteError: () => void;
  expandAll: () => void;
  collapseAll: () => void;
  refresh: () => void;
}

/** Transport-level RPC failures mapped to copy the Changes tab can show. Git's
 *  own failures (hook rejected, identity unset…) carry git's message instead. */
function gitWriteErrorText(code: string): string {
  if (code === 'no_handler') {
    return 'Update the daemon on this machine (`pip install -U vicoa`) to stage and commit from here.';
  }
  if (code === 'target_disconnected' || code === 'timeout' || code === 'not_connected') {
    return 'Machine offline — try again when it reconnects.';
  }
  return `Git operation failed (${code})`;
}

export function useGitTab(args: UseGitTabArgs): UseGitTabApi {
  const { machineId, cwd } = args;
  const [status, setStatus] = useState<GitStatusResult | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [diffs, setDiffs] = useState<Map<string, DiffEntry>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [hideWhitespace, setHideWhitespace] = useState(false);
  const [wrapLines, setWrapLines] = useState(true);
  const [splitView, setSplitViewState] = useState(false);
  const [treeView, setTreeView] = useState(false);
  const [expandSubmodules, setExpandSubmodules] = useState(false);
  const [pendingPaths, setPendingPaths] = useState<Set<string>>(new Set());
  const [writeError, setWriteError] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [commitMessage, setCommitMessage] = useState('');
  const [submodules, setSubmodules] = useState<Map<string, SubmoduleEntry>>(new Map());
  const [submoduleDiffs, setSubmoduleDiffs] = useState<Map<string, DiffEntry>>(new Map());
  const [expandedSubFiles, setExpandedSubFiles] = useState<Set<string>>(new Set());
  const queueRef = useRef(new ConcurrencyQueue(6));

  // `toggleExpand` needs to know whether a row is a gitlink to pick which RPC
  // to fire, but it must not re-create itself on every status refresh.
  const statusRef = useRef(status);
  statusRef.current = status;
  const expandSubmodulesRef = useRef(expandSubmodules);
  expandSubmodulesRef.current = expandSubmodules;
  const hideWhitespaceRef = useRef(hideWhitespace);
  hideWhitespaceRef.current = hideWhitespace;

  const isSubmodulePath = useCallback((path: string, staged: boolean): boolean => {
    const s = statusRef.current;
    if (!s) return false;
    const list = staged ? s.staged : s.unstaged;
    return list.some((e) => e.path === path && e.is_submodule === true);
  }, []);

  const machineIdRef = useRef(machineId);
  const cwdRef = useRef(cwd);
  machineIdRef.current = machineId;
  cwdRef.current = cwd;

  const fetchStatus = useCallback(async () => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    setStatusLoading(true);
    try {
      const result = await rpcGitStatus(mId, c);
      setStatus(result);
      setStatusError(null);
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setStatusError(code);
      // Leave `status` untouched so any previously-loaded status stays visible.
    } finally {
      setStatusLoading(false);
    }
  }, []);

  // Reset + fetch in a single effect so the reset's `setStatus(null)` is
  // guaranteed to be applied before the auto-fetch decision is made.
  // (Splitting them caused the fetch effect's closure to read a stale `status`
  // from the previous session and short-circuit, leaving the Git tab stuck on
  // a skeleton until a full page reload.)
  useEffect(() => {
    setStatus(null);
    setDiffs(new Map());
    setExpanded(new Set());
    setStatusError(null);
    setSubmodules(new Map());
    setSubmoduleDiffs(new Map());
    setExpandedSubFiles(new Set());
    setWriteError(null);
    setCommitMessage('');
    if (machineId && cwd) {
      void fetchStatus();
    }
  }, [machineId, cwd, fetchStatus]);

  const fetchDiff = useCallback(
    async (path: string, staged: boolean) => {
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return;
      const key = diffKey(path, staged);
      setDiffs((prev) => {
        const next = new Map(prev);
        next.set(key, { key, path, staged, loading: true, result: null, error: null });
        return next;
      });
      const hw = hideWhitespace;
      try {
        const result = await queueRef.current.run(() => rpcGitDiff(mId, c, path, staged, hw));
        setDiffs((prev) => {
          const next = new Map(prev);
          next.set(key, { key, path, staged, loading: false, result, error: null });
          return next;
        });
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'unknown';
        setDiffs((prev) => {
          const next = new Map(prev);
          next.set(key, { key, path, staged, loading: false, result: null, error: code });
          return next;
        });
      }
    },
    [hideWhitespace],
  );

  /** Load a submodule's own working-tree status. A submodule is a full repo, so
   *  this is just `git-status` re-pointed at its directory. */
  const fetchSubmoduleStatus = useCallback(async (path: string, staged: boolean) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    const key = diffKey(path, staged);
    setSubmodules((prev) => {
      const next = new Map(prev);
      next.set(key, { key, path, loading: true, result: null, error: null });
      return next;
    });
    try {
      const result = await queueRef.current.run(() =>
        rpcGitStatus(mId, submoduleCwd(c, path)),
      );
      setSubmodules((prev) => {
        const next = new Map(prev);
        next.set(key, { key, path, loading: false, result, error: null });
        return next;
      });
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setSubmodules((prev) => {
        const next = new Map(prev);
        next.set(key, { key, path, loading: false, result: null, error: code });
        return next;
      });
    }
  }, []);

  const fetchSubmoduleDiff = useCallback(
    async (sub: string, file: string, staged: boolean) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    const key = submoduleFileKey(sub, file, staged);
    const hw = hideWhitespaceRef.current;
    setSubmoduleDiffs((prev) => {
      const next = new Map(prev);
      next.set(key, { key, path: file, sub, staged, loading: true, result: null, error: null });
      return next;
    });
    try {
      const result = await queueRef.current.run(() =>
        rpcGitDiff(mId, submoduleCwd(c, sub), file, staged, hw),
      );
      setSubmoduleDiffs((prev) => {
        const next = new Map(prev);
        next.set(key, { key, path: file, sub, staged, loading: false, result, error: null });
        return next;
      });
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setSubmoduleDiffs((prev) => {
        const next = new Map(prev);
        next.set(key, { key, path: file, sub, staged, loading: false, result: null, error: code });
        return next;
      });
    }
    },
    [],
  );

  const toggleExpand = useCallback(
    (path: string, staged: boolean) => {
      const key = diffKey(path, staged);
      // A gitlink row with the toggle on loads its inner file list instead of
      // the "Subproject commit a..b" diff the parent repo would otherwise give.
      const asSubmodule = expandSubmodulesRef.current && isSubmodulePath(path, staged);
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          if (asSubmodule) {
            if (!submodules.has(key)) void fetchSubmoduleStatus(path, staged);
          } else if (!diffs.has(key)) {
            void fetchDiff(path, staged);
          }
        }
        return next;
      });
    },
    [diffs, submodules, fetchDiff, fetchSubmoduleStatus, isSubmodulePath],
  );

  const toggleSubFile = useCallback(
    (sub: string, file: string, staged: boolean) => {
      const key = submoduleFileKey(sub, file, staged);
      setExpandedSubFiles((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          if (!submoduleDiffs.has(key)) void fetchSubmoduleDiff(sub, file, staged);
        }
        return next;
      });
    },
    [submoduleDiffs, fetchSubmoduleDiff],
  );

  /** Switch gitlink rows between "Subproject commit a..b" and the real changes.
   *  Any submodule row already open is re-fetched in the new representation so
   *  the toggle takes effect without a manual collapse/expand. */
  const toggleExpandSubmodules = useCallback(() => {
    const next = !expandSubmodules;
    setExpandSubmodules(next);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('vicoa:git:expand-submodules', next ? '1' : '0');
    }
    // Kept in sync eagerly: `toggleExpand` reads the ref, and a row can be
    // clicked before React commits this state update.
    expandSubmodulesRef.current = next;
    const s = statusRef.current;
    if (!s) return;
    for (const [list, staged] of [
      [s.staged, true],
      [s.unstaged, false],
    ] as const) {
      for (const entry of list) {
        if (!entry.is_submodule) continue;
        const key = diffKey(entry.path, staged);
        if (!expanded.has(key)) continue;
        if (next) {
          if (!submodules.has(key)) void fetchSubmoduleStatus(entry.path, staged);
        } else if (!diffs.has(key)) {
          void fetchDiff(entry.path, staged);
        }
      }
    }
  }, [expandSubmodules, expanded, submodules, diffs, fetchSubmoduleStatus, fetchDiff]);

  const expandAll = useCallback(() => {
    if (!status) return;
    const keys = new Set<string>();
    const enqueue = (path: string, staged: boolean, isSubmodule?: boolean) => {
      const k = diffKey(path, staged);
      keys.add(k);
      if (expandSubmodules && isSubmodule) {
        if (!submodules.has(k)) void fetchSubmoduleStatus(path, staged);
        return;
      }
      if (!diffs.has(k)) void fetchDiff(path, staged);
    };
    status.staged.forEach((e) => enqueue(e.path, true, e.is_submodule));
    status.unstaged.forEach((e) => enqueue(e.path, false, e.is_submodule));
    status.untracked.forEach((e) => enqueue(e.path, false));
    setExpanded(keys);
  }, [diffs, submodules, fetchDiff, fetchSubmoduleStatus, expandSubmodules, status]);

  // Inner submodule files stay collapsed too, so re-expanding a submodule
  // doesn't dump every one of its file diffs back onto the screen.
  const collapseAll = useCallback(() => {
    setExpanded(new Set());
    setExpandedSubFiles(new Set());
  }, []);

  const refresh = useCallback(() => {
    void fetchStatus();
    for (const entry of diffs.values()) {
      if (expanded.has(entry.key)) {
        void fetchDiff(entry.path, entry.staged);
      }
    }
    for (const entry of submodules.values()) {
      if (expandSubmodules && expanded.has(entry.key)) {
        void fetchSubmoduleStatus(entry.path, entry.key.startsWith('S:'));
      }
    }
    for (const [key, entry] of submoduleDiffs) {
      if (!expandedSubFiles.has(key) || !entry.sub) continue;
      void fetchSubmoduleDiff(entry.sub, entry.path, entry.staged);
    }
  }, [
    fetchStatus,
    diffs,
    expanded,
    fetchDiff,
    expandSubmodules,
    submodules,
    fetchSubmoduleStatus,
    submoduleDiffs,
    expandedSubFiles,
    fetchSubmoduleDiff,
  ]);

  const toggleHideWhitespace = useCallback(() => {
    setHideWhitespace((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('vicoa:git:hide-whitespace', next ? '1' : '0');
      }
      // Invalidate existing diffs since the ignore-whitespace flag has changed.
      const expandedSnapshot = new Set(expanded);
      setDiffs(new Map());
      // Re-fetch the currently expanded set with the new flag.
      // We defer the calls so React commits the empty map before we re-populate.
      setTimeout(() => {
        for (const key of expandedSnapshot) {
          const found = diffs.get(key);
          if (found) {
            const mId = machineIdRef.current;
            const c = cwdRef.current;
            if (!mId || !c) return;
            void queueRef.current
              .run(() => rpcGitDiff(mId, c, found.path, found.staged, next))
              .then(
                (result) => {
                  setDiffs((prev) => {
                    const m = new Map(prev);
                    m.set(found.key, {
                      key: found.key,
                      path: found.path,
                      staged: found.staged,
                      loading: false,
                      result,
                      error: null,
                    });
                    return m;
                  });
                },
                (err) => {
                  const code = err instanceof RpcError ? err.code : 'unknown';
                  setDiffs((prev) => {
                    const m = new Map(prev);
                    m.set(found.key, {
                      key: found.key,
                      path: found.path,
                      staged: found.staged,
                      loading: false,
                      result: null,
                      error: code,
                    });
                    return m;
                  });
                },
              );
          }
        }
      }, 0);
      // Submodule file diffs take the same -w flag, so they're stale now too.
      // `hideWhitespaceRef` is already updated, so the re-fetch picks up `next`.
      hideWhitespaceRef.current = next;
      const staleSubFiles = Array.from(submoduleDiffs.values()).filter(
        (e) => e.sub && expandedSubFiles.has(e.key),
      );
      setSubmoduleDiffs(new Map());
      setTimeout(() => {
        for (const entry of staleSubFiles) {
          if (entry.sub) void fetchSubmoduleDiff(entry.sub, entry.path, entry.staged);
        }
      }, 0);
      return next;
    });
  }, [diffs, expanded, submoduleDiffs, expandedSubFiles, fetchSubmoduleDiff]);

  const toggleWrap = useCallback(() => {
    setWrapLines((v) => {
      const next = !v;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('vicoa:git:word-wrap', next ? '1' : '0');
      }
      return next;
    });
  }, []);
  const toggleSplitView = useCallback(() => {
    setSplitViewState((v) => {
      const next = !v;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('vicoa:git:split-view', next ? '1' : '0');
      }
      return next;
    });
  }, []);
  const setSplitView = useCallback((next: boolean) => setSplitViewState(next), []);

  // The git tab's view toggles are persisted global preferences, hydrated
  // post-mount (reading localStorage during render would mismatch the server
  // render). Word wrap defaults on, so only an explicit '0' turns it off; the
  // rest default off.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const ls = window.localStorage;
    setTreeView(ls.getItem('vicoa:git:tree-view') === '1');
    setWrapLines(ls.getItem('vicoa:git:word-wrap') !== '0');
    setHideWhitespace(ls.getItem('vicoa:git:hide-whitespace') === '1');
    setExpandSubmodules(ls.getItem('vicoa:git:expand-submodules') === '1');
    setSplitViewState(ls.getItem('vicoa:git:split-view') === '1');
  }, []);
  const toggleTreeView = useCallback(() => {
    setTreeView((v) => {
      const next = !v;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('vicoa:git:tree-view', next ? '1' : '0');
      }
      return next;
    });
  }, []);

  /** Stage or unstage one path, then re-pull status. The row jumps sections,
   *  so both of its diff keys (and their expansion) are stale — drop them. */
  const applyStage = useCallback(
    async (path: string, stage: boolean) => {
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return;
      setWriteError(null);
      setPendingPaths((prev) => new Set(prev).add(path));
      try {
        const outcome = stage
          ? await rpcGitStage(mId, c, [path])
          : await rpcGitUnstage(mId, c, [path]);
        if (!outcome.ok) {
          setWriteError(outcome.message);
        } else {
          const stale = [diffKey(path, true), diffKey(path, false)];
          setDiffs((prev) => {
            const next = new Map(prev);
            stale.forEach((k) => next.delete(k));
            return next;
          });
          setExpanded((prev) => {
            const next = new Set(prev);
            stale.forEach((k) => next.delete(k));
            return next;
          });
        }
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'unknown';
        setWriteError(gitWriteErrorText(code));
      } finally {
        setPendingPaths((prev) => {
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
        void fetchStatus();
      }
    },
    [fetchStatus],
  );
  const stagePath = useCallback((path: string) => void applyStage(path, true), [applyStage]);
  const unstagePath = useCallback((path: string) => void applyStage(path, false), [applyStage]);

  const commit = useCallback(
    async (message: string): Promise<boolean> => {
      const mId = machineIdRef.current;
      const c = cwdRef.current;
      if (!mId || !c) return false;
      setWriteError(null);
      setCommitting(true);
      try {
        const outcome = await rpcGitCommit(mId, c, message);
        if (!outcome.ok) {
          setWriteError(outcome.message);
          return false;
        }
        // Everything staged just left the working tree — open diffs are stale.
        setDiffs(new Map());
        setExpanded(new Set());
        setCommitMessage('');
        return true;
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'unknown';
        setWriteError(gitWriteErrorText(code));
        return false;
      } finally {
        setCommitting(false);
        void fetchStatus();
      }
    },
    [fetchStatus],
  );

  const clearWriteError = useCallback(() => setWriteError(null), []);

  return {
    status,
    statusLoading,
    statusError,
    diffs,
    expanded,
    hideWhitespace,
    wrapLines,
    splitView,
    treeView,
    expandSubmodules,
    submodules,
    submoduleDiffs,
    expandedSubFiles,
    pendingPaths,
    writeError,
    committing,
    commitMessage,
    setCommitMessage,
    toggleHideWhitespace,
    toggleWrap,
    toggleSplitView,
    setSplitView,
    toggleTreeView,
    toggleExpandSubmodules,
    toggleExpand,
    toggleSubFile,
    stagePath,
    unstagePath,
    commit,
    clearWriteError,
    expandAll,
    collapseAll,
    refresh,
  };
}
