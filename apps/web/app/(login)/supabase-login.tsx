'use client';

import Link from 'next/link';
import { useActionState, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Mail } from 'lucide-react';
import Image from 'next/image';
import { supabaseSignIn, supabaseSignUp, supabaseSignInWithGoogle, supabaseSignInWithApple } from './supabase-actions';
import { ActionState } from '@/lib/auth/supabase-helpers';
import { getDesktopConfig } from '@/lib/runtime-config';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import {
  startDesktopOAuth,
  exchangeDesktopOAuthCode,
  parseOAuthCallbackUrl,
  DESKTOP_OAUTH_REDIRECT,
  type DesktopOAuthProvider,
} from '@/lib/desktop-oauth';
import posthog from 'posthog-js';

// Desktop v1: a normal web OAuth redirect can't complete inside Electron
// (Google blocks embedded user agents and the http callback can't navigate back
// into the window), so in desktop mode the social buttons take an
// external-browser + `vicoa://` deep-link path (see `lib/desktop-oauth.ts` and
// the handlers below) instead of the web server-action redirect. The branch is
// on the RUNTIME `getDesktopConfig()` (injected by the Electron preload), so web
// behavior is untouched and there's no reliance on a compile-time build flag.

// Desktop-only status for the external-browser OAuth handshake. `idle` is the
// normal chooser; the other states drive the "waiting"/"completing"/error card.
type DesktopOAuthStatus = 'idle' | 'waiting' | 'exchanging' | 'error';

