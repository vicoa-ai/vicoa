/**
 * User preferences — userData/settings.json, the desktop analogue of an
 * IDE's settings file. Human-readable and safe to hand-edit; the renderer
 * is the writer (via the preload bridge) and gets a synchronous snapshot at
 * document load (same pattern as the desktop config injection).
 *
 * Flat map of preference key → JSON value, e.g.
 *   { "sidebar-group-by": "project",
 *     "sidebar-project-order": ["vipost", "vicoa-ai"],
 *     "desktop-shortcut-overrides": { "open-diff": { … } } }
 */
import { app, ipcMain } from 'electron';
import * as fs from 'node:fs';
import * as path from 'node:path';

type SettingsMap = Record<string, unknown>;

let cache: SettingsMap | null = null;

function settingsPath(): string {
  return path.join(app.getPath('userData'), 'settings.json');
}

function loadSettings(): SettingsMap {
  if (cache !== null) return cache;
  try {
    const raw = JSON.parse(fs.readFileSync(settingsPath(), 'utf8'));
    cache = typeof raw === 'object' && raw !== null && !Array.isArray(raw) ? (raw as SettingsMap) : {};
  } catch {
    cache = {};
  }
  return cache;
}

function persist(): void {
  try {
    fs.writeFileSync(settingsPath(), JSON.stringify(cache ?? {}, null, 2) + '\n');
  } catch (err) {
    console.warn('[settings] failed to persist:', err);
  }
}

export function registerSettingsIpc(): void {
  // Synchronous snapshot for the preload (one read per document load).
  ipcMain.on('vicoa:get-settings', (event) => {
    event.returnValue = loadSettings();
  });

  ipcMain.handle('vicoa:settings-set', (_event, key: unknown, value: unknown) => {
    if (typeof key !== 'string' || key.length === 0 || key.length > 200) {
      return;
    }
    const settings = loadSettings();
    if (value === null || value === undefined) {
      delete settings[key];
    } else {
      settings[key] = value; // structured-clone-validated by the IPC layer
    }
    persist();
  });
}
