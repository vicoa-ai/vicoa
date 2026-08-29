'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  clearDesktopAuthNonce,
  desktopAuthUrl,
  getDesktopAuthBridge,
  readDesktopAuthNonce,
  storeDesktopAuthNonce,
} from '@/lib/desktop-auth';
import { useDesktopAuthCallback } from '../use-desktop-auth-callback';
import { DRAG_REGION } from '@/lib/app-region';

/**
 * Desktop-app waiting screen for the browser sign-in handoff.
 *
 * The welcome page opens `<web>/desktop-auth?state=<nonce>` in the system
 * browser and stashes the nonce in localStorage; this screen waits for the
 * `vicoa://auth/callback` deep link. Reception + validation live in
 * `useDesktopAuthCallback` (shared with /desktop-welcome, so a callback that
 * lands while the app is on either page completes the sign-in). The browser
 * is opened ONLY by an explicit action (the welcome button, or "Try again"
 * below) — never on mount — so a remount can never spawn another
 * /desktop-auth tab.
 */

export default function DesktopSignInPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<'waiting' | 'connecting' | 'error'>('waiting');
  const [error, setError] = useState<string | null>(null);

  useDesktopAuthCallback((status) => {
    if (status.kind === 'connecting') {
      setPhase('connecting');
      setError(null);
    } else if (status.kind === 'mismatch') {
      setPhase('error');
      setError(
        `This sign-in came from an attempt this app doesn't recognize and was ignored for safety ` +
          `(link ${status.receivedState.slice(0, 8) || 'none'}…, expected ${status.pendingState.slice(0, 8) || 'none'}…). ` +
          'Click "Try again" to restart.'
      );
    } else {
      setPhase('error');
      setError(status.message);
    }
  });

  // Re-open the browser reusing the PENDING nonce (localStorage is the source
  // of truth — a pending callback stays valid), minting a fresh one only when
  // none exists.
  const openBrowser = useCallback(() => {
    const bridge = getDesktopAuthBridge();
    if (!bridge) {
      setPhase('error');
      setError('Desktop bridge unavailable — try signing in in the app instead.');
      return;
    }
    const nonce = readDesktopAuthNonce() || crypto.randomUUID();
    storeDesktopAuthNonce(nonce);
    setPhase('waiting');
    setError(null);
    const mode = new URLSearchParams(window.location.search).get('mode');
    void bridge.openExternal(desktopAuthUrl(nonce, mode));
  }, []);

  const cancel = useCallback(() => {
    clearDesktopAuthNonce();
    router.push('/desktop-welcome');
  }, [router]);

  return (
    <div className="flex h-screen flex-col bg-background font-mono">
      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      <div className="flex flex-1 flex-col items-center justify-center gap-8 px-6 pb-16">
        <Image
          src="/images/vicoa-light.webp"
          alt="Vicoa"
          width={0}
          height={0}
          sizes="100vw"
          className="h-12 w-auto opacity-90"
        />
        {phase === 'error' ? (
          <p className="max-w-sm text-center text-sm text-destructive">{error}</p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            {phase === 'connecting' && <Loader2 className="h-4 w-4 animate-spin" />}
            {phase === 'connecting'
              ? 'Signing you in…'
              : 'Continue in your browser to finish signing in'}
          </p>
        )}
        {phase !== 'connecting' && (
          <>
            <Button
              variant="outline"
              className="w-64 font-mono"
              onClick={cancel}
            >
              Cancel sign-in
            </Button>
            <div className="flex flex-col items-center gap-1.5 text-xs text-muted-foreground/70">
              <button
                type="button"
                onClick={openBrowser}
                className="cursor-pointer underline-offset-4 hover:text-foreground hover:underline"
              >
                {phase === 'error' ? 'Try again' : 'Browser didn’t open? Try again'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
