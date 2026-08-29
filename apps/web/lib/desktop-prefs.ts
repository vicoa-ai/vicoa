'use client';

/**
 * User-preference storage abstraction.
 *
 * Desktop: preferences live in the shell's `userData/settings.json` (the
 * IDE-style, hand-editable file). The preload injects a synchronous snapshot
 * (`__VICOA_SETTINGS__`) at document load and exposes a write bridge
 * (`vicoaDesktopSettings.set`); this module keeps a local copy of the
 * snapshot so reads stay synchronous after writes.
 *
 * Web / SSR: falls back to localStorage (JSON-encoded), preserving today's
 * behavior. A legacy raw-string value (pre-JSON encoding) is returned as-is.
 *
 * Migration: on desktop, a key missing from settings.json but present in
 * localStorage (pre-settings builds) is imported on first read.
 */

interface DesktopSettingsBridge {
  set: (key: string, value: unknown) => Promise<void>;
}

declare global {
  interface Window {
    /** Injected by the Electron preload; absent on plain web. */
    __VICOA_SETTINGS__?: Record<string, unknown>;
    vicoaDesktopSettings?: DesktopSettingsBridge;
  }
}

let snapshot: Record<string, unknown> | null | undefined;

/** Local mutable copy of the injected snapshot; null on plain web / SSR. */
function desktopSnapshot(): Record<string, unknown> | null {
  if (snapshot !== undefined) return snapshot;
  if (typeof window === 'undefined' || window.__VICOA_SETTINGS__ === undefined) {
    // SSR passes must not latch null before the injected snapshot is visible.
    if (typeof window === 'undefined') return null;
    snapshot = null;
    return snapshot;
  }
  snapshot = { ...window.__VICOA_SETTINGS__ };
  return snapshot;
}

function readLocalStorage(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return raw; // legacy raw string (pre-JSON values like 'time')
    }
  } catch {
    return null;
  }
}

export function getPref<T>(key: string): T | null {
  if (typeof window === 'undefined') return null;
  const settings = desktopSnapshot();
  if (settings !== null) {
    if (key in settings) return settings[key] as T;
    const legacy = readLocalStorage(key);
    if (legacy !== null) {
      setPref(key, legacy); // one-time import into settings.json
      return legacy as T;
    }
    return null;
  }
  return readLocalStorage(key) as T | null;
}

export function setPref(key: string, value: unknown): void {
  if (typeof window === 'undefined') return;
  const settings = desktopSnapshot();
  if (settings !== null) {
    if (value === null || value === undefined) delete settings[key];
    else settings[key] = value;
    void window.vicoaDesktopSettings?.set(key, value ?? null);
    return;
  }
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable — the preference just won't persist.
  }
}
