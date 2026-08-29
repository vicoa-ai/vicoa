/**
 * Desktop login handoff helpers (desktop-app v1 plan, "Login flow").
 *
 * The Electron preload exposes `window.vicoaDesktopAuth` alongside
 * `window.__VICOA_DESKTOP__` (see electron/src/preload.ts — that file lives in
 * a separate TS project excluded from this tsconfig, so the renderer-side
 * type of the bridge is declared here). Flow:
 *
 *   1. The user signs into Supabase in-window (existing /sign-in page).
 *   2. While the daemon is still in `local` mode, the renderer mints a CLI
 *      key straight from the cloud backend: `POST /api/v1/auth/cli-key` with
 *      the Supabase JWT (same backend call app/api/cli-auth/generate-key
 *      makes server-side; response shape is APIKeyResponse — `api_key` holds
 *      the raw key).
 *   3. `vicoaDesktopAuth.setApiKey(key)` hands it to the Electron main
 *      process, which persists it, restarts the daemon in cloud mode, and
 *      reloads the window — the injected config then reports `mode: 'cloud'`.
 *
 * NOTE: the mint deliberately does NOT go through `getBackendAPI()`, which in
 * desktop-local mode routes every call to the daemon's local server — the CLI
 * key can only be minted by the cloud backend.
 */

import { getCloudApiBase } from '@/lib/runtime-config';

/** localStorage key holding the browser-handoff nonce. Persisted (not just a
    ref) so it survives a `/desktop-signin` remount — otherwise a remount would
    mint a fresh nonce, re-open the browser, and orphan the pending callback.
    localStorage (not sessionStorage) because the browser leg can outlive the
    renderer's session: an app restart or window re-create mid-flow (e.g. the
    user signs up and confirms email minutes later) must still be able to match
    the buffered callback's `state` when `/desktop-signin` comes back up. */
export const DESKTOP_AUTH_NONCE_KEY = 'vicoa-desktop-auth-nonce';

/** localStorage key holding recently ISSUED handoff nonces (JSON array of
    `{ n, t }`). A browser leg can outlive the attempt that opened it — Chrome
    session restore resurrects an old sign-in tab, the user types credentials
    into it, and its callback carries an older (but app-issued) state. Any
    nonce this app recently issued is trustworthy, so callbacks are validated
    against this history, not only the latest nonce. */
export const DESKTOP_AUTH_NONCE_HISTORY_KEY = 'vicoa-desktop-auth-nonces';

/** How long an issued nonce stays acceptable. Long enough for "restored the
    tab after lunch", short enough that ancient links die. */
export const DESKTOP_AUTH_NONCE_TTL_MS = 24 * 60 * 60 * 1000;

interface IssuedNonce {
  n: string;
  t: number;
}

/** Drop expired entries and cap the list (pure; unit-tested). */
export function pruneNonceHistory(
  history: IssuedNonce[],
  now: number,
  ttlMs: number = DESKTOP_AUTH_NONCE_TTL_MS,
  maxEntries = 10
): IssuedNonce[] {
  return history
    .filter((e) => e && typeof e.n === 'string' && e.n.length > 0)
    .filter((e) => typeof e.t === 'number' && now - e.t <= ttlMs)
    .slice(-maxEntries);
}