export function SupabaseLogin({
  mode = 'signin',
  googleClientId,
  appleClientId,
}: {
  mode?: 'signin' | 'signup';
  googleClientId?: string;
  appleClientId?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect');
  const priceId = searchParams.get('priceId');
  const inviteId = searchParams.get('inviteId');
  const emailParam = searchParams.get('email');
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    mode === 'signin' ? supabaseSignIn : supabaseSignUp,
    { error: '' }
  );

  // Desktop external-browser OAuth handshake state (unused on plain web).
  const [oauthStatus, setOauthStatus] = useState<DesktopOAuthStatus>('idle');
  const [oauthError, setOauthError] = useState<string | null>(null);
  // Single-flight guard: a buffered/replayed callback URL must not double-run
  // `exchangeCodeForSession`. Set true the moment we accept a code, reset when a
  // fresh OAuth attempt starts (retry).
  const oauthHandledRef = useRef(false);

  const beginDesktopOAuth = useCallback(async (provider: DesktopOAuthProvider) => {
    oauthHandledRef.current = false;
    setOauthError(null);
    setOauthStatus('waiting');
    try {
      await startDesktopOAuth(provider);
    } catch (err) {
      setOauthStatus('error');
      setOauthError(err instanceof Error ? err.message : 'Could not start sign-in');
    }
  }, []);

  const cancelDesktopOAuth = useCallback(() => {
    oauthHandledRef.current = false;
    setOauthError(null);
    setOauthStatus('idle');
  }, []);

  // Desktop: catch the `vicoa://auth/callback?…` deep link from the system
  // browser, exchange the PKCE code for a session in THIS renderer, then hand
  // off to /dashboard where the existing DesktopAuthHandoff mints the CLI key.
  // Subscribed on mount (before any click) so a fast callback is never missed;
  // the shell also buffers + replays a callback that beat this subscription.
  useEffect(() => {
    if (getDesktopConfig() === null) return;
    const bridge = getDesktopAuthBridge();
    if (!bridge) return;

    const unsubscribe = bridge.onDeepLink((url) => {
      if (!url.startsWith(DESKTOP_OAUTH_REDIRECT)) return; // ignore unrelated deep links
      const { code, error, errorDescription } = parseOAuthCallbackUrl(url);

      if (error) {
        oauthHandledRef.current = false;
        setOauthStatus('error');
        setOauthError(errorDescription || error);
        return;
      }
      if (!code) return;
      if (oauthHandledRef.current) return; // single-flight: drop replays
      oauthHandledRef.current = true;
      setOauthStatus('exchanging');

      void (async () => {
        try {
          await exchangeDesktopOAuthCode(code);
          // Session is now set in this renderer's storage. Route to the
          // dashboard, where DesktopAuthHandoff mints the CLI key and hands it
          // to the shell (daemon restarts in cloud mode + window reloads). Keep
          // the "completing" state up so the UI doesn't flash back.
          router.replace('/dashboard');
        } catch (err) {
          oauthHandledRef.current = false;
          setOauthStatus('error');
          setOauthError(err instanceof Error ? err.message : 'Sign-in could not be completed');
        }
      })();
    });

    return unsubscribe;
  }, [router]);

  const handleGoogleSignIn = async () => {
    posthog.capture(mode === 'signup' ? 'signup_started' : 'login_started', { method: 'google' });
    if (getDesktopConfig() !== null) {
      await beginDesktopOAuth('google');
      return;
    }
    await supabaseSignInWithGoogle(redirect || undefined);
  };

  const handleAppleSignIn = async () => {
    posthog.capture(mode === 'signup' ? 'signup_started' : 'login_started', { method: 'apple' });
    if (getDesktopConfig() !== null) {
      await beginDesktopOAuth('apple');
      return;
    }
    await supabaseSignInWithApple(redirect || undefined);
  };

  return (
    <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Image 
            src="/images/vicoa-light.webp"
            alt="Vibe Code Anywhere Logo" 
            width={0} 
            height={0} 
            sizes="100vw"
            className="h-12 w-auto opacity-90" 
          />
        </div>
        <h2 className="mt-6 text-center text-3xl text-foreground">
          {mode === 'signin'
            ? 'Sign in to Vicoa'
            : 'Welcome to Vicoa'}
        </h2>
        <p className="mt-2 text-center text-base text-muted-foreground">
          {mode === 'signin'
            ? 'Run a team of coding agents. Anywhere. Any Device.'
            : 'Run a team of coding agents. Anywhere. Any Device.'}
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        {!showEmailForm && oauthStatus === 'idle' && (
          <>
            <div className="flex flex-col items-center gap-3">
              {googleClientId ? (
                <Button
                  type="button"
                  onClick={handleGoogleSignIn}
                  variant="outline"
                  className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground"
                >
                  <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="currentColor"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  Continue with Google
                </Button>
              ) : null}

              {appleClientId ? (
                <Button
                  type="button"
                  onClick={handleAppleSignIn}
                  variant="outline"
                  className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground"
                >
                  <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
                  </svg>
                  Continue with Apple
                </Button>
              ) : null}
              {(googleClientId || appleClientId) && (
                <div className="w-full max-w-xs flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-px flex-1 bg-muted" />
                  <span>OR</span>
                  <div className="h-px flex-1 bg-muted" />
                </div>
              )}
              <Button
                type="button"
                onClick={() => {
                  posthog.capture(mode === 'signup' ? 'signup_started' : 'login_started', { method: 'email' });
                  setShowEmailForm(true);
                }}
                variant="outline"
                className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground"
              >
                <Mail className="w-5 h-5 mr-2" />
                Continue with Email
              </Button>
            </div>
          </>
        )}

        {!showEmailForm && oauthStatus !== 'idle' && (
          <div className="flex flex-col items-center gap-4">
            {oauthStatus === 'error' ? (
              <>
                <p className="w-full max-w-xs text-center text-sm text-red-500">
                  {oauthError || 'Sign-in was not completed.'}
                </p>
                <Button
                  type="button"
                  onClick={cancelDesktopOAuth}
                  variant="outline"
                  className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground"
                >
                  Try again
                </Button>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {oauthStatus === 'exchanging'
                    ? 'Completing sign-in…'
                    : 'Waiting for browser sign-in…'}
                </div>
                <p className="w-full max-w-xs text-center text-xs text-muted-foreground">
                  {oauthStatus === 'exchanging'
                    ? 'Connecting your account.'
                    : 'Finish signing in with your provider in the browser window that just opened, then return here.'}
                </p>
                {oauthStatus === 'waiting' && (
                  <button
                    type="button"
                    onClick={cancelDesktopOAuth}
                    className="text-sm text-foreground hover:underline"
                  >
                    Cancel
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {showEmailForm && (
          <form className="space-y-6 mt-6" action={formAction}>
            <input type="hidden" name="redirect" value={redirect || ''} />
            <input type="hidden" name="priceId" value={priceId || ''} />
            <input type="hidden" name="inviteId" value={inviteId || ''} />
            <div className="flex flex-col items-center">
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                defaultValue={emailParam || state.email}
                required
                maxLength={50}
                className="w-full max-w-xs px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none"
                placeholder="Enter your email"
              />
            </div>

            <div className="flex flex-col items-center">
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={
                  mode === 'signin' ? 'current-password' : 'new-password'
                }
                defaultValue={state.password}
                required
                minLength={8}
                maxLength={100}
                className="w-full max-w-xs px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none"
                placeholder="Enter your password"
              />
            </div>

            {mode === 'signin' && (
              <div className="flex flex-col items-center">
                <div className="w-full max-w-xs flex justify-end text-sm">
                  <Link
                    href="/forgot-password"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Forgot password?
                  </Link>
                </div>
              </div>
            )}

            {state?.error && (
              <div className="flex flex-col items-center">
                <div className="w-full max-w-xs text-red-500 text-sm">{state.error}</div>
              </div>
            )}

            {state?.success && (
              <div className="flex flex-col items-center">
                <div className="w-full max-w-xs text-green-500 text-sm">{state.success}</div>
              </div>
            )}

            <div className="flex flex-col items-center">
              <Button
                type="submit"
                variant="outline"
                className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground"
                disabled={pending}
              >
                {pending ? (
                  <>
                    <Loader2 className="animate-spin mr-2 h-4 w-4" />
                    Loading...
                  </>
                ) : (
                  'Continue'
                )}
              </Button>
            </div>
          </form>
        )}

        <div className="mt-6">
          <div className="flex justify-center text-sm text-muted-foreground">
            {showEmailForm ? (
              <button
                type="button"
                onClick={() => setShowEmailForm(false)}
                className="text-foreground hover:underline"
              >
                {mode === 'signin' ? 'Back to Sign in' : 'Back to Sign up'}
              </button>
            ) : (
              <>
                <span>
                  {mode === 'signin'
                    ? "Don't have an account?"
                    : "Already have an account?"}
                </span>
                <Link
                  href={`${mode === 'signin' ? '/sign-up' : '/sign-in'}${
                    redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
                  }${priceId ? `&priceId=${priceId}` : ''}`}
                  className="ml-1 text-foreground hover:underline"
                >
                  {mode === 'signin' ? 'Sign up' : 'Sign in'}
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
