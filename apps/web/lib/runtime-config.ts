/**
 * Desktop runtime seam (desktop-app v1 plan, "Renderer runtime config").
 *
 * The Electron preload injects `window.__VICOA_DESKTOP__` via contextBridge
 * before the renderer loads. This module is the ONLY reader of that global —
 * ws-client.ts and the REST layer consult it; components never branch on
 * desktop directly.
 *
 * - `mode: 'local'`  — logged-out desktop. ALL traffic (WS updates, RPC, REST)
 *   goes to the daemon's local server at `wsUrl`/`apiBase`, authenticated with
 *   the spawn nonce in `token` (WS subprotocol `vicoa-local.<token>`, REST
 *   `Authorization: Bearer <token>`). No Supabase anywhere.
 * - `mode: 'cloud'`  — logged-in desktop. WS updates + REST go to the cloud
 *   exactly as on the web (Supabase JWT); the RPC/pty side channel is routed
 *   per target machine — this machine goes direct to the local socket, other
 *   machines ride the cloud relay (see `getRpcClient()` in ws-client.ts).
 *
 * On plain web — or during SSR, where `window` does not exist — this returns
 * `null` and every consumer follows its existing path unchanged.
 */

export interface DesktopRuntimeConfig {
  mode: 'local' | 'cloud';
  wsUrl: string;
  apiBase: string;
  token: string;
  /**
   * Self-hosted cloud endpoints, injected when the user pointed the desktop app
   * at their own backend (env `VICOA_API_URL`/`VICOA_WS_URL` or
   * ~/.vicoa/desktop.json). Absent on Vicoa's hosted service, where the
   * build-time `NEXT_PUBLIC_*` values apply. See `getCloudApiBase`.
   */
  cloudApiBase?: string;
  cloudWsUrl?: string;
}

/**
 * Window-control bridge for the Windows custom title bar (titleBarStyle:'hidden').
 * Injected by the Electron preload; absent on macOS/web (macOS keeps the native
 * traffic lights, so nothing here is needed there).
 */
export interface VicoaDesktopWindow {
  minimize: () => void;
  toggleMaximize: () => void;
  isMaximized: () => Promise<boolean>;
  close: () => void;
  popupMenu: () => void;
  onMaximizeChanged: (cb: (isMaximized: boolean) => void) => () => void;
}

/**
 * File-path bridge. Electron ≥ 32 removed `File.path`; `webUtils.getPathForFile`
 * is the supported way to resolve a dropped/picked File to its absolute on-disk
 * path. Injected by the preload; absent on plain web (browsers deliberately
 * hide local paths for privacy). Used by drag-drop to reference a dropped
 * folder by path instead of uploading its bytes.
 */
export interface VicoaDesktopFiles {
  getPathForFile: (file: File) => string;
}

declare global {
  interface Window {
    /** Injected by the Electron preload (contextBridge); absent on plain web. */
    __VICOA_DESKTOP__?: DesktopRuntimeConfig;
    /** Electron `process.platform` ('darwin' | 'win32' | 'linux' | …); absent on web. */
    __VICOA_PLATFORM__?: string;
    /** Window-control bridge (Windows custom title bar); absent on macOS/web. */
    vicoaDesktopWindow?: VicoaDesktopWindow;
    /** File-path bridge (webUtils.getPathForFile); absent on plain web. */
    vicoaDesktopFiles?: VicoaDesktopFiles;
  }
}

/** The preload-injected desktop config, or `null` on plain web / SSR. */
export function getDesktopConfig(): DesktopRuntimeConfig | null {
  if (typeof window === 'undefined') return null;
  return window.__VICOA_DESKTOP__ ?? null;
}

/** True only in logged-out desktop mode (everything served by the local daemon). */
export function isDesktopLocal(): boolean {
  return getDesktopConfig()?.mode === 'local';
}

/**
 * REST base for cloud traffic.
 *
 * A packaged desktop build inlines `NEXT_PUBLIC_BACKEND_API_URL` at build time,
 * so a self-hoster can only repoint it at runtime — the shell injects
 * `cloudApiBase` when configured and it wins here. On the web the deployment's
 * own env var is already the right answer.
 */
export function getCloudApiBase(): string {
  // Server-side (Next route handlers / server components), the browser's URL can
  // be unreachable from this process: in Docker the browser reaches the backend
  // on a published localhost port, but this container must use the compose
  // service name. BACKEND_INTERNAL_URL carries that address.
  //
  // Read it with bracket notation on purpose: Next's build-time DefinePlugin
  // inlines `process.env.IDENTIFIER` dot-access as a constant (an unset var
  // folds to `undefined` and the branch is dead-code-eliminated), but leaves
  // computed `process.env['…']` access as a genuine runtime lookup — which is
  // what lets the compose file set this via `environment` with no rebuild.
  // Vicoa's hosted deployment leaves it unset and falls through unchanged.
  const internalBackendUrl = process.env['BACKEND_INTERNAL_URL'];
  if (typeof window === 'undefined' && internalBackendUrl) {
    return internalBackendUrl;
  }
  return (
    getDesktopConfig()?.cloudApiBase ??
    process.env.NEXT_PUBLIC_BACKEND_API_URL ??
    'http://localhost:8000'
  );
}

/** WebSocket endpoint for cloud traffic; same precedence as `getCloudApiBase`. */
export function getCloudWsUrl(): string {
  return (
    getDesktopConfig()?.cloudWsUrl ??
    process.env.NEXT_PUBLIC_VICOA_WS_URL ??
    'ws://localhost:8080/ws'
  );
}

/** Electron platform string, or `null` on plain web / SSR. */
export function getDesktopPlatform(): string | null {
  if (typeof window === 'undefined') return null;
  return window.__VICOA_PLATFORM__ ?? null;
}

/** The Windows window-control bridge, or `null` when unavailable (macOS/web/SSR). */
export function getDesktopWindowBridge(): VicoaDesktopWindow | null {
  if (typeof window === 'undefined') return null;
  return window.vicoaDesktopWindow ?? null;
}

/**
 * Absolute on-disk path for a dropped/picked `File`, or `null` when it can't be
 * resolved — plain web (no bridge), SSR, or a File the bridge rejects. Only the
 * desktop app can answer this; the web build always returns `null`.
 */
export function getDesktopFilePath(file: File): string | null {
  if (typeof window === 'undefined') return null;
  const bridge = window.vicoaDesktopFiles;
  if (!bridge) return null;
  try {
    const path = bridge.getPathForFile(file);
    return path && path.length > 0 ? path : null;
  } catch {
    return null;
  }
}
