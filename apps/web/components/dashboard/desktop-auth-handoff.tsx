'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { createClient } from '@/lib/auth/supabase-client';
import { getDesktopConfig } from '@/lib/runtime-config';
import { CliKeyMintError, getDesktopAuthBridge, mintCliKey } from '@/lib/desktop-auth';

type HandoffState =
  | { kind: 'idle' }
  | { kind: 'connecting' }
  | { kind: 'error'; message: string };

/**
 * Completes the desktop login handoff: whenever a Supabase session appears
 * while the shell is still in `local` mode, mint a CLI key from the cloud
 * backend and hand it to the Electron main process (`lib/desktop-auth.ts`).
 * On success the shell restarts the daemon in cloud mode and reloads the
 * window by itself — the "Connecting…" pill stays up until that reload.
 *
 * Mounted at the root so it survives any in-app sign-in path (email, OAuth,
 * already-signed-in cookie) regardless of route. The `/desktop-signin`
 * browser-handoff owns its own key handoff (it hands the app the api_key it
 * minted server-side), so this skips that route to avoid a double mint/reload.
 * Idempotent and single-flight; failures surface inline with a retry button.
 * Renders nothing on plain web and in desktop-cloud mode.
 */
export function DesktopAuthHandoff() {
  const pathname = usePathname();
  const [state, setState] = useState<HandoffState>({ kind: 'idle' });
  const inFlightRef = useRef(false);
  const handedOffRef = useRef(false);

  const attempt = useCallback(async () => {
    const config = getDesktopConfig();
    if (!config || config.mode !== 'local') return;
    // The browser-handoff screen performs its own setSession + setApiKey.
    if (pathname === '/desktop-signin') return;
    const bridge = getDesktopAuthBridge();
    if (!bridge) return;
    if (inFlightRef.current || handedOffRef.current) return;

    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) return; // not signed in yet — stay idle

    inFlightRef.current = true;
    setState({ kind: 'connecting' });
    try {
      const key = await mintCliKey(session.access_token);
      const result = await bridge.setApiKey(key);
      if (!result.ok) {
        throw new Error(result.error || 'Desktop shell rejected the API key');
      }
      // Success: the window reloads into cloud mode on its own. Keep the
      // "Connecting…" state up so there's no flash back to the local UI.
      handedOffRef.current = true;
    } catch (err) {
      inFlightRef.current = false;
      // Backend rejected the session's token outright: the renderer holds a
      // DEAD session (e.g. revoked server-side while its cookies survived a
      // sign-out that errored). Retrying can never succeed — clear the stale
      // session so the gate's SIGNED_OUT handler routes to /desktop-welcome,
      // instead of spinning on 401s behind the gate's splash.
      if (err instanceof CliKeyMintError && (err.status === 401 || err.status === 403)) {
        setState({ kind: 'idle' });
        try {
          await supabase.auth.signOut({ scope: 'local' });
        } catch {
          // Cookies survive; the next attempt lands back here and re-tries.
        }
        return;
      }
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Failed to connect your account',
      });
    }
  }, [pathname]);

  useEffect(() => {
    const config = getDesktopConfig();
    if (!config || config.mode !== 'local') return;

    void attempt();

    // Catch sessions that appear after mount (email sign-in redirect races,
    // OAuth callbacks, token restores).
    const supabase = createClient();
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'INITIAL_SESSION' || event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        void attempt();
      }
    });
    return () => data.subscription.unsubscribe();
  }, [attempt]);

  if (state.kind === 'idle') return null;

  return (
    <div className="fixed top-3 left-1/2 -translate-x-1/2 z-[100] font-mono">
      {state.kind === 'connecting' ? (
        <div className="flex items-center gap-2 rounded-full border border-border bg-background/95 px-4 py-1.5 text-xs text-muted-foreground shadow-lg">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Connecting your account…
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-full border border-destructive/40 bg-background/95 px-4 py-1.5 text-xs text-destructive shadow-lg">
          <span className="max-w-xs truncate" title={state.message}>
            Couldn&apos;t connect your account: {state.message}
          </span>
          <button
            type="button"
            onClick={() => void attempt()}
            className="shrink-0 rounded-full border border-border px-2 py-0.5 text-foreground hover:bg-muted transition-colors"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
