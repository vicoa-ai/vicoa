'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Check, ExternalLink, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { getBackendAPI, type BillingSubscription } from '@/lib/backend-api';
import posthog from 'posthog-js';
import { describePrepaidPass, getBillingPlanLabel, isPrepaidProvider } from '@/lib/billing';

const freePlanFeatures = [
  'Web & mobile access',
  'Talk to code',
  'Real-time notifications',
  'Community support',
];

export function BillingSettingsSection({
  checkoutSuccess = false,
}: {
  checkoutSuccess?: boolean;
}) {
  const {
    data: billingSubscription,
    error: billingSubscriptionError,
    isLoading: isBillingSubscriptionLoading,
    mutate: mutateBillingSubscription,
  } = useSWR<BillingSubscription>('billing-subscription', async () =>
    getBackendAPI(true).getBillingSubscription()
  );
  const [billingAction, setBillingAction] = useState<'portal' | null>(null);
  const [billingError, setBillingError] = useState<string | null>(null);
  const [billingNotice, setBillingNotice] = useState<string | null>(null);

  useEffect(() => {
    if (checkoutSuccess) {
      setBillingNotice('Subscription updated successfully.');
      void mutateBillingSubscription();
    }
  }, [checkoutSuccess, mutateBillingSubscription]);

  const getBillingBaseUrl = () => {
    if (typeof window === 'undefined') {
      return '/dashboard/settings?tab=billing';
    }

    return `${window.location.origin}/dashboard/settings?tab=billing`;
  };

  const handleOpenPortal = async () => {
    setBillingAction('portal');
    setBillingError(null);
    setBillingNotice(null);
    posthog.capture('billing_portal_opened');

    try {
      const backendAPI = getBackendAPI(true);
      const session = await backendAPI.createBillingPortalSession({
        return_url: getBillingBaseUrl(),
      });

      window.location.assign(session.url);
    } catch (error) {
      setBillingError(
        error instanceof Error ? error.message : 'Failed to open billing portal.'
      );
      setBillingAction(null);
    }
  };

  const isBillingLoading = isBillingSubscriptionLoading;
  const billingFetchError = billingSubscriptionError instanceof Error;
  const isFreePlan = (billingSubscription?.plan_type ?? 'free') === 'free';
  const isStripePro = billingSubscription?.plan_type === 'pro' && billingSubscription.provider === 'stripe';
  const isMobileStorePro = billingSubscription?.plan_type === 'pro'
    && (billingSubscription.provider === 'apple' || billingSubscription.provider === 'google');
  const isPrepaidPro = billingSubscription?.plan_type === 'pro'
    && isPrepaidProvider(billingSubscription.provider);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Billing</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 px-6 py-0">
        {billingNotice && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
            {billingNotice}
          </div>
        )}
        {billingError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {billingError}
          </div>
        )}
        {isBillingLoading ? (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading subscription details...
          </div>
        ) : billingFetchError ? (
          <div className="text-sm text-muted-foreground">
            Billing details are unavailable right now.
          </div>
        ) : isFreePlan ? (
          <div>
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-base font-medium text-foreground">Free Plan</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Try Vicoa
                </p>
              </div>
              <Button asChild className="sm:min-w-[120px]">
                <Link href="/dashboard/upgrade">Upgrade</Link>
              </Button>
            </div>

            <ul className="mt-6 space-y-3">
              {freePlanFeatures.map((feature) => (
                <li key={feature} className="flex items-start gap-3">
                  <Check className="mt-0.5 h-5 w-5 flex-shrink-0 text-muted-foreground" />
                  <span className="text-sm text-foreground/80">{feature}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : isStripePro ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-base font-medium text-foreground">
                Pro Plan
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Your subscription is managed with Stripe.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={handleOpenPortal}
              disabled={billingAction !== null}
            >
              {billingAction === 'portal' ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Opening
                </>
              ) : (
                <>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Manage subscription
                </>
              )}
            </Button>
          </div>
        ) : isMobileStorePro ? (
          <div>
            <p className="text-base font-medium text-foreground">
              Pro Plan
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {billingSubscription?.provider === 'apple'
                ? 'Your subscription is managed in the App Store.'
                : 'Your subscription is managed in the Google Play Store.'}
            </p>
          </div>
        ) : isPrepaidPro && billingSubscription ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-base font-medium text-foreground">
                Pro Plan
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {describePrepaidPass(billingSubscription)}
              </p>
            </div>
            <Button
              variant="outline"
              className="cursor-pointer"
              onClick={handleOpenPortal}
              disabled={billingAction !== null}
            >
              {billingAction === 'portal' ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Opening
                </>
              ) : (
                <>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Extend pass
                </>
              )}
            </Button>
          </div>
        ) : (
          <div>
            <p className="text-sm text-muted-foreground">Plan</p>
            <p className="text-base font-medium text-foreground">
              {getBillingPlanLabel(billingSubscription?.plan_type)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Billing information is available, but this subscription type is not yet configurable here.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
