'use client';

import { useEffect } from 'react';
import { RotateCw } from 'lucide-react';
import posthog from 'posthog-js';
import { Button } from '@/components/ui/button';

/**
 * Error boundary for the authenticated dashboard segment (`/dashboard/*`). This
 * is where the desktop app lands after sign-in + paywall, and where the reported
 * Windows "blank main page" surfaces. A throw here used to bubble to nothing and
 * paint white; now it shows a recoverable card and reports the error to PostHog
 * with the desktop runtime config so a Windows-only failure is diagnosable.
 *
 * (A pure client-segment HANG — an empty Suspense fallback that never resolves —
 * is not a throw and won't reach here; that path is addressed by the visible
 * loader in new-session/page.tsx and the renderer.log capture in the shell.)
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    try {
      const desktop =
        typeof window !== 'undefined'
          ? (window as unknown as { __VICOA_DESKTOP__?: unknown }).__VICOA_DESKTOP__
          : undefined;
      posthog.capture('desktop_render_error', {
        boundary: 'dashboard',
        message: error?.message,
        digest: error?.digest,
        stack: error?.stack?.slice(0, 2000),
        pathname: typeof window !== 'undefined' ? window.location?.pathname : undefined,
        desktop_config: desktop,
      });
    } catch {
      // never let error reporting throw from an error boundary
    }
  }, [error]);

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <h1 className="text-xl font-semibold text-foreground">Something went wrong</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        This screen failed to load. Reloading usually fixes it.
      </p>
      <Button onClick={() => reset()} className="gap-2">
        <RotateCw className="h-4 w-4" />
        Reload
      </Button>
    </div>
  );
}
