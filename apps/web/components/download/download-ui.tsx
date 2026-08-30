'use client';

import type { ReactNode } from 'react';
import Image from 'next/image';
import posthog from 'posthog-js';
import { Globe, Monitor, Smartphone, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CopyButton } from './copy-button';

/* -------------------------------------------------------------------------- */
/* Icons                                                                       */
/* -------------------------------------------------------------------------- */

/** Brand marks aren't in lucide, so they're inlined; the generic ones aren't. */
export type IconName =
  | 'apple'
  | 'windows'
  | 'linux'
  | 'android'
  | 'terminal'
  | 'globe'
  | 'monitor'
  | 'phone';

function Icon({ name, className }: { name: IconName; className?: string }) {
  const cls = cn('h-5 w-5', className);
  switch (name) {
    case 'apple':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={cn(cls, 'fill-current')}>
          <path d="M16.365 12.346c.02 2.135 1.87 2.846 1.89 2.855-.016.05-.295 1.011-.971 2.003-.584.858-1.19 1.713-2.145 1.73-.937.018-1.238-.555-2.31-.555-1.07 0-1.406.537-2.292.573-.921.034-1.622-.924-2.211-1.78-1.204-1.742-2.123-4.923-.888-7.069.613-1.065 1.709-1.739 2.899-1.757.904-.018 1.758.609 2.31.609.55 0 1.585-.753 2.673-.642.455.02 1.735.184 2.556 1.386-.066.041-1.526.892-1.511 2.647ZM14.322 4.37c.49-.593.82-1.42.73-2.245-.706.029-1.56.471-2.067 1.063-.454.525-.853 1.366-.744 2.171.786.061 1.59-.4 2.081-.989Z" />
        </svg>
      );
    case 'windows':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={cn(cls, 'fill-current')}>
          <path d="M3 5.1 10 4.05v6.9H3V5.1Zm0 13.8V13h7v6.95L3 18.9Zm8-14.9L21 2.5V11H11V3.9ZM11 13h10v8.5l-10-1.4V13Z" />
        </svg>
      );
    case 'linux':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={cn(cls, 'fill-current')}>
          <path d="M12.5 2c-1.7 0-2.9 1.5-2.9 3.4 0 .6.1 1.5.1 2-.6.7-2.3 3-2.9 4.5-.4 1-.9 1.9-1.6 2.7-.5.5-.5 1.2-.1 1.6.3.3.7.3 1.1.1.1.7.1 1.6.6 2.2.3.4.7.5 1.1.5h8.4c.4 0 .8-.1 1.1-.5.5-.6.5-1.5.6-2.2.4.2.8.2 1.1-.1.4-.4.4-1.1-.1-1.6-.7-.8-1.2-1.7-1.6-2.7-.6-1.5-2.3-3.8-2.9-4.5 0-.5.1-1.4.1-2C15.4 3.5 14.2 2 12.5 2Zm-1.4 3.1c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9Zm2.8 0c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9Z" />
        </svg>
      );
    case 'android':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={cn(cls, 'fill-current')}>
          <path d="M17.6 9.48l1.84-3.18a.4.4 0 1 0-.7-.4l-1.87 3.23a11.43 11.43 0 0 0-9.74 0L5.26 5.9a.4.4 0 1 0-.7.4L6.4 9.48A10.81 10.81 0 0 0 1 18h22a10.81 10.81 0 0 0-5.4-8.52ZM7 15.25a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5Zm10 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5Z" />
        </svg>
      );
    case 'terminal':
      return <Terminal className={cls} />;
    case 'globe':
      return <Globe className={cls} />;
    case 'monitor':
      return <Monitor className={cls} />;
    case 'phone':
      return <Smartphone className={cls} />;
  }
}

/* -------------------------------------------------------------------------- */
/* Layout primitives                                                           */
/* -------------------------------------------------------------------------- */

export function DownloadSection({
  title,
  description,
  icon,
  children,
  footnote,
}: {
  title: string;
  description?: string;
  icon: IconName;
  children: ReactNode;
  footnote?: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border/60 bg-muted/20 p-6 md:p-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        <Icon name={icon} className="mt-1.5 h-5 w-5 shrink-0 text-muted-foreground" />
      </div>

      <div className="divide-y divide-border/60">{children}</div>

      {footnote && <p className="mt-5 text-xs text-muted-foreground">{footnote}</p>}
    </section>
  );
}

export function DownloadRow({
  icon,
  label,
  children,
}: {
  icon: IconName;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 py-5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <Icon name={icon} className="h-5 w-5 text-foreground" />
        <span className="text-sm font-medium text-foreground">{label}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">{children}</div>
    </div>
  );
}

/**
 * An action pill. Omit `href` to render a placeholder: it still looks and
 * tracks like a real download, but does nothing. When desktop builds ship,
 * pass the release URL and the placeholder behaviour disappears on its own.
 *
 * Pass `qr` to reveal a scannable code on hover — for store links, where the
 * visitor is on a desktop but the app lives on their phone.
 */
export function DownloadPill({
  href,
  label,
  external,
  track,
  qr,
}: {
  href?: string;
  label: string;
  external?: boolean;
  track: string;
  qr?: { src: string; position: 'top' | 'bottom' };
}) {
  const isPlaceholder = !href;

  const pill = (
    <a
      href={href ?? '#'}
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
      title={isPlaceholder ? 'Coming soon' : undefined}
      aria-label={isPlaceholder ? `${label} (coming soon)` : label}
      onClick={(e) => {
        if (isPlaceholder) e.preventDefault();
        posthog.capture('download_clicked', { target: track, placeholder: isPlaceholder });
      }}
      className="inline-flex items-center justify-center rounded-full bg-foreground px-4 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
    >
      {label}
      {external && (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="ml-1.5 h-3 w-3"
          aria-hidden="true"
        >
          <path d="M7 17 17 7" />
          <path d="M7 7h10v10" />
        </svg>
      )}
    </a>
  );

  if (!qr) return pill;

  return (
    <div className="group relative">
      {pill}
      {/* Decorative: the pill itself is the accessible affordance. */}
      <div
        aria-hidden="true"
        className={cn(
          // w-max: an abspos box shrink-to-fits against its containing block,
          // which here is only as wide as the pill — without it the QR squeezes.
          'pointer-events-none absolute left-1/2 z-50 w-max -translate-x-1/2 opacity-0 transition-opacity duration-200 group-hover:opacity-100',
          qr.position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'
        )}
      >
        <div className="rounded-xl border border-border bg-popover p-3 shadow-2xl">
          <div className="rounded-md bg-white p-2">
            <Image src={qr.src} alt="" width={128} height={128} className="h-auto w-32" />
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">Scan to download</p>
        </div>
      </div>
    </div>
  );
}

/** A muted badge for platforms whose builds aren't published yet. */
export function ComingSoon({ label = 'Coming soon' }: { label?: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/40 px-4 py-1.5 text-sm font-medium text-muted-foreground">
      {label}
    </span>
  );
}

/** A copy-able shell command, shown on the right of a row. */
export function CommandBlock({ command, event }: { command: string; event: string }) {
  return (
    <div className="flex w-full items-center gap-2 rounded-lg border border-border/60 bg-background px-3 py-2 sm:w-auto">
      <code className="flex-1 truncate font-mono text-sm text-foreground">
        <span className="select-none text-muted-foreground">$ </span>
        {command}
      </code>
      <CopyButton value={command} event={event} iconOnly />
    </div>
  );
}
