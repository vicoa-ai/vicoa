/**
 * Desktop auto-update — renderer side of the preload bridge (src/updater.ts).
 *
 * The Electron main process owns electron-updater; this module mirrors its
 * status over `window.vicoaDesktopUpdates` and exposes:
 *   - useDesktopUpdateStatus()  — live status via useSyncExternalStore
 *   - check / download / quitAndInstall / getAppVersion action wrappers
 *   - bannerViewForStatus()     — pure derivation of what the banner shows
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

export async function downloadUpdate(): Promise<void> {
  try {
    await getDesktopUpdatesBridge()?.download();
  } catch {
    // errors surface as a status push; the caller shows the banner/error text
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
  | { kind: 'available'; version: string }
  | { kind: 'downloading'; percent: number }
  | { kind: 'downloaded'; version: string }
  | { kind: 'error'; message: string };

/**
 * What the top-of-window banner should show, or null when it stays hidden.
 *
 * - `checking` / `not-available` / `idle` never surface a banner — that
 *   feedback lives in Settings; the banner is for actionable states only.
 * - `available` / `downloaded` hide once the user dismisses that exact version
 *   (a newer version re-shows).
 * - `error` only shows when the user kicked off the action themselves
 *   (`userActed`), so a failed background check never nags.
 */
export function bannerViewForStatus(
  status: UpdateStatus,
  dismissedVersion: string | null,
  userActed: boolean,
): UpdateBannerView | null {
  switch (status.state) {
    case 'available':
      return status.version === dismissedVersion
        ? null
        : { kind: 'available', version: status.version };
    case 'downloading':
      return { kind: 'downloading', percent: status.percent };
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
