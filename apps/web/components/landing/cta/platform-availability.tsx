'use client';

import Link from 'next/link';
import posthog from 'posthog-js';
import { cn } from '@/lib/utils';

type PlatformAvailabilityProps = {
  className?: string;
  buttonClassName?: string;
  iconClassName?: string;
  size?: 'sm' | 'md' | 'lg';
};

const SIZE_STYLES = {
  sm: {
    button: 'h-10 w-10',
    icon: 'h-6 w-6',
  },
  md: {
    button: 'h-12 w-12',
    icon: 'h-7 w-7',
  },
  lg: {
    button: 'h-14 w-14',
    icon: 'h-8 w-8',
  },
} as const;

export function PlatformAvailability({
  className,
  buttonClassName,
  iconClassName,
  size = 'md',
}: PlatformAvailabilityProps) {
  const sizeStyles = SIZE_STYLES[size];
  const buttonClasses = cn(
    'inline-flex items-center justify-center rounded-xl border border-border/70 bg-background text-foreground transition-all duration-300 hover:border-foreground/40 hover:shadow-sm',
    sizeStyles.button,
    buttonClassName
  );
  const iconClasses = cn(sizeStyles.icon, iconClassName);

  return (
    <div className={cn('flex items-center justify-center gap-3', className)}>
      <Link
        href="http://apps.apple.com/sg/app/id6751626168"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Open Vicoa on the App Store"
        className={buttonClasses}
        onClick={() => posthog.capture('app_store_clicked', { platform: 'ios' })}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className={cn(iconClasses, 'fill-current')}>
          <path d="M16.365 12.346c.02 2.135 1.87 2.846 1.89 2.855-.016.05-.295 1.011-0.971 2.003-.584.858-1.19 1.713-2.145 1.73-.937.018-1.238-.555-2.31-.555-1.07 0-1.406.537-2.292.573-.921.034-1.622-.924-2.211-1.78-1.204-1.742-2.123-4.923-.888-7.069.613-1.065 1.709-1.739 2.899-1.757.904-.018 1.758.609 2.31.609.55 0 1.585-.753 2.673-.642.455.02 1.735.184 2.556 1.386-.066.041-1.526.892-1.511 2.647ZM14.322 4.37c.49-.593.82-1.42.73-2.245-.706.029-1.56.471-2.067 1.063-.454.525-.853 1.366-.744 2.171.786.061 1.59-.4 2.081-.989Z" />
        </svg>
      </Link>
      <Link
        href="https://play.google.com/store/apps/details?id=app.vicoa"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Open Vicoa on Google Play"
        className={buttonClasses}
        onClick={() => posthog.capture('app_store_clicked', { platform: 'android' })}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className={iconClasses}>
          <path d="M4.77 3.18 13.3 11.7 4.75 20.25A2.2 2.2 0 0 1 4 18.7V4.74c0-.58.29-1.09.77-1.56Z" fill="#34A853" />
          <path d="m16.03 14.42-2.73-2.72 2.74-2.74 3.35 1.9c.82.46.82 1.64 0 2.1l-3.36 1.46Z" fill="#FBBC04" />
          <path d="M4.77 3.18c.1-.11.22-.2.34-.27.38-.21.85-.22 1.28.03l9.64 5.49-2.73 2.73L4.77 3.18Z" fill="#4285F4" />
          <path d="m4.75 20.25 8.55-8.55 2.73 2.72-9.64 5.5a1.4 1.4 0 0 1-1.28.03c-.13-.07-.25-.16-.36-.27Z" fill="#EA4335" />
        </svg>
      </Link>
    </div>
  );
}
