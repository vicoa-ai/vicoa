/**
 * Vicoa desktop shell — app lifecycle orchestration.
 *
 * Boot order: single-instance lock -> nonce + free port -> renderer (bundled
 * standalone server when packaged, else the next dev server URL) -> spawn
 * daemon -> healthz green -> create window.
 *
 * Two renderer modes:
 * - Dev (default from a checkout): load VICOA_RENDERER_URL / localhost:3000 —
 *   unchanged from the v1 dev workflow.
 * - Bundled (app.isPackaged or VICOA_BUNDLED=1): boot the packaged Next
 *   standalone server in a utilityProcess and load it (see renderer-server.ts).
 *
 * macOS lifecycle choice (v1): closing the window keeps the app (and the
 * daemon) alive — standard macOS behavior; reopen via dock or tray. On
 * Windows/Linux, closing the window quits the app (and the daemon with it).
 */
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  Notification,
  shell,
  type MenuItemConstructorOptions,
} from 'electron';
import { execFile } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import {
  bundledDaemonPath,
  generateNonce,
  hasWriteKey,
  isBundled,
  pickFreePort,
  readSelfHostEndpoints,
  removeWriteKey,
  rendererServerPath,
  rendererUrl,
  saveWriteKey,
  type DesktopConfig,
} from './config';
import { DaemonManager, daemonCommandAvailable, type DaemonState } from './daemon-manager';
import { startRendererServer, type RendererServer } from './renderer-server';
import { createMainWindow } from './window';
import { createTray, destroyTray, updateTrayDaemonState } from './tray';
import { registerSettingsIpc } from './settings';
import { setupAutoUpdater } from './updater';
import { engageGpuFallback, GPU_FALLBACK_ARG, isGpuFallbackEngaged } from './gpu-fallback';
import {
  ensureManagedDaemon,
  isManagedDaemonInstalled,
  isPlatformSupported,
  managedDaemonExe,
  pinnedDaemonVersion,
  type DaemonProgress,
} from './cli-bootstrap';
import {
  autoInstallCliLinkOnce,
  displayPath,
  getCliLinkStatus,
  installCliLink,
  refreshCliLinkIfInstalled,
} from './cli-link';
import { showProvisioningWindow } from './provisioning-window';

app.setName('Vicoa');

// ---------------------------------------------------------------------------
// Windows GPU crash → software-render fallback (Orca pattern, adapted).
//
// Launch with hardware acceleration ON so healthy Windows GPUs keep it. On a
// machine with a genuinely broken GPU stack (some VMs, stale drivers) the renderer
// can crash in a reload-proof loop — a Chromium ANGLE → Direct3D GPU crash. When
// the renderer's bounded auto-reload gives up (onRendererRecoveryExhausted, below)
// we persist a marker and relaunch with acceleration OFF — passing `--gpu-fallback`
// on the relaunch argv so that process is guaranteed software-rendered (argv can't
// be misread, so no relaunch loop; the marker persists the choice across future
// manual launches + updates). macOS/Linux never disable acceleration. Must run
// before the `ready` event.
//
// This is a defensive net for REAL GPU faults only. The `-36861` crash that first
// motivated a Windows GPU workaround was NOT a GPU fault — it was an empty
// `locales/` dir from `electronLanguages: ['en']` (fixed in
// electron-builder.config.cjs; see electron/electron#45251), which forcing
// acceleration off never fixed. Do not read `-36861` as "the GPU" again.
// ---------------------------------------------------------------------------
let gpuFallbackActive = false;
if (process.platform === 'win32') {
  try {
    if (process.argv.includes(GPU_FALLBACK_ARG) || isGpuFallbackEngaged(app.getPath('userData'))) {
      app.disableHardwareAcceleration();
      app.commandLine.appendSwitch('disable-gpu');
      gpuFallbackActive = true;
    }
  } catch {
    // Never block boot on the marker read; worst case acceleration stays on.
  }
}

/** Custom URL scheme for OAuth callbacks and other deep links: vicoa://… */
const DEEP_LINK_SCHEME = 'vicoa';

/**
 * Deep-link URLs that arrived before a renderer was listening (cold start, or
 * mid-reload). Held here until a renderer subscribes (preload's onDeepLink
 * sends 'vicoa:deep-link-subscribe') or the current renderer is idle enough to
 * receive them — never dropped.
 */
const pendingDeepLinks: string[] = [];

/**
 * In-app navigation requests from notification clicks, buffered like deep
 * links until a renderer is loaded and subscribed ('vicoa:navigate-subscribe').
 */
const pendingNavigations: string[] = [];

/**
 * Live notifications held by reference until dismissed/clicked — Electron
 * GC-collects an unreferenced Notification, which kills its click handler.
 * Bounded so banners that macOS silently absorbs into Notification Center
 * (no 'close' event) can't accumulate.
 */
const liveNotifications = new Set<Notification>();
const MAX_LIVE_NOTIFICATIONS = 20;

let mainWindow: BrowserWindow | null = null;
let daemonManager: DaemonManager | null = null;
let rendererServer: RendererServer | null = null;
/** URL the window loads: bundled standalone server (packaged) or next dev. */
let effectiveRendererUrl = '';
let localPort = 0;
let localNonce = '';
let isQuitting = false;
let quitCleanupDone = false;
let failureDialogOpen = false;