function readNonceHistory(): IssuedNonce[] {
  try {
    const raw = window.localStorage.getItem(DESKTOP_AUTH_NONCE_HISTORY_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? pruneNonceHistory(parsed as IssuedNonce[], Date.now()) : [];
  } catch {
    return [];
  }
}

/** Read the pending handoff nonce ('' when none). Reads the legacy
    sessionStorage slot too so a flow started pre-upgrade still completes. */
export function readDesktopAuthNonce(): string {
  try {
    return (
      window.localStorage.getItem(DESKTOP_AUTH_NONCE_KEY) ??
      window.sessionStorage.getItem(DESKTOP_AUTH_NONCE_KEY) ??
      ''
    );
  } catch {
    return '';
  }
}

/** Persist the handoff nonce for /desktop-signin to adopt, and remember it
    in the issued-nonce history so a stale-but-ours browser leg still
    completes. */
export function storeDesktopAuthNonce(nonce: string): void {
  try {
    window.localStorage.setItem(DESKTOP_AUTH_NONCE_KEY, nonce);
    const history = readNonceHistory().filter((e) => e.n !== nonce);
    history.push({ n: nonce, t: Date.now() });
    window.localStorage.setItem(
      DESKTOP_AUTH_NONCE_HISTORY_KEY,
      JSON.stringify(pruneNonceHistory(history, Date.now()))
    );
  } catch {
    // Non-fatal; the receiver screen falls back to opening the browser itself.
  }
}

/** True when `state` is a nonce THIS app issued recently (current attempt or
    a still-valid earlier one). The trust boundary is "issued by this app on
    this machine" — a callback with a foreign state is still rejected. */
export function matchesIssuedNonce(state: string): boolean {
  if (!state) return false;
  if (state === readDesktopAuthNonce()) return true;
  return readNonceHistory().some((e) => e.n === state);
}

/** Drop the CURRENT pending nonce (user canceled this attempt). The issued
    history survives so a still-open browser leg from an earlier attempt can
    complete if the user finishes it after all. */
export function clearDesktopAuthNonce(): void {
  try {
    window.localStorage.removeItem(DESKTOP_AUTH_NONCE_KEY);
    window.sessionStorage.removeItem(DESKTOP_AUTH_NONCE_KEY);
  } catch {
    // ignore
  }
}

/** Drop everything — pending nonce AND issued history. Called when a
    sign-in actually completes (no outstanding leg should stay redeemable). */
export function clearAllDesktopAuthNonces(): void {
  try {
    window.localStorage.removeItem(DESKTOP_AUTH_NONCE_KEY);
    window.localStorage.removeItem(DESKTOP_AUTH_NONCE_HISTORY_KEY);
    window.sessionStorage.removeItem(DESKTOP_AUTH_NONCE_KEY);
  } catch {
    // ignore
  }
}

export interface DesktopAuthCallback {
  apiKey: string | null;
  state: string | null;
  /** One-time sign-in token (preferred): verified via `verifyOtp` so the app
      gets its OWN session instead of sharing the browser's refresh token. */
  tokenHash: string | null;
  /** Legacy handoff fields — copies of the browser session's tokens. Only
      used when the web side predates the token_hash flow. */
  accessToken: string | null;
  refreshToken: string | null;
}

/** Parse a `vicoa://auth/callback?…` deep link; null for other deep links. */
export function parseDesktopAuthCallback(url: string): DesktopAuthCallback | null {
  if (!url.startsWith('vicoa://auth/callback')) return null;
  const queryIndex = url.indexOf('?');
  const params = new URLSearchParams(queryIndex === -1 ? '' : url.slice(queryIndex + 1));
  return {
    apiKey: params.get('api_key'),
    state: params.get('state'),
    tokenHash: params.get('token_hash'),
    accessToken: params.get('access_token'),
    refreshToken: params.get('refresh_token'),
  };
}

/** @deprecated Superseded by reading the email from the validated session.
    Still referenced by the settings profile section pending its cleanup. */
export const DESKTOP_ACCOUNT_EMAIL_KEY = 'vicoa-desktop-account-email';

/** Build the browser sign-in handoff URL for `/desktop-auth`. `mode: 'signup'`
    sends the user to create an account instead of signing in. */
export function desktopAuthUrl(nonce: string, mode?: string | null): string {
  const base = process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai';
  const modeParam = mode === 'signup' ? '&mode=signup' : '';
  return `${base}/desktop-auth?state=${nonce}${modeParam}`;
}

export interface DesktopAuthResult {
  ok: boolean;
  error?: string;
}

export interface DesktopAuthBridge {
  /** Persist a freshly minted API key; the shell restarts the daemon in cloud mode and reloads the window. */
  setApiKey(key: string): Promise<DesktopAuthResult>;
  /** Drop the stored key; the shell restarts the daemon with --local-only and reloads the window. */
  signOut(): Promise<DesktopAuthResult>;
  /**
   * Subscribe to `vicoa://…` deep links forwarded by the Electron shell — e.g.
   * the OAuth callback `vicoa://auth/callback?code=…`. The callback receives the
   * FULL url string. Returns an unsubscribe function. A deep link that arrived
   * before this subscription (cold start / mid-reload) is BUFFERED by the shell
   * and replayed on subscribe, so subscribe early and none is missed.
   */
  onDeepLink(cb: (url: string) => void): () => void;
  /**
   * Open a URL in the user's default (system) browser — the OAuth authorize
   * step, or any external link. Only http(s)/`vicoa:` URLs are honored.
   */
  openExternal(url: string): Promise<void>;
}

declare global {
  interface Window {
    /** Injected by the Electron preload (contextBridge); absent on plain web. */
    vicoaDesktopAuth?: DesktopAuthBridge;
  }
}

/** The preload-injected auth bridge, or `null` on plain web / SSR. */
export function getDesktopAuthBridge(): DesktopAuthBridge | null {
  if (typeof window === 'undefined') return null;
  return window.vicoaDesktopAuth ?? null;
}

/** Thrown by `mintCliKey` with the HTTP status, so callers can tell a dead
    session (401/403 — clean up and re-login) from a transient failure. */
export class CliKeyMintError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'CliKeyMintError';
  }
}

/**
 * Mint a CLI API key from the cloud backend using a Supabase access token.
 * Endpoint verified against vicoa-backend `src/backend/auth/routes.py`
 * (`create_cli_key`): `POST /api/v1/auth/cli-key` → APIKeyResponse.
 */
export async function mintCliKey(accessToken: string): Promise<string> {
  const baseUrl = getCloudApiBase();
  const response = await fetch(`${baseUrl}/api/v1/auth/cli-key`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    let message = `Failed to mint CLI key: ${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string' && body.detail.trim()) {
        message = body.detail;
      }
    } catch {
      // Keep the generic HTTP error.
    }
    throw new CliKeyMintError(message, response.status);
  }

  const body = (await response.json()) as { api_key?: unknown };
  if (typeof body.api_key !== 'string' || body.api_key.length === 0) {
    throw new Error('CLI key response did not include an api_key');
  }
  return body.api_key;
}
