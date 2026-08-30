'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getBackendAPI, type BillingInterval, type BillingSubscription } from '@/lib/backend-api';
import {
  PRO_ANNUAL_MONTHLY_EQUIVALENT,
  PRO_ANNUAL_PRICE,
  PRO_MONTHLY_PRICE,
  PRO_TRIAL_DAYS,
  annualSavingPercent,
  checkoutErrorMessage,
  isPro,
  startDesktopCheckout,
} from '@/lib/desktop-paywall';
import {
  trackCheckoutFailed,
  trackCheckoutStarted,
  trackPaywallDeclined,
  trackPaywallOpened,
  trackPaywallSkippedEntitled,
  trackPricingCtaClicked,
} from '@/lib/desktop-telemetry';
import { cn } from '@/lib/utils';

/**
 * Dismissible Pro paywall, shown once after the agent scan.
 *
 * Skipped entirely for anyone already entitled — including iOS/Android
 * subscribers, since the backend keeps one subscription row per user with a
 * `provider` column, so `plan_type === 'pro'` already covers them.
 *
 * Checkout opens in the system browser (Electron won't navigate to Stripe
 * in-window), so entitlement is re-read whenever the window regains focus.
 * That's the same focus-recheck DesktopAuthGate uses; no polling, no new
 * deep-link surface.
 *
 * "Maybe later" is a real, always-live code path — not a config flag.
 */

const PRO_FEATURES = [
  'Unlimited coding agents',
  'Unlimited messages',
  'Run agents in parallel',
  'Unlimited machine connects',
  'Mobile + desktop sync',
  'Priority support',
];

/**
 * A selectable plan tile. Selection is shown purely by the tile's background
 * and ring — deliberately no radio dot or check mark, so the whole card reads
 * as the control.
 */
function PlanCard({
  interval,
  selected,
  onSelect,
}: {
  interval: BillingInterval;
  selected: boolean;
  onSelect: () => void;
}) {
  const isAnnual = interval === 'annual';
  // Both tiles headline a per-month price so $9 vs $12 compares at a glance;
  // the annual tile carries the yearly total in the fine print beneath it.
  const perMonth = isAnnual ? PRO_ANNUAL_MONTHLY_EQUIVALENT : PRO_MONTHLY_PRICE;
  const subtext = isAnnual ? `Try ${PRO_TRIAL_DAYS} days for free` : 'Billed monthly';
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'relative flex min-h-[124px] cursor-pointer flex-col justify-center rounded-xl border p-4 text-left transition-all',
        selected
          ? 'border-primary/60 bg-foreground/[0.07] ring-1 ring-primary/50'
          : 'border-border/60 bg-foreground/[0.02] hover:border-foreground/25 hover:bg-foreground/[0.04]'
      )}
    >
      {isAnnual && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white shadow-sm">
          Save {annualSavingPercent()}%
        </span>
      )}
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {isAnnual ? 'Yearly' : 'Monthly'}
      </span>
      <span className="mt-2 flex items-baseline gap-0.5">
        <span className="text-[28px] font-semibold leading-none text-foreground">${perMonth}</span>
        <span className="text-sm text-muted-foreground">/mo</span>
      </span>
      <span className="mt-2 text-[11px] leading-tight text-muted-foreground">{subtext}</span>
    </button>
  );
}