// ---------------------------------------------------------------------------
// Single-instance lock: a second launch focuses the existing window instead.
// ---------------------------------------------------------------------------
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  registerProtocolClient();
  app.on('second-instance', (_event, argv) => {
    focusOrCreateWindow();
    // A vicoa:// URL launched while we were already running arrives as an argv
    // on this (the primary) instance — Windows/Linux protocol-activation path.
    const deepLink = argv.find((arg) => arg.startsWith(`${DEEP_LINK_SCHEME}://`));
    if (deepLink !== undefined) {
      handleDeepLink(deepLink);
    }
  });
  // macOS delivers protocol activations here (cold-start and while-running).
  app.on('open-url', (_event, url) => {
    handleDeepLink(url);
  });
  void bootstrap();
}

/**
 * Register Vicoa as the handler for `vicoa://` URLs. In dev (`electron .`,
 * `process.defaultApp === true`) the OS needs the Electron binary + our app
 * path to relaunch us, so we pass execPath + argv[1] per the Electron docs;
 * the packaged app registers itself.
 */
function registerProtocolClient(): void {
  const appPath = process.argv[1];
  if (process.defaultApp && appPath !== undefined) {
    app.setAsDefaultProtocolClient(DEEP_LINK_SCHEME, process.execPath, [path.resolve(appPath)]);
  } else {
    app.setAsDefaultProtocolClient(DEEP_LINK_SCHEME);
  }
}

/**
 * Self-hosted backend endpoints, resolved once at startup from env or
 * ~/.vicoa/desktop.json. Empty for everyone on Vicoa's hosted service.
 */
const selfHostEndpoints = readSelfHostEndpoints();

/**
 * Push the self-hosted endpoints into this process's env BEFORE anything is
 * spawned, so the children inherit them:
 *  - the daemon (`vicoa` CLI) reads `VICOA_API_URL` / `VICOA_AUTH_URL`;
 *  - the renderer's standalone Next server reads `NEXT_PUBLIC_*` at runtime for
 *    its server-side routes (the client bundle gets them via the preload
 *    instead, since those values were inlined at build time).
 */
function applySelfHostEnv(): void {
  const { apiUrl, wsUrl, authUrl } = selfHostEndpoints;
  if (apiUrl !== undefined) {
    process.env.VICOA_API_URL = apiUrl;
    process.env.NEXT_PUBLIC_BACKEND_API_URL = apiUrl;
  }
  if (wsUrl !== undefined) {
    process.env.NEXT_PUBLIC_VICOA_WS_URL = wsUrl;
  }
  if (authUrl !== undefined) {
    process.env.VICOA_AUTH_URL = authUrl;
  }
}

function desktopConfig(): DesktopConfig {
  return {
    // Authenticated ⇔ credentials.json has a write_key. Deriving mode from the
    // key (rather than the daemon's --local-only flag) means sign-out — which
    // removes the key without restarting the daemon local-only — immediately
    // reads as `local`, so the reload lands on the login screen instead of a
    // keyless `cloud` state the gate would try to sign out of on a loop.
    mode: hasWriteKey() ? 'cloud' : 'local',
    wsUrl: `ws://127.0.0.1:${localPort}/ws`,
    apiBase: `http://127.0.0.1:${localPort}`,
    token: localNonce,
    // Only present when the user pointed this build at their own backend; the
    // renderer falls back to its build-time defaults when they are absent.
    ...(selfHostEndpoints.apiUrl !== undefined ? { cloudApiBase: selfHostEndpoints.apiUrl } : {}),
    ...(selfHostEndpoints.wsUrl !== undefined ? { cloudWsUrl: selfHostEndpoints.wsUrl } : {}),
  };
}

function focusOrCreateWindow(): void {
  if (mainWindow !== null && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.show();
    mainWindow.focus();
    return;
  }
  ensureMainWindow();
}

