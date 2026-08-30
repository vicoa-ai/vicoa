import Image from 'next/image';
import { Check } from 'lucide-react';
import {
  FixSteer,
  FixWorktree,
  FixAutopilot,
  FixBoard,
} from '@/components/landing/illustrations';

// Each fix mirrors a card in ProblemSection, in the same order and with the same
// index number, so the section reads as a direct answer to the problem above.
const fixes = [
  {
    Art: FixSteer,
    title: 'Steer from any device',
    caption: 'One tap from your phone, no desk required.',
  },
  {
    Art: FixWorktree,
    title: 'Each agent, its own worktree',
    caption: 'Isolated branches, zero collisions.',
  },
  {
    Art: FixAutopilot,
    title: 'Put the busywork on autopilot',
    caption: 'Scheduled runs, hands-off.',
  },
  {
    Art: FixBoard,
    title: 'The whole fleet on one board',
    caption: 'Every agent’s status at a glance.',
  },
];

export function SolutionSection() {
  return (
    <section className="relative overflow-hidden bg-background py-20 sm:py-28 lg:py-32">
      {/* Cool wash: the relief answer to the red tension above */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 left-1/2 h-80 w-[46rem] -translate-x-1/2 rounded-full bg-blue-500/[0.07] blur-3xl dark:bg-blue-500/[0.12]"
      />

      <div className="relative z-10 mx-auto max-w-[85rem] px-4 sm:px-6 lg:px-6">
        <div className="mx-auto mb-14 max-w-3xl text-center sm:mb-20">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/[0.06] px-3.5 py-1.5 text-xs font-medium uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            Meet Vicoa
          </div>
          <h2 className="mb-5 text-3xl tracking-tight text-foreground sm:text-4xl lg:text-6xl">
            The same agents.
            <br className="hidden sm:block" /> Without the chaos.
          </h2>
          <p className="text-lg leading-relaxed text-muted-foreground sm:text-xl">
            Vicoa wraps the coding agents you already run and fixes what makes a fleet
            painful — on your desktop and your phone. Here’s how each headache goes away.
          </p>
        </div>

        {/* Four fixes, mirroring the four problems above (same order, same numbers) */}
        <div className="mb-16 grid gap-5 sm:grid-cols-2 sm:gap-6 lg:mb-20">
          {fixes.map((fix, i) => {
            const Art = fix.Art;
            return (
              <div
                key={fix.title}
                className="group flex h-full flex-col overflow-hidden rounded-3xl border bg-card p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-emerald-300/70 hover:shadow-lg sm:p-6 dark:hover:border-emerald-500/40"
              >
                <Art />
                <div className="mt-6 flex items-baseline gap-3">
                  <span className="flex items-center gap-1.5 font-mono text-sm font-medium text-emerald-600 tabular-nums dark:text-emerald-400">
                    <Check className="h-4 w-4 self-center" strokeWidth={2.5} />
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="text-xl font-medium text-card-foreground sm:text-2xl">
                    {fix.title}
                  </h3>
                </div>
                <p className="mt-2 text-base leading-relaxed text-muted-foreground">
                  {fix.caption}
                </p>
              </div>
            );
          })}
        </div>

        {/* Payoff: the whole fleet on one board, promoted to a glowing hero shot */}
        <div className="mx-auto max-w-4xl text-center">
          <h3 className="text-2xl text-foreground sm:text-3xl lg:text-4xl">
            One board. Every agent. At a glance.
          </h3>
          <p className="mx-auto mt-3 max-w-2xl text-base text-muted-foreground sm:text-lg">
            Watch the whole fleet, spot who’s stuck, and jump in — from your desk or your
            phone.
          </p>
        </div>

        <div className="relative mx-auto mt-10 max-w-6xl sm:mt-12">
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-6 -z-10 rounded-[2.5rem] bg-gradient-to-tr from-blue-500/25 via-emerald-500/15 to-transparent blur-2xl dark:from-blue-500/25 dark:via-emerald-500/15"
          />
          <div className="overflow-hidden rounded-2xl border border-border shadow-2xl">
            <Image
              src="/images/features/desktop-ui.webp"
              alt="The Vicoa desktop app showing several coding agents on one board with live status"
              width={1508}
              height={851}
              sizes="(max-width: 1024px) 100vw, 1152px"
              quality={95}
              priority
              className="h-auto w-full"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
