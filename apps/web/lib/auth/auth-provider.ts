/**
 * Which identity provider this deployment authenticates against.
 *
 * Vicoa's hosted service uses Supabase. A self-hosted deployment can instead
 * run the backend's built-in provider (`AUTH_PROVIDER=builtin`), which issues
 * its own RS256 session tokens and needs no external SaaS — see
 * `backend/src/shared/auth/provider.py`. This module is the only place the web
 * app decides which of the two it is talking to.
 *
 * The value is a build-time `NEXT_PUBLIC_*` because it has to be legible to the
 * client bundle and to middleware, both of which run before any request to the
 * backend. It must match the backend's `AUTH_PROVIDER`; `GET /api/v1/auth/config`
 * reports what the server actually resolved.
 */

export type AuthProviderName = 'supabase' | 'builtin';

/** Cookie the built-in provider's session token lives in. */
export const BUILTIN_SESSION_COOKIE = 'vicoa_session';

export function getAuthProviderName(): AuthProviderName {
  return process.env.NEXT_PUBLIC_AUTH_PROVIDER === 'builtin' ? 'builtin' : 'supabase';
}

export function isBuiltinAuth(): boolean {
  return getAuthProviderName() === 'builtin';
}

export type BuiltinClaims = {
  sub: string;
  email?: string;
  /** Display name, from the token's `name` claim. */
  name?: string;
  exp?: number;
};

/**
 * Read a built-in session token's claims **without verifying the signature**.
 *
 * Safe here and only here: the client uses this to render its own name and to
 * decide when to stop presenting an expired token. Every authorization decision
 * is made by the backend, which does verify. Returns null for anything
 * malformed or already expired.
 */
export function decodeBuiltinToken(token: string | null | undefined): BuiltinClaims | null {
  if (!token) return null;
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(json) as BuiltinClaims;
    if (!claims?.sub) return null;
    if (claims.exp && claims.exp * 1000 <= Date.now()) return null;
    return claims;
  } catch {
    return null;
  }
}

/** Pull the session cookie out of a raw `Cookie:`/`document.cookie` string. */
export function readSessionCookie(cookieHeader: string | null | undefined): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(';')) {
    const [name, ...rest] = part.trim().split('=');
    if (name === BUILTIN_SESSION_COOKIE) {
      return decodeURIComponent(rest.join('=')) || null;
    }
  }
  return null;
}
