/**
 * Preload bridge (contextIsolation on, sandboxed).
 *
 * Config injection uses a single synchronous IPC call at preload init instead
 * of `additionalArguments` because:
 *  1. The config is dynamic: the login handoff restarts the daemon and flips
 *     mode local->cloud, then reloads the window — preload re-runs and pulls
 *     fresh config. additionalArguments are frozen at BrowserWindow creation,
 *     which would force a full window re-create on every auth change.
 *  2. additionalArguments land on the renderer's process command line, which
 *     is visible to every local user via `ps` — the nonce is a bearer secret
 *     and must stay off the process table.
 * The one-time sendSync costs a single main-process round trip per document
 * load, before any page script runs — negligible.
 */
import { contextBridge, ipcRenderer, webUtils } from 'electron';

interface DesktopConfig {
  mode: 'local' | 'cloud';
  wsUrl: string;
  apiBase: string;
  token: string;
  /** Self-hosted cloud endpoints; absent unless the user configured them. */
  cloudApiBase?: string;
  cloudWsUrl?: string;
}

interface AuthResult {
  ok: boolean;
  error?: string;
}

const config = ipcRenderer.sendSync('vicoa:get-desktop-config') as DesktopConfig;

contextBridge.exposeInMainWorld('__VICOA_DESKTOP__', config);

// Static platform tag ('darwin' | 'win32' | 'linux' | …) so the renderer can
// draw the Windows custom title bar without a main round trip. `process.platform`
// is available even in a sandboxed preload.
contextBridge.exposeInMainWorld('__VICOA_PLATFORM__', process.platform);

// User preferences snapshot (userData/settings.json). Read synchronously at
// preload init — same pattern as the config above — so renderer code can
// read prefs without an async round trip. Writes go through the bridge.
const initialSettings = ipcRenderer.sendSync('vicoa:get-settings') as Record<string, unknown>;
contextBridge.exposeInMainWorld('__VICOA_SETTINGS__', initialSettings);

contextBridge.exposeInMainWorld('vicoaDesktopSettings', {
  /** Persist a preference (null deletes it). Fire-and-forget semantics. */
  set: (key: string, value: unknown): Promise<void> =>
    ipcRenderer.invoke('vicoa:settings-set', key, value),
});

// File-path bridge: Electron ≥ 32 dropped `File.path`, so drag-drop uses
// `webUtils.getPathForFile` to resolve a dropped folder/file to its absolute
// on-disk path. Called synchronously in the renderer during the drop event.
contextBridge.exposeInMainWorld('vicoaDesktopFiles', {
  getPathForFile: (file: File): string => webUtils.getPathForFile(file),
});

contextBridge.exposeInMainWorld('vicoaDesktopShell', {
  /** Native directory picker; resolves to the chosen absolute path or null. */
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('vicoa:pick-folder'),
});

// Install-the-`vicoa`-command bridge (see src/cli-link.ts). Exposes the CLI the
// app already bundles on the user's shell PATH. Present on every desktop build.
interface CliLinkStatus {
  installed: boolean;
  foreign: boolean;
  available: boolean;
  path: string;
}
interface CliInstallResult {
  ok: boolean;
  path: string;
  message: string;
  detail: string;
}
contextBridge.exposeInMainWorld('vicoaDesktopCli', {
  /** Current install state of the `vicoa` terminal command. */
  getStatus: (): Promise<CliLinkStatus> => ipcRenderer.invoke('vicoa:cli-status'),
  /** Install/refresh the command; resolves to a result with a PATH hint. */
  install: (): Promise<CliInstallResult> => ipcRenderer.invoke('vicoa:cli-install'),
});

contextBridge.exposeInMainWorld('vicoaDesktopWindow', {
  /** Minimize the window (Windows custom title bar). */
  minimize: (): void => ipcRenderer.send('vicoa:window-minimize'),
  /** Toggle maximize/restore (Windows custom title bar). */
  toggleMaximize: (): void => ipcRenderer.send('vicoa:window-maximize-toggle'),
  /** Current maximize state, for the initial button icon. */
  isMaximized: (): Promise<boolean> => ipcRenderer.invoke('vicoa:window-is-maximized'),
  /** Close the window (quits on Windows/Linux). */
  close: (): void => ipcRenderer.send('vicoa:window-close'),
  /** Pop the application menu (Edit/View/Window) at the cursor — the ··· button. */
  popupMenu: (): void => ipcRenderer.send('vicoa:menu-popup'),
  /**
   * Subscribe to OS maximize-state changes (snap, double-click, keyboard) so the
   * renderer's maximize/restore icon stays in sync. Returns an unsubscribe fn.
   */
  onMaximizeChanged: (cb: (isMaximized: boolean) => void): (() => void) => {
    const listener = (_event: unknown, isMaximized: boolean): void => cb(isMaximized);
    ipcRenderer.on('vicoa:window-maximize-changed', listener);
    return () => {
      ipcRenderer.removeListener('vicoa:window-maximize-changed', listener);
    };
  },
});

