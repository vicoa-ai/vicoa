'use client';

/**
 * The in-app plan picker, as a large dialog over whatever the user was doing.
 * It shows the pricing page's own cards (`<PricingCards inApp />`), so plans,
 * prices and features read the same on the website and in the app.
 *
 * It replaces navigating to `/dashboard/upgrade` from inside the app: that
 * page renders outside the dashboard shell, so opening it unmounted the
 * session list and its live connection, and coming back loaded them all
 * again. The page stays for links from outside the app (the pricing page's
 * sign-up redirect).
 *
 * Mounted once by the dashboard shell; anything inside it opens the dialog
 * with `openUpgradeDialog()`.
 *
 * Checkout: the desktop opens Stripe in the system browser and re-reads the
 * plan whenever the window regains focus, closing once it reads Pro (the same
 * focus re-check as the onboarding paywall). The web navigates to Stripe and
 * comes back to Settings → Billing.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import posthog from 'posthog-js';
import { X } from 'lucide-react';
import { PricingCards } from '@/components/billing/pricing-cards';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { SEATS_PAGE_HREF } from '@/lib/billing';
import { refreshBillingSubscription } from '@/lib/billing-subscription';
import { isPro } from '@/lib/desktop-paywall';

const OPEN_EVENT = 'vicoa:open-upgrade-dialog';

export function openUpgradeDialog(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function UpgradeDialog() {
  const [open, setOpen] = useState(false);
  // Desktop only: checkout is open in the browser, so the plan may change
  // when the window comes back into focus.
  const [awaitingBrowser, setAwaitingBrowser] = useState(false);

  useEffect(() => {
    const onOpen = () => {
      setAwaitingBrowser(false);
      setOpen(true);
      posthog.capture('upgrade_page_viewed', { presentation: 'dialog' });
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!open || !awaitingBrowser) return;
    const onFocus = async () => {
      const plan = await refreshBillingSubscription();
      if (isPro(plan)) setOpen(false);
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [open, awaitingBrowser]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[calc(100vh-3rem)] max-w-[1180px] gap-0 overflow-y-auto p-6 custom-scrollbar sm:p-8 sm:rounded-2xl">
        <button
          type="button"
          aria-label="Close"
          onClick={() => setOpen(false)}
          className="absolute right-3 top-3 z-10 flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-5 text-center">
          <DialogTitle className="text-2xl font-semibold tracking-tight text-foreground">
            Upgrade your plan
          </DialogTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Choose the plan that fits you. Manage your subscription from settings after checkout.
          </p>
        </div>

        <PricingCards inApp onCheckoutInBrowser={() => setAwaitingBrowser(true)} />

        {awaitingBrowser && (
          <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
            Checkout is open in your browser. Your plan updates here when you come back.
          </p>
        )}

        <div className="mt-5 text-center text-xs text-muted-foreground">
          <Link
            href={SEATS_PAGE_HREF}
            onClick={() => setOpen(false)}
            className="cursor-pointer underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            Buying for a team? Choose seats
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  );
}
