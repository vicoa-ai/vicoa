/**
 * Main window: persisted bounds (shell-state.json in userData), off-screen
 * display validation, debounced bounds writes, external-link handling.
 * Patterns adapted from Orca's createMainWindow.ts (MIT, Lovecast Inc.).
 */
import { app, BrowserWindow, screen, shell } from 'electron';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { readShellState, updateShellState, type PersistedWindowState } from './shell-state';

const MIN_WIDTH = 800;
const MIN_HEIGHT = 560;
const BOUNDS_WRITE_DEBOUNCE_MS = 500;

/** How many times we auto-reload a failed/crashed renderer before giving up. */
const MAX_AUTO_RELOADS = 3;
/** Renderer crashes within this window that trip the shell's recovery escalation. */
const CRASH_ESCALATE_WINDOW_MS = 60_000;
const CRASH_ESCALATE_THRESHOLD = 3;

/**
 * Append-only renderer diagnostics (userData/renderer.log, truncated at 256KB).
 * A packaged app has no visible console, so a blank / hung / crashed renderer is
 * otherwise undiagnosable — this captures document-load failures, renderer-
 * process exits, and renderer console warnings/errors (a failed client-segment
 * fetch or a hydration error shows up here). It is the trail needed for the
 * Windows "blank main page" and "render error on first launch" reports.
 */
function logRenderer(message: string): void {
  try {
    const logPath = path.join(app.getPath('userData'), 'renderer.log');
    try {
      if (fs.existsSync(logPath) && fs.statSync(logPath).size > 256 * 1024) {
        fs.unlinkSync(logPath);
      }
    } catch {
      // best-effort rotation
    }
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
  } catch {
    // diagnostics must never break the window
  }
}

function readWindowState(): PersistedWindowState | null {
  return readShellState().window ?? null;
}

function writeWindowState(state: PersistedWindowState): void {
  updateShellState({ window: state });
}

/**
 * A persisted rect is only reused when it meaningfully overlaps some current
 * display's workArea (>= half of the min dimensions) — a rect saved on a
 * disconnected external monitor must not restore off-screen. (Orca pattern.)
 */
function rectVisibleOnSomeDisplay(rect: { x: number; y: number; width: number; height: number }): boolean {
  try {
    return screen.getAllDisplays().some((display) => {
      const wa = display.workArea;
      const overlapX = Math.max(
        0,
        Math.min(rect.x + rect.width, wa.x + wa.width) - Math.max(rect.x, wa.x),
      );
      const overlapY = Math.max(
        0,
        Math.min(rect.y + rect.height, wa.y + wa.height) - Math.max(rect.y, wa.y),
      );
      return overlapX >= MIN_WIDTH / 2 && overlapY >= MIN_HEIGHT / 2;
    });
  } catch {
    return false;
  }
}

export interface CreateMainWindowOptions {
  preloadPath: string;
  /** Renderer URL (next dev server in v1). */
  url: string;
  /**
   * Consulted on every close request. Returning true hides the window instead
   * of destroying it (macOS tray-alive pattern) — the renderer keeps running,
   * so its WebSocket keeps delivering the events that drive notifications and
   * the dock badge. Must return false while the app is quitting, or quit would
   * be swallowed.
   */
  shouldHideOnClose?: () => boolean;
  /**
   * Called once when the renderer has crashed/failed to load past its auto-reload
   * budget. The shell uses this to engage the Windows GPU software-render fallback
   * (relaunch with acceleration disabled) instead of leaving a dead white window.
   */
  onRendererRecoveryExhausted?: () => void;
}