contextBridge.exposeInMainWorld('vicoaDesktopNotifications', {
  /**
   * Show a native notification for a session status transition. Fire-and-
   * forget: main validates the payload, shows the banner, and handles the
   * click (focus/re-show the window, then navigate to the session).
   */
  notify: (payload: { instanceId: string; title: string; body: string }): void => {
    ipcRenderer.send('vicoa:notify', payload);
  },
  /** Mirror the count of sessions awaiting input onto the dock badge. */
  setBadgeCount: (count: number): void => {
    ipcRenderer.send('vicoa:set-badge-count', count);
  },
  /** Open macOS System Settings on Vicoa's Notifications pane (no-op elsewhere). */
  openNotificationSettings: (): Promise<void> =>
    ipcRenderer.invoke('vicoa:open-notification-settings'),
  /**
   * The app's real macOS notification authorization, read by the bundled
   * UNUserNotificationCenter helper: 'authorized' | 'denied' |
   * 'not-determined' | 'unknown', or null when unavailable (dev / non-mac).
   */
  getAuthorizationStatus: (): Promise<string | null> =>
    ipcRenderer.invoke('vicoa:notification-status'),
  /**
   * Subscribe to in-app navigation requests from notification clicks. The
   * callback receives a renderer route path (e.g. /dashboard/agents/<id>).
   * Requests that arrived before a renderer was listening are replayed on
   * subscribe. Returns an unsubscribe function.
   */
  onNavigate: (cb: (path: string) => void): (() => void) => {
    const listener = (_event: unknown, navPath: string): void => cb(navPath);
    ipcRenderer.on('vicoa:navigate', listener);
    ipcRenderer.send('vicoa:navigate-subscribe');
    return () => {
      ipcRenderer.removeListener('vicoa:navigate', listener);
    };
  },
});

contextBridge.exposeInMainWorld('vicoaDesktopAuth', {
  /** Persist a freshly minted API key; daemon restarts in cloud mode and the window reloads. */
  setApiKey: (key: string): Promise<AuthResult> => ipcRenderer.invoke('vicoa:set-api-key', key),
  /** Drop the stored key; daemon restarts with --local-only and the window reloads. */
  signOut: (): Promise<AuthResult> => ipcRenderer.invoke('vicoa:sign-out'),
  /**
   * Subscribe to vicoa:// deep links (e.g. the OAuth callback
   * `vicoa://auth/callback?...`). The callback receives the FULL url string.
   * Returns an unsubscribe function. Deep links that arrived before this
   * subscription (cold start / mid-reload) are replayed on subscribe, so a
   * callback is never missed.
   */
  onDeepLink: (cb: (url: string) => void): (() => void) => {
    const listener = (_event: unknown, url: string): void => cb(url);
    ipcRenderer.on('vicoa:deep-link', listener);
    // Tell main we're listening so it drains any buffered deep links to us.
    ipcRenderer.send('vicoa:deep-link-subscribe');
    return () => {
      ipcRenderer.removeListener('vicoa:deep-link', listener);
    };
  },
  /**
   * Open a URL in the user's default browser (the OAuth authorize step, or any
   * external link). Only http(s) and vicoa: URLs are honored. Resolves when the
   * OS opener has been invoked.
   */
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke('vicoa:open-external', url),
});

// Auto-update bridge (see src/updater.ts + lib/desktop-updates.ts). Present on
// every desktop build; the underlying checks only do real work when packaged.
type UpdateStatus =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available' }
  | { state: 'downloading'; percent: number; version: string }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string };

contextBridge.exposeInMainWorld('vicoaDesktopUpdates', {
  /** Synchronous snapshot for first paint (main holds the latest status). */
  getStatus: (): UpdateStatus => ipcRenderer.sendSync('vicoa:update-get-status') as UpdateStatus,
  /** The running app version (electron/package.json). */
  getVersion: (): Promise<string> => ipcRenderer.invoke('vicoa:update-get-version'),
  /** Trigger a check now; resolves to the resulting status. */
  check: (): Promise<UpdateStatus> => ipcRenderer.invoke('vicoa:update-check'),
  /** Start downloading the available update (progress arrives via onStatus). */
  download: (): Promise<void> => ipcRenderer.invoke('vicoa:update-download'),
  /** Quit and install the downloaded update, then relaunch. */
  quitAndInstall: (): Promise<void> => ipcRenderer.invoke('vicoa:update-quit-and-install'),
  /** Subscribe to status pushes from main. Returns an unsubscribe function. */
  onStatus: (cb: (status: UpdateStatus) => void): (() => void) => {
    const listener = (_event: unknown, status: UpdateStatus): void => cb(status);
    ipcRenderer.on('vicoa:update-status', listener);
    return () => {
      ipcRenderer.removeListener('vicoa:update-status', listener);
    };
  },
});
