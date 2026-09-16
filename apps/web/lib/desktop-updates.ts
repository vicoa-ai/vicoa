/**
 * Desktop auto-update — renderer side of the preload bridge (src/updater.ts).
 *
 * The Electron main process owns electron-updater and downloads a newer
 * version on its own as soon as a check finds one; this module mirrors its
 * status over `window.vicoaDesktopUpdates` and exposes:
 *   - useDesktopUpdateStatus()  — live status via useSyncExternalStore
 *   - check / quitAndInstall / getAppVersion action wrappers
 *   - bannerViewForStatus()     — pure derivation of what the callout shows
 *
 * Null bridge on plain web / SSR — every consumer no-ops there.
 */

import { useSyncExternalStore } from 'react';

/** Mirror of the union in electron/src/updater.ts. */
export type UpdateStatus =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available' }
  | { state: 'downloading'; percent: number; version: string }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string };

const IDLE: UpdateStatus = { state: 'idle' };

export interface DesktopUpdatesBridge {
  getStatus: () => UpdateStatus;
  getVersion: () => Promise<string>;
  check: () => Promise<UpdateStatus>;
  download: () => Promise<void>;
  quitAndInstall: () => Promise<void>;
  onStatus: (cb: (status: UpdateStatus) => void) => () => void;
}

export function getDesktopUpdatesBridge(): DesktopUpdatesBridge | null {
  if (typeof window === 'undefined') return null;
  const bridge = (window as unknown as { vicoaDesktopUpdates?: DesktopUpdatesBridge })
    .vicoaDesktopUpdates;
  return bridge && typeof bridge.onStatus === 'function' ? bridge : null;
}

// ---------------------------------------------------------------------------
// External store — one subscription to the bridge, cached snapshot shared by
// every useDesktopUpdateStatus() consumer (banner + settings).
// ---------------------------------------------------------------------------

let cachedStatus: UpdateStatus = IDLE;
let bridgeSubscribed = false;
const listeners = new Set<() => void>();

function ensureBridgeSubscription(): void {
  if (bridgeSubscribed) return;
  const bridge = getDesktopUpdatesBridge();
  if (!bridge) return; // web/SSR: stay on IDLE, never subscribe
  bridgeSubscribed = true;
  try {
    cachedStatus = bridge.getStatus() ?? IDLE;
  } catch {
    cachedStatus = IDLE;
  }
  bridge.onStatus((status) => {
    cachedStatus = status;
    for (const listener of listeners) listener();
  });
}

function subscribe(onChange: () => void): () => void {
  ensureBridgeSubscription();
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

function getSnapshot(): UpdateStatus {
  return cachedStatus;
}

function getServerSnapshot(): UpdateStatus {
  return IDLE;
}

/** Live update status; `{ state: 'idle' }` on web / before any check. */
export function useDesktopUpdateStatus(): UpdateStatus {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// ---------------------------------------------------------------------------
// Action wrappers (no-op / null on web)
// ---------------------------------------------------------------------------

export async function checkForUpdates(): Promise<UpdateStatus | null> {
  const bridge = getDesktopUpdatesBridge();
  if (!bridge) return null;
  try {
    return await bridge.check();
  } catch {
    return null;
  }
}

export async function quitAndInstallUpdate(): Promise<void> {
  await getDesktopUpdatesBridge()?.quitAndInstall();
}

export async function getAppVersion(): Promise<string | null> {
  const bridge = getDesktopUpdatesBridge();
  if (!bridge) return null;
  try {
    return await bridge.getVersion();
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Banner derivation (pure — unit-tested in desktop-updates.test.ts)
// ---------------------------------------------------------------------------

export type UpdateBannerView =
  | { kind: 'downloaded'; version: string }
  | { kind: 'error'; message: string };

/**
 * What the sidebar callout should show, or null when it stays hidden.
 *
 * - `idle` / `checking` / `not-available` never surface — that feedback lives
 *   in Settings; the callout is for actionable states only.
 * - `available` / `downloading` stay hidden too: main auto-downloads, so there
 *   is nothing to click until the update is ready (progress is in Settings).
 * - `downloaded` hides once the user dismisses that exact version (a newer
 *   version re-shows).
 * - `error` only shows when the user kicked off the action themselves
 *   (`userActed`), so a failed background check/download never nags.
 */
export function bannerViewForStatus(
  status: UpdateStatus,
  dismissedVersion: string | null,
  userActed: boolean,
): UpdateBannerView | null {
  switch (status.state) {
    case 'downloaded':
      return status.version === dismissedVersion
        ? null
        : { kind: 'downloaded', version: status.version };
    case 'error':
      return userActed ? { kind: 'error', message: status.message } : null;
    default:
      return null;
  }
}
