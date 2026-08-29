'use client';

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  ArrowRight,
  ChevronLeft,
  X,
} from 'lucide-react';
import posthog from 'posthog-js';
import { uploadSurveyAnswer } from '@/lib/supabase/surveys';
import {
  INTRO_SLIDES,
  SlideImagePreloader,
  SlideView,
  StepDots,
  type Slide,
} from '@/components/onboarding/intro-slides';

export const ONBOARDING_KEY = 'vicoa_onboarding_v1_completed';

const REFERRAL_OPTIONS = [
  'App Store',
  'Google Search',
  'Reddit',
  'Twitter / X',
  'YouTube',
  'TikTok',
  'LinkedIn',
  'Friend / Colleague',
  'Rednote',
  'Email',
  'Hacker News',
  'Other',
];

/** The shared intro deck plus this surface's own referral-survey step. */
const STEPS: Slide[] = [
  ...INTRO_SLIDES,
  {
    id: 'referral',
    title: 'Where did you hear about us?',
    subtitle: 'Help us improve',
    description: "We'd love to know how you found Vicoa so we can keep spreading the word.",
    hasImage: false,
  },
];

function ReferralStep({
  selected,
  onSelect,
  otherText,
  onOtherText,
}: {
  selected: string | null;
  onSelect: (v: string) => void;
  otherText: string;
  onOtherText: (v: string) => void;
}) {
  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {REFERRAL_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onSelect(option)}
            className={cn(
              'rounded-lg border px-3 py-2.5 text-sm text-left transition-all duration-150',
              selected === option
                ? 'border-primary bg-primary/10 text-foreground font-medium'
                : 'border-border/60 bg-muted/30 text-muted-foreground hover:border-primary/40 hover:bg-muted/50 hover:text-foreground'
            )}
          >
            {option}
          </button>
        ))}
      </div>
      {selected === 'Other' && (
        <div className="flex justify-end pl-[calc(50%+4px)]">
          <input
            autoFocus
            type="text"
            value={otherText}
            onChange={(e) => onOtherText(e.target.value)}
            placeholder="Please tell us more..."
            className="w-full rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary transition-colors"
          />
        </div>
      )}
    </div>
  );
}

