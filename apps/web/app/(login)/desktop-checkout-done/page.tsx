'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Image from 'next/image';
import { CheckCircle2 } from 'lucide-react';

/**
 * Where Stripe lands the user's BROWSER after desktop checkout.
 *
 * This page is served from the public web origin, not the desktop app —
 * the desktop renderer's origin is a loopback server Stripe can't reach.
 * It exists purely to tell the user to go back to the app; the app itself
 * learns about the payment by re-reading entitlement on window focus, so
 * there is nothing to hand back here. No deep link, no token.
 */
function CheckoutDoneInner() {
  const cancelled = useSearchParams().get('cancelled') === '1';

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-6 text-center">
      <Image
        src="/images/vicoa-light.webp"
        alt="Vicoa"
        width={0}
        height={0}
        sizes="100vw"
        className="h-10 w-auto opacity-90"
      />

      {cancelled ? (
        <div className="space-y-2">
          <h1 className="text-2xl text-foreground">Checkout cancelled</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            No charge was made. You can head back to the Vicoa app and keep going on the free plan.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <CheckCircle2 className="mx-auto h-10 w-10 text-green-500" />
          <h1 className="text-2xl text-foreground">You&apos;re all set</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            Pro is active. Switch back to the Vicoa app — it&apos;ll pick up your new plan
            automatically.
          </p>
        </div>
      )}

      <p className="text-xs text-muted-foreground/60">You can close this tab.</p>
    </div>
  );
}

export default function DesktopCheckoutDonePage() {
  // useSearchParams needs a Suspense boundary during prerender.
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <CheckoutDoneInner />
    </Suspense>
  );
}
