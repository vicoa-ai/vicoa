import { redirect } from 'next/navigation';
import { getSupabaseUser } from '@/lib/auth/supabase-helpers';
import {
  authedRedirectAllowedOrigins,
  resolveAuthedRedirect,
} from '@/lib/auth/redirect-target';

/**
 * Bounce an already-authenticated visitor off /sign-in and /sign-up.
 *
 * Honors the page's `redirect` query param (validated — relative path or
 * allowlisted origin) instead of always landing on /dashboard: the desktop
 * login handoff arrives here as /sign-in?redirect=<desktop-auth URL>, and a
 * user who is already signed in must be sent BACK to /desktop-auth so the
 * app handoff can complete — not stranded on the dashboard.
 */
export async function redirectAuthenticatedUser(redirectParam?: string) {
  const target = resolveAuthedRedirect(redirectParam, authedRedirectAllowedOrigins());

  const user = await getSupabaseUser();

  if (user) {
    redirect(target);
  }
}
