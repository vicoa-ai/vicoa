'use client';

import Image from 'next/image';
import { DynamicPhrase } from '@/components/landing/sections/dynamic-phrase';
import { EmailCapture } from '@/components/landing/sections/email-capture';
import { AIProviderLogos } from '@/components/landing/sections/ai-provider-logos';
import { SupportedAgents } from '@/components/landing/sections/supported-agents';
import { HeroStats } from '@/components/landing/sections/hero-stats';
import type { AuthUser } from '@/lib/auth/user';
import { DownloadSection } from './download-section';
import { Terminal } from '@/components/terminal';
import { ArrowRight, Terminal as TerminalIcon } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import posthog from 'posthog-js';
import useSWR from 'swr';
import { PlatformAvailability } from '@/components/landing/cta/platform-availability';
import { detectPlatform, type PlatformId } from '@/components/download/download-catalog';
import { cn } from '@/lib/utils';


function AppleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn('fill-current', className)}>
      <path d="M16.365 12.346c.02 2.135 1.87 2.846 1.89 2.855-.016.05-.295 1.011-.971 2.003-.584.858-1.19 1.713-2.145 1.73-.937.018-1.238-.555-2.31-.555-1.07 0-1.406.537-2.292.573-.921.034-1.622-.924-2.211-1.78-1.204-1.742-2.123-4.923-.888-7.069.613-1.065 1.709-1.739 2.899-1.757.904-.018 1.758.609 2.31.609.55 0 1.585-.753 2.673-.642.455.02 1.735.184 2.556 1.386-.066.041-1.526.892-1.511 2.647ZM14.322 4.37c.49-.593.82-1.42.73-2.245-.706.029-1.56.471-2.067 1.063-.454.525-.853 1.366-.744 2.171.786.061 1.59-.4 2.081-.989Z" />
    </svg>
  );
}

function WindowsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn('fill-current', className)}>
      <path d="M3 3h8v8H3V3Zm10 0h8v8h-8V3ZM3 13h8v8H3v-8Zm10 0h8v8h-8v-8Z" />
    </svg>
  );
}

type DesktopPlatform = 'macos' | 'windows' | 'linux';

const DESKTOP_PLATFORMS: { id: DesktopPlatform; label: string }[] = [
  { id: 'macos', label: 'Mac' },
  { id: 'windows', label: 'Windows' },
  { id: 'linux', label: 'Linux' },
];

function DownloadIcon({
  platform,
  className,
}: {
  platform: DesktopPlatform;
  className?: string;
}) {
  if (platform === 'windows') return <WindowsIcon className={className} />;
  if (platform === 'linux') return <TerminalIcon className={className} />;
  return <AppleIcon className={className} />;
}

// The landing page (app/(marketing)/page.tsx) is now a Server Component, so the
// Hero owns the session fetch that personalizes its CTA — the only bit of the
// page that needs the logged-in state. Desktop-local has no server session; the
// null key skips the 401-producing fetch.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';
const fetchUser = (url: string) =>
  fetch(url).then((res) => {
    if (!res.ok) {
      if (res.status === 401) return null;
      throw new Error('Failed to fetch');
    }
    return res.json();
  });

