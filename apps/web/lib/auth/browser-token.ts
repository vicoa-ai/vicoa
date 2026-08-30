'use client';

/**
 * The browser's bearer token, whichever provider issued it.
 *
 * Every client-side caller that needs to authenticate against the backend (the
 * REST client, the WebSocket handshake, the SSE URLs) goes through here rather
 * than reaching for a Supabase client directly — that is what lets a
 * self-hosted build run with no Supabase project configured at all.
 */

import { isBuiltinAuth } from './auth-provider';
import { getBuiltinClaims, getBuiltinToken } from './builtin-client';

export async function getBrowserAccessToken(): Promise<string | null> {
  if (isBuiltinAuth()) {
    return getBuiltinToken();
  }
  try {
    const { createClient } = await import('./supabase-client');
    const {
      data: { session },
    } = await createClient().auth.getSession();
    return session?.access_token ?? null;
  } catch (error) {
    console.error('Error getting access token:', error);
    return null;
  }
}

/** The signed-in user as the browser sees them, provider-agnostic. */
export type BrowserIdentity = {
  id: string;
  email: string;
  display_name: string | null;
};

export async function readBrowserIdentity(): Promise<BrowserIdentity | null> {
  if (isBuiltinAuth()) {
    const claims = getBuiltinClaims();
    return claims
      ? { id: claims.sub, email: claims.email ?? '', display_name: claims.name ?? null }
      : null;
  }
  try {
    const { createClient } = await import('./supabase-client');
    const {
      data: { user },
    } = await createClient().auth.getUser();
    return user
      ? {
          id: user.id,
          email: user.email ?? '',
          display_name: user.user_metadata?.display_name ?? null,
        }
      : null;
  } catch (error) {
    console.error('Error reading the browser identity:', error);
    return null;
  }
}