export function PaywallStep({ onDone }: { onDone: (skipped: boolean) => void }) {
  const [interval, setInterval] = useState<BillingInterval>('annual');
  const [checkingOut, setCheckingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "Maybe later" doesn't leave immediately: it swaps to a reassurance view so
  // the user knows declining doesn't lock them out (a payment-anxiety fix).
  const [declined, setDeclined] = useState(false);
  // Set while the "Maybe later" click re-reads entitlement, so a paid-but-not-
  // yet-propagated user is routed as a conversion instead of shown the
  // free-plan reassurance.
  const [declining, setDeclining] = useState(false);
  const done = useRef(false);

  /** `skipped` = the user did not convert on this paywall. */
  const finish = useCallback(
    (skipped: boolean) => {
      if (done.current) return;
      done.current = true;
      onDone(skipped);
    },
    [onDone]
  );

  // Entitlement check: on mount (catches existing subscribers, who never see
  // this step) and on focus (catches the user returning from Stripe).
  useEffect(() => {
    trackPaywallOpened();

    const check = async (trigger: 'mount' | 'focus') => {
      let plan: BillingSubscription | null = null;
      try {
        plan = await getBackendAPI(true).getBillingSubscription();
      } catch {
        // Unknown entitlement. Do NOT gate on a failed read — a paying
        // customer must never be prompted because a request timed out.
        return;
      }
      if (!isPro(plan)) return;
      // Pro on MOUNT means they arrived already entitled (typically an
      // iOS/Android subscriber) and were correctly never asked. Pro on FOCUS
      // means they just paid in the browser — a conversion, not a skip. The
      // capture used to fire for both, labelling every desktop Stripe
      // conversion as "skipped, already entitled".
      if (trigger === 'mount') trackPaywallSkippedEntitled(plan.provider);
      finish(trigger === 'mount');
    };

    void check('mount');
    const onFocus = () => void check('focus');
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [finish]);

  const checkout = useCallback(async () => {
    if (checkingOut) return;
    setCheckingOut(true);
    setError(null);
    trackPricingCtaClicked(interval);
    try {
      await startDesktopCheckout(interval);
      trackCheckoutStarted(interval);
    } catch (err) {
      trackCheckoutFailed(interval, (err as { status?: number } | null)?.status ?? null);
      setError(checkoutErrorMessage(err));
    } finally {
      // Checkout continues in the browser; re-enable so a user who closed the
      // tab isn't stuck staring at a dead button.
      setCheckingOut(false);
    }
  }, [checkingOut, interval]);

  // "Maybe later": the reassurance view must only ever appear for someone who
  // genuinely declined — never for someone who just paid but whose entitlement
  // hasn't landed yet (Stripe webhook lag). Re-read entitlement first; if
  // they're actually Pro, count it as the conversion it is and move on rather
  // than telling a paying customer "no payment needed".
  const declineLater = useCallback(async () => {
    if (declining) return;
    setDeclining(true);
    let plan: BillingSubscription | null = null;
    try {
      plan = await getBackendAPI(true).getBillingSubscription();
    } catch {
      // Couldn't read entitlement — fall through to the reassurance view rather
      // than trapping the user on the paywall.
    } finally {
      setDeclining(false);
    }
    if (isPro(plan)) {
      finish(false);
      return;
    }
    trackPaywallDeclined(interval);
    setDeclined(true);
  }, [declining, interval, finish]);

  if (declined) {
    return (
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-6 py-8 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15">
          <Check className="h-6 w-6 text-emerald-500" strokeWidth={2.5} />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold text-foreground">You&apos;re all set</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            The Vicoa desktop app is free to use now. Whenever you need unlimited usage across all
            platforms, you can upgrade to Pro anytime from Settings.
          </p>
        </div>
        <Button onClick={() => finish(true)} className="h-11 w-full rounded-full">
          Continue to Vicoa
        </Button>
      </div>
    );
  }

  const isAnnual = interval === 'annual';
  const ctaLabel = checkingOut ? 'Opening checkout…' : isAnnual ? 'Start free trial' : 'Continue';
  // Only the annual price carries a trial (mirrors the marketing pricing page),
  // so the reassuring fine print changes with the selected interval.
  const finePrint = isAnnual
    ? `${PRO_TRIAL_DAYS}-day free trial, then $${PRO_ANNUAL_PRICE}/yr. Cancel anytime.`
    : `$${PRO_MONTHLY_PRICE}/mo, billed monthly. Cancel anytime.`;

  return (
    <div className="mx-auto flex w-full max-w-[820px] flex-1 flex-col items-center justify-center px-6 py-8">
      <div className="grid w-full overflow-hidden rounded-2xl border border-border/70 bg-card shadow-xl shadow-black/10 md:grid-cols-2">
        {/* Left — the value proposition. */}
        <div className="relative flex flex-col justify-center overflow-hidden p-7">
          <div
            aria-hidden
            className="pointer-events-none absolute -left-20 -top-20 h-52 w-52 rounded-full bg-foreground/[0.05] blur-3xl"
          />
          <div className="relative space-y-2">
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-foreground">
              Go unlimited with Vicoa Pro
            </h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Run as many coding agents as you like, in parallel, from any device.
            </p>
          </div>
          <ul className="relative mt-6 space-y-3">
            {PRO_FEATURES.map((feature) => (
              <li key={feature} className="flex items-center gap-3 text-[13px] text-foreground/90">
                <Check className="h-4 w-4 shrink-0 text-emerald-500" strokeWidth={2.75} />
                {feature}
              </li>
            ))}
          </ul>
        </div>

        {/* Right — the plan chooser and call to action. */}
        <div className="flex flex-col gap-4 p-7">
          <span className="text-center text-sm font-medium text-foreground">Choose your plan</span>

          <div
            className="grid grid-cols-2 gap-3 py-3"
            role="radiogroup"
            aria-label="Billing interval"
          >
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

          <div className="mt-auto space-y-3">
            <Button
              onClick={checkout}
              disabled={checkingOut}
              className="h-11 w-full gap-2 rounded-full"
            >
              {checkingOut && <Loader2 className="h-4 w-4 animate-spin" />}
              {ctaLabel}
            </Button>
            <button
              type="button"
              onClick={declineLater}
              disabled={declining}
              className="w-full cursor-pointer py-1 text-center text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline disabled:cursor-default disabled:opacity-60"
            >
              {declining ? 'One moment…' : 'Maybe later'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
