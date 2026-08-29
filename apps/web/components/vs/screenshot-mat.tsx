import React from 'react';
import { cn } from '@/lib/utils';

/**
 * Soft gradient "mat" behind a product screenshot, matching the desktop-intro
 * onboarding slides: a light blue→peach card with padding, rounded corners, and
 * a soft shadow so screenshots pop against the dark page. Transparent-background
 * shots (app windows) let the gradient show through; cropped shots sit rounded
 * on top. Override the padding (or add transitions) via `className`.
 */
export function ScreenshotMat({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl bg-gradient-to-br from-[#C9DEFF] to-[#FFEDE2] p-3 shadow-lg sm:p-5',
        className
      )}
    >
      {children}
    </div>
  );
}
