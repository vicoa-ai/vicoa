/**
 * Desktop social-login (OAuth) flow (desktop-app v1 plan, "Login flow").
 *
 * A normal web OAuth redirect can't complete inside Electron — Google blocks
 * embedded/Electron user agents, and the http(s) callback can't navigate back
 * into the app window. The standard desktop pattern instead:
 *
 *   1. `startDesktopOAuth(provider)` — ask supabase-js for the provider authorize
 *      URL WITHOUT navigating (`skipBrowserRedirect: true`) and with a custom
 *      redirect (`vicoa://auth/callback`). This also stashes the PKCE code
 *      verifier in THIS renderer's Supabase storage. Then hand the URL to the
 *      Electron shell to open in the user's SYSTEM browser.
 *   2. The user completes sign-in in their real browser; the provider redirects
 *      to `vicoa://auth/callback?code=…`, which the OS routes to the registered
 *      Electron shell, which forwards it to the renderer via `onDeepLink`.
 *   3. `parseOAuthCallbackUrl(url)` extracts the `code` (or an `error`), and
 *      `exchangeDesktopOAuthCode(code)` swaps it for a Supabase session — the
 *      verifier from step 1 lives in this same renderer, so the exchange
 *      succeeds. The existing `DesktopAuthHandoff` then mints the CLI key.
 *
 * All three functions run in the browser renderer only. On plain web the social
 * buttons keep their existing server-action redirect path — this module is not
 * used there.
 */

import { createClient } from '@/lib/auth/supabase-client';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';

/** Custom-scheme callback the Electron shell registers and forwards to the renderer. */
export const DESKTOP_OAUTH_REDIRECT = 'vicoa://auth/callback';

/** Providers wired up for desktop social login. */
export type DesktopOAuthProvider = 'google' | 'apple';

export interface ParsedOAuthCallback {
  /** PKCE authorization code, if the callback carried one. */
  code?: string;
  /** Provider/Supabase error slug (e.g. `access_denied`), if the callback failed. */
  error?: string;
  /** Human-readable error detail that accompanies `error`, if present. */
  errorDescription?: string;
}

/**
 * Pure parser for a `vicoa://auth/callback` deep link.
 *
 * Supabase's PKCE flow returns `?code=…` in the query string, but some
 * providers/configurations put the params in the URL fragment (`#code=…`), and
 * failures arrive as `?error=…&error_description=…`. This scans BOTH the query
 * and the fragment (query wins on conflict) so the caller doesn't depend on
 * `URL` parsing the non-special `vicoa:` scheme consistently across runtimes.
 */
export function parseOAuthCallbackUrl(rawUrl: string): ParsedOAuthCallback {
  const result: ParsedOAuthCallback = {};

  const collect = (segment: string): void => {
    if (!segment) return;
    const params = new URLSearchParams(segment);
    const code = params.get('code');
    if (!result.code && code) {
      result.code = code;
    }
    const error = params.get('error');
    if (!result.error && error) {
      result.error = error;
      result.errorDescription = params.get('error_description') ?? undefined;
    }
  };

  // Split off the fragment (everything after the first `#`) and, from what
  // remains, the query (everything after the first `?`).
  const hashIndex = rawUrl.indexOf('#');
  const beforeHash = hashIndex >= 0 ? rawUrl.slice(0, hashIndex) : rawUrl;
  const fragment = hashIndex >= 0 ? rawUrl.slice(hashIndex + 1) : '';

  const queryIndex = beforeHash.indexOf('?');
  const query = queryIndex >= 0 ? beforeHash.slice(queryIndex + 1) : '';

  collect(query);
  collect(fragment);
  return result;
}

/**
 * Kick off the desktop OAuth flow: mint the provider authorize URL without
 * navigating and open it in the system browser. Throws if the desktop bridge is
 * unavailable, Supabase errors, or no URL comes back.
 */
export async function startDesktopOAuth(provider: DesktopOAuthProvider): Promise<void> {
  const bridge = getDesktopAuthBridge();
  if (!bridge) {
    throw new Error('Desktop bridge unavailable');
  }

  const supabase = createClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: DESKTOP_OAUTH_REDIRECT,
      // Return the URL instead of navigating the Electron window (which would
      // load the provider page in a blocked embedded user agent). PKCE is the
      // supabase-js v2 default, so the code verifier is stashed in this
      // renderer's storage as a side effect.
      skipBrowserRedirect: true,
    },
  });

  if (error) {
    throw new Error(error.message);
  }
  if (!data?.url) {
    throw new Error('Supabase did not return an OAuth URL');
  }

  await bridge.openExternal(data.url);
}

/**
 * Exchange a PKCE authorization code (from the `vicoa://auth/callback` deep
 * link) for a Supabase session in this renderer. On success the session is
 * persisted and `onAuthStateChange`/`getSession` will report it — the existing
 * `DesktopAuthHandoff` takes over from there. Throws on Supabase error.
 */
export async function exchangeDesktopOAuthCode(code: string): Promise<void> {
  const supabase = createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    throw new Error(error.message);
  }
}