function ensureMainWindow(): void {
  if (mainWindow !== null && !mainWindow.isDestroyed()) {
    return;
  }
  if (effectiveRendererUrl === '') {
    return; // renderer not resolved yet (bundled server still booting)
  }
  mainWindow = createMainWindow({
    preloadPath: path.join(__dirname, 'preload.js'),
    url: effectiveRendererUrl,
    // macOS: closing hides (renderer stays alive → notifications + badge keep
    // working, matching the tray-alive lifecycle). Real close still happens on
    // quit. Windows/Linux keep destroy-on-close (the app quits with it).
    shouldHideOnClose: () => process.platform === 'darwin' && !isQuitting,
    onRendererRecoveryExhausted,
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function reloadRenderer(): void {
  if (mainWindow !== null && !mainWindow.isDestroyed()) {
    // Reload re-runs the preload, which pulls fresh config (mode may have flipped).
    mainWindow.webContents.reload();
  }
}

/**
 * The renderer crashed/failed past its auto-reload budget (window.ts). On Windows
 * a persistent, reload-proof crash is treated as a possible GPU fault: persist the
 * software-render marker and relaunch with acceleration off (see the header block).
 * No-op elsewhere, or if we are already software-rendering (so this crash isn't
 * GPU) — the guard on gpuFallbackActive also makes a fallback relaunch loop
 * impossible.
 */
function onRendererRecoveryExhausted(): void {
  if (process.platform !== 'win32' || gpuFallbackActive || isQuitting) {
    return;
  }
  try {
    engageGpuFallback(app.getPath('userData'), 'render-process-crash-loop');
  } catch (err) {
    console.warn('[main] failed to persist GPU fallback marker:', err);
  }
  console.log('[main] renderer crash loop — relaunching with GPU acceleration disabled');
  gpuFallbackActive = true;
  isQuitting = true;
  app.relaunch({ args: [GPU_FALLBACK_ARG] });
  void runQuitCleanup().finally(() => app.exit(0));
}

// ---------------------------------------------------------------------------
// Deep links (vicoa://) — OAuth callback plumbing. The renderer owns the OAuth
// flow; the shell only forwards the full callback URL into the renderer.
// ---------------------------------------------------------------------------
function handleDeepLink(url: string): void {
  if (typeof url !== 'string' || !url.startsWith(`${DEEP_LINK_SCHEME}://`)) {
    return; // ignore anything that isn't one of our deep links
  }
  logDeepLinkEvent(`received ${redactDeepLink(url)}`);
  pendingDeepLinks.push(url);
  flushDeepLinks();
}

/** Strip credential-bearing params; keep state so handoff issues stay diagnosable. */
function redactDeepLink(url: string): string {
  try {
    const queryIndex = url.indexOf('?');
    if (queryIndex === -1) return url;
    const params = new URLSearchParams(url.slice(queryIndex + 1));
    for (const secret of ['api_key', 'token_hash', 'access_token', 'refresh_token']) {
      if (params.has(secret)) params.set(secret, '<redacted>');
    }
    return `${url.slice(0, queryIndex)}?${params.toString()}`;
  } catch {
    return `${url.split('?')[0]}?<unparseable>`;
  }
}

/**
 * Append-only handoff diagnostics (userData/deep-link.log, truncated at
 * 256KB). Deep links + setApiKey outcomes — the exact trail needed when a
 * sign-in "did nothing", since packaged apps have no visible console.
 */
function logDeepLinkEvent(message: string): void {
  try {
    const logPath = path.join(app.getPath('userData'), 'deep-link.log');
    try {
      if (fs.existsSync(logPath) && fs.statSync(logPath).size > 256 * 1024) {
        fs.unlinkSync(logPath);
      }
    } catch {
      // best-effort rotation
    }
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
  } catch {
    // diagnostics must never break the flow
  }
}

/**
 * Persist the bundled standalone renderer server's stdout/stderr to
 * userData/renderer-server.log (rotated at 256KB). A packaged app has no visible
 * console, so an SSR error that answers a route with a 500 — the usual cause of
 * a blank WHITE screen — is otherwise invisible. Server-side complement to the
 * renderer.log capture in window.ts.
 */
function logRendererServer(message: string): void {
  try {
    const logPath = path.join(app.getPath('userData'), 'renderer-server.log');
    try {
      if (fs.existsSync(logPath) && fs.statSync(logPath).size > 256 * 1024) {
        fs.unlinkSync(logPath);
      }
    } catch {
      // best-effort rotation
    }
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
  } catch {
    // diagnostics must never break boot
  }
}

/**
 * Best-effort delivery to a loaded renderer (warm path: the OAuth screen is
 * already up and subscribed). If the window is missing or mid-load, links stay
 * buffered — the renderer's 'vicoa:deep-link-subscribe' ping (post-load, or
 * after a reload) drains them race-free.
 */
function flushDeepLinks(): void {
  if (mainWindow === null || mainWindow.isDestroyed()) {
    return;
  }
  const wc = mainWindow.webContents;
  if (wc.isLoading()) {
    return;
  }
  while (pendingDeepLinks.length > 0) {
    wc.send('vicoa:deep-link', pendingDeepLinks.shift() as string);
  }
}

// ---------------------------------------------------------------------------
// Session notifications (renderer-triggered) + notification-click navigation.
// The renderer watches instance status transitions over its WebSocket and
// sends 'vicoa:notify'; main shows the native banner so a click can focus
// (or re-show) the window and route to the session.
// ---------------------------------------------------------------------------
function requestNavigation(path: string): void {
  pendingNavigations.push(path);
  flushNavigations();
}

/** Same delivery contract as flushDeepLinks: loaded renderer or stay buffered. */
function flushNavigations(): void {
  if (mainWindow === null || mainWindow.isDestroyed()) {
    return;
  }
  const wc = mainWindow.webContents;
  if (wc.isLoading()) {
    return;
  }
  while (pendingNavigations.length > 0) {
    wc.send('vicoa:navigate', pendingNavigations.shift() as string);
  }
}

interface SessionNotificationPayload {
  instanceId: string;
  title: string;
  body: string;
}

/** Instance ids come from our own backend rows; anything else is dropped. */
const INSTANCE_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function parseNotifyPayload(raw: unknown): SessionNotificationPayload | null {
  if (typeof raw !== 'object' || raw === null) {
    return null;
  }
  const { instanceId, title, body } = raw as Record<string, unknown>;
  if (typeof instanceId !== 'string' || typeof title !== 'string' || typeof body !== 'string') {
    return null;
  }
  if (instanceId !== '' && !INSTANCE_ID_RE.test(instanceId)) {
    return null;
  }
  return { instanceId, title: title.slice(0, 200), body: body.slice(0, 500) };
}

function showSessionNotification(payload: SessionNotificationPayload): void {
  if (!Notification.isSupported()) {
    return;
  }
  const notification = new Notification({ title: payload.title, body: payload.body });
  if (liveNotifications.size >= MAX_LIVE_NOTIFICATIONS) {
    const oldest = liveNotifications.values().next().value;
    if (oldest !== undefined) {
      liveNotifications.delete(oldest);
    }
  }
  liveNotifications.add(notification);
  notification.on('click', () => {
    liveNotifications.delete(notification);
    focusOrCreateWindow();
    // An empty instanceId (the settings page's test notification) just
    // focuses the window without routing anywhere.
    if (payload.instanceId !== '') {
      requestNavigation(`/dashboard/agents/${payload.instanceId}`);
    }
  });
  notification.on('close', () => {
    liveNotifications.delete(notification);
  });
  notification.show();
  console.log(`[main] notification shown: ${payload.title} — ${payload.body}`);
}

// ---------------------------------------------------------------------------
// macOS notification registration + authorization status.
// ---------------------------------------------------------------------------

/**
 * macOS requires a notification to have been posted at least once before the
 * app appears in System Settings -> Notifications — and on a fresh install
 * that first post is also what pops the OS "Allow notifications?" dialog.
 * Fire a silent no-op notification during startup to ensure registration.
 * (Paseo pattern; harmless when already authorized — silent and closed on
 * show. Requires the bundle to carry a signature: see after-pack.cjs.)
 */
function ensureNotificationCenterRegistration(): void {
  if (process.platform !== 'darwin' || !Notification.isSupported()) {
    return;
  }
  const probe = new Notification({ title: app.name, silent: true });
  probe.on('show', () => probe.close());
  const closeTimer = setTimeout(() => probe.close(), 2_000);
  closeTimer.unref?.();
  probe.show();
}

type NotificationAuthorizationStatus = 'authorized' | 'denied' | 'not-determined' | 'unknown';

/**
 * The bundled UNUserNotificationCenter status helper (Orca pattern; built by
 * scripts/build-notification-status.mjs). It must sit in Contents/MacOS next
 * to the Electron executable — NSBundle resolves the bundle by walking up
 * from the executable path. Absent in dev runs -> callers get null.
 */
function notificationStatusHelperPath(): string | null {
  if (process.platform !== 'darwin') {
    return null;
  }
  const candidate = path.join(path.dirname(process.execPath), 'vicoa-notification-status');
  return fs.existsSync(candidate) ? candidate : null;
}

/**
 * Reads the app's real notification authorization. Electron itself exposes
 * nothing (posting silently succeeds even while macOS suppresses display), so
 * the helper's native settings read is the only truthful signal. Returns null
 * when the helper is unavailable (dev) or fails.
 */
function readNotificationAuthorizationStatus(): Promise<NotificationAuthorizationStatus | null> {
  const helperPath = notificationStatusHelperPath();
  if (helperPath === null) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    execFile(helperPath, [], { timeout: 4_000 }, (error, stdout) => {
      if (error) {
        resolve(null);
        return;
      }
      try {
        const parsed = JSON.parse(String(stdout).trim()) as { authorization?: string };
        switch (parsed.authorization) {
          case 'authorized':
          case 'provisional':
          case 'ephemeral':
            resolve('authorized');
            return;
          case 'denied':
            resolve('denied');
            return;
          case 'not-determined':
            resolve('not-determined');
            return;
          default:
            resolve('unknown');
        }
      } catch {
        resolve(null);
      }
    });
  });
}

/** Only hand http(s) and our own vicoa: scheme to the OS opener. */
function isAllowedExternalUrl(url: string): boolean {
  try {
    const scheme = new URL(url).protocol;
    return scheme === 'http:' || scheme === 'https:' || scheme === `${DEEP_LINK_SCHEME}:`;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Managed daemon (de-bundled builds): the frozen daemon is NOT shipped in the
// installer; it's downloaded to userData on first run. See cli-bootstrap.ts.
// ---------------------------------------------------------------------------

/**
 * True when this build must DOWNLOAD the daemon rather than use a bundled one:
 * packaged, no explicit VICOA_DAEMON_CMD override, and no daemon present in the
 * app bundle. That covers a de-bundled installer AND the default bundled build
 * whose daemon has gone missing/corrupt (bundledDaemonPath() === null) — i.e.
 * the self-heal fallback. Dev checkouts keep using `vicoa` on PATH; a bundled
 * build with its daemon intact returns false and behaves exactly as before.
 */
function usesManagedDaemon(): boolean {
  if (!isBundled()) return false;
  const override = process.env.VICOA_DAEMON_CMD;
  if (typeof override === 'string' && override.trim().length > 0) return false;
  return bundledDaemonPath() === null;
}

/** Managed daemon exe handed to DaemonManager (resolution prefers it over PATH), or null. */
function managedDaemonPathForManager(): string | null {
  return usesManagedDaemon() ? managedDaemonExe(pinnedDaemonVersion()) : null;
}

const PROVISION_PHASE_LABEL: Record<DaemonProgress['phase'], string> = {
  resolving: 'Locating the Vicoa agent…',
  downloading: 'Downloading the Vicoa agent…',
  verifying: 'Verifying download…',
  extracting: 'Extracting…',
  installing: 'Installing…',
};

let provisioningWindow: ReturnType<typeof showProvisioningWindow> | null = null;

/**
 * Ensure the managed daemon is present before we try to start it. No-op for
 * bundled / override / dev builds, and when it is already installed. Otherwise
 * downloads it, showing a small progress splash. Returns false when it could not
 * be provisioned (offline, unsupported platform) — callers then fall through to
 * the existing "daemon unavailable" degraded path.
 */
async function ensureDaemonProvisioned(): Promise<boolean> {
  if (!usesManagedDaemon()) return true;
  const version = pinnedDaemonVersion();
  if (isManagedDaemonInstalled(version)) return true;
  if (!isPlatformSupported()) return false;

  const splash = provisioningWindow ?? showProvisioningWindow();
  provisioningWindow = splash;
  splash.setProgress(null, 'Preparing the Vicoa agent…');
  try {
    await ensureManagedDaemon((p) => {
      if (p.phase === 'downloading' && p.totalBytes !== undefined) {
        const mb = (n: number): string => (n / 1_000_000).toFixed(0);
        splash.setProgress(
          p.fraction ?? null,
          `Downloading the Vicoa agent… ${mb(p.receivedBytes ?? 0)} / ${mb(p.totalBytes)} MB`,
        );
      } else {
        // Unknown content-length or a non-download phase: indeterminate bar + label.
        splash.setProgress(null, PROVISION_PHASE_LABEL[p.phase]);
      }
    });
    splash.close();
    provisioningWindow = null;
    return true;
  } catch (err) {
    console.warn('[main] daemon provisioning failed:', err);
    splash.fail(
      `Couldn't download the Vicoa agent.\n${err instanceof Error ? err.message : String(err)}\n` +
        'Check your connection and reopen Vicoa.',
    );
    // Leave the error visible briefly, then dismiss so the degraded window/dialog shows through.
    setTimeout(() => {
      splash.close();
      provisioningWindow = null;
    }, 6_000);
    return false;
  }
}

/**
 * Kick the managed-daemon download in the BACKGROUND (no splash) — used on the
 * logged-out first launch so the agent is likely already downloaded by the time
 * the user finishes signing in. Cheap no-op when not applicable / already present.
 */
function warmManagedDaemon(): void {
  if (!usesManagedDaemon() || !isPlatformSupported()) return;
  if (isManagedDaemonInstalled(pinnedDaemonVersion())) return;
  void ensureManagedDaemon().catch((err) => {
    console.warn('[main] background daemon warm-up failed (will retry on demand):', err);
  });
}

function onDaemonState(state: DaemonState): void {
  updateTrayDaemonState(state);
  if (state.status === 'running') {
    // Window creation is gated on the first healthy daemon; also covers
    // supervisor recoveries when the window was never created.
    ensureMainWindow();
  }
  if (state.status === 'failed') {
    showDaemonFailedDialog(state);
  }
}

function showDaemonFailedDialog(state: DaemonState): void {
  if (failureDialogOpen || isQuitting) {
    return;
  }
  failureDialogOpen = true;
  const message = 'The Vicoa daemon failed to start.';
  const detail =
    (state.lastError ?? 'Unknown error') +
    '\n\nCheck that the `vicoa` CLI is installed (or VICOA_DAEMON_CMD is set), then restart the daemon.';
  const options = {
    type: 'error' as const,
    title: 'Vicoa',
    message,
    detail,
    buttons: ['Restart daemon', 'Dismiss'],
    defaultId: 0,
    cancelId: 1,
  };
  const dialogPromise =
    mainWindow !== null && !mainWindow.isDestroyed()
      ? dialog.showMessageBox(mainWindow, options)
      : dialog.showMessageBox(options);
  void dialogPromise.then(({ response }) => {
    failureDialogOpen = false;
    if (response === 0) {
      void daemonManager?.restart();
    }
  });
}

/**
 * No daemon executable anywhere (no bundled binary, nothing on PATH, no
 * override): the app stays open in a degraded state — window + tray work,
 * sessions can't start — and tells the user how to install the CLI.
 */
function showDaemonMissingDialog(): void {
  if (failureDialogOpen || isQuitting) {
    return;
  }
  failureDialogOpen = true;
  // A de-bundled build downloads its own daemon, so a missing daemon there means
  // the download did not complete — a network/retry story, not "install the CLI".
  const managed = usesManagedDaemon();
  const options = {
    type: 'warning' as const,
    title: 'Vicoa',
    message: managed ? 'The Vicoa agent could not be downloaded.' : 'The Vicoa CLI was not found.',
    detail: managed
      ? 'Vicoa downloads its agent runtime on first launch, but the download did not complete.\n\n' +
        'Check your internet connection, then use "Restart daemon" from the tray menu to try again.'
      : 'Install the Vicoa CLI: npm i -g @vicoa/cli\n\n' +
        'The app will stay open, but coding sessions cannot start until the CLI is installed. ' +
        'After installing, use "Restart daemon" from the tray menu.',
    buttons: ['OK'],
    defaultId: 0,
  };
  const dialogPromise =
    mainWindow !== null && !mainWindow.isDestroyed()
      ? dialog.showMessageBox(mainWindow, options)
      : dialog.showMessageBox(options);
  void dialogPromise.then(() => {
    failureDialogOpen = false;
  });
}

// ---------------------------------------------------------------------------
// IPC: renderer runtime config + login handoff
// ---------------------------------------------------------------------------
function registerIpcHandlers(): void {
  ipcMain.on('vicoa:get-desktop-config', (event) => {
    event.returnValue = desktopConfig();
  });

  // A renderer just attached its onDeepLink listener — replay any buffered
  // deep links to it. Fires on first mount and after every reload, so a
  // callback that arrived while no renderer was listening is never lost.
  ipcMain.on('vicoa:deep-link-subscribe', (event) => {
    while (pendingDeepLinks.length > 0) {
      event.sender.send('vicoa:deep-link', pendingDeepLinks.shift() as string);
    }
  });

  // Native session notification (status transition seen by the renderer's
  // WebSocket). Shown from main so the click handler can focus/re-show the
  // window and route to the session even when the window is hidden.
  ipcMain.on('vicoa:notify', (_event, raw: unknown) => {
    const payload = parseNotifyPayload(raw);
    if (payload !== null) {
      showSessionNotification(payload);
    }
  });

  // Dock badge = number of sessions awaiting input (macOS; no-op elsewhere).
  ipcMain.on('vicoa:set-badge-count', (_event, raw: unknown) => {
    if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < 0) {
      return;
    }
    try {
      app.setBadgeCount(Math.floor(raw));
    } catch (err) {
      console.warn('[main] failed to set badge count:', err);
    }
  });

  // A renderer attached its onNavigate listener — replay buffered navigation
  // requests (notification clicked while the window was recreating/reloading).
  ipcMain.on('vicoa:navigate-subscribe', (event) => {
    while (pendingNavigations.length > 0) {
      event.sender.send('vicoa:navigate', pendingNavigations.shift() as string);
    }
  });

  // Real macOS notification authorization for the renderer (settings page +
  // enablement nudge). null = helper unavailable (dev run / non-mac).
  ipcMain.handle('vicoa:notification-status', () => readNotificationAuthorizationStatus());

  // Open macOS System Settings on the Notifications pane so the user can
  // grant/enable Vicoa. Fixed URL built here — this is not routed through the
  // generic open-external path, whose scheme allowlist (http/https/vicoa)
  // correctly rejects x-apple.systempreferences from the renderer.
  ipcMain.handle('vicoa:open-notification-settings', async () => {
    if (process.platform !== 'darwin') {
      return;
    }
    // darwin 22 == macOS 13 (Ventura), where the app-scoped Notifications
    // pane extension URL exists; earlier versions get the legacy pane.
    const darwinMajor = Number.parseInt(os.release(), 10);
    const bundleId = app.isPackaged ? 'ai.vicoa.desktop' : 'com.github.Electron';
    const url =
      Number.isFinite(darwinMajor) && darwinMajor >= 22
        ? `x-apple.systempreferences:com.apple.Notifications-Settings.extension?id=${bundleId}`
        : 'x-apple.systempreferences:com.apple.preference.notifications';
    await shell.openExternal(url);
  });

  // Open a URL in the user's default browser (OAuth authorize step, external
  // links). Validated to http(s)/vicoa: so the renderer can't drive the OS
  // opener at arbitrary schemes (e.g. file:, mailto:, custom handlers).
  ipcMain.handle('vicoa:open-external', async (_event, url: unknown) => {
    if (typeof url !== 'string' || !isAllowedExternalUrl(url)) {
      return;
    }
    await shell.openExternal(url);
  });

  // Native directory picker (new-session working directory). Returns the
  // chosen absolute path, or null when the user cancels.
  ipcMain.handle('vicoa:pick-folder', async () => {
    const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? null;
    const result = win
      ? await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] })
      : await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'] });
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0];
  });

  // Install-the-`vicoa`-command bridge (Settings UI). Status is a trimmed view
  // for the renderer; install returns the full result so the UI can show the
  // PATH hint inline. The app menu item uses the same core with a native dialog.
  ipcMain.handle('vicoa:cli-status', () => {
    const s = getCliLinkStatus();
    return {
      installed: s.installed,
      foreign: s.foreign,
      available: s.currentBinary !== null,
      path: displayPath(s.path),
    };
  });
  ipcMain.handle('vicoa:cli-install', () => installCliLink());

  // Windows custom title bar (titleBarStyle:'hidden'): the renderer draws its own
  // min/max/close controls and a ··· button, so drive the native window and pop
  // the existing application menu from here. Harmless on macOS (unused; the
  // native traffic lights + menu bar handle this).
  ipcMain.on('vicoa:window-minimize', (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });
  ipcMain.on('vicoa:window-maximize-toggle', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win === null) {
      return;
    }
    if (win.isMaximized()) {
      win.unmaximize();
    } else {
      win.maximize();
    }
  });
  ipcMain.handle('vicoa:window-is-maximized', (event) => {
    return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
  });
  ipcMain.on('vicoa:window-close', (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });
  ipcMain.on('vicoa:menu-popup', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    Menu.getApplicationMenu()?.popup(win !== null ? { window: win } : undefined);
  });

  ipcMain.handle('vicoa:set-api-key', async (_event, key: unknown) => {
    if (typeof key !== 'string' || key.trim().length === 0) {
      return { ok: false, error: 'API key must be a non-empty string' };
    }
    if (daemonManager === null) {
      return { ok: false, error: 'Daemon manager not initialized' };
    }
    try {
      saveWriteKey(key.trim());
    } catch (err) {
      logDeepLinkEvent(`setApiKey: failed to write credentials: ${String(err)}`);
      return { ok: false, error: `Failed to write credentials: ${String(err)}` };
    }
    logDeepLinkEvent('setApiKey: key saved, ensuring daemon is present');
    // De-bundled build: make sure the frozen daemon is downloaded before the
    // first cloud-mode start (the background warm-up may still be in flight).
    if (!(await ensureDaemonProvisioned())) {
      logDeepLinkEvent('setApiKey: daemon provisioning failed');
      return {
        ok: false,
        error: 'Could not download the Vicoa agent. Check your connection and try again.',
      };
    }
    // The daemon (and thus the CLI binary) is now on disk — finish the
    // first-run auto-install for a de-bundled build whose binary didn't exist at
    // boot. No-op once the one-time marker is set. See autoInstallCliLinkOnce.
    void autoInstallCliLinkOnce();
    logDeepLinkEvent('setApiKey: restarting daemon in cloud mode');
    const healthy = await daemonManager.restart(false);
    if (!healthy) {
      const error = daemonManager.state.lastError ?? 'Daemon did not become healthy';
      logDeepLinkEvent(`setApiKey: daemon restart FAILED: ${error}`);
      return { ok: false, error };
    }
    logDeepLinkEvent('setApiKey: daemon healthy, reloading renderer');
    reloadRenderer();
    return { ok: true };
  });

  ipcMain.handle('vicoa:sign-out', async () => {
    if (daemonManager === null) {
      return { ok: false, error: 'Daemon manager not initialized' };
    }
    try {
      removeWriteKey();
    } catch (err) {
      return { ok: false, error: `Failed to update credentials: ${String(err)}` };
    }
    // Local mode is not exposed/supported (login is required), so do NOT restart
    // the daemon with --local-only on sign-out. `mode` is derived from the
    // write_key (now removed), so the reload lands on the login screen. The
    // still-running daemon is replaced on the next sign-in (setApiKey restarts
    // it in cloud mode).
    // const healthy = await daemonManager.restart(true);
    // if (!healthy) {
    //   return { ok: false, error: daemonManager.state.lastError ?? 'Daemon did not become healthy' };
    // }
    reloadRenderer();
    return { ok: true };
  });
}

