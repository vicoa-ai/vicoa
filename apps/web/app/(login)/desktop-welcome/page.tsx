'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  desktopAuthUrl,
  getDesktopAuthBridge,
  readDesktopAuthNonce,
  storeDesktopAuthNonce,
} from '@/lib/desktop-auth';
import { trackSignInStarted } from '@/lib/desktop-telemetry';
import { useDesktopAuthCallback } from '../use-desktop-auth-callback';
import { DRAG_REGION } from '@/lib/app-region';

/**
 * Desktop welcome / login-required landing.
 *
 * Shown whenever the app has no signed-in session — first launch or right after
 * sign-out. Nothing happens until the user chooses an action, so a signed-out
 * launch or a logout rests here instead of yanking the user out to the browser.
 *
 * Choosing an action mints (or reuses) the handoff nonce, stashes it in
 * localStorage, opens the system browser, then navigates to the
 * `/desktop-signin` waiting screen.
 *
 * This page ALSO receives the `vicoa://auth/callback` deep link (via
 * `useDesktopAuthCallback`): a callback that arrives while the app rests here
 * — e.g. the app restarted mid-handoff, or the user canceled back — used to
 * be forwarded to a page with no listener and silently lost, breaking the
 * first sign-in attempt.
 */
export default function DesktopWelcomePage() {
  const router = useRouter();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useDesktopAuthCallback((status) => {
    if (status.kind === 'connecting') {
      setConnecting(true);
      setError(null);
    } else if (status.kind === 'mismatch') {
      // A callback from an attempt this app doesn't recognize; starting a
      // fresh attempt below reuses the pending nonce, so point at the button.
      setConnecting(false);
      setError(
        `That sign-in link wasn't from a current attempt ` +
          `(link ${status.receivedState.slice(0, 8) || 'none'}…) — click Continue to sign in again.`
      );
    } else {
      setConnecting(false);
      setError(status.message);
    }
  });

  const start = useCallback(
    (mode: 'signin' | 'signup') => {
      // Reuse a pending nonce (e.g. the app restarted mid-handoff and the
      // shell is still buffering that callback) so the earlier browser leg
      // can still complete; mint a fresh one otherwise.
      const nonce = readDesktopAuthNonce() || crypto.randomUUID();
      storeDesktopAuthNonce(nonce);
      // Paired with `desktop_onboarding_signin_returned` in
      // useDesktopAuthCallback: together they are the only measurement of a step
      // whose failure happens inside another application entirely.
      trackSignInStarted();
      getDesktopAuthBridge()?.openExternal(desktopAuthUrl(nonce, mode));
      router.push(mode === 'signup' ? '/desktop-signin?mode=signup' : '/desktop-signin');
    },
    [router],
  );

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      {/* Single centered column: the whole block stays vertically centered with
          fixed internal spacing, so a very tall window keeps the logo in the
          middle instead of pushing the title up and the actions down.
          `pb-11` cancels the 44px top drag strip so the group reads as truly
          centered on screen. */}
      <div className="flex flex-1 flex-col items-center justify-center px-4 pb-11 sm:px-6 lg:px-8">
        <div className="flex w-full max-w-md flex-col items-center">
          <Image
            src="/images/vicoa-light.webp"
            alt="Vicoa"
            width={0}
            height={0}
            sizes="100vw"
            className="h-12 w-auto opacity-90"
          />
          <h2 className="mt-6 text-center text-3xl text-foreground">Sign in to Vicoa</h2>
          <p className="mt-2 text-center text-base text-muted-foreground">
            Run a team of coding agents. Anywhere. Any Device.
          </p>

          <div className="mt-8 flex w-full flex-col items-center gap-4">
            {connecting ? (
              <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Signing you in…
              </div>
            ) : (
              <>
                {error && (
                  <p className="max-w-xs text-center text-sm text-destructive">{error}</p>
                )}
                <Button
                  type="button"
                  onClick={() => start('signin')}
                  className="w-full max-w-xs flex justify-center items-center py-5 px-4 rounded-lg text-sm font-medium"
                >
                  Continue to sign in
                </Button>
                <button
                  type="button"
                  onClick={() => start('signup')}
                  className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  Sign up
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
