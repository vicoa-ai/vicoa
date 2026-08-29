import Link from 'next/link';
import {
  Check,
  Blocks,
  CreditCard,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { VsProductCard } from '@/lib/vs-source';

/** Pick a reassurance icon for a hero trust chip from its text. */
function trustChipIcon(chip: string) {
  const t = chip.toLowerCase();
  if (t.includes('card')) return CreditCard;
  if (t.includes('data') || t.includes('privacy') || t.includes('train'))
    return ShieldCheck;
  if (t.includes('agent') || t.includes('works with')) return Blocks;
  if (t.includes('free')) return Sparkles;
  return Check;
}

interface VsHeroProps {
  title: string;
  competitor: string;
  tagline?: string;
  description: string;
  vicoa?: VsProductCard;
  rival?: VsProductCard;
  trustChips?: string[];
}

function ProductCard({
  name,
  card,
  recommended = false,
}: {
  name: string;
  card?: VsProductCard;
  recommended?: boolean;
}) {
  return (
    <div
      className={`relative flex h-full flex-col rounded-2xl border p-6 text-left backdrop-blur-sm ${
        recommended
          ? 'border-primary/40 bg-gradient-to-br from-primary/[0.14] to-primary/[0.04] shadow-md ring-1 ring-primary/20'
          : 'border-border bg-card/70'
      }`}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-lg font-semibold text-foreground">{name}</span>
        {recommended && (
          <span className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-2.5 py-0.5 text-xs font-medium text-white shadow-sm">
            Our pick
          </span>
        )}
      </div>
      {card?.pitch && (
        <p className="text-sm leading-relaxed text-muted-foreground">
          {card.pitch}
        </p>
      )}
      {card?.chips && card.chips.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {card.chips.map((chip, i) => (
            <li
              key={i}
              className="flex items-start gap-2.5 text-sm text-foreground/80"
            >
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                  recommended
                    ? 'bg-primary/15 text-primary'
                    : 'bg-foreground/10 text-foreground/50'
                }`}
              >
                <Check className="h-3.5 w-3.5" />
              </span>
              <span>{chip}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function VsHero({
  title,
  competitor,
  tagline,
  description,
  vicoa,
  rival,
  trustChips,
}: VsHeroProps) {
  // Split a "Vicoa vs X: descriptor" title on the first colon so the brand
  // comparison sits on its own line and the (keyword-rich) descriptor reads as a
  // smaller second line, instead of wrapping mid-phrase.
  const colonIdx = title.indexOf(': ');
  const titleLead = colonIdx === -1 ? title : title.slice(0, colonIdx);
  const titleRest = colonIdx === -1 ? '' : title.slice(colonIdx + 2);

  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-primary/[0.08] via-background to-background">
      {/* Vibrant ambient color glows behind the hero */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -top-24 left-[12%] h-80 w-80 rounded-full bg-blue-500/25 blur-[110px]" />
        <div className="absolute -top-10 right-[12%] h-72 w-72 rounded-full bg-violet-500/25 blur-[110px]" />
        <div className="absolute top-24 left-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-fuchsia-500/15 blur-[110px]" />
      </div>
      <div className="relative container mx-auto max-w-5xl px-4 py-16 text-center md:py-20">
        <h1 className="mx-auto max-w-4xl font-medium leading-tight text-foreground">
          <span className="block text-3xl md:text-5xl">{titleLead}</span>
          {titleRest && (
            <span className="mt-3 block text-2xl text-foreground md:text-4xl">
              {titleRest}
            </span>
          )}
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base text-muted-foreground md:text-lg">
          {tagline || description}
        </p>

        <div className="mt-8 flex flex-col items-center gap-8">
          <Link href="/download">
            <Button size="lg" className="h-12 rounded-full px-8 text-base">
              Get Vicoa for free
            </Button>
          </Link>
          {trustChips && trustChips.length > 0 && (
            <ul className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
              {trustChips.map((chip, i) => {
                const Icon = trustChipIcon(chip);
                return (
                  <li key={i} className="flex items-center gap-1.5">
                    <Icon className="h-3.5 w-3.5 text-primary/70" />
                    {chip}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Dual product cards with a center VS badge */}
        {(vicoa || rival) && (
          <div className="relative mx-auto mt-12 grid max-w-4xl gap-4 sm:grid-cols-2">
            <ProductCard name="Vicoa" card={vicoa} recommended />
            <ProductCard name={competitor} card={rival} />
            <div className="pointer-events-none absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 sm:block">
              <span className="flex h-11 w-11 items-center justify-center rounded-full border-4 border-background bg-gradient-to-br from-blue-500 to-indigo-500 text-xs font-semibold uppercase tracking-wide text-white shadow-md">
                vs
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
