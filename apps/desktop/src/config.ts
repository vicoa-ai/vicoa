/**
 * Nonce / port / paths / credentials helpers for the Vicoa desktop shell.
 *
 * The daemon wire contract (plans/todos/desktop-app-v1-implementation.md):
 * - Electron generates a per-launch 32-byte hex nonce and picks a free
 *   localhost port itself, then passes both to the daemon via env + flags.
 * - Authenticated = ~/.vicoa/credentials.json exists with a non-empty
 *   `write_key` string (same shape the `vicoa` CLI reads/writes).
 */
import { app } from 'electron';
import { randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as net from 'node:net';
import * as os from 'node:os';
import * as path from 'node:path';
import { readShellState, updateShellState } from './shell-state';

/** Runtime config injected into the renderer as `window.__VICOA_DESKTOP__`. */
export interface DesktopConfig {
  mode: 'local' | 'cloud';
  wsUrl: string;
  apiBase: string;
  token: string;
  /** Self-hosted cloud REST base (see `readSelfHostEndpoints`); absent → build-time default. */
  cloudApiBase?: string;
  /** Self-hosted cloud WebSocket URL; absent → build-time default. */
  cloudWsUrl?: string;
}

/** Runtime override of the cloud endpoints, for people running their own backend. */
export interface SelfHostEndpoints {
  apiUrl?: string;
  wsUrl?: string;
  authUrl?: string;
}

/** Per-launch secret shared with the daemon; renderer presents it as Bearer/WS subprotocol token. */
export function generateNonce(): string {
  return randomBytes(32).toString('hex');
}

/**
 * Ask the OS for a free localhost port (listen on port 0, read the assigned
 * port, close). Small TOCTOU window before the daemon binds it — acceptable
 * for v1 (loopback, immediately respawned on failure by the supervisor).
 */
export function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (address === null || typeof address === 'string') {
        server.close();
        reject(new Error('Failed to determine a free port'));
        return;
      }
      const port = address.port;
      server.close((err) => (err ? reject(err) : resolve(port)));
    });
  });
}

/** Whether `port` is currently bindable on loopback. */
function portAvailable(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => resolve(false));
    server.listen(port, '127.0.0.1', () => {
      server.close(() => resolve(true));
    });
  });
}

/** Uncommon loopback port tried on a fresh install (before one is persisted). */
const DEFAULT_RENDERER_PORT = 43117;

/**
 * A STABLE port for the packaged renderer server, persisted in shell state.
 *
 * The renderer's origin is `http://127.0.0.1:<port>`, and Chromium keys
 * localStorage (drafts, panel state…) by origin — a random per-launch port
 * silently reset every preference on each run. Reuse the persisted port
 * whenever it's still free; fall back to a fresh one (persisting it) only
 * when something else grabbed it, which costs at most a one-time reset of
 * the origin-keyed state.
 */
export async function getStableRendererPort(): Promise<number> {
  const saved = readShellState().rendererPort ?? null;

  for (const candidate of [saved, DEFAULT_RENDERER_PORT]) {
    if (candidate !== null && (await portAvailable(candidate))) {
      updateShellState({ rendererPort: candidate });
      return candidate;
    }
  }

  const fresh = await pickFreePort();
  updateShellState({ rendererPort: fresh });
  return fresh;
}

/**
 * Bundled mode = production boot path: serve the renderer from the packaged
 * Next standalone server and prefer the bundled frozen daemon. True when the
 * app is packaged, or forced via VICOA_BUNDLED=1 for pre-package testing of
 * the exact same code path from a checkout.
 */
export function isBundled(): boolean {
  return app.isPackaged || process.env.VICOA_BUNDLED === '1';
}

/**
 * Root of the bundled resources. Packaged: Electron's resources dir
 * (extraResources land there). Unpackaged (VICOA_BUNDLED=1): the electron/
 * directory itself, where the build scripts stage renderer-dist/ and
 * daemon-dist/ — same layout, different root.
 */
function bundledResource(...packagedSegments: string[]): string {
  return path.join(process.resourcesPath, ...packagedSegments);
}

/** Absolute path to the bundled Next standalone entry (may not exist — caller checks). */
export function rendererServerPath(): string {
  if (app.isPackaged) {
    return bundledResource('renderer', 'server.js');
  }
  return path.join(__dirname, '..', 'renderer-dist', 'server.js');
}

/**
 * Bundled frozen daemon executable (PyInstaller onedir staged as
 * resources/daemon/<exe> next to its _internal/). Null when not bundled or
 * missing — the caller falls back to `vicoa` on PATH.
 */
export function bundledDaemonPath(): string | null {
  const name = process.platform === 'win32' ? 'vicoa.exe' : 'vicoa';
  const exe = app.isPackaged
    ? bundledResource('daemon', name)
    : path.join(__dirname, '..', 'daemon-dist', process.arch === 'x64' ? 'x64' : 'arm64', name);
  try {
    return fs.existsSync(exe) ? exe : null;
  } catch {
    return null;
  }
}

