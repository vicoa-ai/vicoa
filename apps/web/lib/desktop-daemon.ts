/**
 * The desktop daemon's cloud link — renderer side of the preload bridge
 * (electron/src/main.ts `publishCloudState`).
 *
 * Only the desktop shell can know this: the daemon is its child process, and
 * the status comes from polling that daemon's own `/healthz`. The web build
 * has no bridge, so every consumer no-ops there.
 *
 * `detail` is the server's own sentence for a refused link. It is shown
 * verbatim — only the server knows which limit was hit and what the plan
 * allows, so rewording it here would eventually lie.
 */

import { useSyncExternalStore } from 'react';

/** Mirror of `CloudStatus` in electron/src/daemon-manager.ts. */
export type DaemonCloudStatus =
  | 'connecting'
  | 'connected'
  | 'auth_failed'
  | 'machine_limit'
  | null;

export interface DaemonCloudState {
  status: DaemonCloudStatus;
  detail: string;
}

const UNKNOWN: DaemonCloudState = { status: null, detail: '' };

interface DesktopDaemonBridge {
  getCloudState: () => DaemonCloudState;
  onCloudState: (cb: (state: DaemonCloudState) => void) => () => void;
  restart: () => Promise<boolean>;
}

function getBridge(): DesktopDaemonBridge | null {
  if (typeof window === 'undefined') return null;
  const bridge = (window as unknown as { vicoaDesktopDaemon?: DesktopDaemonBridge })
    .vicoaDesktopDaemon;
  return bridge && typeof bridge.onCloudState === 'function' ? bridge : null;
}

// One subscription to the bridge; every consumer shares the snapshot.
let cached: DaemonCloudState = UNKNOWN;
let subscribed = false;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function ensureSubscription(): void {
  if (subscribed) return;
  const bridge = getBridge();
  if (!bridge) return; // web/SSR: stay unknown, never subscribe
  subscribed = true;
  try {
    cached = bridge.getCloudState() ?? UNKNOWN;
  } catch {
    cached = UNKNOWN;
  }
  bridge.onCloudState((state) => {
    cached = state ?? UNKNOWN;
    emit();
  });
}

export function useDaemonCloudState(): DaemonCloudState {
  ensureSubscription();
  return useSyncExternalStore(
    (listener) => {
      ensureSubscription();
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => cached,
    () => UNKNOWN, // server snapshot: nothing is known during SSR
  );
}

/** Restart the daemon. Resolves false on the web build, where there is none. */
export async function restartDesktopDaemon(): Promise<boolean> {
  const bridge = getBridge();
  if (!bridge) return false;
  try {
    return await bridge.restart();
  } catch {
    return false;
  }
}
