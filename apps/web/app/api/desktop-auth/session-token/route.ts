import { NextResponse } from 'next/server';
import { createClient as createSupabaseClient } from '@supabase/supabase-js';
import { createClient } from '@/lib/auth/supabase-server';

/**
 * Mint a ONE-TIME sign-in token for the desktop app (browser handoff).
 *
 * The old handoff copied the browser's access+refresh tokens into the
 * `vicoa://` callback, so the app and the website shared ONE refresh-token
 * family. With Supabase refresh-token rotation, whichever client refreshed
 * first invalidated the other's token; the loser's next refresh tripped
 * reuse detection and revoked the WHOLE family — signing the user out of the
 * website (and eventually the app) about an hour after every desktop login.
 *
 * Instead: `generateLink({ type: 'magiclink' })` (admin API — no email is
 * sent) returns a `hashed_token`; the app verifies it once with
 * `verifyOtp` and receives its OWN independent session. It is single-use,
 * short-lived, and never a long-lived credential in a URL.
 *
 * 501 when the service-role key isn't configured — the caller falls back to
 * the legacy token handoff so the flow never hard-breaks on deploy config.
 */
export async function POST() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceRoleKey || !user.email) {
    return NextResponse.json({ error: 'One-time token minting not configured' }, { status: 501 });
  }

  const admin = createSupabaseClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const { data, error } = await admin.auth.admin.generateLink({
    type: 'magiclink',
    email: user.email,
  });

  const tokenHash = data?.properties?.hashed_token;
  if (error || !tokenHash) {
    return NextResponse.json(
      { error: error?.message ?? 'Failed to mint a one-time token' },
      { status: 500 }
    );
  }

  return NextResponse.json({ tokenHash });
}
