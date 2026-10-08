'use client';

/**
 * The signed-in user's subscription, read once and shared.
 *
 * One SWR key for every surface (account menus, Settings → Billing, the seats
 * page, the upgrade dialog), so a change made in one shows in all of them.
 * The account menus and the dashboard context read it with every automatic
 * revalidation off: it is fetched when the dashboard first mounts and then
 * only refreshed when it can actually have changed, i.e. after we send the
 * user to Stripe or the billing page in their browser, or when a menu opens
 * on a value older than `MENU_MAX_AGE_MS`.
 */

import useSWR, { mutate } from 'swr';
import { getBackendAPI, type BillingSubscription } from '@/lib/backend-api';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import { webOrigin } from '@/lib/desktop-paywall';

export const BILLING_SUBSCRIPTION_KEY = 'billing-subscription';

/** Where the subscription is managed, on the web dashboard. */
export const BILLING_SETTINGS_HREF = '/dashboard/settings?tab=billing';

/** A menu opening on an older value refreshes it in the background. */
export const MENU_MAX_AGE_MS = 10 * 60 * 1000;

let lastFetchedAt = 0;

export async function fetchBillingSubscription(): Promise<BillingSubscription> {
  const subscription = await getBackendAPI(true).getBillingSubscription();
  lastFetchedAt = Date.now();
  return subscription;
}

/**
 * The cached subscription, fetched on first use only. `undefined` while that
 * first read is in flight or after it failed: callers show nothing rather
 * than guess, since offering Upgrade to a paying customer is worse than
 * showing no plan.
 */
export function useBillingSubscription(enabled = true): BillingSubscription | undefined {
  const { data } = useSWR<BillingSubscription>(
    enabled ? BILLING_SUBSCRIPTION_KEY : null,
    fetchBillingSubscription,
    {
      revalidateIfStale: false,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      shouldRetryOnError: false,
    },
  );
  return data;
}

export function refreshBillingSubscription(): Promise<BillingSubscription | undefined> {
  return mutate<BillingSubscription>(BILLING_SUBSCRIPTION_KEY);
}

export function refreshBillingSubscriptionIfOlderThan(maxAgeMs: number): void {
  if (lastFetchedAt && Date.now() - lastFetchedAt > maxAgeMs) {
    void refreshBillingSubscription();
  }
}

/**
 * Refresh once, the next time the window regains focus: the user has gone to
 * their browser to pay or change the plan, and coming back is when it may
 * have changed.
 */
export function refreshBillingSubscriptionOnNextFocus(): void {
  window.addEventListener('focus', () => void refreshBillingSubscription(), { once: true });
}

/**
 * Open the billing page. The desktop app has no Billing tab (Stripe's portal
 * and checkout run in the browser anyway), so it opens the web dashboard's in
 * the system browser; on the web it is an in-app navigation.
 */
export function openBillingSettings(navigate: (href: string) => void): void {
  const bridge = getDesktopAuthBridge();
  if (bridge) {
    bridge.openExternal(`${webOrigin()}${BILLING_SETTINGS_HREF}`);
    refreshBillingSubscriptionOnNextFocus();
    return;
  }
  navigate(BILLING_SETTINGS_HREF);
}