/** Renderer URL for the dev path: the next dev server. Bundled mode ignores this (see renderer-server.ts). */
export function rendererUrl(): string {
  return process.env.VICOA_RENDERER_URL ?? 'http://localhost:3000';
}

/** Origin handed to the daemon as VICOA_LOCAL_ORIGIN (it rejects other WS Origins). */
export function rendererOrigin(): string {
  return new URL(rendererUrl()).origin;
}

export function vicoaConfigDir(): string {
  return path.join(os.homedir(), '.vicoa');
}

export function credentialsPath(): string {
  return path.join(vicoaConfigDir(), 'credentials.json');
}

/** Parse ~/.vicoa/credentials.json; null when missing/corrupt. */
export function readCredentials(): Record<string, unknown> | null {
  try {
    const raw = fs.readFileSync(credentialsPath(), 'utf8');
    const data: unknown = JSON.parse(raw);
    if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
      return data as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

/** Authenticated = credentials.json has a non-empty string `write_key`. */
export function hasWriteKey(): boolean {
  const creds = readCredentials();
  const key = creds?.['write_key'];
  return typeof key === 'string' && key.trim().length > 0;
}

function writeCredentialsFile(data: Record<string, unknown>): void {
  const dir = vicoaConfigDir();
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = credentialsPath();
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', { mode: 0o600 });
  // mkdir/writeFile modes are ignored for pre-existing paths; enforce explicitly.
  fs.chmodSync(file, 0o600);
}

/** Merge `write_key` into credentials.json (preserving unknown fields), mode 600. */
export function saveWriteKey(key: string): void {
  const existing = readCredentials() ?? {};
  writeCredentialsFile({ ...existing, write_key: key });
}

/** Remove `write_key` from credentials.json, preserving any other fields. No-op when file is absent. */
export function removeWriteKey(): void {
  const existing = readCredentials();
  if (existing === null) {
    return;
  }
  delete existing['write_key'];
  writeCredentialsFile(existing);
}

/**
 * Where a self-hosted backend lives.
 *
 * The packaged app is built against Vicoa's hosted service — the renderer
 * bundle inlines `NEXT_PUBLIC_BACKEND_API_URL` / `NEXT_PUBLIC_VICOA_WS_URL` at
 * build time — so pointing a *downloaded* build at your own backend has to
 * happen at runtime. First hit wins:
 *
 *   1. env: `VICOA_API_URL`, `VICOA_WS_URL`, `VICOA_AUTH_URL`
 *   2. `~/.vicoa/desktop.json`: `{ "apiUrl": …, "wsUrl": …, "authUrl": … }`
 *   3. nothing set → the build-time defaults (Vicoa's hosted service)
 *
 * `wsUrl` is derived from `apiUrl` when only the latter is given.
 */
export function desktopConfigFilePath(): string {
  return path.join(vicoaConfigDir(), 'desktop.json');
}

function readDesktopConfigFile(): SelfHostEndpoints {
  try {
    const raw = fs.readFileSync(desktopConfigFilePath(), 'utf8');
    const data: unknown = JSON.parse(raw);
    if (typeof data !== 'object' || data === null || Array.isArray(data)) return {};
    const record = data as Record<string, unknown>;
    const pick = (key: string): string | undefined => {
      const value = record[key];
      return typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined;
    };
    return { apiUrl: pick('apiUrl'), wsUrl: pick('wsUrl'), authUrl: pick('authUrl') };
  } catch {
    return {};
  }
}

/** `https://host` → `wss://host/ws` (and `http://` → `ws://`). */
function deriveWsUrl(apiUrl: string): string | undefined {
  try {
    const url = new URL(apiUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = url.pathname.replace(/\/+$/, '') + '/ws';
    return url.toString();
  } catch {
    return undefined;
  }
}

export function readSelfHostEndpoints(): SelfHostEndpoints {
  const file = readDesktopConfigFile();
  const fromEnv = (name: string): string | undefined => {
    const value = process.env[name];
    return value !== undefined && value.trim() !== '' ? value.trim() : undefined;
  };

  const apiUrl = fromEnv('VICOA_API_URL') ?? file.apiUrl;
  const wsUrl =
    fromEnv('VICOA_WS_URL') ?? file.wsUrl ?? (apiUrl !== undefined ? deriveWsUrl(apiUrl) : undefined);
  const authUrl = fromEnv('VICOA_AUTH_URL') ?? file.authUrl;

  const endpoints: SelfHostEndpoints = {};
  if (apiUrl !== undefined) endpoints.apiUrl = apiUrl;
  if (wsUrl !== undefined) endpoints.wsUrl = wsUrl;
  if (authUrl !== undefined) endpoints.authUrl = authUrl;
  return endpoints;
}
