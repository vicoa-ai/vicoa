'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, CircleAlert, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  rpcWorktreeRunSetup,
  rpcWorktreeSetupStatus,
  type WorktreeSetupStatus,
} from '@/components/files-git-panel/rpc';

/** Poll cadence while a run is in flight. Setup is `npm ci`-scale, so 1.5s is
 *  plenty responsive without hammering the daemon's WS. */
const POLL_MS = 1500;
/** How long "Setup done" lingers before the chip disappears. */
const DONE_LINGER_MS = 8000;
/** A run that finished longer ago than this isn't news — don't resurface it on
 *  every page load; only a failure stays until the user retries or dismisses. */
const RECENT_MS = 2 * 60 * 1000;

type Known = Exclude<WorktreeSetupStatus, { status: 'none' }>;

/**
 * Chat-header chip (right cluster, before Share) for the session worktree's
 * setup run (committed vicoa.json, executed by the daemon in the background).
 * Sized like the icon buttons beside it. Reads the daemon's run record over
 * `worktree-setup-status`: spinner + "Setup 3/7" while running, a brief "Setup
 * done", or a persistent "Setup failed" — click for the per-command outcome and
 * the log tail, with a Retry. Renders nothing when the daemon has no record
 * (not a worktree session, no config, or an old daemon that left setup to the
 * terminal) or the RPC errors.
 */
export function WorktreeSetupBadge({
  machineId,
  cwd,
}: {
  machineId: string | null;
  cwd: string | null;
}) {
  const [status, setStatus] = useState<Known | null>(null);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // Bumped after a retry so the poll effect below restarts against the fresh run.
  const [pollKey, setPollKey] = useState(0);
  // Tracks whether THIS mount saw the run in flight, so a completion that
  // happens under our eyes shows "Setup done" while a stale success from a
  // previous visit stays quiet.
  const sawRunningRef = useRef(false);

  const fetchStatus = useCallback(async (): Promise<Known | null> => {
    if (!machineId || !cwd) return null;
    try {
      const s = await rpcWorktreeSetupStatus(machineId, cwd);
      return s.status === 'none' ? null : s;
    } catch {
      return null;
    }
  }, [machineId, cwd]);

  useEffect(() => {
    setStatus(null);
    setDismissed(false);
    // A retry keeps the "saw it running" memory: the user asked for this run.
    if (pollKey === 0) sawRunningRef.current = false;
    if (!machineId || !cwd) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      timer = null;
      const s = await fetchStatus();
      if (cancelled) return;
      if (s?.status === 'running') sawRunningRef.current = true;
      setStatus(s);
      if (s?.status === 'running') {
        timer = setTimeout(() => void tick(), POLL_MS);
      }
    };
    void tick();
    // A terminal `npm ci` finishing while the tab was hidden: refresh on return.
    const onVisibility = () => {
      if (document.visibilityState === 'visible' && timer === null) void tick();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [machineId, cwd, fetchStatus, pollKey]);

  // "Setup done" lingers briefly, then the chip goes away on its own.
  useEffect(() => {
    if (status?.status !== 'succeeded' || open) return;
    const t = setTimeout(() => setDismissed(true), DONE_LINGER_MS);
    return () => clearTimeout(t);
  }, [status?.status, open]);

  const retry = useCallback(async () => {
    if (!machineId || status === null || status.status === 'running') return;
    setRetrying(true);
    try {
      await rpcWorktreeRunSetup(machineId, status.worktree_path, status.source_repo);
      sawRunningRef.current = true;
      // Restart the poll loop against the fresh record.
      setPollKey((k) => k + 1);
    } catch {
      /* daemon offline / untrusted — the chip keeps showing the old outcome */
    } finally {
      setRetrying(false);
    }
  }, [machineId, status]);

  if (status === null || dismissed) return null;
  // An old success (page reload minutes later) isn't worth a chip. A failure is,
  // until the user looks at it.
  if (
    status.status === 'succeeded' &&
    !sawRunningRef.current &&
    status.finished_at !== null &&
    Date.now() - status.finished_at * 1000 > RECENT_MS
  ) {
    return null;
  }

  const finished = status.commands.filter((c) => c.status === 'ok').length;
  const runningIndex = status.commands.find((c) => c.status === 'running')?.index ?? null;
  const label =
    status.status === 'running'
      ? `Setup ${runningIndex ?? finished + 1}/${status.total}`
      : status.status === 'succeeded'
        ? 'Setup done'
        : 'Setup failed';
  const tone =
    status.status === 'failed'
      ? 'text-destructive hover:bg-destructive/10'
      : status.status === 'succeeded'
        ? 'text-success hover:bg-success/10'
        : 'text-muted-foreground hover:bg-muted';
  const failedStep = status.commands.find((c) => c.status === 'failed') ?? null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Worktree setup — click for details"
        className={`mr-1 inline-flex h-8 flex-shrink-0 cursor-pointer items-center gap-1.5 rounded px-2 font-mono text-sm ${tone}`}
      >
        {status.status === 'running' ? (
          <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" />
        ) : status.status === 'succeeded' ? (
          <Check className="h-3.5 w-3.5 flex-shrink-0" />
        ) : (
          <CircleAlert className="h-3.5 w-3.5 flex-shrink-0" />
        )}
        <span>{label}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Worktree setup</DialogTitle>
            <DialogDescription>
              {status.status === 'running'
                ? 'Running the repository’s setup commands in this worktree on the machine.'
                : status.status === 'succeeded'
                  ? 'All setup commands finished.'
                  : failedStep
                    ? `Stopped at step ${failedStep.index}${
                        failedStep.timed_out
                          ? ' (timed out)'
                          : failedStep.aborted
                            ? ' (aborted)'
                            : failedStep.exit_code !== null
                              ? ` (exit ${failedStep.exit_code})`
                              : ''
                      }. Later steps did not run.`
                    : 'Setup did not complete.'}
            </DialogDescription>
          </DialogHeader>
          <ol className="space-y-1 text-xs font-mono">
            {status.commands.map((c) => (
              <li key={c.index} className="flex items-start gap-2">
                <span className="mt-0.5 w-3.5 flex-shrink-0">
                  {c.status === 'ok' ? (
                    <Check className="h-3.5 w-3.5 text-success" />
                  ) : c.status === 'failed' ? (
                    <CircleAlert className="h-3.5 w-3.5 text-destructive" />
                  ) : c.status === 'running' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : (
                    <span className="block h-3.5 w-3.5 text-center text-muted-foreground">·</span>
                  )}
                </span>
                <span
                  className={`break-all ${
                    c.status === 'pending' ? 'text-muted-foreground' : ''
                  }`}
                >
                  {c.command}
                </span>
              </li>
            ))}
          </ol>
          {status.output_tail.length > 0 && (
            <pre className="custom-scrollbar max-h-64 overflow-auto rounded bg-muted p-3 text-xs font-mono whitespace-pre-wrap">
              {status.output_tail}
            </pre>
          )}
          <DialogFooter>
            <Button variant="outline" className="cursor-pointer" onClick={() => setOpen(false)}>
              Close
            </Button>
            {status.status !== 'running' && (
              <Button
                className="cursor-pointer"
                disabled={retrying}
                onClick={() => void retry()}
              >
                {retrying ? 'Starting…' : 'Run setup again'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
