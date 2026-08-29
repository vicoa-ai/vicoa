'use client';

import { useEffect, useState } from 'react';
import posthog from 'posthog-js';
import { Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  detectMacArch,
  detectPlatform,
  heroFor,
  TAGLINE,
  type DesktopUrls,
  type HeroAction,
  type HeroContent,
} from './download-catalog';

function HeroButton({ action, primary }: { action: HeroAction; primary: boolean }) {
  const isPlaceholder = !action.href;
  return (
    <a
      href={action.href ?? '#'}
      target={action.external ? '_blank' : undefined}
      rel={action.external ? 'noopener noreferrer' : undefined}
      title={isPlaceholder ? 'Coming soon' : undefined}
      aria-label={isPlaceholder ? `${action.label} (coming soon)` : action.label}
      onClick={(e) => {
        if (isPlaceholder) e.preventDefault();
        posthog.capture('download_clicked', { target: action.track, placeholder: isPlaceholder });
      }}
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-colors',
        primary
          ? 'bg-foreground text-background hover:bg-foreground/85'
          : 'border border-border/70 text-foreground/80 hover:border-foreground/40 hover:text-foreground'
      )}
    >
      {primary && <Download className="h-4 w-4" />}
      {action.label}
    </a>
  );
}

/**
 * Page header. Detects the visitor's OS — and on a Mac, the CPU — to surface
 * the one download they most likely want; everything else stays available in
 * the sections below.
 *
 * Detection runs in an effect rather than during render, so the server and the
 * first client pass agree on the neutral fallback and hydration stays quiet.
 */
export function DownloadHero({ urls }: { urls?: DesktopUrls }) {
  const [hero, setHero] = useState<HeroContent | null>(null);

  useEffect(() => {
    const platform = detectPlatform();
    if (!platform) return;
    setHero(heroFor(platform, platform === 'macos' ? detectMacArch() : 'unknown', urls));
  }, [urls]);

  const hasPlaceholder = hero?.actions.some((a) => !a.href) ?? false;

  return (
    <header>
      <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
        {hero ? `Vicoa for ${hero.osLabel}` : 'Download'}
      </h1>
      <p className="mt-2 text-muted-foreground">{TAGLINE}</p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        {hero?.actions.map((action, i) => (
          <HeroButton key={action.track} action={action} primary={i === 0} />
        ))}
        <a
          href="#all-platforms"
          className="inline-flex items-center rounded-full border border-border/70 px-5 py-2.5 text-sm font-medium text-foreground/80 transition-colors hover:border-foreground/40 hover:text-foreground"
        >
          See all platforms
        </a>
      </div>

      {hasPlaceholder && (
        <p className="mt-4 text-xs text-muted-foreground">Linux builds are coming soon.</p>
      )}
    </header>
  );
}
