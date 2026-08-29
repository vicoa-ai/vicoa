import {
  MousePointer2,
  Repeat,
  Check,
  X,
  Clock,
  Lock,
  Bell,
  Calendar,
  AlertTriangle,
  LayoutGrid,
  ArrowRight,
  ArrowLeft,
} from 'lucide-react';

/**
 * Small code-drawn illustrations (pure CSS/SVG, theme-aware, no images) for the
 * Problem and Solution tiles. Each renders inside a fixed-height, border-less
 * Frame so the grid stays even. Problem art skews red/amber (broken state); fix
 * art skews emerald/blue (resolved state). Fix N visually answers Problem N.
 */
function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex h-52 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-muted/70 via-muted/40 to-muted/20 p-3 sm:h-60 dark:from-muted/50 dark:via-muted/25 dark:to-muted/10">
      {/* Scale the fixed-size mockups up on wider viewports where the card (and
          thus the frame) has room, so the figures don't read as tiny on desktop. */}
      <div className="origin-center scale-100 md:scale-110 lg:scale-[1.35] xl:scale-[1.5]">
        {children}
      </div>
    </div>
  );
}

/* ---------------------------- Problem illustrations ---------------------------- */

// Chained to your desk: a terminal that runs, finishes its work, then just
// blocks — waiting on a human before it can take another step.
export function ProblemWaiting() {
  return (
    <Frame>
      <div className="w-[224px] overflow-hidden rounded-xl bg-slate-900 shadow-xl ring-1 ring-black/10">
        <div className="flex items-center gap-1.5 border-b border-white/10 px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-red-400/90" />
          <span className="h-2 w-2 rounded-full bg-amber-400/90" />
          <span className="h-2 w-2 rounded-full bg-emerald-400/90" />
          <span className="ml-1.5 font-mono text-[9px] text-white/40">agent — run</span>
        </div>
        <div className="space-y-1.5 p-3 font-mono text-[9px] leading-none">
          <div className="text-emerald-400">$ agent run build</div>
          <div className="text-white/45">✓ compiled 42 files</div>
          <div className="text-white/45">✓ tests passed</div>
          <div className="mt-2.5 flex items-center gap-1.5 rounded-md bg-amber-400/10 px-2 py-1.5 text-amber-300 ring-1 ring-amber-400/25">
            <Clock className="h-3 w-3 animate-pulse" />
            <span>Waiting for you…</span>
            <span className="ml-auto h-3 w-[3px] animate-pulse rounded-sm bg-amber-300/80" />
          </div>
        </div>
      </div>
    </Frame>
  );
}

// Agents trip over each other: two agents converge on one file and leave a
// merge conflict in their wake.
export function ProblemCollision() {
  const chip =
    'flex h-9 w-9 items-center justify-center rounded-xl text-sm font-semibold text-white shadow-md';
  return (
    <Frame>
      <div className="flex items-center gap-1.5">
        <div className={`${chip} bg-gradient-to-br from-blue-500 to-blue-600`}>A</div>
        <ArrowRight className="h-4 w-4 shrink-0 text-blue-500" />
        <div className="relative w-[96px] overflow-hidden rounded-lg border bg-card shadow-sm">
          <div className="border-b px-2 py-1 text-[9px] font-medium text-foreground">
            app.tsx
          </div>
          <div className="space-y-0.5 p-1.5 font-mono text-[7px] leading-tight">
            <div className="rounded-sm bg-emerald-500/15 px-1 text-emerald-600 dark:text-emerald-400">
              + header
            </div>
            <div className="rounded-sm bg-red-500/15 px-1 text-red-600 dark:text-red-400">
              − header
            </div>
            <div className="px-1 text-muted-foreground">{'<<<<<<<'}</div>
          </div>
          <span className="absolute -right-1.5 -top-1.5 rounded-full bg-red-500 px-1.5 py-0.5 text-[7px] font-semibold uppercase tracking-wide text-white shadow">
            conflict
          </span>
        </div>
        <ArrowLeft className="h-4 w-4 shrink-0 text-violet-500" />
        <div className={`${chip} bg-gradient-to-br from-violet-500 to-violet-600`}>B</div>
      </div>
    </Frame>
  );
}

