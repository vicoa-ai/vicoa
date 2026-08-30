/**
 * Desktop paywall: entitlement + checkout.
 *
 * Entitlement is `plan_type === 'pro'` — there is no `is_pro` boolean. The
 * backend keeps ONE `subscriptions` row per user with a `provider` column
 * (`stripe | apple | google`), so an existing iOS/Android subscriber already
 * resolves as pro here and is never re-prompted. No mobile-specific check
 * needed.
 *
 * Checkout runs in the system browser (Electron blocks in-window navigation to
 * Stripe anyway), so the app learns about payment by re-reading entitlement
 * when its window regains focus.
 */

import { getBackendAPI, type BillingInterval } from '@/lib/backend-api';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';

/** Monthly list price, USD. Mirrors app/(marketing)/pricing/pricing-cards.tsx. */
export const PRO_MONTHLY_PRICE = 12;
/** Annual list price, USD. */
export const PRO_ANNUAL_PRICE = 108;
/** What the annual plan works out to per month. */
export const PRO_ANNUAL_MONTHLY_EQUIVALENT = 9;
/**
 * Free-trial length on the annual plan, in days. Mirrors the `trialDays`
 * default in app/(marketing)/pricing/pricing-cards.tsx — the annual Stripe
 * price is the one that carries a trial, so this copy only shows for annual.
 */
export const PRO_TRIAL_DAYS = 7;

export function annualSavingPercent(): number {
  return Math.round((1 - PRO_ANNUAL_PRICE / (PRO_MONTHLY_PRICE * 12)) * 100);
}

export function isPro(plan: { plan_type: string } | null | undefined): boolean {
  return plan?.plan_type === 'pro';
}

/**
 * Should the paywall be shown?
 *
 * `null` means the entitlement read failed. Answer NO in that case: prompting
 * a paying customer because a request timed out is a much worse outcome than
 * missing an upsell.
 */
export function shouldShowPaywall(plan: { plan_type: string } | null | undefined): boolean {
  if (plan === null || plan === undefined) return false;
  return !isPro(plan);
}

/**
 * The public web origin.
 *
 * NOT `window.location.origin`: in the packaged app that is the renderer's own
 * loopback server (`http://localhost:43117`), so a Stripe redirect there would
 * dead-end in the user's browser. Same source `desktopAuthUrl()` uses.
 */
export function webOrigin(): string {
  return process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai';
}

/**
 * Turn a failed checkout into something the user can act on.
 *
 * The common failure is a 401: the request went out with no Supabase session,
 * so there is nothing to retry. Saying "try again" there is worse than useless
 * — it points at the wrong problem entirely.
 */
export function checkoutErrorMessage(err: unknown): string {
  const status = (err as { status?: number } | null)?.status;
  if (status === 401 || status === 403) {
    return 'Your session has expired. Sign out and back in, then try upgrading again.';
  }
  return "Couldn't start checkout. Please try again.";
}

/**
 * Open Stripe checkout in the system browser.
 *
 * Uses the `openExternal` bridge rather than `window.location.assign` (which
 * `pricing-cards.tsx` does): in Electron that navigation is cancelled by the
 * `will-navigate` handler and shelled out anyway, leaving the caller's
 * in-flight state stuck forever because the promise never settles.
 */
export async function startDesktopCheckout(interval: BillingInterval): Promise<void> {
  const session = await getBackendAPI(true).createBillingCheckoutSession({
    plan_type: 'pro',
    billing_interval: interval,
    success_url: `${webOrigin()}/desktop-checkout-done`,
    cancel_url: `${webOrigin()}/desktop-checkout-done?cancelled=1`,
  });
  const bridge = getDesktopAuthBridge();
  if (bridge) {
    bridge.openExternal(session.checkout_url);
    return;
  }
  // Not in the desktop shell (dev in a plain browser): fall back to a normal
  // navigation so the flow is still testable.
  window.location.assign(session.checkout_url);
}
