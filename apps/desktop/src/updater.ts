/**
 * Auto-update — electron-updater against GitHub Releases at vicoa-ai/vicoa.
 *
 * Manual download, install-on-restart (the renderer drives the flow):
 *   check()          -> 'checking' -> 'available' | 'not-available'
 *   download()       -> 'downloading'(percent) -> 'downloaded'
 *   quitAndInstall() -> onBeforeInstall() cleanup, then Squirrel.Mac swaps the
 *                       bundle and relaunches.
 *
 * Detection is what makes the sidebar callout appear, so checks are triggered
 * from several angles, all rate-limited through maybeCheck(): startup, a 30min
 * interval, window focus, wake-from-sleep, and renderer load. Any one of them
 * alone leaves a hole — the interval is the worst case, not the mechanism.
 *
 * Only live in packaged builds: electron-updater needs the app-update.yml that
 * electron-builder writes from the `publish` config, and a dev checkout has
 * none. In dev the IPC handlers are still registered (so the renderer bridge is
 * present-but-inert) but every check/download is a no-op that reports 'idle'.
 *
 * macOS note: checkForUpdates/downloadUpdate work on any build, but
 * quitAndInstall's Squirrel.Mac step only APPLIES an update when the new bundle
 * is Developer ID signed + notarized and its identity matches the running app
 * (see electron-builder.config.cjs, VICOA_MAC_RELEASE). Unsigned dev-packaged
 * builds surface an 'error' at install time — expected until we ship signed.
 */
import { app, BrowserWindow, ipcMain, powerMonitor } from 'electron';
import { autoUpdater } from 'electron-updater';

/** Union mirrored on the renderer side in lib/desktop-updates.ts. */
export type UpdateStatus =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available' }
  | { state: 'downloading'; percent: number; version: string }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string };

/**
 * Background re-check cadence once the app has been open a while. This is the
 * ceiling on how long a long-lived session can sit on a stale version with
 * nothing else waking the updater, so it stays well under an hour — a 6h
 * cadence meant a release published mid-session went unnoticed for most of a
 * working day, and the callout only appeared after a relaunch.
 */
const CHECK_INTERVAL_MS = 30 * 60 * 1000; // 30min
/** First check fires shortly after boot, once the window is up. */
const INITIAL_CHECK_DELAY_MS = 10_000;
/**
 * Floor between two checks, whatever triggered them. The ambient triggers
 * (interval, window focus, wake-from-sleep, renderer load) all funnel through
 * maybeCheck and several of them can fire in the same second — alt-tabbing back
 * to a window that just reloaded hits three at once. This collapses a burst
 * into one request; an explicit user-driven check ignores it.
 */
const MIN_CHECK_GAP_MS = 5 * 60 * 1000; // 5min
/**
 * After quitAndInstall commits, force the process to exit if it has not died
 * within this window. Squirrel.Mac's ShipIt (and the Win/Linux installers) wait
 * for the OLD process to exit before swapping the bundle and relaunching. If a
 * lingering handle keeps the process alive after `quitAndInstall` closes the
 * windows + calls app.quit(), the app looks closed but never terminates, so the
 * update silently never applies and never relaunches (Orca #4438 — the exact
 * "closed but not quit, no relaunch" symptom). A healthy quit exits in well
 * under a second, so this only fires on a wedged teardown.
 */
const INSTALL_EXIT_WATCHDOG_MS = 10_000;

interface UpdaterOptions {
  /** Live main window (may be null/recreated) — status pushes target it. */
  getWindow: () => BrowserWindow | null;
  /**
   * Run app teardown (stop daemon + renderer server) BEFORE Squirrel installs.
   * Must NOT call app.exit — quitAndInstall drives the actual quit so the
   * install can proceed. See main.ts runQuitCleanup.
   */
  onBeforeInstall: () => Promise<void>;
}

let latestStatus: UpdateStatus = { state: 'idle' };
let pendingVersion = '';
let getMainWindow: () => BrowserWindow | null = () => null;
let installExitTimer: ReturnType<typeof setTimeout> | null = null;
let lastCheckStartedAt = 0;

/**
 * Guarantee the old process exits after an update install has committed, so the
 * installer can swap the bundle and relaunch. exit(0) (not exit(1)) keeps
 * Squirrel/ShipIt on the normal relaunch path. Unref'd so the watchdog itself
 * never keeps the app alive; a clean quit that beats the deadline no-ops it.
 */
function armInstallExitWatchdog(): void {
  if (installExitTimer !== null) return;
  installExitTimer = setTimeout(() => {
    console.warn(
      '[updater] process still alive after install commit — forcing exit so the installer can relaunch',
    );
    app.exit(0);
  }, INSTALL_EXIT_WATCHDOG_MS);
  installExitTimer.unref?.();
}

function setStatus(status: UpdateStatus): void {
  latestStatus = status;
  const win = getMainWindow();
  if (win !== null && !win.isDestroyed()) {
    win.webContents.send('vicoa:update-status', status);
  }
}

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  const text = String(err ?? '').trim();
  return text.length > 0 ? text : 'Update failed';
}

