'use client';

import Link from 'next/link';
import posthog from 'posthog-js';
import { Button } from '@/components/ui/button';

interface VsCtaProps {
  /** Slug of the comparison page, for attribution (e.g. "happy"). */
  slug?: string;
  heading?: string;
  subheading?: string;
  cta?: string;
  href?: string;
}

const BENEFITS = [
  'No credit card',
  'Works with your existing agents',
  'Free tier',
];

/**
 * Conversion block for the end of a `/vs` article. Rendered inside `.prose` but
 * wrapped in `not-prose` so its layout is self-contained. Styled to match the
 * landing-page CTA: a deep blue→indigo gradient card with a line texture, glow
 * blobs, a social-proof badge, a big white pill button, and benefit chips.
 */
export function VsCta({
  slug,
  heading = 'Try the fuller alternative, free',
  subheading = 'Vicoa works with the coding agents already on your machine. No credit card required.',
  cta = 'Get Vicoa for free',
  href = '/download',
}: VsCtaProps) {
  return (
    <div className="not-prose relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900 px-6 py-16 text-center sm:px-14 sm:py-20">
      {/* Diagonal line texture */}
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZGVmcz48cGF0dGVybiBpZD0iYSIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBwYXR0ZXJuVHJhbnNmb3JtPSJyb3RhdGUoNDUpIj48cmVjdCB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIGZpbGw9Im5vbmUiLz48cGF0aCBkPSJNLTEwIDMwbDIwLTIwTTEwIDcwbDIwLTIwTTMwIDUwbDIwLTIwTTUwIDMwbDIwLTIwTTcwIDEwbDIwLTIwTTkwIDMwbDIwLTIwIiBzdHJva2U9InJnYmEoMjU1LDI1NSwyNTUsMC4xKSIgc3Ryb2tlLXdpZHRoPSIxIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] opacity-20" />
      {/* Glow blobs */}
      <div className="pointer-events-none absolute -top-16 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-blue-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-10 right-1/4 h-56 w-56 rounded-full bg-indigo-500/20 blur-3xl" />

      <div className="relative mx-auto max-w-2xl">
        <div className="mb-6 inline-flex items-center rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-sm font-medium text-blue-100 backdrop-blur-sm">
          🚀 Join 17,000+ developers
        </div>

        <h2 className="text-3xl font-medium leading-tight text-white sm:text-4xl">
          {heading}
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-slate-200">
          {subheading}
        </p>

        <div className="mt-8 flex justify-center">
          <Link
            href={href}
            onClick={() =>
              posthog.capture('vs_cta_clicked', { location: 'article', slug })
            }
          >
            <Button
              size="lg"
              className="h-12 rounded-full border-0 bg-white px-8 text-base font-medium text-slate-900 shadow-lg transition-all duration-300 hover:scale-105 hover:bg-slate-100 hover:shadow-2xl"
            >
              {cta}
            </Button>
          </Link>
        </div>

        <div className="mt-8 flex flex-col items-center justify-center gap-x-8 gap-y-3 text-sm text-blue-200 sm:flex-row">
          {BENEFITS.map((benefit) => (
            <div key={benefit} className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-400" />
              <span>{benefit}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
