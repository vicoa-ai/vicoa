import { Monitor, Smartphone, Globe, Tablet, ShieldCheck, ArrowRight, ArrowDown } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { PlatformAvailability } from '../cta/platform-availability';
import { cn } from '@/lib/utils';

const MOBILE_ONELINK_URL =
  process.env.NEXT_PUBLIC_MOBILE_ONELINK_URL || 'https://vicoa.ai/download-mobile-app';

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn('fill-current', className)}>
      <path d="M16.365 12.346c.02 2.135 1.87 2.846 1.89 2.855-.016.05-.295 1.011-.971 2.003-.584.858-1.19 1.713-2.145 1.73-.937.018-1.238-.555-2.31-.555-1.07 0-1.406.537-2.292.573-.921.034-1.622-.924-2.211-1.78-1.204-1.742-2.123-4.923-.888-7.069.613-1.065 1.709-1.739 2.899-1.757.904-.018 1.758.609 2.31.609.55 0 1.585-.753 2.673-.642.455.02 1.735.184 2.556 1.386-.066.041-1.526.892-1.511 2.647ZM14.322 4.37c.49-.593.82-1.42.73-2.245-.706.029-1.56.471-2.067 1.063-.454.525-.853 1.366-.744 2.171.786.061 1.59-.4 2.081-.989Z" />
    </svg>
  );
}

// Brand marks from public/images/integrations. Colors are theme-tuned so each
// logo stays legible on the card in both light and dark: Claude's mark is
// already colored; the OpenAI/Codex glyph is a dark mark that we invert on
// dark surfaces; OpenCode ships a dark and a light variant that we swap.
function AgentLogo({ agent }: { agent: 'claude' | 'codex' | 'opencode' }) {
  const base = '/images/integrations';
  const size = 'h-4 w-4 shrink-0';
  if (agent === 'claude') {
    return <img src={`${base}/claude-color.svg`} alt="Claude Code" width={16} height={16} className={size} />;
  }
  if (agent === 'codex') {
    return <img src={`${base}/openai.svg`} alt="Codex" width={16} height={16} className={cn(size, 'dark:invert')} />;
  }
  return (
    <>
      <img src={`${base}/opencode-dark.svg`} alt="OpenCode" width={16} height={16} className={cn(size, 'dark:hidden')} />
      <img src={`${base}/opencode.svg`} alt="OpenCode" width={16} height={16} className={cn(size, 'hidden dark:block')} />
    </>
  );
}

function StatusRow({
  agent,
  branch,
  status,
  color,
  filled = true,
}: {
  agent: 'claude' | 'codex' | 'opencode';
  branch: string;
  status: string;
  color: string;
  filled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex min-w-0 items-center gap-2 text-foreground">
        <AgentLogo agent={agent} />
        <span className="truncate text-muted-foreground">{branch}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
        <span
          className={cn('h-1.5 w-1.5 rounded-full', color, !filled && 'bg-transparent ring-1 ring-inset ring-muted-foreground/50')}
        />
        {status}
      </span>
    </div>
  );
}

export type Step = {
  number: string;
  title: string;
  description: string;
  visual: ReactNode;
};

