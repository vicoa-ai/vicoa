'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import posthog from 'posthog-js';
import useSWR from 'swr';
import { ArrowRight, Check, Download, Loader2 } from 'lucide-react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getBackendAPI, type BillingInterval } from '@/lib/backend-api';

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
  const discountPercentage = Math.round((1 - annualPrice / (monthlyPrice * 12)) * 100);
  const upgradeRedirect = '/dashboard/upgrade';

  const freeFeatures = [
    'Unlimited desktop app (Mac, Windows, Linux)',
    '20 messages/month on mobile',
    'Run multiple agents in parallel',
    'Claude Code, Codex, Cursor & more',
    'Bring your own subscriptions & keys',
    'Community support',
  ];

  const proFeatures = [
    'Everything in Free',
    'Unlimited messages everywhere',
    ...(isAnnual ? [`${trialDays}-day free trial`] : []),
    'No commitment, cancel anytime',
    'Priority support',
    'Early feature access',
  ];

  const teamsFeatures = [
    'Everything in Pro',
    'Centralized billing & admin portal',
    'SSO & SCIM provisioning',
    'On-premise deployment',
    'Usage analytics & advanced security',
    'SLA & dedicated support',
  ];

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
      <div className="flex items-center justify-center gap-3 mb-16">
        <button
          onClick={() => { setIsAnnual(false); posthog.capture('billing_toggle_changed', { interval: 'monthly' }); }}
          className={`px-6 py-2.5 text-sm font-medium rounded-lg transition-all ${
            !isAnnual
              ? 'bg-black dark:bg-white text-white dark:text-black shadow-sm'
              : 'bg-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Monthly
        </button>
        <button
          onClick={() => { setIsAnnual(true); posthog.capture('billing_toggle_changed', { interval: 'annual' }); }}
          className={`px-6 py-2.5 text-sm font-medium rounded-lg transition-all ${
            isAnnual
              ? 'bg-black dark:bg-white text-white dark:text-black shadow-sm'
              : 'bg-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Annual · Save {discountPercentage}%
        </button>
      </div>

      <div className="grid lg:grid-cols-3 gap-8 lg:gap-16 max-w-7xl mx-auto">
        {/* Free Tier */}
        <Card className="relative flex min-h-[470px] flex-col border-0 hover:shadow-xl transition-all duration-300">
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Free</CardTitle>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              <div className="flex items-baseline gap-2 mb-3">
                <span className="text-3xl font-semibold text-foreground">$0</span>
                <span className="text-lg text-muted-foreground">/month</span>
              </div>
            </div>

            <div className="space-y-1">
              <ul className="space-y-3">
                {freeFeatures.map((feature, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-slate-600 dark:text-slate-400 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-foreground/80">{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
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
        <Card className="relative flex min-h-[470px] flex-col border-0 ring-2 ring-blue-600 dark:ring-blue-500 shadow-lg hover:shadow-xl transition-all duration-300">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-3 py-1 text-xs font-semibold text-white shadow-sm dark:bg-blue-500">
            Most Popular
          </div>
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Pro</CardTitle>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              <div className="flex items-baseline gap-2 mb-3">
                {isAnnual ? (
                  <>
                    <span className="text-3xl font-semibold text-foreground">
                      ${annualMonthlyEquivalent}
                    </span>
                    <span className="text-lg text-muted-foreground">/month, </span>
                    <span className="text-base text-muted-foreground">billed yearly</span>
                  </>
                ) : (
                  <>
                    <span className="text-3xl font-semibold text-foreground">
                      ${monthlyPrice}
                    </span>
                    <span className="text-lg text-muted-foreground">/month</span>
                  </>
                )}
              </div>
            </div>

            <div className="space-y-1">
              <ul className="space-y-3">
                {proFeatures.map((feature, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-slate-600 dark:text-slate-400 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-foreground/80">{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
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

        {/* Teams Tier */}
        <Card className="relative flex min-h-[470px] flex-col border-0 hover:shadow-xl transition-all duration-300">
          <CardHeader className="pb-0">
            <CardTitle className="text-2xl mb-0">Teams</CardTitle>
          </CardHeader>

          <CardContent className="space-y-8 flex-1">
            <div>
              <div className="flex items-baseline gap-2 mb-3">
                <span className="text-3xl font-semibold text-foreground">Custom</span>
              </div>
            </div>

            <div className="space-y-1">
              <ul className="space-y-3">
                {teamsFeatures.map((feature, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-slate-600 dark:text-slate-400 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-foreground/80">{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>

          <CardFooter className="pt-2">
            <Button
              variant="outline"
              className="h-12 w-full rounded-full"
              onClick={() => {
                posthog.capture('pricing_cta_clicked', { plan: 'teams' });
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