export function createMainWindow(options: CreateMainWindowOptions): BrowserWindow {
  const saved = readWindowState();
  const savedUsable =
    saved !== null &&
    saved.width >= MIN_WIDTH &&
    saved.height >= MIN_HEIGHT &&
    rectVisibleOnSomeDisplay(saved);

  const defaultSize = (() => {
    try {
      const { width, height } = screen.getPrimaryDisplay().workAreaSize;
      return { width: Math.min(1280, width), height: Math.min(860, height) };
    } catch {
      return { width: 1280, height: 860 };
    }
  })();

  const win = new BrowserWindow({
    width: savedUsable ? saved.width : defaultSize.width,
    height: savedUsable ? saved.height : defaultSize.height,
    ...(savedUsable ? { x: saved.x, y: saved.y } : {}),
    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,
    title: 'Vicoa',
    show: false,
    // Custom title bar per platform. macOS: hide the OS titlebar but keep the
    // frame — the traffic lights float over the renderer's own header, which
    // reserves top-left space for them at { x: 16, y: 16 }. Windows: hide the
    // title bar AND auto-hide the menu bar; the renderer draws its own
    // min/max/close controls plus a ··· button that pops the application menu
    // (Orca pattern). Linux keeps the default OS frame for now.
    ...(process.platform === 'darwin'
      ? { titleBarStyle: 'hiddenInset' as const, trafficLightPosition: { x: 16, y: 16 } }
      : process.platform === 'win32'
        ? { titleBarStyle: 'hidden' as const, autoHideMenuBar: true }
        : {}),
    webPreferences: {
      preload: options.preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // The hidden-but-alive window (hide-on-close) is what keeps session
      // notifications flowing; Chromium's intensive timer throttling would
      // otherwise let the WS liveness/reconnect timers drift for minutes.
      backgroundThrottling: false,
    },
  });

  win.once('ready-to-show', () => {
    if (saved?.maximized === true) {
      win.maximize();
    }
    win.show();
  });

  // ---- Debounced bounds persistence (frozen once close begins) -------------
  let boundsTimer: NodeJS.Timeout | null = null;
  let windowClosing = false;
  const saveBounds = (): void => {
    if (boundsTimer !== null) {
      clearTimeout(boundsTimer);
    }
    boundsTimer = setTimeout(() => {
      boundsTimer = null;
      if (windowClosing || win.isDestroyed() || win.isFullScreen()) {
        return;
      }
      const bounds = win.getBounds();
      writeWindowState({ ...bounds, maximized: win.isMaximized() });
    }, BOUNDS_WRITE_DEBOUNCE_MS);
  };
  win.on('resize', saveBounds);
  win.on('move', saveBounds);
  win.on('close', (event) => {
    if (options.shouldHideOnClose?.() === true) {
      // Keep the renderer alive: hide instead of destroy. A fullscreen window
      // can't just hide (macOS would strand an empty space), so leave
      // fullscreen first and hide once the transition completes.
      event.preventDefault();
      if (win.isFullScreen()) {
        win.once('leave-full-screen', () => win.hide());
        win.setFullScreen(false);
      } else {
        win.hide();
      }
      return;
    }
    // OS teardown can emit resize/move with near-minimum bounds; freeze
    // persistence so those don't clobber the user's real last size.
    windowClosing = true;
    if (boundsTimer !== null) {
      clearTimeout(boundsTimer);
      boundsTimer = null;
    }
  });

  // ---- External link handling ----------------------------------------------
  const appOrigin = new URL(options.url).origin;
  win.webContents.setWindowOpenHandler((details) => {
    if (/^https?:/i.test(details.url)) {
      void shell.openExternal(details.url);
    }
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    try {
      if (new URL(url).origin === appOrigin) {
        return; // in-app navigation (and dev-server reloads) stay in-window
      }
    } catch {
      // unparseable URL: fall through to block
    }
    event.preventDefault();
    if (/^https?:/i.test(url)) {
      void shell.openExternal(url);
    }
  });

  // ---- Windows custom-title-bar maximize state ------------------------------
  // The renderer draws its own maximize/restore button on Windows, so mirror the
  // real OS maximize state to it (double-click, snap, keyboard, etc.). No-op on
  // macOS, where the native traffic lights own this.
  const emitMaximizeState = (): void => {
    if (!win.isDestroyed()) {
      win.webContents.send('vicoa:window-maximize-changed', win.isMaximized());
    }
  };
  win.on('maximize', emitMaximizeState);
  win.on('unmaximize', emitMaximizeState);

  // ---- Renderer failure diagnostics + bounded auto-recovery ----------------
  // No renderer-side error boundary can catch a renderer that never mounts: a
  // client chunk/segment that fails to load hangs on an empty fallback, and a
  // crashed render process paints white. Log every failure and, for the
  // recoverable ones (a transient document-load failure or a process crash),
  // reload with backoff. This is what turns the reported Windows "blank main
  // page" and the "render error on the very first post-install launch" into a
  // self-healing reload instead of a dead window the user must quit and reopen.
  let autoReloads = 0;
  let reloadTimer: NodeJS.Timeout | null = null;
  let recoveryExhaustedFired = false;
  const crashTimestamps: number[] = [];
  const scheduleReload = (why: string): void => {
    if (win.isDestroyed() || reloadTimer !== null) {
      return;
    }
    if (autoReloads >= MAX_AUTO_RELOADS) {
      logRenderer(`giving up auto-reload after ${autoReloads} attempts (${why})`);
      // Escalate once: the shell can turn a persistent crash (the Windows GPU
      // crash) into a software-render relaunch instead of a dead white window.
      if (!recoveryExhaustedFired) {
        recoveryExhaustedFired = true;
        options.onRendererRecoveryExhausted?.();
      }
      return;
    }
    const delayMs = 750 * 2 ** autoReloads; // 750ms, 1.5s, 3s
    autoReloads += 1;
    logRenderer(`scheduling auto-reload #${autoReloads} in ${delayMs}ms (${why})`);
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      if (!win.isDestroyed()) {
        win.webContents.reload();
      }
    }, delayMs);
  };

  win.webContents.on('did-finish-load', () => {
    // A clean load resets the budget so a later, unrelated failure still recovers.
    autoReloads = 0;
    logRenderer('renderer did-finish-load');
  });

  // Every top-level navigation with its HTTP status. A blank WHITE screen is
  // usually the bundled Next server answering the route with a non-200 (e.g. a
  // 500 from an SSR throw) — this line shows exactly that ("… -> 500 …"), which
  // an empty-fallback hang (200 but no content) would not.
  win.webContents.on('did-navigate', (_event, url, httpResponseCode, httpStatusText) => {
    logRenderer(`did-navigate ${url} -> ${httpResponseCode} ${httpStatusText}`);
  });

  win.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      // -3 is ERR_ABORTED — fired by ordinary redirects/soft-navigations, not a fault.
      if (errorCode === -3) {
        return;
      }
      logRenderer(
        `did-fail-load code=${errorCode} "${errorDescription}" url=${validatedURL} mainFrame=${isMainFrame}`,
      );
      if (isMainFrame) {
        scheduleReload(`did-fail-load ${errorCode}`);
      }
    },
  );

  win.webContents.on('render-process-gone', (_event, details) => {
    logRenderer(`render-process-gone reason=${details.reason} exitCode=${details.exitCode}`);
    // clean-exit is a normal teardown; every other reason is a crash worth recovering.
    if (details.reason === 'clean-exit') {
      return;
    }
    // Escalation is driven by a time window, NOT the auto-reload counter (which
    // did-finish-load resets between crashes): a reloaded page that briefly loads
    // before crashing again would otherwise keep the counter at 0 forever. Three
    // crashes inside a minute means reloading won't help — hand off to the shell
    // (the Windows GPU software-render relaunch) instead of looping.
    const now = Date.now();
    crashTimestamps.push(now);
    let oldest = crashTimestamps[0];
    while (oldest !== undefined && now - oldest > CRASH_ESCALATE_WINDOW_MS) {
      crashTimestamps.shift();
      oldest = crashTimestamps[0];
    }
    if (crashTimestamps.length >= CRASH_ESCALATE_THRESHOLD && !recoveryExhaustedFired) {
      logRenderer(
        `render crashed ${crashTimestamps.length}x within ${CRASH_ESCALATE_WINDOW_MS / 1000}s — escalating recovery`,
      );
      recoveryExhaustedFired = true;
      options.onRendererRecoveryExhausted?.();
      return;
    }
    scheduleReload(`render-process-gone ${details.reason}`);
  });

  win.webContents.on('unresponsive', () => {
    logRenderer('renderer unresponsive');
  });

  // Renderer console warnings/errors (level 2=warning, 3=error). A failed
  // client-segment fetch or a hydration error logs here and is otherwise
  // invisible in a packaged build; noisy info/debug (0/1) is dropped.
  win.webContents.on('console-message', (_details, level, message, line, sourceId) => {
    if (level >= 2) {
      logRenderer(`console[${level === 3 ? 'error' : 'warn'}] ${message} (${sourceId}:${line})`);
    }
  });

  void win.loadURL(options.url);
  return win;
}
