import { Users, Download, Bot } from 'lucide-react';

// Product-proof numbers shown under the hero screenshot.
//
// Sourced 2026-08-16 and rounded DOWN to the nearest defensible round number
// (bump periodically):
//   developers    — prod DB `users` count               (17,004)
//   CLI downloads — npm @vicoa/cli 27,721 + PyPI vicoa 16,645 all-time (44,366)
//   coding agents — supported agents (see StatsBandSection / "Works with" row)
const heroStats = [
  { value: '17,000+', label: 'developers', Icon: Users },
  { value: '44,000+', label: 'CLI downloads', Icon: Download },
  { value: '8+', label: 'coding agents', Icon: Bot },
];

export function HeroStats() {
  return (
    <div className="mt-20 mb-10 flex flex-wrap items-stretch justify-center gap-x-8 gap-y-6 sm:gap-x-12">
      {heroStats.map((s, i) => (
        <div key={s.label} className="flex items-center gap-x-8 sm:gap-x-12">
          {i > 0 && (
            <span aria-hidden className="hidden h-10 w-px self-center bg-border sm:block" />
          )}
          <div className="text-center">
            <div className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              {s.value}
            </div>
            <div className="mt-0.5 flex items-center justify-center gap-1.5 text-sm text-muted-foreground">
              <s.Icon aria-hidden className="h-3.5 w-3.5 shrink-0" />
              {s.label}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
