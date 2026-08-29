'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, ChevronLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  INTRO_SLIDES,
  SlideImagePreloader,
  SlideView,
  StepDots,
} from '@/components/onboarding/intro-slides';
import { markDesktopIntroSeen } from '@/lib/desktop-onboarding';
import {
  trackIntroCompleted,
  trackIntroStarted,
  trackIntroStepViewed,
} from '@/lib/desktop-telemetry';
import { DRAG_REGION } from '@/lib/app-region';

/**
 * Desktop intro — the first thing a new install shows, before sign-in.
 *
 * `DesktopAuthGate` sends a signed-out shell here while the intro flag is
 * unset, and to `/desktop-welcome` (sign-in) once it is. Both the terminal
 * action and Skip set the flag, so the intro is seen at most once per install
 * even if the user never signs in.
 *
 * Slides are shared with the web `OnboardingModal` via `intro-slides.tsx` —
 * same copy, same screenshots. This surface has no referral survey (that is
 * post-signup on web) and no modal chrome: it owns the whole window.
 */
export default function DesktopIntroPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const [animationDir, setAnimationDir] = useState<'forward' | 'back'>('forward');

  useEffect(() => {
    trackIntroStarted();
  }, []);

  const trackStep = useCallback((index: number) => {
    trackIntroStepViewed(index, INTRO_SLIDES[index].id);
  }, []);

  const finish = useCallback(
    (skipped: boolean) => {
      markDesktopIntroSeen();
      trackIntroCompleted(skipped, currentStep + 1);
      router.replace('/desktop-welcome');
    },
    [currentStep, router]
  );

  const goNext = useCallback(() => {
    if (isAnimating) return;
    if (currentStep === INTRO_SLIDES.length - 1) {
      finish(false);
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
  }, [currentStep, isAnimating, finish, trackStep]);

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

  const slide = INTRO_SLIDES[currentStep];
  const isLast = currentStep === INTRO_SLIDES.length - 1;

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Fetch every slide screenshot up front so forward/back navigation paints
          instantly instead of loading the image on arrival. */}
      <SlideImagePreloader slides={INTRO_SLIDES} />

      {/* Frameless-window drag strip (traffic lights float over it). */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />

      {/* No top progress bar: the StepDots in the footer already indicate
          progress, and a second indicator at the very top read as browser-like
          chrome on the desktop window. */}

      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col p-6 sm:p-8 min-h-0">
        <div
          className={cn(
            'flex flex-1 flex-col min-h-0 transition-all duration-200',
            isAnimating && animationDir === 'forward'
              ? 'opacity-0 translate-x-4'
              : isAnimating && animationDir === 'back'
              ? 'opacity-0 -translate-x-4'
              : 'opacity-100 translate-x-0'
          )}
        >
          {/* Center the slide as a group. The screenshots are landscape
              (1431×884) and width-capped by the `max-w-5xl` column, so on a very
              tall window they can't grow to fill the height — letting the image
              box grow (`fillHeight`) would strand empty space around it and pin
              the header to the top and the description to the bottom. Instead the
              image sizes to its content and `justify-center` keeps the header,
              image, and description together with constant spacing in the middle.
              On a short window the image box still shrinks (min-h-0) so nothing
              overflows. Welcome has no image and centers the same way. */}
          <div
            className={cn(
              'flex w-full flex-1 flex-col min-h-0 justify-center',
              slide.id === 'welcome' && 'items-center text-center'
            )}
          >
            <SlideView slide={slide} size="lg" fillHeight={false} />
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 flex shrink-0 items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {currentStep > 0 && (
              <button
                type="button"
                onClick={goBack}
                className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
                aria-label="Previous step"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            )}
            <StepDots
              total={INTRO_SLIDES.length}
              current={currentStep}
              onSelect={(i) => {
                setCurrentStep(i);
                trackStep(i);
              }}
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => finish(true)}
              className="cursor-pointer px-2 text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              Skip
            </button>
            <Button onClick={goNext} className="min-w-[120px] gap-2">
              {isLast ? 'Get Started' : 'Next'}
              {!isLast && <ArrowRight className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
