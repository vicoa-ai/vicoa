'use client';

import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AgentScanStep } from '@/components/desktop/agent-scan-step';
import { PaywallStep } from '@/components/desktop/paywall-step';
import { markDesktopSetupDone } from '@/lib/desktop-onboarding';
import { trackOnboardingCompleted, trackScanContinued } from '@/lib/desktop-telemetry';
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
 * Every exit — finished, skipped, or dismissed — sets the flag and lands on
 * /dashboard (which middleware forwards to New Session). There is no path
 * through here that can trap a user.
 */
export default function DesktopSetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<'scan' | 'paywall'>('scan');
  // Carried from the scan step so the terminal event can report what this
  // install actually ended up with. A ref, not state: the paywall step is the
  // only thing that renders after it's set, and it doesn't read it.
  const installedCount = useRef(0);

  const finish = useCallback(
    (paywallSkipped: boolean) => {
      markDesktopSetupDone();
      trackOnboardingCompleted(installedCount.current, paywallSkipped);
      router.replace('/dashboard');
    },
    [router]
  );

  const onScanContinue = useCallback((skipped: boolean, count: number) => {
    installedCount.current = count;
    trackScanContinued(skipped);
    setStep('paywall');
  }, []);

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      <div className="flex flex-1 flex-col overflow-y-auto">
        {step === 'scan' ? (
          <AgentScanStep onContinue={onScanContinue} />
        ) : (
          <PaywallStep onDone={finish} />
        )}
      </div>
    </div>
  );
}
