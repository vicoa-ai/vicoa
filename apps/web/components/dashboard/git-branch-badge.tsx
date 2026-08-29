'use client';

import { useEffect, useState } from 'react';
import { GitBranch } from 'lucide-react';
import { rpcGitStatus } from '@/components/files-git-panel/rpc';

/**
 * Chat-header badge: the session project's current git branch, fetched over
 * the machine's git-status RPC. Renders nothing until a branch is known
 * (no machine, not a repo, RPC error → stays hidden). Refreshes when the
 * window returns to the foreground, since a terminal checkout can change the
 * branch underneath us.
 */
export function GitBranchBadge({
  machineId,
  cwd,
}: {
  machineId: string | null;
  cwd: string | null;
}) {
  const [branch, setBranch] = useState<string | null>(null);

  useEffect(() => {
    setBranch(null);
    if (!machineId || !cwd) return;
    let cancelled = false;
    const fetchBranch = () => {
      rpcGitStatus(machineId, cwd)
        .then((status) => {
          if (!cancelled) setBranch(status.branch);
        })
        .catch(() => {
          if (!cancelled) setBranch(null);
        });
    };
    fetchBranch();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') fetchBranch();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [machineId, cwd]);

  if (!branch) return null;

  return (
    <span className="ml-1.5 flex min-w-0 items-center gap-1 font-mono text-sm text-muted-foreground">
      <GitBranch className="h-3.5 w-3.5 flex-shrink-0" />
      <span className="truncate">{branch}</span>
    </span>
  );
}
