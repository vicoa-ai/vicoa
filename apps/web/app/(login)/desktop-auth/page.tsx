'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createClient } from '@/lib/auth/supabase-client';

/**
 * Browser side of the desktop sign-in handoff (Conductor-style flow).
 *
 * The desktop app opens this page in the user's system browser with a
 * `state` nonce. After the user signs in here (any method — email, Google,
 * Apple), we mint an agent API key via the same endpoint the CLI login uses
 * and bounce it back to the app through the registered `vicoa://` scheme.
 * The app's waiting screen validates the nonce and completes sign-in.
 *
 * Already-signed-in visitors get a "Continue as <email>" button instead of
 * an invisible auto-redirect: the explicit click doubles as the user gesture
 * browsers want before launching a custom-protocol URL. A user who lands
 * back here straight from /sign-in (`resume=1`, appended before the sign-in
 * round trip) just signed in on purpose, so the handoff continues
 * automatically.
 *
 * The callback prefers a one-time `token_hash` (minted server-side) over
 * copying this browser's access/refresh tokens: a copied refresh token puts
 * the app and the website in ONE rotation family, and whichever refreshes
 * second gets the whole family revoked — signing the user out of the website
 * an hour after every desktop login. The legacy token fields remain only as
 * a fallback while the endpoint rolls out.
 */

interface HandoffTokens {
  accessToken: string;
  refreshToken: string;
}

function buildCallbackUrl(
  apiKey: string,
  state: string,
  tokenHash: string | null,
  tokens: HandoffTokens | null
): string {
  const params = new URLSearchParams({ api_key: apiKey, state });
  if (tokenHash) {
    params.set('token_hash', tokenHash);
  } else if (tokens) {
    // Legacy fallback (endpoint unavailable): carry the Supabase session
    // back so the app's renderer still holds a validated session. Bound by
    // the `state` nonce, same trust boundary as the api_key in this URL.
    params.set('access_token', tokens.accessToken);
    params.set('refresh_token', tokens.refreshToken);
  }
  return `vicoa://auth/callback?${params.toString()}`;
}

async function mintSessionTokenHash(): Promise<string | null> {
  try {
    const response = await fetch('/api/desktop-auth/session-token', { method: 'POST' });
    if (!response.ok) return null;
    const { tokenHash } = (await response.json()) as { tokenHash?: string };
    return typeof tokenHash === 'string' && tokenHash.length > 0 ? tokenHash : null;
  } catch {
    return null;
  }
}

