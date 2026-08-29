/**
 * System tray: "Open Vicoa", "Restart daemon", "Quit". Daemon status shows in
 * the tray tooltip rather than as a menu item.
 * The Tray instance is held at module scope — Electron GC-collects it (and
 * the icon vanishes) if no live reference is kept. (Orca pattern.)
 */
import { Menu, nativeImage, Tray } from 'electron';
import * as path from 'node:path';
import type { DaemonState } from './daemon-manager';

export interface TrayCallbacks {
  onOpen: () => void;
  onRestartDaemon: () => void;
  onQuit: () => void;
}

let tray: Tray | null = null;
let callbacks: TrayCallbacks | null = null;
let lastState: DaemonState = { status: 'idle', localOnly: true };

function daemonStatusLabel(state: DaemonState): string {
  switch (state.status) {
    case 'idle':
      return 'Daemon: not started';
    case 'starting':
      return 'Daemon: starting…';
    case 'running':
      return runningLabel(state);
    case 'restarting':
      return 'Daemon: restarting…';
    case 'failed':
      return 'Daemon: failed';
    case 'stopped':
      return 'Daemon: stopped';
  }
}

/** Running label refined by the /healthz `cloud` field when the daemon reports one. */
function runningLabel(state: DaemonState): string {
  if (state.localOnly) {
    return 'Daemon: running (local-only)';
  }
  switch (state.cloudStatus) {
    case 'connected':
      return 'Daemon: connected (cloud)';
    case 'connecting':
      return 'Daemon: connecting to cloud…';
    case 'auth_failed':
      return 'Daemon: auth failed — sign in again';
    case null:
      // Credentialed run reporting no cloud link (shouldn't normally happen).
      return 'Daemon: running (cloud link off)';
    default:
      // Older daemon without the cloud field — preserve the historical label.
      return 'Daemon: running (connected)';
  }
}

function rebuildMenu(): void {
  if (tray === null || tray.isDestroyed() || callbacks === null) {
    return;
  }
  const cbs = callbacks;
  const menu = Menu.buildFromTemplate([
    { label: 'Open Vicoa', click: () => cbs.onOpen() },
    { type: 'separator' },
    { label: 'Restart daemon', click: () => cbs.onRestartDaemon() },
    { type: 'separator' },
    { label: 'Quit', click: () => cbs.onQuit() },
  ]);
  tray.setContextMenu(menu);
  tray.setToolTip(`Vicoa — ${daemonStatusLabel(lastState)}`);
}

/** Create the tray (idempotent). The `trayTemplate.png` filename suffix makes macOS treat it as a template image. */
export function createTray(cbs: TrayCallbacks): Tray {
  callbacks = cbs;
  if (tray !== null && !tray.isDestroyed()) {
    rebuildMenu();
    return tray;
  }
  const iconPath = path.join(__dirname, '..', 'resources', 'trayTemplate.png');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  rebuildMenu();
  return tray;
}

/** Reflect a daemon supervisor state change in the tray menu + tooltip. */
export function updateTrayDaemonState(state: DaemonState): void {
  lastState = state;
  rebuildMenu();
}

export function destroyTray(): void {
  if (tray !== null && !tray.isDestroyed()) {
    tray.destroy();
  }
  tray = null;
  callbacks = null;
}
