'use client';

import { useEffect, useRef } from 'react';
import {
  clearAllDesktopAuthNonces,
  getDesktopAuthBridge,
  matchesIssuedNonce,
  parseDesktopAuthCallback,
  readDesktopAuthNonce,
} from '@/lib/desktop-auth';
import { createClient } from '@/lib/auth/supabase-client';
import { trackSignInReturned, type SignInOutcome } from '@/lib/desktop-telemetry';

/**
 * Shared receiver for the browser sign-in handoff's `vicoa://auth/callback`
 * deep link. Mounted by EVERY page the signed-out desktop app can rest on
 * (/desktop-welcome and /desktop-signin) so a callback can never arrive on a
 * page without a listener — the shell forwards deep links to the loaded
 * window regardless of route, and an unheard callback is silently lost
 * (the "first sign-in did nothing, second worked" bug).
 *
 * The nonce is validated against localStorage AT CALLBACK TIME (not a
 * mount-time snapshot): the app may have remounted, restarted, or navigated
 * between opening the browser and the callback landing, and storage is the
 * source of truth that survives all of those.
 */

export type DesktopAuthCallbackStatus =
  | { kind: 'connecting' }
  | { kind: 'mismatch'; receivedState: string; pendingState: string }
  | { kind: 'error'; message: string };

// Module-level single-flight: welcome and signin may briefly overlap during
// a route transition, and the shell can replay a buffered link to a new
// subscriber — the handoff (verifyOtp + setApiKey + daemon restart) must run
// exactly once per callback.
let handoffInFlight = false;

/**
 * Telemetry-only dedupe for `desktop_onboarding_signin_returned`, keyed on
 * (outcome, callback url).
 *
 * The two conditions the single-flight above exists for — overlapping
 * welcome/signin subscribers, and the shell replaying a buffered link — would
 * otherwise double-count the mismatch branch, which returns before
 * `handoffInFlight` is ever set. Deliberately dedupes only the *event*: the
 * handoff itself must stay re-runnable, because a failed `setApiKey` is
 * retried precisely by replaying the callback.
 */
let lastReportedOutcome = '';

function reportOutcome(outcome: SignInOutcome, url: string): void {
  const key = `${outcome}:${url}`;
  if (key === lastReportedOutcome) return;
  lastReportedOutcome = key;
  trackSignInReturned(outcome);
}

export function useDesktopAuthCallback(
  onStatus: (status: DesktopAuthCallbackStatus) => void
) {
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;

  useEffect(() => {
    const bridge = getDesktopAuthBridge();
    if (!bridge) return;

    const unsubscribe = bridge.onDeepLink((url) => {
      const parsed = parseDesktopAuthCallback(url);
      // OAuth-code callbacks belong to the in-app /sign-in flow — ignore.
      if (!parsed?.apiKey) return;
      if (handoffInFlight) return;

      // Accept any nonce THIS app recently issued — not only the newest.
      // Browser legs outlive attempts (Chrome session restore resurrects an
      // old sign-in tab; the user types credentials into it and its callback
      // carries an older state). Every issued nonce is ours, so the trust
      // boundary — reject callbacks this app never initiated — is unchanged.
      if (!parsed.state || !matchesIssuedNonce(parsed.state)) {
        reportOutcome('mismatch', url);
        onStatusRef.current({
          kind: 'mismatch',
          receivedState: parsed.state ?? '',
          pendingState: readDesktopAuthNonce(),
        });
        return;
      }

      const apiKey = parsed.apiKey;
      const { tokenHash, accessToken, refreshToken } = parsed;
      handoffInFlight = true;
      onStatusRef.current({ kind: 'connecting' });
      void (async () => {
        try {
          // Establish the renderer's Supabase session, so cloud mode has the
          // user's identity + data — not just the daemon's api_key. Skipped
          // when a session already exists: a REPLAYED callback (the vicoa://
          // URL fires from both the auto-navigation and the browser's
          // confirm-dialog click) carries an already-consumed one-time
          // token, and re-verifying it would fail a handoff that only needs
          // the daemon key retried.
          const supabase = createClient();
          const {
            data: { session: existingSession },
          } = await supabase.auth.getSession();
          if (!existingSession) {
            if (tokenHash) {
              // One-time token → the app's OWN session (independent refresh-
              // token family; refreshing here can't sign the website out).
              const { error } = await supabase.auth.verifyOtp({
                type: 'magiclink',
                token_hash: tokenHash,
              });
              if (error) throw new Error(error.message);
            } else if (accessToken && refreshToken) {
              // Legacy handoff from an older web deploy.
              const { error } = await supabase.auth.setSession({
                access_token: accessToken,
                refresh_token: refreshToken,
              });
              if (error) throw new Error(error.message);
            }
          }
          const result = await bridge.setApiKey(apiKey);
          if (!result.ok) {
            // Keep the nonces: they are only burned on SUCCESS. A failed
            // daemon start (e.g. --takeover colliding with a user-run
            // daemon) surfaces its real error, and a replayed callback or
            // "Try again" re-validates and re-runs the whole handoff.
            handoffInFlight = false;
            reportOutcome('error', url);
            onStatusRef.current({
              kind: 'error',
              message: result.error || 'The app rejected the sign-in key',
            });
            return;
          }
          // Fire before the cleanup below: the shell restarts the daemon and
          // reloads this window right after, and posthog-js batches captures —
          // it flushes the queue via sendBeacon on pagehide, which a
          // webContents reload does fire, but there is no reason to hand it
          // less time than we can.
          reportOutcome('success', url);
          // Success: the shell restarts the daemon and reloads this window.
          // Best-effort cleanup — the reload may tear this context down
          // before it runs; leftovers are TTL'd and harmless.
          clearAllDesktopAuthNonces();
        } catch (err) {
          handoffInFlight = false;
          reportOutcome('error', url);
          onStatusRef.current({
            kind: 'error',
            message: err instanceof Error ? err.message : 'Failed to complete sign-in',
          });
        }
      })();
    });
    return unsubscribe;
  }, []);
}