function DesktopAuthContent() {
  const [phase, setPhase] = useState<
    'checking' | 'no-state' | 'signin' | 'ready' | 'minting' | 'done' | 'error'
  >('checking');
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [launchUrl, setLaunchUrl] = useState<string | null>(null);
  const mintingRef = useRef(false);

  const state = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('state')
    : null;

  const redirectToSignIn = useCallback(() => {
    // Round-trip through the normal web sign-in/sign-up, then back here.
    // `resume=1` marks the return leg so the handoff continues without
    // another click; `mode=signup` (from the desktop welcome page's Sign up
    // link) sends the user to create an account instead of signing in.
    const returnTo = new URL(window.location.href);
    returnTo.searchParams.set('resume', '1');
    const mode = returnTo.searchParams.get('mode');
    const target = mode === 'signup' ? '/sign-up' : '/sign-in';
    window.location.href = `${target}?redirect=${encodeURIComponent(returnTo.toString())}`;
  }, []);

  const mintAndLaunch = useCallback(async (tokens: HandoffTokens | null) => {
    if (mintingRef.current) return;
    mintingRef.current = true;
    setPhase('minting');
    try {
      const response = await fetch('/api/cli-auth/generate-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        throw new Error('Failed to generate a key for the app');
      }
      const { apiKey } = await response.json();
      // One-time token so the app gets its own session (see file docs).
      const tokenHash = await mintSessionTokenHash();
      const url = buildCallbackUrl(apiKey, state ?? '', tokenHash, tokens);
      setLaunchUrl(url);
      setPhase('done');
      // Hand off to the app. The success UI stays up with a manual button in
      // case the OS blocks the automatic redirect.
      window.location.href = url;
    } catch (err) {
      mintingRef.current = false;
      setError(err instanceof Error ? err.message : 'Something went wrong');
      setPhase('error');
    }
  }, [state]);

  const continueWithSession = useCallback(async () => {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      redirectToSignIn();
      return;
    }
    const tokens = session.access_token && session.refresh_token
      ? { accessToken: session.access_token, refreshToken: session.refresh_token }
      : null;
    void mintAndLaunch(tokens);
  }, [mintAndLaunch, redirectToSignIn]);

  const useDifferentAccount = useCallback(async () => {
    try {
      // scope: 'local' clears this browser only — no global revoke that
      // would sign the user's other devices out.
      await createClient().auth.signOut({ scope: 'local' });
    } catch {
      // Proceed to sign-in regardless.
    }
    redirectToSignIn();
  }, [redirectToSignIn]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        // No `state` nonce → this page wasn't opened by the desktop app
        // (omnibox autocomplete and leftover tabs land here bare). Without
        // it, minting would fire a callback the app can never accept — so
        // don't run the handoff at all, just point at the app.
        if (!state) {
          setPhase('no-state');
          return;
        }
        const supabase = createClient();
        const { data: { session } } = await supabase.auth.getSession();
        if (cancelled) return;
        if (session) {
          const resume = new URLSearchParams(window.location.search).get('resume') === '1';
          if (resume) {
            // Fresh from the sign-in round trip: that sign-in was the user
            // gesture — continue without another click.
            const tokens = session.access_token && session.refresh_token
              ? { accessToken: session.access_token, refreshToken: session.refresh_token }
              : null;
            void mintAndLaunch(tokens);
          } else {
            setEmail(session.user?.email ?? null);
            setPhase('ready');
          }
        } else {
          setPhase('signin');
          redirectToSignIn();
        }
      } catch {
        if (!cancelled) {
          setError('Failed to check your sign-in status');
          setPhase('error');
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [mintAndLaunch, redirectToSignIn]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-6 font-mono">
      <Image
        src="/images/vicoa-light.webp"
        alt="Vicoa"
        width={0}
        height={0}
        sizes="100vw"
        className="h-12 w-auto opacity-90"
      />
      {phase === 'no-state' ? (
        <>
          <div className="text-center">
            <h1 className="text-xl text-foreground">This page connects the Vicoa app</h1>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Open the Vicoa desktop app and click <span className="text-foreground">Continue to sign in</span> —
              it will bring you back here with a secure link.
            </p>
          </div>
          <Button asChild variant="outline" className="font-mono">
            <a href="/dashboard">Go to dashboard</a>
          </Button>
        </>
      ) : phase === 'ready' ? (
        <>
          <div className="text-center">
            <h1 className="text-xl text-foreground">Sign in to the Vicoa app</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {email ? (
                <>You&apos;re signed in as <span className="text-foreground">{email}</span>.</>
              ) : (
                'You’re already signed in.'
              )}
            </p>
          </div>
          <Button className="w-64 font-mono" onClick={() => void continueWithSession()}>
            Continue
          </Button>
          <button
            type="button"
            onClick={() => void useDifferentAccount()}
            className="cursor-pointer text-xs text-muted-foreground/70 underline-offset-4 hover:text-foreground hover:underline"
          >
            Use a different account
          </button>
        </>
      ) : phase === 'done' ? (
        <>
          <div className="text-center">
            <h1 className="text-xl text-foreground">You&apos;re signed in</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Vicoa should open automatically. You can close this tab.
            </p>
          </div>
          {launchUrl && (
            <Button asChild className="font-mono">
              <a href={launchUrl}>Launch Vicoa</a>
            </Button>
          )}
        </>
      ) : phase === 'error' ? (
        <>
          <div className="text-center">
            <h1 className="text-xl text-foreground">Couldn&apos;t connect the app</h1>
            <p className="mt-2 text-sm text-destructive">{error}</p>
          </div>
          <Button
            variant="outline"
            className="font-mono"
            onClick={() => {
              setError(null);
              window.location.reload();
            }}
          >
            Try again
          </Button>
        </>
      ) : (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {phase === 'signin' ? 'Redirecting to sign-in…' : 'Connecting the Vicoa app…'}
        </div>
      )}
    </div>
  );
}

export default function DesktopAuthPage() {
  return (
    <Suspense fallback={null}>
      <DesktopAuthContent />
    </Suspense>
  );
}
