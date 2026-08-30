'use client';

import { useEffect } from 'react';

import { getDesktopConfig } from '@/lib/runtime-config';
import {
  getSilencePhoneWhenFocused,
  onSilencePhoneWhenFocusedChange,
} from '@/lib/desktop-notifications';
import { getWsClient } from '@/lib/ws-client';

/**
 * How often the desktop re-asserts foreground while it stays active, and how
 * often the idle check runs. The server treats a foreground report as stale
 * after ~75s, so a comfortably shorter tick keeps a genuinely-active window
 * suppressing phone push, and also detects the active→idle crossing within one
 * tick of the threshold.
 */
const TICK_MS = 25_000;

/**
 * No keyboard/mouse for this long (while the window is focused) counts as the
 * user having stepped away — we stop suppressing so the phone push comes
 * through. Mirrors an "away" idle timeout; deliberately generous so quietly
 * reading the screen doesn't flip it too eagerly.
 */
const IDLE_MS = 3 * 60_000;

/**
 * Coalesce the flood of `mousemove` events: at most one presence re-eval per
 * this window, so returning from idle re-suppresses within ~1s without calling
 * the evaluator on every pixel of movement.
 */
const INPUT_THROTTLE_MS = 1_000;

const INPUT_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart'] as const;

/**
 * Report whether the user is actively at the desktop app to the backend, so it
 * can silence the phone push while they are — the phone counterpart to the
 * "Only when unfocused" desktop-banner policy. "Actively at" means the window
 * is the visible, focused window AND there's been keyboard/mouse input within
 * the idle timeout; walking away (no input for {@link IDLE_MS}) lets the phone
 * push through even with the app still focused.
 *
 * Runs only in the desktop app's cloud (logged-in) mode: the plain-web build
 * has no desktop config, and desktop-local is logged-out (no cloud account, so
 * no phone push exists to suppress). Mount once, high in the dashboard tree.
 */
export function useDesktopForegroundPresence(): void {
  useEffect(() => {
    // Cloud desktop only. `local` mode talks to the daemon, not the cloud
    // backend that fires FCM, and has no signed-in user to push to.
    if (getDesktopConfig()?.mode !== 'cloud') return;

    const ws = getWsClient();
    const releaseConn = ws.retainConnection();

    let enabled = getSilencePhoneWhenFocused();
    let lastInputAt = Date.now();
    // Last value actually sent, so transitions send once instead of per-event.
    let lastSent: boolean | null = null;
    let lastInputEval = 0;

    // True only when the app is the visible/focused window AND the user has
    // interacted within the idle window. Off when disabled so a prior
    // foreground can't keep suppressing.
    const desired = (): boolean =>
      enabled &&
      document.visibilityState !== 'hidden' &&
      document.hasFocus() &&
      Date.now() - lastInputAt < IDLE_MS;

    // Send only on a change; the tick handles TTL refresh separately.
    const sync = () => {
      const value = desired();
      if (value !== lastSent) {
        lastSent = value;
        ws.sendPresence(value);
      }
    };

    const onInput = () => {
      lastInputAt = Date.now();
      // Coming back from idle should re-suppress promptly, but don't re-eval on
      // every mousemove.
      if (lastInputAt - lastInputEval > INPUT_THROTTLE_MS) {
        lastInputEval = lastInputAt;
        sync();
      }
    };

    // Regaining focus / becoming visible is itself user activity.
    const onFocus = () => {
      lastInputAt = Date.now();
      sync();
    };
    const onBlur = () => sync();
    const onVisibility = () => {
      if (document.visibilityState !== 'hidden') lastInputAt = Date.now();
      sync();
    };

    for (const evt of INPUT_EVENTS) {
      window.addEventListener(evt, onInput, { passive: true });
    }
    window.addEventListener('focus', onFocus);
    window.addEventListener('blur', onBlur);
    document.addEventListener('visibilitychange', onVisibility);

    const tick = setInterval(() => {
      // Catch the active→idle crossing, then refresh the server TTL while active.
      sync();
      if (lastSent === true) ws.sendPresence(true);
    }, TICK_MS);

    const unsubscribePref = onSilencePhoneWhenFocusedChange((value) => {
      enabled = value;
      sync();
    });

    // Assert the initial state right away.
    sync();

    return () => {
      clearInterval(tick);
      for (const evt of INPUT_EVENTS) window.removeEventListener(evt, onInput);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('blur', onBlur);
      document.removeEventListener('visibilitychange', onVisibility);
      unsubscribePref();
      // Clear presence so a server-side connection that outlives this reporter
      // (until the socket drops) doesn't keep suppressing phone push.
      ws.sendPresence(false);
      releaseConn();
    };
  }, []);
}
