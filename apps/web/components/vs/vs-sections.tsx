import React from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { VsHighlight, VsKeyTakeaway } from '@/lib/vs-source';

/** Consistent section shell: optional eyebrow + centered heading + intro. */
export function VsSection({
  eyebrow,
  title,
  intro,
  children,
  muted = false,
  className = '',
}: {
  eyebrow?: string;
  title?: string;
  intro?: string;
  children: React.ReactNode;
  muted?: boolean;
  className?: string;
}) {
  return (
    <section className={`${muted ? 'bg-muted/30' : ''} ${className}`}>
      <div className="container mx-auto max-w-5xl px-4 py-16 md:py-20">
        {(eyebrow || title || intro) && (
          <div className="mx-auto mb-10 max-w-2xl text-center">
            {eyebrow && (
              <div className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-primary">
                {eyebrow}
              </div>
            )}
            {title && (
              <h2 className="text-2xl font-medium text-foreground md:text-3xl">
                {title}
              </h2>
            )}
            {intro && (
              <p className="mt-3 text-muted-foreground">{intro}</p>
            )}
          </div>
        )}
        {children}
      </div>
    </section>
  );
}

/** "The gist" TL;DR: a labeled one-liner per decision axis. */
export function KeyTakeaways({ items }: { items: VsKeyTakeaway[] }) {
  return (
    <div className="mx-auto mt-5 max-w-3xl rounded-2xl border border-border bg-card p-6 sm:p-7">
      <div className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-primary">
        The gist
      </div>
      <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {items.map((item, i) => (
          <div key={i} className="flex flex-col">
            <dt className="text-sm font-semibold text-foreground">
              {item.label}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {item.text}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Rotating vibrant accents so the three stat cards read as a colorful band.
const HIGHLIGHT_ACCENTS = [
  { stat: 'from-blue-500 to-cyan-400', glow: 'bg-blue-500/15', border: 'border-blue-500/25' },
  { stat: 'from-violet-500 to-fuchsia-400', glow: 'bg-violet-500/15', border: 'border-violet-500/25' },
  { stat: 'from-emerald-500 to-teal-400', glow: 'bg-emerald-500/15', border: 'border-emerald-500/25' },
];

export function HighlightCards({ items }: { items: VsHighlight[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {items.map((item, i) => {
        const accent = HIGHLIGHT_ACCENTS[i % HIGHLIGHT_ACCENTS.length];
        return (
          <div
            key={i}
            className={`relative overflow-hidden rounded-2xl border ${accent.border} bg-card p-6 text-center`}
          >
            <div
              aria-hidden
              className={`pointer-events-none absolute -top-10 left-1/2 h-28 w-40 -translate-x-1/2 rounded-full ${accent.glow} blur-2xl`}
            />
            <div
              className={`relative bg-gradient-to-r ${accent.stat} bg-clip-text text-4xl font-bold text-transparent md:text-5xl`}
            >
              {item.stat}
            </div>
            <div className="relative mt-1 text-sm font-medium text-foreground">
              {item.label}
            </div>
            {item.detail && (
              <p className="relative mt-2 text-sm text-muted-foreground">
                {item.detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function RivalStrengths({
  items,
}: {
  items: { title: string; body: string }[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {items.map((item, i) => (
        <div
          key={i}
          className="rounded-2xl border border-border bg-card p-6"
        >
          <h3 className="mb-2 text-base font-medium text-foreground">
            {item.title}
          </h3>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {item.body}
          </p>
        </div>
      ))}
    </div>
  );
}

interface KeepComparingItem {
  title: string;
  competitor: string;
  href: string;
  description: string;
}

export function KeepComparing({ items }: { items: KeepComparingItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="group flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/50"
        >
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <span className="text-primary">Vicoa</span>
            <span className="text-xs uppercase tracking-wide text-muted-foreground">
              vs
            </span>
            <span className="text-foreground/80">{item.competitor}</span>
          </div>
          <p className="line-clamp-2 text-sm text-muted-foreground">
            {item.description}
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-foreground/70 transition-colors group-hover:text-primary">
            Read comparison
            <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          </span>
        </Link>
      ))}
    </div>
  );
}