export const defaultSteps: Step[] = [
  {
    number: '01',
    title: 'Install & sign in',
    description:
      'Download the desktop app and sign in. Vicoa auto-detects the agents you already have.',
    visual: (
      <div className="w-full space-y-4">
        <Link
          href="/download"
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-gray-400 bg-white px-5 py-3 text-base text-black shadow-sm transition-colors duration-300 hover:border-gray-600 hover:bg-gray-100 cursor-pointer"
        >
          <AppleIcon className="h-5 w-5" />
          Download for Mac
        </Link>
        <div>
          <p className="mb-2 text-xs text-muted-foreground/70">Prefer the terminal?</p>
          <div className="flex items-center gap-2 rounded-lg bg-secondary px-4 py-3 font-mono text-sm">
            <span className="text-green-400">$</span>
            <span>npm i -g @vicoa/cli</span>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: '02',
    title: 'Run coding agents in parallel',
    description:
      'Start Claude Code, Codex, or other AI agents, each on its own git worktree, all on one workspace.',
    visual: (
      <div className="w-full space-y-2.5 rounded-xl border bg-card p-4 font-mono text-sm shadow-sm">
        <StatusRow agent="claude" branch="feat/payments" status="working" color="bg-green-500" />
        <StatusRow agent="codex" branch="fix/login" status="waiting" color="bg-amber-500" />
        <StatusRow agent="opencode" branch="main" status="idle" color="bg-muted-foreground/40" filled={false} />
      </div>
    ),
  },
  {
    number: '03',
    title: 'Steer from any device',
    description:
      'Grab the mobile app to approve, redirect, and answer questions from anywhere.',
    visual: (
      <div className="w-full">
        <p className="mb-3 text-xs text-muted-foreground/70">Scan the code, or tap a store.</p>
        <div className="flex items-center gap-4">
          <Link
            href={MOBILE_ONELINK_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Scan or tap to download the Vicoa mobile app"
            className="shrink-0 rounded-xl border border-border/60 bg-white p-2 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md cursor-pointer"
          >
            <img
              src="/images/vicoa-app-qrcode.png"
              alt="QR code to download the Vicoa mobile app"
              width={80}
              height={80}
              className="h-22 w-22"
            />
          </Link>
          <PlatformAvailability className="flex-col items-start justify-start" />
        </div>
      </div>
    ),
  },
];

export function HowItWorksSection({
  content = {
    stepsTitle: 'Start at your desk, steer from any device',
    stepsDescription: 'From your computer to your phone in simple three steps',
  },
  steps = defaultSteps,
}: {
  content?: { stepsTitle: string; stepsDescription: string };
  steps?: Step[];
} = {}) {
  return (
    <section className="py-20 bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 mb-16 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
            {content.stepsTitle}
          </h2>
          <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-3xl mx-auto">
            {content.stepsDescription}
          </p>
        </div>

        {/* Diagram: your machine → secure relay → every device */}
        {/* <div className="mb-20 flex flex-col items-stretch justify-center gap-4 lg:flex-row lg:items-center lg:gap-6">
          <div className="flex flex-1 flex-col items-center rounded-2xl border bg-card p-6 text-center shadow-sm lg:max-w-xs">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400">
              <Monitor className="h-6 w-6" />
            </div>
            <div className="text-base font-medium text-foreground">Your machine</div>
            <div className="mt-1 text-sm text-muted-foreground">
              Runs the fleet; your real code stays here
            </div>
          </div>

          <div className="flex flex-col items-center justify-center gap-1 text-muted-foreground">
            <ArrowDown className="h-5 w-5 lg:hidden" />
            <ArrowRight className="hidden h-5 w-5 lg:block" />
            <span className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5" />
              Secure relay
            </span>
            <ArrowDown className="h-5 w-5 lg:hidden" />
            <ArrowRight className="hidden h-5 w-5 lg:block" />
          </div>

          <div className="flex flex-1 flex-col items-center rounded-2xl border bg-card p-6 text-center shadow-sm lg:max-w-xs">
            <div className="mb-3 flex items-center gap-2 text-blue-600 dark:text-blue-400">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-900/20">
                <Smartphone className="h-6 w-6" />
              </span>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-900/20">
                <Globe className="h-5 w-5" />
              </span>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-900/20">
                <Tablet className="h-5 w-5" />
              </span>
            </div>
            <div className="text-base font-medium text-foreground">Phone · Web · Tablet</div>
            <div className="mt-1 text-sm text-muted-foreground">
              Steer any agent from anywhere
            </div>
          </div>
        </div> */}

        {/* Numbered steps — herdr-style rows: big index, headline, right-side visual */}
        <div className="mx-auto max-w-5xl border-t border-border/60">
          {steps.map((step) => (
            <div
              key={step.number}
              className="grid grid-cols-1 items-center gap-6 border-b border-border/60 py-10 lg:grid-cols-[5rem_minmax(0,1fr)_minmax(0,22rem)] lg:gap-10"
            >
              <div className="font-mono text-5xl font-semibold leading-none tabular-nums text-muted-foreground/25 lg:text-6xl">
                {step.number}
              </div>
              <div>
                <h3 className="mb-3 flex items-center gap-2 text-xl text-foreground lg:text-2xl">
                  {step.title}
                  <ArrowRight className="h-5 w-5 text-muted-foreground/50" />
                </h3>
                <p className="max-w-xl leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </div>
              <div className="lg:justify-self-end lg:max-w-sm">{step.visual}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
