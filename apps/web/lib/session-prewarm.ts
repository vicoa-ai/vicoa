'use client';

/**
 * Prewarm a new session while the user is still typing its first message.
 *
 * Starting an agent (the process, then the agent's own engine) takes seconds
 * that do not depend on the prompt. When the composer gets its first input,
 * the client asks the machine's daemon to `prewarm-session` with exactly the
 * parameters the spawn will send, minus the prompt. The daemon starts that
 * session early and holds it; the `spawn-session` that follows is handed to it
 * instead of a cold start. Nothing reaches the server's session list until
 * then, and an unused prewarm is dropped by the daemon after a few minutes.
 *
 * The parameters must match the spawn's exactly (directory, agent, metadata,
 * profile), or the daemon cannot tell it is the same session and starts cold:
 * callers build both from the same values.
 *
 * On wherever the daemon supports it. The daemon decides per agent and answers
 * `skipped` for one it cannot start early; the server can switch the whole
 * feature off (SESSION_PREWARM_ENABLED=false) and a machine can opt out with
 * VICOA_PREWARM=0.
 */

import { readCapabilities, type WorktreeMode } from './worktree-selection';
import { getWsClient } from './ws-client';

/** Re-ask for the same session at most this often while the user types; the
 * daemon keeps it warm for a few minutes after each ask. */
export const PREWARM_REPEAT_MS = 30_000;

type MetadataShape = {
  metadata?: Record<string, unknown> | null;
  machine_metadata?: Record<string, unknown> | null;
};

/** Whether the machine's daemon serves `prewarm-session`. */
export function machineSupportsPrewarm(machine: MetadataShape | null | undefined): boolean {
  const caps = readCapabilities(machine);
  return Array.isArray(caps) && caps.some((c) => String(c) === 'prewarm');
}

export interface PrewarmConditions {
  machineSupports: boolean;
  worktreeMode: WorktreeMode;
  directory: string;
  /** Something is in the composer (typed, pasted, dictated or an image). */
  hasDraft: boolean;
  /** A send is in flight, or the composer cannot send (a blocking reason). */
  busy: boolean;
}

/**
 * Whether to prewarm now. Never for a new worktree: it is named from the
 * prompt before the agent starts, so nothing can start before the send. The
 * agent is the daemon's call (it skips agents it cannot start early).
 */
export function shouldPrewarm(c: PrewarmConditions): boolean {
  return (
    c.machineSupports &&
    c.worktreeMode !== 'new' &&
    c.directory.trim() !== '' &&
    c.hasDraft &&
    !c.busy
  );
}

type CallRpc = (
  machineId: string,
  method: string,
  params: Record<string, unknown>,
) => Promise<unknown>;

/**
 * Sends `prewarm-session`, at most once per `PREWARM_REPEAT_MS` for the same
 * machine and parameters. Changed parameters (another model, directory,
 * profile, ...) are a different session and go out at once. Best-effort: a
 * failure only means the spawn starts cold.
 */
export function createSessionPrewarmer(callRpc: CallRpc, now: () => number = Date.now) {
  const lastSent = new Map<string, number>();
  return {
    request(machineId: string, params: Record<string, unknown>): boolean {
      const key = JSON.stringify([machineId, params]);
      const at = now();
      const last = lastSent.get(key);
      if (last !== undefined && at - last < PREWARM_REPEAT_MS) return false;
      lastSent.set(key, at);
      if (lastSent.size > 50) {
        const oldest = lastSent.keys().next();
        if (!oldest.done) lastSent.delete(oldest.value);
      }
      void callRpc(machineId, 'prewarm-session', params).catch(() => {});
      return true;
    },
  };
}

let shared: ReturnType<typeof createSessionPrewarmer> | null = null;

/**
 * The page-wide prewarmer. Goes through the same connection as
 * `spawn-session` (the server relay), which resolves an agent profile's
 * instructions for both, so the two requests carry the same metadata.
 */
export function getSessionPrewarmer(): ReturnType<typeof createSessionPrewarmer> {
  if (!shared) {
    shared = createSessionPrewarmer((machineId, method, params) =>
      getWsClient().callRpc(machineId, method, params),
    );
  }
  return shared;
}
