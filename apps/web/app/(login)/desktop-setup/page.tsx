'use client';

import { useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { AgentScanStep } from '@/components/desktop/agent-scan-step';
import { markDesktopSetupDone } from '@/lib/desktop-onboarding';
import { trackOnboardingCompleted, trackScanContinued } from '@/lib/desktop-telemetry';
import { DRAG_REGION } from '@/lib/app-region';

/**
 * Post-sign-in setup: the agent scan, then the app.
 *
 * Deliberately NOT in DesktopAuthGate's AUTH_ROUTES — it needs cloud mode and
 * a session, which is exactly how the gate already treats a non-auth route.
 * The gate sends a freshly signed-in shell here while the setup flag is unset,
 * and straight to /dashboard once it's set.
 *
 * Onboarding asks for no payment. The plan is offered where it is needed: the
 * sidebar's Upgrade, and the upgrade dialog a plan limit opens.
 *
 * Every exit, continued or skipped, sets the flag and lands on /dashboard
 * (which middleware forwards to New Session). There is no path through here
 * that can trap a user.
 */
export default function DesktopSetupPage() {
  const router = useRouter();
  const done = useRef(false);

  const onScanContinue = useCallback(
    (skipped: boolean, count: number) => {
      if (done.current) return;
      done.current = true;
      trackScanContinued(skipped);
      markDesktopSetupDone();
      // `paywall_skipped` stays on the event, always true now, so funnels
      // built on it keep reading the same way across the change.
      trackOnboardingCompleted(count, true);
      router.replace('/dashboard');
    },
    [router]
  );

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      <div className="custom-scrollbar flex flex-1 flex-col overflow-y-auto">
        <AgentScanStep onContinue={onScanContinue} />
      </div>
    </div>
  );
}