// Babysitting every step: the same approval, over and over. A stack fading into
// an endless queue, with the cursor stuck clicking "Allow".
export function ProblemBabysitting() {
  const fade = ['opacity-100', 'opacity-70', 'opacity-45'];
  return (
    <Frame>
      <div className="relative w-[210px]">
        <div className="space-y-1.5">
          {fade.map((op, i) => (
            <div
              key={i}
              className={`flex items-center justify-between rounded-lg border bg-card px-2.5 py-2 shadow-sm ${op}`}
            >
              <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <Lock className="h-3 w-3 text-amber-500" />
                Permission needed
              </span>
              <span className="rounded-md bg-foreground/10 px-2 py-0.5 text-[9px] font-medium text-foreground">
                Allow
              </span>
            </div>
          ))}
        </div>
        <div className="absolute -left-1 -top-3 flex items-center gap-1 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[8px] font-medium text-amber-600 dark:text-amber-400">
          <Repeat className="h-2.5 w-2.5" /> again
        </div>
        <MousePointer2 className="absolute -bottom-2 right-5 h-4 w-4 fill-foreground text-foreground drop-shadow" />
      </div>
    </Frame>
  );
}

// A wall of terminal tabs: a crowded tab strip with nine more hidden, and no
// way to tell which agent is the one that's stuck.
export function ProblemTabs() {
  return (
    <Frame>
      <div className="w-[224px] overflow-hidden rounded-xl border bg-card shadow-md">
        <div className="flex items-center gap-1 border-b bg-muted/50 px-1.5 py-1.5">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className={`flex h-4 items-center gap-1 rounded px-1 ${
                i === 2 ? 'bg-card ring-1 ring-red-400/60' : 'bg-foreground/[0.06]'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  i === 2
                    ? 'animate-pulse bg-red-500'
                    : i === 4
                      ? 'bg-emerald-500'
                      : 'bg-foreground/25'
                }`}
              />
              <span className="h-1 w-4 rounded-full bg-foreground/15" />
            </div>
          ))}
          <span className="ml-auto pr-0.5 text-[10px] font-medium text-muted-foreground">
            +9
          </span>
        </div>
        <div className="space-y-1.5 p-3">
          <div className="h-1.5 w-3/4 rounded bg-foreground/10" />
          <div className="h-1.5 w-1/2 rounded bg-foreground/10" />
          <div className="mt-2 inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-1 text-[9px] font-medium text-red-600 ring-1 ring-red-500/20 dark:text-red-400">
            <AlertTriangle className="h-2.5 w-2.5" /> Which one is stuck?
          </div>
        </div>
      </div>
    </Frame>
  );
}

/* ---------------------------- Fix illustrations ---------------------------- */

// Steer from any device: the blocking approval from ProblemWaiting arrives as a
// push on your phone, answered with one tap.
export function FixSteer() {
  return (
    <Frame>
      <div className="relative w-[132px] rounded-[1.6rem] border-[3px] border-foreground/15 bg-card p-1.5 shadow-xl">
        <div className="mx-auto mb-1.5 h-1 w-8 rounded-full bg-foreground/15" />
        <div className="mb-1.5 flex items-center gap-1.5 rounded-lg bg-foreground/[0.04] px-1.5 py-1.5 ring-1 ring-border">
          <span className="flex h-4 w-4 items-center justify-center rounded-md bg-blue-500 shadow-sm">
            <Bell className="h-2.5 w-2.5 text-white" />
          </span>
          <div className="flex-1 space-y-1">
            <div className="h-1 w-12 rounded-full bg-foreground/20" />
            <div className="h-1 w-8 rounded-full bg-foreground/10" />
          </div>
        </div>
        <div className="rounded-lg border bg-background p-2">
          <div className="text-[9px] font-semibold text-foreground">Agent needs you</div>
          <div className="text-[8px] text-muted-foreground">Approve the change?</div>
          <div className="mt-1.5 flex gap-1">
            <span className="flex flex-1 items-center justify-center gap-0.5 rounded-md bg-emerald-500 py-1 text-[8px] font-medium text-white shadow-sm">
              <Check className="h-2.5 w-2.5" /> Approve
            </span>
            <span className="flex items-center justify-center rounded-md border px-1.5 text-muted-foreground">
              <X className="h-2.5 w-2.5" />
            </span>
          </div>
        </div>
        <MousePointer2 className="absolute -bottom-1 right-3 h-4 w-4 fill-foreground text-foreground drop-shadow" />
      </div>
    </Frame>
  );
}

