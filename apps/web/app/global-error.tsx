'use client';

import { useEffect } from 'react';
import posthog from 'posthog-js';

/**
 * Last-resort error boundary. `global-error.tsx` replaces the root layout, so it
 * catches errors thrown in the root layout itself (or anything not caught by a
 * nearer `error.tsx`). Before this existed there were NO error boundaries in the
 * app at all, so any uncaught render error painted a blank white window — the
 * desktop app's worst failure mode, since a packaged build has no console.
 *
 * It renders its own <html>/<body> (the layout is bypassed) and, on desktop,
 * reports the error to PostHog with the runtime config snapshot so a Windows-only
 * failure is diagnosable without a local repro.
 */
export default function GlobalError({
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
        boundary: 'global',
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
    <html lang="en" className="dark">
      <body
        style={{ background: '#171717', color: '#ededed' }}
        className="min-h-[100dvh] bg-background text-foreground"
      >
        <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 px-6 text-center">
          <h1 className="text-xl font-semibold">Something went wrong</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            The app hit an unexpected error. Reloading usually fixes it.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            style={{ background: '#ededed', color: '#171717' }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
