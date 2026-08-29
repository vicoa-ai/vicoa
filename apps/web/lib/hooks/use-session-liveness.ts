'use client';

import { useEffect, useMemo, useState } from 'react';

import { resolveLiveState, type LiveState } from '@/lib/session-liveness';

/** How often liveness is recomputed. Heartbeats are 30s, so 15s is ~2x. */
const DEFAULT_TICK_MS = 15_000;

/**
 * A clock that advances on an interval, to re-render time-derived UI.
 *
 * Liveness decays with elapsed time rather than in response to an event, so
 * without a tick a session that dies while the user is looking at the list
 * would keep rendering as alive until something else forced a re-render.
 */
export function useNow(intervalMs: number = DEFAULT_TICK_MS): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
}

export interface LivenessInstance {
  last_heartbeat_at?: string | null;
  machine_id?: string | null;
  live_state?: LiveState;
}

/**
 * Live state for one session, recomputed on a timer.
 *
 * `machine` is optional. When the caller has the owning machine we derive the
 * full answer; when it doesn't, we can still prove the session is alive from
 * its own heartbeat, and otherwise fall back to the server's snapshot rather
 * than guessing "machine offline" from missing data.
 */
export function useSessionLiveness(
  instance: LivenessInstance | null | undefined,
  machine?: { last_heartbeat_at?: string | null } | null
): LiveState {
  const now = useNow();

  return useMemo(
    () => resolveLiveState(instance, machine, now),
    [instance, machine, now]
  );
}
