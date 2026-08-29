'use client';

import { useEffect } from 'react';
import { RotateCw } from 'lucide-react';
import posthog from 'posthog-js';
import { Button } from '@/components/ui/button';

// Error boundary for the public marketing segment. Before the (dashboard) group
// was split these pages were covered by the dashboard error boundary; this keeps
// them on a recoverable inline card instead of bubbling to app/global-error.tsx.
export default function MarketingError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    try {
      posthog.capture('marketing_render_error', {
        message: error?.message,
        digest: error?.digest,
        pathname: typeof window !== 'undefined' ? window.location?.pathname : undefined,
      });
    } catch {
      // never let error reporting throw from an error boundary
    }
  }, [error]);

  return (
    <div className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-xl font-semibold text-foreground">Something went wrong</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        This page failed to load. Reloading usually fixes it.
      </p>
      <Button onClick={() => reset()} className="gap-2">
        <RotateCw className="h-4 w-4" />
        Reload
      </Button>
    </div>
  );
}
