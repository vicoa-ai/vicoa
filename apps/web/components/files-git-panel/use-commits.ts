'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CommitEntry, CommitFilesResult, GitDiffResult, RefRevision } from './rpc';
import { rpcGitCommitDiff, rpcGitCommitFiles, rpcGitLog } from './rpc';
import { ConcurrencyQueue } from './concurrency';
import { RpcError } from '@/lib/ws-client';

const PAGE = 50;
const MAX = 200;

export interface CommitFilesEntry {
  loading: boolean;
  result: CommitFilesResult | null;
  error: string | null;
}

export interface CommitDiffEntry {
  loading: boolean;
  result: GitDiffResult | null;
  error: string | null;
}

export function fileKey(commitId: string, path: string): string {
  return `${commitId}:${path}`;
}

interface Args {
  machineId: string | null;
  cwd: string | null;
}

export function useCommits({ machineId, cwd }: Args) {
  const [commits, setCommits] = useState<CommitEntry[]>([]);
  const [logLoading, setLogLoading] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [currentRef, setCurrentRef] = useState<RefRevision | undefined>();
  const [upstreamRef, setUpstreamRef] = useState<RefRevision | undefined>();
  const [expandedCommits, setExpandedCommits] = useState<Set<string>>(new Set());
  const [filesByCommit, setFilesByCommit] = useState<Map<string, CommitFilesEntry>>(new Map());
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [commitDiffs, setCommitDiffs] = useState<Map<string, CommitDiffEntry>>(new Map());
  const queueRef = useRef(new ConcurrencyQueue(6));

  const machineIdRef = useRef(machineId);
  const cwdRef = useRef(cwd);
  machineIdRef.current = machineId;
  cwdRef.current = cwd;

  const fetchLog = useCallback(async (nextLimit: number) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    setLogLoading(true);
    try {
      const result = await rpcGitLog(mId, c, nextLimit);
      setCommits(result.commits);
      setHasMore(result.has_more);
      setCurrentRef(result.current_ref);
      setUpstreamRef(result.upstream_ref);
      setLogError(null);
    } catch (err) {
      setLogError(err instanceof RpcError ? err.code : 'unknown');
    } finally {
      setLogLoading(false);
    }
  }, []);

  // Reset + fetch on session change (mirrors use-git-tab's single-effect reset).
  useEffect(() => {
    setCommits([]);
    setHasMore(false);
    setLimit(PAGE);
    setExpandedCommits(new Set());
    setFilesByCommit(new Map());
    setExpandedFiles(new Set());
    setCommitDiffs(new Map());
    setLogError(null);
    if (machineId && cwd) void fetchLog(PAGE);
  }, [machineId, cwd, fetchLog]);

  const fetchFiles = useCallback(async (commitId: string) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    setFilesByCommit((prev) =>
      new Map(prev).set(commitId, { loading: true, result: null, error: null }),
    );
    try {
      const result = await queueRef.current.run(() => rpcGitCommitFiles(mId, c, commitId));
      setFilesByCommit((prev) =>
        new Map(prev).set(commitId, { loading: false, result, error: null }),
      );
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setFilesByCommit((prev) =>
        new Map(prev).set(commitId, { loading: false, result: null, error: code }),
      );
    }
  }, []);

  const fetchDiff = useCallback(async (commitId: string, path: string) => {
    const mId = machineIdRef.current;
    const c = cwdRef.current;
    if (!mId || !c) return;
    const key = fileKey(commitId, path);
    setCommitDiffs((prev) =>
      new Map(prev).set(key, { loading: true, result: null, error: null }),
    );
    try {
      const result = await queueRef.current.run(() => rpcGitCommitDiff(mId, c, commitId, path));
      setCommitDiffs((prev) => new Map(prev).set(key, { loading: false, result, error: null }));
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'unknown';
      setCommitDiffs((prev) =>
        new Map(prev).set(key, { loading: false, result: null, error: code }),
      );
    }
  }, []);

  const toggleCommit = useCallback(
    (commitId: string) => {
      setExpandedCommits((prev) => {
        const next = new Set(prev);
        if (next.has(commitId)) {
          next.delete(commitId);
        } else {
          next.add(commitId);
          setFilesByCommit((fbc) => {
            if (!fbc.has(commitId)) void fetchFiles(commitId);
            return fbc;
          });
        }
        return next;
      });
    },
    [fetchFiles],
  );

  const toggleFile = useCallback(
    (commitId: string, path: string) => {
      const key = fileKey(commitId, path);
      setExpandedFiles((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          setCommitDiffs((cd) => {
            if (!cd.has(key)) void fetchDiff(commitId, path);
            return cd;
          });
        }
        return next;
      });
    },
    [fetchDiff],
  );

  const loadMore = useCallback(() => {
    setLimit((prev) => {
      const next = Math.min(prev + PAGE, MAX);
      if (next !== prev) void fetchLog(next);
      return next;
    });
  }, [fetchLog]);

  const refresh = useCallback(() => {
    void fetchLog(limit);
  }, [fetchLog, limit]);

  return {
    commits,
    logLoading,
    logError,
    hasMore,
    currentRef,
    upstreamRef,
    expandedCommits,
    filesByCommit,
    expandedFiles,
    commitDiffs,
    toggleCommit,
    toggleFile,
    loadMore,
    refresh,
  };
}
