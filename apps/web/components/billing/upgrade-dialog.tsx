'use client';

/**
 * The in-app plan picker, as a large dialog over whatever the user was doing.
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

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import posthog from 'posthog-js';
import { Check, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { PlanCard } from '@/components/desktop/paywall-step';
import { getBackendAPI, type BillingInterval } from '@/lib/backend-api';
import { PRO_PLAN_FEATURES, SEATS_PAGE_HREF } from '@/lib/billing';
import {
  BILLING_SETTINGS_HREF,
  refreshBillingSubscription,
} from '@/lib/billing-subscription';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import {
  PRO_ANNUAL_PRICE,
  PRO_MONTHLY_PRICE,
  checkoutErrorMessage,
  isPro,
  startDesktopCheckout,
  webOrigin,
} from '@/lib/desktop-paywall';
import {
  trackCheckoutFailed,
  trackCheckoutStarted,
  trackPricingCtaClicked,
} from '@/lib/desktop-telemetry';

const OPEN_EVENT = 'vicoa:open-upgrade-dialog';

export function openUpgradeDialog(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function UpgradeDialog() {
  const [open, setOpen] = useState(false);
  // Opens on annual, the cheaper per-month price.
  const [interval, setInterval] = useState<BillingInterval>('annual');
  const [checkingOut, setCheckingOut] = useState(false);
  // Desktop only: checkout is open in the browser, so the plan may change
  // when the window comes back into focus.
  const [awaitingBrowser, setAwaitingBrowser] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onOpen = () => {
      setError(null);
      setAwaitingBrowser(false);
      setCheckingOut(false);
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

  const checkout = useCallback(async () => {
    if (checkingOut) return;
    setCheckingOut(true);
    setError(null);
    trackPricingCtaClicked(interval);
    try {
      if (getDesktopAuthBridge()) {
        await startDesktopCheckout(interval);
        trackCheckoutStarted(interval);
        setAwaitingBrowser(true);
        // Checkout continues in the browser; re-enable so a user who closed
        // the tab can start it again.
        setCheckingOut(false);
        return;
      }
      const session = await getBackendAPI(true).createBillingCheckoutSession({
        plan_type: 'pro',
        billing_interval: interval,
        success_url: `${window.location.origin}${BILLING_SETTINGS_HREF}&checkout=success`,
        cancel_url: window.location.href,
      });
      trackCheckoutStarted(interval);
      // Stays busy: the page is navigating to Stripe.
      window.location.assign(session.checkout_url);
    } catch (err) {
      trackCheckoutFailed(interval, (err as { status?: number } | null)?.status ?? null);
      setError(checkoutErrorMessage(err));
      setCheckingOut(false);
    }
  }, [checkingOut, interval]);

  const finePrint =
    interval === 'annual'
      ? `$${PRO_ANNUAL_PRICE}/yr, billed yearly. Cancel anytime.`
      : `$${PRO_MONTHLY_PRICE}/mo, billed monthly. Cancel anytime.`;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[90vh] max-w-[860px] gap-0 overflow-y-auto p-0 custom-scrollbar sm:rounded-2xl md:grid-cols-2">
        <button
          type="button"
          aria-label="Close"
          onClick={() => setOpen(false)}
          className="absolute right-3 top-3 z-10 flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Left: what Pro adds. */}
        <div className="relative flex flex-col justify-center overflow-hidden bg-foreground/[0.02] p-8 md:p-10">
          <div
            aria-hidden
            className="pointer-events-none absolute -left-20 -top-20 h-52 w-52 rounded-full bg-foreground/[0.05] blur-3xl"
          />
          <div className="relative space-y-2">
            <DialogTitle className="text-[26px] font-semibold leading-tight tracking-tight text-foreground">
              Upgrade to Pro
            </DialogTitle>
            <p className="text-sm leading-relaxed text-muted-foreground">For power users and teams.</p>
          </div>
          <p className="relative mt-8 text-sm font-medium text-foreground">Everything in Free, plus:</p>
          <ul className="relative mt-4 space-y-3">
            {PRO_PLAN_FEATURES.map((feature) => (
              <li key={feature} className="flex items-center gap-3 text-[13px] text-foreground/90">
                <Check className="h-4 w-4 shrink-0 text-emerald-500" strokeWidth={2.75} />
                {feature}
              </li>
            ))}
          </ul>
        </div>

        {/* Right: the plan chooser and call to action. */}
        <div className="flex flex-col gap-4 p-8 md:p-10">
          <span className="text-center text-sm font-medium text-foreground">Choose your plan</span>

          <div className="grid grid-cols-2 gap-3 py-3" role="radiogroup" aria-label="Billing interval">
            <PlanCard
              interval="annual"
              selected={interval === 'annual'}
              onSelect={() => setInterval('annual')}
            />
            <PlanCard
              interval="monthly"
              selected={interval === 'monthly'}
              onSelect={() => setInterval('monthly')}
            />
          </div>

          <p className="text-center text-xs leading-relaxed text-muted-foreground">{finePrint}</p>

          {error && <p className="text-center text-sm text-destructive">{error}</p>}
          {awaitingBrowser && !error && (
            <p className="text-center text-xs leading-relaxed text-muted-foreground">
              Checkout is open in your browser. Your plan updates here when you come back.
            </p>
          )}

          <div className="mt-auto space-y-4 pt-2">
            <Button
              onClick={() => void checkout()}
              disabled={checkingOut}
              className="h-11 w-full cursor-pointer gap-2 rounded-full"
            >
              {checkingOut && <Loader2 className="h-4 w-4 animate-spin" />}
              {checkingOut ? 'Opening checkout…' : 'Continue'}
            </Button>
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <Link
                href={SEATS_PAGE_HREF}
                onClick={() => setOpen(false)}
                className="cursor-pointer underline-offset-4 transition-colors hover:text-foreground hover:underline"
              >
                Buying for a team? Choose seats
              </Link>
              {/* The contact page, not a mailto: the desktop shell only opens
                  http(s) links. */}
              <a
                href={getDesktopAuthBridge() ? `${webOrigin()}/contact` : '/contact'}
                target="_blank"
                rel="noopener noreferrer"
                className="cursor-pointer underline-offset-4 transition-colors hover:text-foreground hover:underline"
              >
                Enterprise? Contact us
              </a>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
