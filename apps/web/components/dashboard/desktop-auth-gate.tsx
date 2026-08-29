'use client';

import { useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { createClient } from '@/lib/auth/supabase-client';
import { getDesktopConfig } from '@/lib/runtime-config';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import { hasCompletedDesktopSetup, hasSeenDesktopIntro } from '@/lib/desktop-onboarding';
import { getAppVersion } from '@/lib/desktop-updates';
import { trackAppOpened } from '@/lib/desktop-telemetry';

// Compile-time desktop signal (identical on server + client for a desktop
// build, so wrapping children never causes a hydration mismatch on web).
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

/**
 * Login-required gate for the desktop app (desktop-app v1, "Login flow").
 *
 * The desktop shell decides cloud vs. local mode from the daemon's `write_key`
 * (`electron/src/main.ts`), but "signed in" is only true when the renderer also
 * holds a valid Supabase session — that session is the source of truth for
 * identity + all cloud data. This gate enforces that:
 *
 *  - Local mode renders ONLY a splash, never the dashboard — decided
 *    synchronously from the injected config, so the dashboard never mounts and
 *    never queries the local daemon (which does not serve the cloud data
 *    endpoints; hitting it throws CORS/preflight errors). `decide()` then either
 *    sends a signed-out user to `/desktop-welcome`, or — if a session is already
 *    present (login handoff mid-flight) — holds the splash until the shell
 *    reloads into cloud mode.
 *  - The auth surface (`/desktop-welcome` et al.) renders in local mode; a
 *    signed-in cloud shell that lands on it (e.g. right after the cloud reload)
 *    is bounced to `/dashboard`, holding a splash so the auth page never flashes
 *    or re-opens the browser.
 *  - Cloud mode renders the app; `decide()` validates the session in the
 *    background and, if it is genuinely gone, signs the shell out and returns to
 *    `/desktop-welcome`. A transient/offline read fails open (the write_key
 *    already vouched) and re-checks on focus.
 *
 * On plain web (`IS_DESKTOP` false) it renders children untouched.
 */

// Routes that render in LOCAL mode (the signed-out surface). `/desktop-setup`
// is deliberately absent: it runs after sign-in and needs cloud mode + a
// session, which is exactly how a non-auth route is already treated below.
// Listing it here would splash it forever for the signed-in shell it targets.
const AUTH_ROUTES = [
  '/desktop-intro',
  '/desktop-welcome',
  '/sign-in',
  '/sign-up',
  '/desktop-signin',
  '/desktop-auth',
  '/forgot-password',
  '/reset-password',
];

function isAuthRoute(pathname: string | null): boolean {
  if (!pathname) return false;
  return AUTH_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

async function readSession() {
  try {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    return { session, ok: true as const };
  } catch {
    return { session: null, ok: false as const };
  }
}

function DesktopSplash() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  );
}

export function DesktopAuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  // Cloud-mode render is optimistic; `decide()` flips this on only to hold a
  // splash while it actively redirects (marketing root, auth route, or a
  // signed-out cloud shell).
  const [cloudRedirecting, setCloudRedirecting] = useState(false);

  const decide = useCallback(async () => {
    const config = getDesktopConfig();
    const onAuthRoute = isAuthRoute(pathname);
    const isCloud = !!config && config.mode === 'cloud';

    // Local mode (or no injected config): not signed in, OR a login handoff is
    // mid-flight.
    if (!isCloud) {
      if (onAuthRoute) return; // the sign-in surface renders as-is
      const { session } = await readSession();
      // Session present → the shell is minting the CLI key and will reload into
      // cloud mode on its own (see DesktopAuthHandoff). Hold the splash.
      if (session) return;
      // First launch rests on the intro; every later signed-out launch (and any
      // sign-out) goes straight to the sign-in surface.
      router.replace(hasSeenDesktopIntro() ? '/desktop-welcome' : '/desktop-intro');
      return;
    }

    // Cloud mode: validate the session in the background.
    const { session, ok } = await readSession();
    if (!ok) {
      // Transient/offline read: fail open — the write_key already vouches for
      // cloud mode, and focus/auth events will re-check.
      setCloudRedirecting(false);
      return;
    }

    if (session) {
      // A signed-in shell must leave the auth surface and never rest on the
      // marketing root. First sign-in detours through post-auth setup (agent
      // scan + paywall); afterwards it goes straight to the app.
      if (onAuthRoute || pathname === '/') {
        setCloudRedirecting(true);
        router.replace(hasCompletedDesktopSetup() ? '/dashboard' : '/desktop-setup');
        return;
      }
      setCloudRedirecting(false);
      return;
    }

    // Cloud shell but no renderer session → drop the daemon to local and return
    // to the welcome screen. The reload lands back here in local mode.
    setCloudRedirecting(true);
    const bridge = getDesktopAuthBridge();
    if (bridge) {
      try {
        const result = await bridge.signOut();
        if (result.ok) return; // shell restarts local-only and reloads the window
      } catch {
        // Fall through to the client-side redirect.
      }
    }
    router.replace('/desktop-welcome');
  }, [pathname, router]);

  useEffect(() => {
    setMounted(true);
  }, []);

  // The raw "app opened" signal for the download → open → activate funnel.
  // Fires once per launch (guarded in trackAppOpened) from the root gate, before
  // any onboarding/auth branch, so returning users who never re-see the intro
  // are still counted — unlike desktop_onboarding_intro_started. `first_run` is
  // read here, before the intro flow sets the seen-flag; app_version is
  // best-effort (null on web / when the updates bridge is absent).
  useEffect(() => {
    if (!IS_DESKTOP) return;
    const first_run = !hasSeenDesktopIntro();
    void getAppVersion()
      .catch(() => null)
      .then((app_version) => trackAppOpened({ first_run, app_version }));
  }, []);

  useEffect(() => {
    if (!IS_DESKTOP) return;

    void decide();

    // React to a sign-out while the window is open, and re-validate on focus.
    const supabase = createClient();
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_OUT') void decide();
    });
    const onFocus = () => void decide();
    window.addEventListener('focus', onFocus);
    return () => {
      data.subscription.unsubscribe();
      window.removeEventListener('focus', onFocus);
    };
  }, [decide]);

  if (!IS_DESKTOP) return <>{children}</>;
  // Pre-mount: render the splash on both server and client (no window yet), so
  // reading the injected config below only ever happens post-hydration.
  if (!mounted) return <DesktopSplash />;

  const config = getDesktopConfig();
  const onAuthRoute = isAuthRoute(pathname);
  const isCloud = !!config && config.mode === 'cloud';

  if (onAuthRoute) {
    // Local mode shows the sign-in surface; a signed-in cloud shell is bounced
    // to /dashboard by decide(), so hold a splash instead of flashing the page
    // (which would re-open the browser on /desktop-signin).
    return isCloud ? <DesktopSplash /> : <>{children}</>;
  }

  // Non-auth routes: never render the dashboard in local mode (local-daemon
  // CORS) or on the marketing root.
  if (!isCloud || pathname === '/') return <DesktopSplash />;
  if (cloudRedirecting) return <DesktopSplash />;
  return <>{children}</>;
}
