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
    const client = createClient();
    const {
      data: { user },
    } = await client.auth.getUser();
    if (!user) return null;
    // Same precedence the backend reads off the token (`_display_name` in
    // shared/auth/supabase_provider.py) — a Google sign-in publishes
    // `full_name`, not `display_name`, and reading only the latter sent a null
    // that the backend used to write over a perfectly good name.
    const metadata = user.user_metadata ?? {};
    let name: string | null =
      metadata.display_name?.trim() || metadata.full_name?.trim() || metadata.name?.trim() || null;
    if (!name) {
      // The legacy Supabase-side copy: accounts that set a name before the
      // backend owned one have it only here. Sync carries it over once; a
      // failure just means the account keeps no name for now.
      const { data } = await client
        .from('profiles')
        .select('display_name')
        .eq('id', user.id)
        .maybeSingle();
      name = data?.display_name?.trim() || null;
    }
    return { id: user.id, email: user.email ?? '', display_name: name };
  } catch (error) {
    console.error('Error reading the browser identity:', error);
    return null;
  }
}