export function OnboardingModal({ forceShow, onClose, isOnboard = true }: { forceShow?: boolean; onClose?: () => void; isOnboard?: boolean } = {}) {
  const [visible, setVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [referral, setReferral] = useState<string | null>(null);
  const [otherText, setOtherText] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [animationDir, setAnimationDir] = useState<'forward' | 'back'>('forward');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    // Skip if cli-auth flow is in progress
    const isCLIAuthPending =
      sessionStorage.getItem('vicoa_cli_auth_pending') === 'true' ||
      params.get('from') === 'cli-auth';
    if (isCLIAuthPending) return;

    const isNewUser = params.get('new_user') === '1';
    const hasOnboardingFlag = sessionStorage.getItem('vicoa_show_onboarding') === 'true';
    const completed = localStorage.getItem(ONBOARDING_KEY);

    if (isNewUser) {
      sessionStorage.setItem('vicoa_show_onboarding', 'true');
      params.delete('new_user');
      const newSearch = params.toString();
      window.history.replaceState({}, '', window.location.pathname + (newSearch ? '?' + newSearch : ''));
    }

    if (forceShow || ((isNewUser || hasOnboardingFlag) && !completed)) {
      setVisible(true);
      posthog.capture('onboarding_started', { source: forceShow ? 'settings_replay' : 'first_visit' });
    }
  }, []);

  const complete = useCallback(
    async (skipped: boolean) => {
      localStorage.setItem(ONBOARDING_KEY, 'true');
      sessionStorage.removeItem('vicoa_show_onboarding');
      setVisible(false);
      onClose?.();
      posthog.capture('onboarding_completed', {
        skipped,
        referral: referral ?? 'not_answered',
        steps_completed: currentStep + 1,
      });
      if (referral) {
        posthog.capture('onboarding_referral', { source: referral });
        const answer = referral === 'Other' ? `Other: ${otherText.trim()}` : referral;
        try {
          await uploadSurveyAnswer('Where did you hear about us?', answer);
        } catch (e) {
          console.error('[onboarding] survey upload failed', e);
        }
      }
    },
    [referral, currentStep]
  );

  const trackStep = useCallback((index: number) => {
    posthog.capture('onboarding_step_viewed', {
      step_index: index,
      step_id: STEPS[index].id,
    });
  }, []);

  const visibleStepCount = isOnboard ? STEPS.length : STEPS.length - 1;

  const goNext = useCallback(() => {
    if (isAnimating) return;
    const isLast = currentStep === visibleStepCount - 1;
    if (isLast) {
      complete(false);
      return;
    }
    setAnimationDir('forward');
    setIsAnimating(true);
    setTimeout(() => {
      const next = currentStep + 1;
      setCurrentStep(next);
      setIsAnimating(false);
      trackStep(next);
    }, 200);
  }, [currentStep, isAnimating, complete, trackStep]);

  const goBack = useCallback(() => {
    if (isAnimating || currentStep === 0) return;
    setAnimationDir('back');
    setIsAnimating(true);
    setTimeout(() => {
      const prev = currentStep - 1;
      setCurrentStep(prev);
      setIsAnimating(false);
      trackStep(prev);
    }, 200);
  }, [currentStep, isAnimating, trackStep]);

  if (!visible) return null;

  const activeSteps = isOnboard ? STEPS : STEPS.filter((s) => s.id !== 'referral');
  const step = activeSteps[currentStep];
  const isLast = currentStep === activeSteps.length - 1;
  const isReferralStep = step.id === 'referral';

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-background/60 backdrop-blur-md">
      {/* Fetch every slide screenshot up front so forward/back navigation paints
          instantly instead of loading the image on arrival (matches the desktop
          intro). */}
      <SlideImagePreloader slides={INTRO_SLIDES} />

      {/* Card */}
      <div className="relative w-full max-w-3xl mx-4 bg-card border border-border/60 rounded-2xl shadow-2xl overflow-hidden flex flex-col" style={{ height: 'min(680px, 90vh)' }}>
        {/* Close button — shown only in tour mode (not onboarding) */}
        {!isOnboard && (
          <button
            type="button"
            onClick={() => complete(true)}
            className="absolute top-4 right-4 z-10 cursor-pointer text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted/50"
            aria-label="Close tour"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        {/* Progress bar */}
        <div className="h-0.5 bg-border/40 w-full">
          <div
            className="h-full bg-primary transition-all duration-500 ease-out"
            style={{ width: `${((currentStep + 1) / activeSteps.length) * 100}%` }}
          />
        </div>

        <div className="p-6 sm:p-8 flex flex-col flex-1 min-h-0">
          {/* Step content */}
          <div
            className={cn(
              'flex-1 flex flex-col min-h-0 transition-all duration-200',
              isAnimating && animationDir === 'forward'
                ? 'opacity-0 translate-x-4'
                : isAnimating && animationDir === 'back'
                ? 'opacity-0 -translate-x-4'
                : 'opacity-100 translate-x-0'
            )}
          >
            <div className={cn(
              'flex-1 flex flex-col min-h-0',
              step.id === 'welcome' && 'items-center justify-center text-center'
            )}>
              <SlideView slide={step}>
                {isReferralStep && (
                  <ReferralStep
                    selected={referral}
                    onSelect={setReferral}
                    otherText={otherText}
                    onOtherText={setOtherText}
                  />
                )}
              </SlideView>
            </div>
          </div>

          {/* Footer */}
          <div className="mt-6 shrink-0 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              {currentStep > 0 && (
                <button
                  type="button"
                  onClick={goBack}
                  className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-md hover:bg-muted/50"
                  aria-label="Previous step"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
              )}
              <StepDots total={activeSteps.length} current={currentStep} onSelect={(i) => { setCurrentStep(i); trackStep(i); }} />
            </div>

            <div className="flex items-center gap-2">
              <Button
                onClick={goNext}
                className="gap-2 min-w-[120px]"
                disabled={isReferralStep && (!referral || (referral === 'Other' && !otherText.trim()))}
              >
                {isLast ? 'Get Started' : 'Next'}
                {!isLast && <ArrowRight className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
