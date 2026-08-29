/**
 * Derived shell state — one file (userData/shell-state.json) for values the
 * app records about itself: the stable renderer port and the window bounds.
 * NOT user preferences (those live in settings.json, renderer-owned): this
 * file is opaque, main-process-owned, and safe to delete.
 */
import { app } from 'electron';
import * as fs from 'node:fs';
import * as path from 'node:path';

export interface PersistedWindowState {
  x: number;
  y: number;
  width: number;
  height: number;
  maximized: boolean;
}

interface ShellState {
  rendererPort?: number;
  window?: PersistedWindowState;
}

let cache: ShellState | null = null;

function shellStatePath(): string {
  return path.join(app.getPath('userData'), 'shell-state.json');
}

function isWindowState(value: unknown): value is PersistedWindowState {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.x === 'number' &&
    typeof record.y === 'number' &&
    typeof record.width === 'number' &&
    typeof record.height === 'number'
  );
}

function isPort(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 1024 && value < 65536;
}

/** One-time import from the pre-consolidation files (window-state.json,
    renderer-port.json); missing/corrupt legacy files are just skipped. */
function importLegacyState(): ShellState {
  const state: ShellState = {};
  try {
    const raw = JSON.parse(
      fs.readFileSync(path.join(app.getPath('userData'), 'window-state.json'), 'utf8'),
    ) as Record<string, unknown>;
    if (isWindowState(raw)) {
      state.window = {
        x: raw.x as number,
        y: raw.y as number,
        width: raw.width as number,
        height: raw.height as number,
        maximized: raw.maximized === true,
      };
    }
  } catch {
    // no legacy window state
  }
  try {
    const raw = JSON.parse(
      fs.readFileSync(path.join(app.getPath('userData'), 'renderer-port.json'), 'utf8'),
    ) as { port?: unknown };
    if (isPort(raw.port)) {
      state.rendererPort = raw.port;
    }
  } catch {
    // no legacy port file
  }
  return state;
}

export function readShellState(): ShellState {
  if (cache !== null) return cache;
  try {
    const raw = JSON.parse(fs.readFileSync(shellStatePath(), 'utf8')) as Record<string, unknown>;
    cache = {
      ...(isPort(raw.rendererPort) ? { rendererPort: raw.rendererPort } : {}),
      ...(isWindowState(raw.window) ? { window: { ...raw.window, maximized: raw.window.maximized === true } } : {}),
    };
  } catch {
    cache = importLegacyState();
  }
  return cache;
}

export function updateShellState(patch: Partial<ShellState>): void {
  cache = { ...readShellState(), ...patch };
  try {
    fs.writeFileSync(shellStatePath(), JSON.stringify(cache, null, 2));
  } catch (err) {
    console.warn('[shell-state] failed to persist:', err);
  }
}