// ---------------------------------------------------------------------------
// Application menu: app name + standard Edit/View/Window so macOS copy/paste
// shortcuts work.
// ---------------------------------------------------------------------------
/**
 * Menu action: install the `vicoa` terminal command (the CLI bundled in the app
 * — task/automation/instance subcommands) onto the user's PATH, then report the
 * outcome. See cli-link.ts.
 */
async function handleInstallCliLink(): Promise<void> {
  let result;
  try {
    result = await installCliLink();
  } catch (err) {
    result = {
      ok: false,
      path: '',
      elevated: false,
      message: 'Could not install the vicoa command.',
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  const options = {
    type: result.ok ? ('info' as const) : ('warning' as const),
    title: 'Vicoa',
    message: result.message,
    detail: result.detail,
    buttons: ['OK'],
    defaultId: 0,
  };
  if (mainWindow !== null && !mainWindow.isDestroyed()) {
    void dialog.showMessageBox(mainWindow, options);
  } else {
    void dialog.showMessageBox(options);
  }
}

/** Shared menu entry — reachable from the macOS app menu and the Help menu. */
const installCliMenuItem: MenuItemConstructorOptions = {
  label: 'Install "vicoa" Terminal Command…',
  click: () => {
    void handleInstallCliLink();
  },
};

function buildAppMenu(): void {
  const isMac = process.platform === 'darwin';
  const template: MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: 'Vicoa',
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              installCliMenuItem,
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          } satisfies MenuItemConstructorOptions,
        ]
      : []),
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Window',
      submenu: isMac
        ? [{ role: 'minimize' }, { role: 'zoom' }, { type: 'separator' }, { role: 'front' }]
        : [{ role: 'minimize' }, { role: 'close' }],
    },
    // Help menu carries the CLI installer on every platform (on macOS the app
    // menu has it too; on Windows/Linux this is the only place it surfaces).
    {
      role: 'help',
      submenu: [installCliMenuItem],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

/**
 * macOS dock icon. Packaged builds get it from the bundled .icns (electron-
 * builder mac.icon), so this only matters in dev, where the dock would
 * otherwise show the generic Electron icon. Best-effort: a missing/empty asset
 * leaves the default in place.
 */
function setDockIcon(): void {
  if (process.platform !== 'darwin' || app.dock === undefined || app.isPackaged) {
    return;
  }
  try {
    const iconPath = path.join(__dirname, '..', 'resources', 'icon-512.png');
    const image = nativeImage.createFromPath(iconPath);
    if (!image.isEmpty()) {
      app.dock.setIcon(image);
    }
  } catch (err) {
    console.warn('[main] failed to set dock icon:', err);
  }
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
async function bootstrap(): Promise<void> {
  await app.whenReady();
  applySelfHostEnv();
  setDockIcon();
  buildAppMenu();
  // If the user installed the `vicoa` terminal command, silently re-point it at
  // this build's binary (an app update or managed-daemon bump may have moved it).
  // Fire-and-forget; never prompts. See cli-link.ts.
  void refreshCliLinkIfInstalled();
  // Install-by-default: on first run, expose the bundled `vicoa` command without
  // a Settings click. One-time, silent, won't clobber a user's own vicoa. For
  // bundled builds the binary is available now; de-bundled builds complete this
  // after the daemon is provisioned below. See autoInstallCliLinkOnce.
  void autoInstallCliLinkOnce();
  registerIpcHandlers();
  registerSettingsIpc();
  // Auto-update (electron-updater). Registers its renderer IPC always; only
  // schedules real checks in packaged builds. onBeforeInstall reuses the quit
  // cleanup so a Squirrel swap doesn't orphan the daemon/renderer children.
  setupAutoUpdater({ getWindow: () => mainWindow, onBeforeInstall: runQuitCleanup });

  // Windows/Linux cold start via protocol: the vicoa:// URL is one of our own
  // argv. (macOS delivers it through the open-url handler instead.) Buffered
  // until the window + renderer come up.
  const initialDeepLink = process.argv.find((arg) => arg.startsWith(`${DEEP_LINK_SCHEME}://`));
  if (initialDeepLink !== undefined) {
    handleDeepLink(initialDeepLink);
  }

  localNonce = generateNonce();
  localPort = await pickFreePort();

  // De-bundled build with a returning (logged-in) user: start fetching the frozen
  // daemon NOW, in the background, so it downloads concurrently with the (slow on
  // Windows first run) renderer-server boot below. ensureDaemonProvisioned() later
  // awaits this same in-flight download and shows a splash only for the remainder.
  // Logged-out users deliberately DON'T pre-fetch — they download at sign-in
  // (setApiKey), so a tire-kicker never pulls ~150 MB they may never use.
  if (hasWriteKey()) {
    warmManagedDaemon();
  }

  // Renderer first: the daemon needs the renderer origin (VICOA_LOCAL_ORIGIN)
  // and in bundled mode that origin carries the standalone server's port.
  if (isBundled()) {
    // Retry once: the very first launch after an NSIS install can have the Node
    // standalone server exit early or stall while Defender scans the fresh files
    // (the boot-time "renderer error"). A second fork usually starts clean.
    const startPath = rendererServerPath();
    let startError: unknown = null;
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      try {
        rendererServer = await startRendererServer(startPath, logRendererServer);
        effectiveRendererUrl = rendererServer.url;
        startError = null;
        break;
      } catch (err) {
        startError = err;
        logRendererServer(
          `start attempt ${attempt}/2 failed: ${err instanceof Error ? err.message : String(err)}`,
        );
        if (attempt < 2) {
          await new Promise((resolve) => setTimeout(resolve, 1_500));
        }
      }
    }
    if (startError !== null) {
      dialog.showErrorBox(
        'Vicoa',
        `The bundled renderer failed to start.\n\n${startError instanceof Error ? startError.message : String(startError)}`,
      );
      app.exit(1);
      return;
    }
  } else {
    effectiveRendererUrl = rendererUrl();
  }

  daemonManager = new DaemonManager({
    port: localPort,
    nonce: localNonce,
    origin: new URL(effectiveRendererUrl).origin,
    bundledDaemonPath: isBundled() ? bundledDaemonPath() : null,
    managedDaemonPath: managedDaemonPathForManager(),
  });
  daemonManager.onState(onDaemonState);

  createTray({
    onOpen: focusOrCreateWindow,
    onRestartDaemon: () => void ensureDaemonProvisioned().then(() => daemonManager?.restart()),
    onQuit: () => {
      app.quit();
    },
  });

  // Register with the macOS notification center (first run: pops the OS
  // "Allow notifications?" dialog) — must come after setName/dock setup so
  // the dialog carries the right app identity.
  ensureNotificationCenterRegistration();

  // Local (logged-out) mode is disabled: without a write_key, spawn NO
  // daemon at all — the welcome/sign-in surface needs none, no user data is
  // ever created in the local store, and sign-in restarts the daemon in
  // cloud mode via the setApiKey handler.
  // (Previously: const localOnly = !hasWriteKey(); daemonManager.start(localOnly);)
  if (!hasWriteKey()) {
    ensureMainWindow();
    // No daemon is spawned while logged out; the managed daemon (de-bundled
    // builds) is fetched at sign-in — see the setApiKey handler.
    return;
  }

  // De-bundled build with a logged-in user: download the frozen daemon on first
  // run (with a progress splash) BEFORE we probe for it below.
  await ensureDaemonProvisioned();
  // The frozen daemon (hence the CLI binary) now exists: finish the first-run
  // auto-install if the boot-time attempt found nothing to expose. No-op once
  // the one-time marker is set. See autoInstallCliLinkOnce.
  void autoInstallCliLinkOnce();

  // No daemon executable at all (bundled binary absent, download failed, PATH
  // empty-handed, no override): degraded mode — open the window, explain, don't
  // crash-loop.
  const [daemonCmd] = daemonManager.resolvedCommand();
  if (daemonCmd === undefined || !daemonCommandAvailable(daemonCmd, process.env)) {
    updateTrayDaemonState({
      status: 'failed',
      localOnly: true,
      lastError: `Vicoa CLI not found (looked for: ${daemonCmd ?? 'vicoa'})`,
    });
    ensureMainWindow();
    showDaemonMissingDialog();
    return;
  }

  const healthy = await daemonManager.start(false);
  if (healthy) {
    ensureMainWindow(); // also triggered by onDaemonState('running'); idempotent
  } else if (isBundled()) {
    // Packaged app: never leave the user with only a tray icon — show the
    // window in a degraded state alongside the failure dialog.
    ensureMainWindow();
  }
  // On failure onDaemonState('failed') has already surfaced the tray status +
  // dialog; the user can retry from either.
}

app.on('activate', () => {
  // macOS dock click with no window: recreate it (daemon is still running).
  focusOrCreateWindow();
});

app.on('window-all-closed', () => {
  // macOS: stay alive (tray + dock) per platform convention; the daemon keeps
  // running so reopening the window is instant. Elsewhere: quit for real.
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

/**
 * Stop the daemon (SIGTERM -> SIGKILL after 5s) and the bundled renderer
 * server, and tear down the tray. Idempotent. Does NOT exit the process —
 * callers decide what happens next: a normal quit exits after this, while an
 * update install hands off to Squirrel via autoUpdater.quitAndInstall so the
 * bundle swap can proceed (see updater.ts onBeforeInstall).
 */
async function runQuitCleanup(): Promise<void> {
  if (quitCleanupDone) {
    return;
  }
  quitCleanupDone = true;
  try {
    await daemonManager?.stop();
  } catch (err) {
    console.warn('[main] daemon stop during quit failed:', err);
  }
  try {
    await rendererServer?.stop();
  } catch (err) {
    console.warn('[main] renderer server stop during quit failed:', err);
  }
  destroyTray();
}

app.on('before-quit', (event) => {
  isQuitting = true;
  // Cleanup already ran (e.g. an update install did it before handing off to
  // Squirrel) — let this quit proceed untouched so the install completes.
  if (quitCleanupDone) {
    return;
  }
  // Never orphan the children: block this quit, run cleanup, then exit for real.
  event.preventDefault();
  void runQuitCleanup().then(() => app.exit(0));
});