export function HeroSection({
  title,
  subtitle,
}: {
  /** Override the H1. Defaults to the homepage headline + rotating phrase. */
  title?: React.ReactNode;
  /** Override the sub-headline paragraph. Defaults to the homepage copy. */
  subtitle?: React.ReactNode;
} = {}) {
  const { data: user } = useSWR<AuthUser>(IS_DESKTOP ? null : '/api/supabase-user', fetchUser);

  // Detect after mount so server and first client render agree (default view).
  const [platform, setPlatform] = useState<PlatformId | null>(null);
  useEffect(() => {
    setPlatform(detectPlatform());
  }, []);

  // The desktop download is the primary CTA. On a desktop OS we tailor it to the
  // visitor ("Download for Windows/Linux/Mac"); anything else falls back to Mac.
  const detectedDesktop =
    platform === 'macos' || platform === 'windows' || platform === 'linux';
  const downloadPlatform: DesktopPlatform =
    platform === 'windows' || platform === 'linux' ? platform : 'macos';
  const downloadLabel = DESKTOP_PLATFORMS.find((p) => p.id === downloadPlatform)!.label;

  // Logged in: keep the download alongside the Web App button. Logged out:
  // desktop visitors get the download; everyone else gets "Get Vicoa for free".
  const showDownloadButton = user ? true : detectedDesktop;
  const showSecondaryCta = user ? true : !detectedDesktop;

  return (
    <section className="relative py-12 lg:py-14 overflow-hidden bg-muted/30">
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h1 className="text-3xl sm:text-4xl lg:text-7xl text-foreground tracking-tight leading-tight lg:leading-tight mb-6">
            {title ?? (
              <>
                Run a team of coding agents
                <br />
                <DynamicPhrase />
              </>
            )}
          </h1>
          <p className="max-w-3xl mx-auto text-base sm:text-lg lg:text-xl text-muted-foreground mb-8 leading-relaxed">
            {subtitle ?? (
              <>
                Claude Code, Codex, OpenCode, and more agents running in parallel.
                <br />
                Start them at your desk, steer from your phone, get notified when one
                needs you.
              </>
            )}
          </p>

          <div className="mb-8 flex flex-col items-center gap-2">
            <div className="flex flex-wrap items-center justify-center gap-3">
              {showDownloadButton && (
                <Link
                  href="/download"
                  onClick={() => posthog.capture('hero_cta_clicked', { label: `Download for ${downloadLabel}`, logged_in: !!user })}
                  className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-gray-400 bg-white px-6 py-3 text-base text-black shadow-sm transition-colors duration-300 hover:border-gray-600 hover:bg-gray-100"
                >
                  <DownloadIcon platform={downloadPlatform} className="h-6 w-6" />
                  Download for {downloadLabel}
                </Link>
              )}
              {showSecondaryCta && (
                <Link
                  href={user ? '/dashboard' : '/sign-up'}
                  onClick={() => posthog.capture('hero_cta_clicked', { label: user ? 'Web App' : 'Get Vicoa for free', logged_in: !!user })}
                  className={cn(
                    'inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border px-6 py-3 text-base',
                    user
                      ? 'border-border/70 bg-background text-foreground transition-all duration-300 hover:border-foreground/40 hover:shadow-sm'
                      : 'border-gray-400 bg-white text-black shadow-sm transition-colors duration-300 hover:border-gray-600 hover:bg-gray-100'
                  )}
                >
                  {user ? 'Web App' : 'Get Vicoa for free'}
                  {!user && <ArrowRight className="hidden h-5 w-5 sm:inline" />}
                </Link>
              )}
              {user && <PlatformAvailability size="md" />}
            </div>
            {showDownloadButton && (
              <Link
                href="/download"
                onClick={() => posthog.capture('hero_subline_clicked', { platform: downloadPlatform, logged_in: !!user })}
                className="cursor-pointer text-xs text-muted-foreground/70 underline transition-colors hover:text-muted-foreground"
              >
                View all downloads
              </Link>
            )}
          </div>

          {/* Supported agents row */}
          <div className="mt-12 mb-12">
            <SupportedAgents />
          </div>

          {/* Step 1: Installation */}
          {/* <div className="mb-6 flex flex-col lg:flex-row justify-center items-center gap-4">
              <Terminal className="w-full max-w-[56vh] lg:max-w-md xl:max-w-lg 2xl:max-w-xl" showRunComment />
              <PlatformAvailability className="lg:ml-4" />
          </div> */}

          {/* Email Capture */}
          {/* <EmailCapture /> */}

          {/* <DownloadSection /> */}
          
          {/* Hero Image */}
          <div className="max-w-6xl mx-auto mb-8">
            <Image
              src="/images/hero.webp"
              alt="Vibe Code Anywhere (Vicoa)"
              width={4116}
              height={2488}
              priority
              quality={80}
              // Slot is ~1152 CSS px, but we request ~2× so DPR-1 external
              // monitors fetch the 2048 variant and downscale it (crisp at 1:1).
              // Retina (DPR 2) already pulls the 3840 variant, so its load is
              // unchanged; AVIF keeps the DPR-1 byte cost roughly flat.
              sizes="(max-width: 1024px) 100vw, 2048px"
              className="w-full h-auto rounded-xl shadow-lg"
            />
          </div>

          {/* Product-proof stats */}
          <HeroStats />

          {/* <div className="mb-6 flex flex-col lg:flex-row justify-center items-center gap-4">
              <Terminal className="w-full max-w-[56vh] lg:max-w-md xl:max-w-lg 2xl:max-w-xl" showRunComment />
              <PlatformAvailability className="lg:ml-4" />
          </div> */}
          
          {/* AI Provider Logos */}
          {/* <AIProviderLogos /> */}
        </div>
      </div>
    </section>
  );
}
