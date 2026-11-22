'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AgentScanStep } from '@/components/desktop/agent-scan-step';
import { PaywallStep } from '@/components/desktop/paywall-step';
import { useBillingSubscriptionRead } from '@/lib/billing-subscription';
import { markDesktopSetupDone } from '@/lib/desktop-onboarding';
import { PLAN_READ_WAIT_MS, isPro, shouldShowPaywall } from '@/lib/desktop-paywall';
import {
  trackOnboardingCompleted,
  trackPaywallSkippedEntitled,
  trackScanContinued,
} from '@/lib/desktop-telemetry';
import { DRAG_REGION } from '@/lib/app-region';

/**
 * Post-sign-in setup: agent scan, then the Pro paywall.
 *
 * Deliberately NOT in DesktopAuthGate's AUTH_ROUTES — it needs cloud mode and
 * a session, which is exactly how the gate already treats a non-auth route.
 * The gate sends a freshly signed-in shell here while the setup flag is unset,
 * and straight to /dashboard once it's set.
 *
 * Scan first, then payment: the scan is what proves the product works on this
 * machine, and it earns the right to ask.
 *
 * Only people on Free see the paywall. The plan is read while the scan is on
 * screen, so it is usually known by Continue: anyone already on Pro (any
 * store, or a Team seat) goes straight to the app. A read that failed, or is
 * still out `PLAN_READ_WAIT_MS` after Continue, goes to the app too: the
 * paywall is an offer, and neither an unknown plan nor a slow backend may keep
 * anyone out.
 *
 * Every exit — finished, skipped, or dismissed — sets the flag and lands on
 * /dashboard (which middleware forwards to New Session). There is no path
 * through here that can trap a user.
 */
export default function DesktopSetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<'scan' | 'checking' | 'paywall'>('scan');
  // Carried from the scan step so the terminal event can report what this
  // install actually ended up with. A ref, not state: the paywall step is the
  // only thing that renders after it's set, and it doesn't read it.
  const installedCount = useRef(0);
  const done = useRef(false);
  // Shares the dashboard's cached read, so the app doesn't fetch it again.
  const { data: plan, error: planError } = useBillingSubscriptionRead();
  const planSettled = plan !== undefined || planError !== undefined;

  const finish = useCallback(
    (paywallSkipped: boolean) => {
      if (done.current) return;
      done.current = true;
      markDesktopSetupDone();
      trackOnboardingCompleted(installedCount.current, paywallSkipped);
      router.replace('/dashboard');
    },
    [router]
  );

  // The paywall for Free; the app for Pro and for a plan we couldn't read.
  const routeByPlan = useCallback(() => {
    if (shouldShowPaywall(plan ?? null)) {
      setStep('paywall');
      return;
    }
    if (plan && isPro(plan)) trackPaywallSkippedEntitled(plan.provider);
    finish(true);
  }, [plan, finish]);

  const onScanContinue = useCallback(
    (skipped: boolean, count: number) => {
      installedCount.current = count;
      trackScanContinued(skipped);
      if (planSettled) routeByPlan();
      else setStep('checking');
    },
    [planSettled, routeByPlan]
  );

  // Continue came before the plan: route as soon as it lands, or let them in.
  useEffect(() => {
    if (step !== 'checking') return;
    if (planSettled) {
      routeByPlan();
      return;
    }
    const timer = setTimeout(() => finish(true), PLAN_READ_WAIT_MS);
    return () => clearTimeout(timer);
  }, [step, planSettled, routeByPlan, finish]);

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      <div className="custom-scrollbar flex flex-1 flex-col overflow-y-auto">
        {step === 'scan' ? (
          <AgentScanStep onContinue={onScanContinue} />
        ) : step === 'paywall' ? (
          <PaywallStep onDone={finish} />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
    </div>
  );
}