async function runCheck(): Promise<UpdateStatus> {
  if (!app.isPackaged) return latestStatus;
  lastCheckStartedAt = Date.now();
  try {
    await autoUpdater.checkForUpdates();
  } catch (err) {
    setStatus({ state: 'error', message: errorMessage(err) });
  }
  return latestStatus;
}

/**
 * A fresh check would walk back over work already in flight: it pushes
 * 'checking' (which hides the callout) and then 'available', so an update the
 * user has already downloaded loses its "Restart" state and drops back to
 * "Install & Restart". Ambient checks skip these states entirely.
 */
function checkWouldStompProgress(): boolean {
  return (
    latestStatus.state === 'checking' ||
    latestStatus.state === 'downloading' ||
    latestStatus.state === 'downloaded'
  );
}

/**
 * Funnel for every ambient (non-user-driven) check. Rate-limited and
 * state-guarded so the extra triggers below are cheap to add: a release
 * published mid-session should surface the moment the user comes back to the
 * window, not at the next multi-hour tick.
 */
function maybeCheck(reason: string): void {
  if (!app.isPackaged) return;
  if (checkWouldStompProgress()) return;
  if (Date.now() - lastCheckStartedAt < MIN_CHECK_GAP_MS) return;
  console.log(`[updater] checking for updates (${reason})`);
  void runCheck();
}

/**
 * Wire electron-updater's events to status pushes and register the renderer
 * IPC. Safe to call once, after app is ready.
 */
export function setupAutoUpdater(options: UpdaterOptions): void {
  getMainWindow = options.getWindow;

  registerIpc(options.onBeforeInstall);

  if (!app.isPackaged) {
    return; // dev checkout: bridge is inert (no app-update.yml to check)
  }

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('checking-for-update', () => setStatus({ state: 'checking' }));
  autoUpdater.on('update-available', (info) => {
    pendingVersion = info.version;
    setStatus({ state: 'available', version: info.version });
  });
  autoUpdater.on('update-not-available', () => setStatus({ state: 'not-available' }));
  autoUpdater.on('download-progress', (progress) => {
    setStatus({
      state: 'downloading',
      percent: Math.max(0, Math.min(100, Math.round(progress.percent))),
      version: pendingVersion,
    });
  });
  autoUpdater.on('update-downloaded', (info) => setStatus({ state: 'downloaded', version: info.version }));
  autoUpdater.on('error', (err) => setStatus({ state: 'error', message: errorMessage(err) }));

  // First check once the window is up, then periodically. Timers unref'd so a
  // pending check never keeps the app alive on quit.
  // Via maybeCheck, not runCheck: on a fast boot the renderer mounts first and
  // its own trigger already checked, and re-checking on top of that would push
  // 'checking' over a fresh 'available' and flicker the callout away.
  const initial = setTimeout(() => maybeCheck('startup'), INITIAL_CHECK_DELAY_MS);
  initial.unref?.();
  const interval = setInterval(() => maybeCheck('periodic'), CHECK_INTERVAL_MS);
  interval.unref?.();

  // The interval alone is not enough: it is the worst case, not the common one.
  // Desktop sessions live for days, and on macOS closing only hides the window,
  // so "the user came back to Vicoa" is the moment that actually wants a fresh
  // answer. Focus covers alt-tab / reopen-from-tray / re-show after hide.
  app.on('browser-window-focus', () => maybeCheck('window focused'));

  // A sleeping Mac suspends the interval, so a laptop that wakes after a long
  // sleep would otherwise wait out another full period before noticing.
  powerMonitor.on('resume', () => maybeCheck('system resumed'));
}

function registerIpc(onBeforeInstall: () => Promise<void>): void {
  // Synchronous snapshot for the renderer's first paint (useSyncExternalStore).
  ipcMain.on('vicoa:update-get-status', (event) => {
    event.returnValue = latestStatus;
    // The renderer reads this once per page load, so a Cmd/Ctrl+R now also
    // re-checks — the reload-and-it-appears behaviour users already reach for,
    // made deliberate instead of accidental. Rate-limited like every other
    // ambient trigger, and deferred so the sync reply is never held up.
    setImmediate(() => maybeCheck('renderer loaded'));
  });

  ipcMain.handle('vicoa:update-get-version', () => app.getVersion());

  ipcMain.handle('vicoa:update-check', () => runCheck());

  ipcMain.handle('vicoa:update-download', async () => {
    if (!app.isPackaged) return;
    try {
      await autoUpdater.downloadUpdate();
    } catch (err) {
      setStatus({ state: 'error', message: errorMessage(err) });
    }
  });

  ipcMain.handle('vicoa:update-quit-and-install', async () => {
    if (!app.isPackaged) return;
    try {
      await onBeforeInstall();
    } catch (err) {
      console.warn('[updater] pre-install cleanup failed:', err);
    }
    // Defer past the IPC reply so the renderer isn't torn down mid-call.
    // isSilent=false, isForceRunAfter=true -> relaunch after the swap.
    setImmediate(() => {
      autoUpdater.quitAndInstall(false, true);
      // Squirrel closes the windows + calls app.quit(), but a lingering handle
      // can keep the process alive so ShipIt never swaps/relaunches — force it.
      armInstallExitWatchdog();
    });
  });
}
