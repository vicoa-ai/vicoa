'use client';

/**
 * End the browser session, whichever provider started it.
 *
 * Supabase sign-out is scoped `local` so it drops this browser only and leaves
 * the user's other devices (desktop app, phone) signed in. The built-in
 * provider has no server-side session to revoke — its tokens are stateless JWTs
 * — so clearing the cookie is the whole operation.
 */

import { isBuiltinAuth } from './auth-provider';
import { clearBuiltinSession } from './builtin-client';

export async function signOutBrowser(): Promise<void> {
  if (isBuiltinAuth()) {
    clearBuiltinSession();
    return;
  }
  const { createClient } = await import('./supabase-client');
  await createClient().auth.signOut({ scope: 'local' });
}
