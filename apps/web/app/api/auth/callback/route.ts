import { NextResponse } from 'next/server';
import { createClient } from '@/lib/auth/supabase-server';
import { captureServerEvent } from '@/lib/posthog-server';

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get('code');
  const next = requestUrl.searchParams.get('next') ?? '/dashboard';
  const baseOrigin =
    process.env.NODE_ENV !== 'development' && process.env.BASE_URL
      ? process.env.BASE_URL
      : requestUrl.origin;

  if (code) {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      let destination = next;
      const user = data?.user;
      if (user) {
        const provider = user.app_metadata?.provider ?? 'oauth';
        let isNewUser = false;
        if (user.created_at && user.last_sign_in_at) {
          const createdAt = new Date(user.created_at).getTime();
          const lastSignIn = new Date(user.last_sign_in_at).getTime();
          isNewUser = Math.abs(lastSignIn - createdAt) < 120_000;
        }
        if (isNewUser) {
          destination += (destination.includes('?') ? '&' : '?') + 'new_user=1';
          await captureServerEvent(user.id, 'signup_completed', {
            method: provider,
            $set_once: { signup_origin: 'web' },
          });
        } else {
          await captureServerEvent(user.id, 'login_completed', { method: provider });
        }
      }
      return NextResponse.redirect(new URL(destination, baseOrigin));
    }
  }

  // Return the user to an error page with some instructions
  return NextResponse.redirect(new URL('/sign-in?error=auth_failed', baseOrigin));
}