// Each agent, its own worktree: a git trunk with three isolated branches, one
// agent (the same A/B from the collision) parked safely on each.
export function FixWorktree() {
  const branches = [
    { dot: 'bg-blue-500', chip: 'bg-blue-500', label: 'feat/auth', agent: 'A' },
    { dot: 'bg-violet-500', chip: 'bg-violet-500', label: 'fix/cart', agent: 'B' },
    { dot: 'bg-emerald-500', chip: 'bg-emerald-500', label: 'docs/api', agent: 'C' },
  ];
  return (
    <Frame>
      <div className="relative flex items-center">
        {/* trunk with commit dots */}
        <div className="relative mr-3 h-[108px] w-1 rounded-full bg-gradient-to-b from-foreground/25 to-foreground/10">
          {['top-2', 'top-1/2 -translate-y-1/2', 'bottom-2'].map((pos) => (
            <span
              key={pos}
              className={`absolute -left-[5px] h-3 w-3 rounded-full border-2 border-background bg-foreground/40 ${pos}`}
            />
          ))}
        </div>
        <div className="space-y-3">
          {branches.map((b) => (
            <div key={b.label} className="flex items-center gap-2">
              <div className="h-px w-4 rounded bg-foreground/20" />
              <span className={`h-2.5 w-2.5 rounded-full ${b.dot} ring-2 ring-background`} />
              <span className="rounded-md border bg-card px-2 py-1 text-[10px] font-medium text-foreground shadow-sm">
                {b.label}
              </span>
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-md ${b.chip} text-[9px] font-semibold text-white shadow-sm`}
              >
                {b.agent}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Frame>
  );
}

// Put the busywork on autopilot: a schedule toggled on, running a queue of jobs
// on its own while you're away.
export function FixAutopilot() {
  const jobs = [
    { label: 'Run tests → open PR', state: 'done' },
    { label: 'Sync dependencies', state: 'running' },
    { label: 'Nightly refactor', state: 'queued' },
  ] as const;
  return (
    <Frame>
      <div className="w-[224px] overflow-hidden rounded-xl border bg-card p-3 shadow-md">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[10px] font-medium text-foreground">
            <Calendar className="h-3.5 w-3.5 text-emerald-500" />
            Every day · 9:00
          </span>
          <span className="flex h-4 w-7 items-center rounded-full bg-emerald-500 px-0.5 shadow-inner">
            <span className="ml-auto h-3 w-3 rounded-full bg-white shadow" />
          </span>
        </div>
        <div className="mt-2.5 space-y-1.5">
          {jobs.map((r) => (
            <div
              key={r.label}
              className="flex items-center justify-between rounded-md border bg-background px-2 py-1 text-[9px]"
            >
              <span className="text-muted-foreground">{r.label}</span>
              {r.state === 'done' && <Check className="h-3 w-3 text-emerald-500" />}
              {r.state === 'running' && (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
              )}
              {r.state === 'queued' && <Clock className="h-2.5 w-2.5 text-muted-foreground" />}
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <Repeat className="h-2.5 w-2.5 text-emerald-500" />
          <span className="text-[8px] text-muted-foreground">Runs while you’re away</span>
        </div>
      </div>
    </Frame>
  );
}

// The whole fleet on one board: every agent and its live status in one place,
// so the stuck one from ProblemTabs is impossible to miss.
export function FixBoard() {
  const rows = [
    {
      name: 'Claude · auth',
      label: 'Running',
      dot: 'bg-blue-500',
      pill: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
      pulse: true,
    },
    {
      name: 'Codex · cart',
      label: 'Needs you',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
      pulse: true,
    },
    {
      name: 'OpenCode · docs',
      label: 'Done',
      dot: 'bg-emerald-500',
      pill: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
      pulse: false,
    },
  ];
  return (
    <Frame>
      <div className="w-[224px] overflow-hidden rounded-xl border bg-card shadow-md">
        <div className="flex items-center justify-between border-b bg-muted/40 px-2.5 py-1.5">
          <span className="flex items-center gap-1.5 text-[9px] font-semibold text-foreground">
            <LayoutGrid className="h-3 w-3 text-blue-500" /> Fleet
          </span>
          <span className="text-[8px] text-muted-foreground">3 active</span>
        </div>
        <div className="space-y-0.5 p-2">
          {rows.map((r) => (
            <div
              key={r.name}
              className="flex items-center justify-between rounded-md px-1.5 py-1.5"
            >
              <span className="flex items-center gap-1.5 text-[10px] text-foreground">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${r.dot} ${r.pulse ? 'animate-pulse' : ''}`}
                />
                {r.name}
              </span>
              <span className={`rounded-full px-1.5 py-0.5 text-[8px] font-medium ${r.pill}`}>
                {r.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Frame>
  );
}
