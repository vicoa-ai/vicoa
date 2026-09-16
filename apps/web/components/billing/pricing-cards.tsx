'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import posthog from 'posthog-js';
import useSWR from 'swr';
import { ArrowRight, Download, Loader2 } from 'lucide-react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getBackendAPI, type BillingInterval } from '@/lib/backend-api';
import { IncludedGlyph } from '@/components/billing/plan-glyphs';
import { cn } from '@/lib/utils';

const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error('Failed to fetch');
  }

  return res.json();
});

function CheckoutAbandonedTracker() {
  const searchParams = useSearchParams();
  useEffect(() => {
    if (searchParams.get('cancelled') === '1') {
      posthog.capture('checkout_abandoned', { plan: 'pro' });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

/**
 * A plan's bullets: a few words each, no explanations. The comparison table
 * below the cards carries the detail. `leadIn` names the tier this one builds
 * on ("Everything in Free, plus:") so the bullets only list what is new.
 */
function FeatureList({ leadIn, features }: { leadIn?: string; features: string[] }) {
  return (
    <div className="space-y-3">
      {leadIn && <p className="text-sm font-medium text-foreground">{leadIn}</p>}
      <ul className="space-y-3">
        {features.map((text) => (
          <li key={text} className="flex items-start gap-3">
            <IncludedGlyph className="mt-0.5" />
            <span className="text-sm text-foreground/80">{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PricingCards({ trialDays = 7 }: { trialDays?: number }) {
  const [isAnnual, setIsAnnual] = useState(false);
  const [activeCheckoutPlan, setActiveCheckoutPlan] = useState<'pro' | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const { data: supabaseUser } = useSWR('/api/supabase-user', fetcher);
  const router = useRouter();
  const isAuthLoading = typeof supabaseUser === 'undefined';

  const monthlyPrice = 12;
  const annualPrice = 108;
  const annualMonthlyEquivalent = '9';
  const annualSaving = monthlyPrice * 12 - annualPrice;
  const discountPercentage = Math.round((1 - annualPrice / (monthlyPrice * 12)) * 100);
  const upgradeRedirect = '/dashboard/upgrade';

  const freeFeatures = [
    'Desktop app for Mac, Windows & Linux',
    'Mobile & web remote control',
    '40+ coding agents',
    'Bring your own subscriptions & API keys',
    '1 remote machine',
    '10 automations',
    'Community support',
  ];

  const proFeatures = [
    'Unlimited machines',
    'Unlimited automations',
    'Priority support',
    'Early feature access',
  ];

  const enterpriseFeatures = [
    'Centralized billing & admin portal',
    'SSO & SCIM',
    'On-premise deployment',
    'Usage analytics',
    'Advanced security',
    'SLA & dedicated support',
  ];

  const selectInterval = (annual: boolean) => {
    setIsAnnual(annual);
    posthog.capture('billing_toggle_changed', { interval: annual ? 'annual' : 'monthly' });
  };

  const startCheckout = async () => {
    setCheckoutError(null);
    posthog.capture('pricing_cta_clicked', { plan: 'pro', interval: isAnnual ? 'annual' : 'monthly' });

    if (!supabaseUser) {
      router.push(`/sign-up?redirect=${encodeURIComponent(upgradeRedirect)}`);
      return;
    }

    setActiveCheckoutPlan('pro');
    posthog.capture('checkout_started', { plan: 'pro', interval: isAnnual ? 'annual' : 'monthly' });

    try {
      const origin = window.location.origin;
      const successUrl = `${origin}/dashboard`;
      const existingSearch = window.location.search ? window.location.search + '&cancelled=1' : '?cancelled=1';
      const cancelUrl = `${origin}${window.location.pathname}${existingSearch}`;
      const backendAPI = getBackendAPI(true);
      const billingInterval: BillingInterval = isAnnual ? 'annual' : 'monthly';
      const session = await backendAPI.createBillingCheckoutSession({
        plan_type: 'pro',
        billing_interval: billingInterval,
        success_url: successUrl,
        cancel_url: cancelUrl,
      });

      window.location.assign(session.checkout_url);
    } catch (error) {
      setCheckoutError(
        error instanceof Error ? error.message : 'Failed to start checkout.'
      );
      setActiveCheckoutPlan(null);
    }
  };

  const toggleButton = (annual: boolean) =>
    cn(
      'cursor-pointer rounded-full px-5 py-2 text-sm font-medium transition-colors',
      isAnnual === annual
        ? 'bg-background text-foreground shadow-sm'
        : 'text-muted-foreground hover:text-foreground'
    );

  return (
    <>
      <Suspense fallback={null}>
        <CheckoutAbandonedTracker />
      </Suspense>
      {checkoutError && (
        <div className="mx-auto mb-8 max-w-2xl rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {checkoutError}
        </div>
      )}

      {/* Billing Toggle */}
      <div className="mb-10 flex justify-center">
        <div
          role="radiogroup"
          aria-label="Billing interval"
          className="inline-flex items-center rounded-full bg-muted p-1"
        >
          <button
            type="button"
            role="radio"
            aria-checked={!isAnnual}
            onClick={() => selectInterval(false)}
            className={toggleButton(false)}
          >
            Monthly
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={isAnnual}
            onClick={() => selectInterval(true)}
            className={toggleButton(true)}
          >
            Annual
            <span className="ml-1.5 text-xs text-muted-foreground">Save {discountPercentage}%</span>
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-8 lg:gap-16 max-w-7xl mx-auto">
        {/* Free Tier */}
        <Card className="relative flex min-h-[470px] flex-col border-0 hover:shadow-xl transition-all duration-300">
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Free</CardTitle>
            <p className="text-sm text-muted-foreground">
              Everything you need to run agents on your machine.
            </p>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-semibold text-foreground">$0</span>
                <span className="text-lg text-muted-foreground">/month</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Free forever</p>
            </div>

            <FeatureList features={freeFeatures} />
          </CardContent>

          <CardFooter className="pt-2">
            <Button
              variant="outline"
              className="h-12 w-full rounded-full"
              onClick={() => {
                posthog.capture('pricing_cta_clicked', { plan: 'free' });
                router.push('/download');
              }}
            >
              <Download className="mr-2 h-4 w-4" />
              Download
            </Button>
          </CardFooter>
        </Card>

        {/* Pro Tier */}
        <Card className="relative flex min-h-[470px] flex-col border-0 ring-2 ring-blue-600 dark:ring-blue-500 shadow-lg hover:shadow-xl transition-all duration-300 bg-gradient-to-b from-blue-50/70 to-card to-40% dark:from-blue-950/30">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-3 py-1 text-xs font-semibold text-white shadow-sm dark:bg-blue-500">
            Most Popular
          </div>
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Pro</CardTitle>
            <p className="text-sm text-muted-foreground">
              All your machines, no limits.
            </p>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              {isAnnual ? (
                <>
                  <div className="flex items-baseline gap-2">
                    <span className="text-lg text-muted-foreground line-through">
                      ${monthlyPrice}
                    </span>
                    <span className="text-3xl font-semibold text-foreground">
                      ${annualMonthlyEquivalent}
                    </span>
                    <span className="text-lg text-muted-foreground">/month</span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Billed ${annualPrice} yearly · save ${annualSaving}/year
                  </p>
                </>
              ) : (
                <>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-semibold text-foreground">
                      ${monthlyPrice}
                    </span>
                    <span className="text-lg text-muted-foreground">/month</span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">Billed monthly</p>
                </>
              )}
            </div>

            <FeatureList leadIn="Everything in Free, plus:" features={proFeatures} />
          </CardContent>

          <CardFooter className="pt-2">
            <Button
              className="h-12 w-full rounded-full"
              onClick={() => void startCheckout()}
              disabled={activeCheckoutPlan !== null || isAuthLoading}
            >
              {activeCheckoutPlan === 'pro' ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing
                </>
              ) : isAuthLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading
                </>
              ) : (
                <>
                  {isAnnual ? `Start ${trialDays}-Day Free Trial` : 'Get Pro'}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </CardFooter>
        </Card>

        {/* Enterprise Tier */}
        <Card className="relative flex min-h-[470px] flex-col border-0 hover:shadow-xl transition-all duration-300">
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Enterprise</CardTitle>
            <p className="text-sm text-muted-foreground">
              Pro for your whole org, with admin controls.
            </p>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-semibold text-foreground">Custom</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Tailored to your organization</p>
            </div>

            <FeatureList leadIn="Everything in Pro, plus:" features={enterpriseFeatures} />
          </CardContent>

          <CardFooter className="pt-2">
            <Button
              variant="outline"
              className="h-12 w-full rounded-full"
              onClick={() => {
                posthog.capture('pricing_cta_clicked', { plan: 'enterprise' });
                window.location.assign('mailto:hi@vicoa.ai');
              }}
            >
              Contact Us
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </CardFooter>
        </Card>
      </div>
    </>
  );
}
