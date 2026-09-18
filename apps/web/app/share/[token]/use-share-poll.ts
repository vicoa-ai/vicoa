'use client';

// Polling for the public share viewer (collaboration §9, old plan D4).
//
// Viewers poll rather than open a socket: polling lands on the stateless,
// horizontally scalable `backend` app, while a WebSocket would land on the
// relay pinned to one worker that also carries every daemon socket. The cost
// is latency only — a message arrives whole either way — and a 5 s cadence
// while the tab is visible and the session active reads as live to a
// spectator. Hidden tabs and finished sessions drop to 30 s, and every
// return to the tab refreshes immediately.

import { useCallback, useEffect, useRef, useState } from 'react';

export const POLL_ACTIVE_MS = 5_000;
export const POLL_IDLE_MS = 30_000;

/** Whether the document is visible (true during SSR so the first client render matches). */
export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    update();
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  return visible;
}

/**
 * Run `tick` every `intervalMs`, plus immediately on focus / becoming visible.
 * Overlapping runs are skipped (a slow poll never stacks), and an unmounted
 * component's late result is ignored via the returned `alive` guard.
 */
export function useSharePoll(
  tick: () => Promise<void>,
  { intervalMs, enabled = true }: { intervalMs: number; enabled?: boolean },
): { refresh: () => void } {
  const tickRef = useRef(tick);
  tickRef.current = tick;
  const runningRef = useRef(false);

  const run = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    try {
      await tickRef.current();
    } catch {
      // The tick owns its error state; a rejected poll must not kill the loop.
    } finally {
      runningRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => void run(), intervalMs);
    const onFocus = () => void run();
    const onVisible = () => {
      if (document.visibilityState === 'visible') void run();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled, intervalMs, run]);

  return { refresh: () => void run() };
}
