import Image from 'next/image';
import {
  ArrowUp,
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileCode,
  Folder,
  GitBranch,
  Globe,
  HardDrive,
  Laptop,
  Loader2,
  Lock,
  MousePointer2,
  Plus,
  Repeat,
  Server,
  Smartphone,
  Terminal,
  Wifi,
} from 'lucide-react';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { cn } from '@/lib/utils';

/**
 * Animated, theme-aware product mockups for the landing feature showcase
 * (components/landing/sections/feature-showcase-section.tsx). Each demo is pure
 * CSS/SVG (with the real brand logos via <AgentTypeIcon>) — no screenshots — so
 * it plays on the server-rendered page and works in light and dark. Looping
 * keyframes live in app/globals.css (`vc-*`) and freeze to a sensible static
 * frame under prefers-reduced-motion.
 *
 * Palette discipline: structure is neutral (foreground / muted / border / card).
 * Blue is the single accent (matches the app's sky "awaiting input" dot and
 * primary buttons). Red/green appear only in a git diff, where they carry meaning.
 */

function DemoShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  // Frameless: the mock sits directly on the page. Two width profiles — the
  // single-surface demos upscale more; the multi-panel `wide` demos start wider
  // (and shrink a touch on phones so they still fit a narrow viewport).
  return (
    <div className="flex w-full items-center justify-center py-4">
      <div
        className={cn(
          'origin-center',
          wide
            ? 'scale-[0.8] sm:scale-100 xl:scale-[1.25]'
            : 'scale-100 sm:scale-110 lg:scale-[1.25] xl:scale-[1.4]',
        )}
      >
        {children}
      </div>
    </div>
  );
}

/* Shared pieces -------------------------------------------------------------- */

// The bare brand mark (no chip). Mono/dark glyphs (OpenAI/Codex, Cursor, Copilot)
// are inverted on dark surfaces; the colored ones (Claude, Gemini) render as-is.
// OpenCode's mark is two-tone rather than a single solid shape, so CSS invert
// washes it out in both themes — it ships dedicated light/dark variants that we
// swap instead (same fix as how-it-works-section.tsx's AgentLogo).
// `dim` desaturates finished sessions like the real sidebar.
function AgentLogo({ name, size = 18, dim = false }: { name: string; size?: number; dim?: boolean }) {
  const lower = name.toLowerCase();
  if (lower.includes('opencode')) {
    return (
      <span className={cn('relative inline-block shrink-0', dim && 'opacity-50 grayscale')} style={{ width: size, height: size }}>
        <Image src="/images/integrations/opencode-dark.svg" alt="OpenCode" fill className="dark:hidden" />
        <Image src="/images/integrations/opencode.svg" alt="OpenCode" fill className="hidden dark:block" />
      </span>
    );
  }
  const mono = /codex|cursor|copilot/.test(lower);
  return (
    <AgentTypeIcon
      agentTypeName={name}
      size={size}
      className={cn('shrink-0', mono && 'dark:invert', dim && 'opacity-50 grayscale')}
    />
  );
}

function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('animate-spin text-muted-foreground', className)} />;
}

// Neutral window traffic-lights (no red/amber/green — keeps the palette calm).
function WinDots() {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full bg-muted-foreground/25" />
      <span className="h-2 w-2 rounded-full bg-muted-foreground/25" />
      <span className="h-2 w-2 rounded-full bg-muted-foreground/25" />
    </span>
  );
}

/* 1 — Run a whole fleet, see it at a glance (session list) -------------------- */

export function DemoFleet({ exclude = [] }: { exclude?: string[] } = {}) {
  const rows = (
    [
      { agent: 'claude', title: 'Add OAuth login flow', branch: 'feat/auth', state: 'running' },
      { agent: 'codex', title: 'Fix cart total rounding', branch: 'fix/cart', state: 'needs' },
      { agent: 'opencode', title: 'Document the REST API', branch: 'docs/api', state: 'done', time: '4m' },
      { agent: 'gemini', title: 'Migrate to Postgres 16', branch: 'chore/db', state: 'running' },
      { agent: 'claude', title: 'Refactor billing module', branch: 'refactor/billing', state: 'done', time: '1h' },
    ] as const
  ).filter((r) => !exclude.includes(r.agent));
  const running = rows.filter((r) => r.state === 'running').length;
  const needs = rows.filter((r) => r.state === 'needs').length;
  return (
    <DemoShell>
      <div className="w-[334px] overflow-hidden rounded-xl border border-border bg-card shadow-md">
        <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
          <span className="text-[11px] font-semibold text-foreground">Sessions</span>
          <span className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <Spinner className="h-2.5 w-2.5" /> {running} running
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> {needs} needs you
            </span>
          </span>
        </div>
        <div className="divide-y divide-border/60">
          {rows.map((r, i) => {
            const done = r.state === 'done';
            return (
              <div key={i} className="flex items-center gap-2.5 px-3 py-2">
                <AgentLogo name={r.agent} size={18} dim={done} />
                <div className="min-w-0 flex-1">
                  <div className={cn('truncate text-[11px]', done ? 'text-muted-foreground' : 'text-foreground')}>
                    {r.title}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
                    <GitBranch className="h-2.5 w-2.5" /> {r.branch}
                  </div>
                </div>
                {r.state === 'running' && <Spinner className="h-3.5 w-3.5 shrink-0" />}
                {r.state === 'needs' && (
                  <span className="h-2 w-2 shrink-0 rounded-full bg-sky-400" title="Awaiting input" />
                )}
                {done && <span className="shrink-0 text-[9px] text-muted-foreground">{r.time}</span>}
              </div>
            );
          })}
        </div>
      </div>
    </DemoShell>
  );
}

/* 2 — Steer any agent from any device (mobile chat + desktop sync) ------------ */

function ChatBubbles({ synced = false }: { synced?: boolean }) {
  // The conversation, shared by the phone and the mirrored desktop. `synced`
  // delays the new user turn slightly so the desktop looks like it's catching up.
  return (
    <div className="space-y-2">
      <div className="flex justify-start">
        <div className="max-w-[84%] rounded-lg rounded-tl-sm bg-muted px-2.5 py-1.5 text-[9px] leading-snug text-foreground/80">
          On it — I’ll wire up OAuth. Which providers?
        </div>
      </div>
      <div className={cn('flex justify-end', synced ? 'vc-st-sync' : 'vc-st-user')}>
        <div className="max-w-[84%] rounded-lg rounded-br-sm bg-blue-500 px-2.5 py-1.5 text-[9px] leading-snug text-white">
          Supabase + Google &amp; GitHub
        </div>
      </div>
      <div className="vc-st-reply flex justify-start">
        <div className="flex items-center gap-1 rounded-lg rounded-tl-sm bg-muted px-2.5 py-2">
          <span className="vc-dot h-1 w-1 rounded-full bg-foreground/50" style={{ animationDelay: '0s' }} />
          <span className="vc-dot h-1 w-1 rounded-full bg-foreground/50" style={{ animationDelay: '0.2s' }} />
          <span className="vc-dot h-1 w-1 rounded-full bg-foreground/50" style={{ animationDelay: '0.4s' }} />
        </div>
      </div>
    </div>
  );
}

export function DemoSteer() {
  return (
    <DemoShell wide>
      <div className="flex w-[428px] items-start justify-between">
        {/* Desktop web app — top-aligned beside the phone */}
        <div className="w-[246px] shrink-0 overflow-hidden rounded-xl border border-border bg-card shadow-xl">
          {/* browser toolbar */}
          <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-2.5 py-1.5">
            <WinDots />
            <span className="flex items-center gap-0.5 text-muted-foreground">
              <ChevronLeft className="h-3 w-3" />
              <ChevronRight className="h-3 w-3" />
            </span>
            <span className="flex flex-1 items-center gap-1 truncate rounded-md border border-border bg-background px-2 py-0.5 font-mono text-[8px] text-muted-foreground">
              <Lock className="h-2 w-2 shrink-0" /> vicoa.ai/dashboard
            </span>
          </div>
          {/* app body: session sidebar + chat */}
          <div className="flex">
            <div className="w-[46px] shrink-0 space-y-1 border-r border-border bg-muted/20 p-1.5">
              <div className="mb-1 text-[6px] font-semibold uppercase tracking-wide text-muted-foreground">
                Sessions
              </div>
              {['claude', 'codex', 'opencode'].map((a, i) => (
                <div
                  key={a}
                  className={cn('flex items-center gap-1 rounded px-1 py-0.5', i === 0 && 'bg-blue-500/10')}
                >
                  <AgentLogo name={a} size={11} />
                  <span className="h-1 w-4 rounded-full bg-foreground/15" />
                </div>
              ))}
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-center gap-1.5 border-b border-border px-2.5 py-2">
                <AgentLogo name="claude" size={13} />
                <span className="truncate text-[8px] font-medium text-foreground">Add OAuth login flow</span>
                <span className="ml-auto flex shrink-0 items-center gap-1 text-[7px] text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> synced
                </span>
              </div>
              <div className="min-h-[132px] p-2.5">
                <ChatBubbles synced />
              </div>
            </div>
          </div>
        </div>

        {/* Phone — the same session in your hand */}
        <div className="w-[168px] shrink-0">
          <div className="relative rounded-[1.65rem] bg-zinc-900 p-[2px] shadow-2xl dark:bg-zinc-800">
            <span className="absolute -left-[2px] top-24 h-9 w-[2px] rounded-l bg-zinc-700" />
            <span className="absolute -right-[2px] top-20 h-12 w-[2px] rounded-r bg-zinc-700" />

            <div className="relative overflow-hidden rounded-[1.5rem] bg-background">
              {/* Dynamic Island */}
              <div className="absolute left-1/2 top-2 z-40 flex h-4 w-14 -translate-x-1/2 items-center justify-end rounded-full bg-zinc-950 pr-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-700" />
              </div>

              {/* status bar */}
              <div className="flex items-center justify-between px-4 pb-1 pt-2.5 text-[8px] font-semibold text-foreground">
                <span>9:41</span>
                <span className="flex items-center gap-1">
                  <span className="flex items-end gap-[1px]">
                    <span className="h-1 w-[2px] rounded-sm bg-foreground/80" />
                    <span className="h-[6px] w-[2px] rounded-sm bg-foreground/80" />
                    <span className="h-2 w-[2px] rounded-sm bg-foreground/80" />
                    <span className="h-2.5 w-[2px] rounded-sm bg-foreground/30" />
                  </span>
                  <Wifi className="h-2.5 w-2.5" />
                  <span className="relative ml-0.5 flex h-2 w-3.5 items-center rounded-[3px] border border-foreground/50 px-[1px]">
                    <span className="h-1 w-2 rounded-[1px] bg-foreground/80" />
                    <span className="absolute -right-[2px] top-1/2 h-1 w-[1.5px] -translate-y-1/2 rounded-r bg-foreground/50" />
                  </span>
                </span>
              </div>

              {/* app header */}
              <div className="flex items-center gap-1.5 border-b border-border px-3 pb-2 pt-1">
                <ChevronLeft className="h-3 w-3 text-muted-foreground" />
                <AgentLogo name="claude" size={14} />
                <span className="truncate text-[9px] font-semibold text-foreground">Add OAuth login flow</span>
                <span className="ml-auto shrink-0"><Spinner className="h-2.5 w-2.5" /></span>
              </div>

              {/* messages — taller area */}
              <div className="min-h-[214px] px-2.5 py-2.5">
                <ChatBubbles />
              </div>

              {/* composer — smaller controls, like the real app */}
              <div className="mx-2 mb-2 rounded-2xl border border-border bg-card p-1.5">
                <div className="relative min-h-[13px] px-1 pb-1 text-[8px] leading-snug">
                  <span className="text-muted-foreground/70">Type messages, @files, /skills…</span>
                  <span className="vc-st-draft absolute inset-x-1 top-0 bg-card text-foreground">
                    Supabase + Google &amp; GitHub
                    <span className="vc-caret ml-px inline-block h-2.5 w-[2px] translate-y-[1px] bg-foreground/70" />
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Plus className="h-3 w-3 text-muted-foreground" />
                  <span className="ml-auto flex h-4 w-4 items-center justify-center rounded-full bg-blue-500">
                    <ArrowUp className="h-2.5 w-2.5 text-white" strokeWidth={2.5} />
                  </span>
                </div>
              </div>

              {/* home indicator */}
              <div className="mx-auto mb-1.5 h-1 w-20 rounded-full bg-foreground/25" />
            </div>
          </div>
        </div>
      </div>
    </DemoShell>
  );
}

/* 3 — Any machine, from any device (remote connection) ----------------------- */

function NodeBox({
  icon,
  label,
  tag,
  running,
  className,
}: {
  icon: React.ReactNode;
  label: string;
  tag: string;
  running?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-1.5 rounded-lg border border-border bg-card px-2 py-1.5 shadow-sm',
        className,
      )}
    >
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="truncate text-[9px] font-medium text-foreground">{label}</div>
        <div className="flex items-center gap-1 text-[7.5px] text-muted-foreground">
          {running && <span className="h-1 w-1 rounded-full bg-sky-400" />}
          {tag}
        </div>
      </div>
    </div>
  );
}

export function DemoMachines() {
  return (
    <DemoShell>
      <div className="relative h-[248px] w-[344px]">
        {/* Flowing connectors routed through the Vicoa hub */}
        <svg viewBox="0 0 344 248" className="absolute inset-0 h-full w-full text-muted-foreground/45">
          {['M110,32 L140,92', 'M110,136 L140,120', 'M234,32 L204,92', 'M234,136 L204,120', 'M172,196 L172,142'].map(
            (d) => (
              <path key={d} d={d} fill="none" stroke="currentColor" strokeWidth={1.5} className="vc-dash" />
            ),
          )}
        </svg>

        {/* Left: machines running agents */}
        <div className="absolute left-0 top-3 z-10 w-[108px]">
          <NodeBox icon={<Server className="h-3.5 w-3.5" />} label="Server" tag="runs 2 agents" running />
        </div>
        <div className="absolute left-0 top-[116px] z-10 w-[108px]">
          <NodeBox icon={<HardDrive className="h-3.5 w-3.5" />} label="Mac mini" tag="runs 1 agent" running />
        </div>

        {/* Right: control surfaces */}
        <div className="absolute right-0 top-3 z-10 w-[108px]">
          <NodeBox icon={<Smartphone className="h-3.5 w-3.5" />} label="iPhone" tag="controls" />
        </div>
        <div className="absolute right-0 top-[116px] z-10 w-[108px]">
          <NodeBox icon={<Globe className="h-3.5 w-3.5" />} label="Web" tag="controls" />
        </div>

        {/* Bottom: a laptop does both */}
        <div className="absolute bottom-0 left-1/2 z-10 w-[128px] -translate-x-1/2">
          <NodeBox icon={<Laptop className="h-3.5 w-3.5" />} label="Laptop" tag="runs 1 · controls" running />
        </div>

        {/* Center: the Vicoa relay */}
        <div className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2">
          <div className="flex flex-col items-center gap-0.5 rounded-xl border border-blue-500/40 bg-card px-3 py-2 shadow-md ring-4 ring-blue-500/10">
            <Image src="/images/vicoa-light.webp" alt="Vicoa" width={24} height={24} className="rounded-md" />
            <span className="text-[9px] font-semibold text-foreground">Vicoa</span>
            <span className="text-[7px] text-muted-foreground">secure relay</span>
          </div>
        </div>
      </div>
    </DemoShell>
  );
}

/* 4 — See and judge what each agent did (Changes / Files / Terminal tabs) ----- */

function ViewerTabs({ active }: { active: 'Changes' | 'Files' | 'Terminal' }) {
  const tabs = ['Changes', 'Files', 'Terminal'] as const;
  return (
    <div className="flex items-center gap-1 border-b border-border px-2">
      {tabs.map((t) => (
        <span
          key={t}
          className={cn(
            'border-b-2 px-2 py-1.5 text-[9px] font-medium',
            t === active ? 'border-blue-500 text-foreground' : 'border-transparent text-muted-foreground',
          )}
        >
          {t}
        </span>
      ))}
    </div>
  );
}

export function DemoDiff() {
  return (
    <DemoShell>
      <div className="w-[338px] overflow-hidden rounded-xl border border-border bg-card shadow-md">
        <div className="flex items-center gap-1.5 border-b border-border bg-muted/30 px-3 py-2">
          <WinDots />
          <span className="ml-1 text-[9px] font-medium text-foreground">Review</span>
          <span className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground">
            <GitBranch className="h-2.5 w-2.5" /> feat/auth
          </span>
        </div>
        <ViewerTabs active="Changes" />
        <div className="flex">
          <div className="w-[96px] shrink-0 space-y-0.5 border-r border-border bg-muted/20 p-1.5">
            {[
              { f: 'login.ts', add: '+18', active: true },
              { f: 'session.ts', add: '+6' },
              { f: 'oauth.ts', add: '+31' },
              { f: 'types.ts', add: '+2' },
            ].map((it) => (
              <div
                key={it.f}
                className={cn(
                  'flex items-center justify-between rounded-md px-1.5 py-1 text-[8px]',
                  it.active ? 'bg-blue-500/10 font-medium text-foreground' : 'text-muted-foreground',
                )}
              >
                <span className="truncate">{it.f}</span>
                <span className="text-emerald-600 dark:text-emerald-400">{it.add}</span>
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-1 overflow-hidden whitespace-nowrap p-2 font-mono text-[8.5px] leading-[1.5]">
            <div className="mb-1 flex items-center gap-2 text-[8px] text-muted-foreground">
              <span className="text-foreground">src/auth/login.ts</span>
              <span className="text-emerald-600 dark:text-emerald-400">+18</span>
              <span className="text-red-500">−3</span>
            </div>
            <div className="space-y-[3px]">
              <div className="text-muted-foreground/70">
                <span className="mr-2 select-none text-muted-foreground/40">17</span>
                import {'{'} signJWT {'}'} from &apos;./jwt&apos;
              </div>
              <div className="text-muted-foreground/70">
                <span className="mr-2 select-none text-muted-foreground/40">18</span>
                export async function login(user) {'{'}
              </div>
              <div className="rounded bg-red-500/10 text-red-600 dark:text-red-400">
                <span className="mr-2 select-none text-red-400/50">19</span>− const token = sign
                <span className="rounded bg-red-500/25 px-0.5">Old</span>(user)
              </div>
              <div className="rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
                <span className="mr-2 select-none text-emerald-500/50">19</span>+ const token = sign
                <span className="vc-word rounded px-0.5">JWT</span>(user,{' '}
                <span className="vc-word rounded px-0.5">opts</span>)
              </div>
              <div className="rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
                <span className="mr-2 select-none text-emerald-500/50">20</span>+ await audit(user.id,{' '}
                <span className="vc-word rounded px-0.5">&apos;login&apos;</span>)
              </div>
              <div className="text-muted-foreground/70">
                <span className="mr-2 select-none text-muted-foreground/40">21</span>
                {'  '}return {'{'} token {'}'}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 border-t border-border px-3 py-2 text-[8px] text-muted-foreground">
          <span className="text-foreground">4 files changed</span>
          <span className="text-emerald-600 dark:text-emerald-400">+57</span>
          <span className="text-red-500">−9</span>
          <span className="ml-auto flex items-center gap-1">
            <Clock className="h-2.5 w-2.5" /> 3 commits · reviewable on mobile
          </span>
        </div>
      </div>
    </DemoShell>
  );
}

/* 5 — Read the code right next to the chat (files viewer) -------------------- */

// The lines the "cursor" drags over and drops into the composer.
const SELECTED_CODE = ['// tokens expire in 30 days', 'const exp = Date.now() + TTL'];

export function DemoFiles() {
  return (
    <DemoShell wide>
      <div className="flex h-[276px] w-[430px] overflow-hidden rounded-xl border border-border bg-card shadow-md">
        {/* Left: chat + composer that receives the selected code */}
        <div className="flex w-[172px] shrink-0 flex-col border-r border-border">
          <div className="flex items-center gap-1.5 border-b border-border px-2.5 py-2">
            <AgentLogo name="claude" size={14} />
            <span className="truncate text-[8px] font-medium text-foreground">Chat</span>
          </div>
          <div className="flex-1 space-y-2 p-2.5">
            <div className="rounded-lg rounded-tl-sm bg-muted px-2.5 py-1.5 text-[8px] leading-snug text-foreground/80">
              Where should the token expiry live?
            </div>
            {/* the selected code, sent verbatim as a message (no inner bg — just the bubble) */}
            <div className="vc-fl-sent flex justify-end">
              <div className="max-w-[92%] rounded-lg rounded-br-sm bg-blue-500 px-2 py-1.5 font-mono text-[7px] leading-[1.5] text-white">
                {SELECTED_CODE.map((l) => (
                  <div key={l} className="truncate">{l}</div>
                ))}
              </div>
            </div>
          </div>
          {/* composer showing the pasted-in code */}
          <div className="m-2 rounded-xl border border-border bg-background p-2">
            <div className="relative min-h-[26px]">
              <span className="text-[8px] text-muted-foreground/70">Add a comment…</span>
              <div className="vc-fl-draft absolute inset-0 rounded bg-background">
                <div className="rounded bg-muted px-1.5 py-1 font-mono text-[7px] leading-[1.5] text-foreground">
                  {SELECTED_CODE.map((l) => (
                    <div key={l} className="truncate">{l}</div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-1 flex items-center">
              <Plus className="h-3 w-3 text-muted-foreground" />
              <span className="ml-auto flex h-4 w-4 items-center justify-center rounded-full bg-blue-500">
                <ArrowUp className="h-2.5 w-2.5 text-white" strokeWidth={2.5} />
              </span>
            </div>
          </div>
        </div>

        {/* Right: file tree + file contents with a live cursor selection */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-1 border-b border-border bg-muted/30 px-2.5 py-2 font-mono text-[8px] text-muted-foreground">
            <Folder className="h-2.5 w-2.5" /> src / auth /<span className="text-foreground">login.ts</span>
          </div>
          <div className="flex min-h-0 flex-1">
            <div className="w-[84px] shrink-0 space-y-0.5 border-r border-border p-2 text-[8px]">
              {['auth/', 'login.ts', 'jwt.ts', 'oauth.ts'].map((f, i) => (
                <div
                  key={f}
                  className={cn(
                    'flex items-center gap-1 truncate rounded px-1 py-0.5',
                    i === 1 ? 'bg-blue-500/10 text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {i === 0 ? <Folder className="h-2.5 w-2.5" /> : <FileCode className="h-2.5 w-2.5" />}
                  {f}
                </div>
              ))}
            </div>
            <div className="relative min-w-0 flex-1 overflow-hidden whitespace-nowrap p-2 font-mono text-[8px] leading-[1.8] text-muted-foreground">
              <div><span className="mr-1.5 text-muted-foreground/40">18</span>export async function login(user) {'{'}</div>
              <div><span className="mr-1.5 text-muted-foreground/40">19</span>{'  '}const token = signJWT(user)</div>
              <div className="relative">
                {/* text selection the cursor drags over lines 20-21, code only (not the gutter) */}
                <span className="vc-fl-select pointer-events-none absolute left-[15px] top-0 h-[28px] w-[150px] rounded-sm bg-blue-500/25 ring-1 ring-blue-500/40" />
                <div className="relative text-foreground/90"><span className="mr-1.5 text-muted-foreground/40">20</span>{'  '}// tokens expire in 30 days</div>
                <div className="relative text-foreground/90"><span className="mr-1.5 text-muted-foreground/40">21</span>{'  '}const exp = Date.now() + TTL</div>
                <MousePointer2 className="vc-fl-select absolute left-[152px] top-[19px] h-3 w-3 fill-background text-foreground drop-shadow" />
              </div>
              <div><span className="mr-1.5 text-muted-foreground/40">22</span>{'  '}return {'{'} token, exp {'}'}</div>
              <div><span className="mr-1.5 text-muted-foreground/40">23</span>{'}'}</div>
            </div>
          </div>
        </div>
      </div>
    </DemoShell>
  );
}

/* 6 — A real terminal, beside the agent (chat left, terminal right) ----------- */

export function DemoTerminal() {
  return (
    <DemoShell wide>
      <div className="flex h-[276px] w-[430px] overflow-hidden rounded-xl border border-border bg-card shadow-md">
        {/* Chat on the left */}
        <div className="flex w-[180px] shrink-0 flex-col border-r border-border">
          <div className="flex items-center gap-1.5 border-b border-border px-2.5 py-2">
            <AgentLogo name="codex" size={14} />
            <span className="truncate text-[8px] font-medium text-foreground">Codex · fix/cart</span>
          </div>
          <div className="flex-1 space-y-2 p-2.5">
            <div className="rounded-lg rounded-tl-sm bg-muted px-2.5 py-1.5 text-[8px] leading-snug text-foreground/80">
              Run the cart tests and fix the rounding bug.
            </div>
            <div className="flex justify-end">
              <div className="max-w-[90%] rounded-lg rounded-br-sm bg-blue-500 px-2.5 py-1.5 text-[8px] leading-snug text-white">
                Ran the suite — 2 files green, patching totals now.
              </div>
            </div>
            <div className="flex items-center gap-1 text-[8px] text-muted-foreground">
              <Spinner className="h-2.5 w-2.5" /> editing cart/total.ts
            </div>
          </div>
        </div>

        {/* Terminal on the right — a genuinely dark terminal surface */}
        <div className="flex min-w-0 flex-1 flex-col bg-zinc-950">
          <div className="flex items-center gap-1.5 border-b border-white/10 px-2.5 py-2">
            <span className="h-2 w-2 rounded-full bg-white/20" />
            <span className="h-2 w-2 rounded-full bg-white/20" />
            <span className="h-2 w-2 rounded-full bg-white/20" />
            <span className="ml-1 flex items-center gap-1 font-mono text-[8px] text-zinc-400">
              <Terminal className="h-2.5 w-2.5" /> zsh — fix/cart
            </span>
          </div>
          <div className="flex-1 space-y-[3px] p-2.5 font-mono text-[8px] leading-[1.7]">
            <div className="text-zinc-300"><span className="text-blue-400">➜</span> <span className="text-cyan-400">cart</span> pnpm test</div>
            <div className="text-zinc-500">RUN v2.1.4 · 42 files</div>
            <div className="text-emerald-400">✓ auth/login.spec.ts (12)</div>
            <div className="text-emerald-400">✓ cart/total.spec.ts (8)</div>
            <div className="text-zinc-500">Test Files 2 passed · Duration 1.4s</div>
            <div className="flex items-center gap-1 text-zinc-400">
              <Loader2 className="h-2.5 w-2.5 animate-spin text-zinc-500" /> db/migrate.spec.ts
            </div>
            <div className="pt-1 text-zinc-300"><span className="text-blue-400">➜</span> <span className="text-cyan-400">cart</span> pnpm dev
              <span className="vc-caret ml-0.5 inline-block h-2.5 w-[4px] translate-y-[1px] bg-zinc-300" />
            </div>
          </div>
        </div>
      </div>
    </DemoShell>
  );
}

/* 7 — Plan on a board, start a session from a task (Todo / In Progress / Done)  */

function PriorityBars({ n }: { n: number }) {
  return (
    <span className="flex items-end gap-[2px]">
      {[0, 1, 2].map((b) => (
        <span
          key={b}
          className={cn('w-[2px] rounded-sm', b < n ? 'bg-muted-foreground/70' : 'bg-muted-foreground/20')}
          style={{ height: `${4 + b * 2}px` }}
        />
      ))}
    </span>
  );
}

function BoardCard({
  title,
  bars,
  labels,
  children,
  active,
}: {
  title: string;
  bars: number;
  labels?: string[];
  children?: React.ReactNode;
  active?: boolean;
}) {
  return (
    <div
      className={cn(
        'rounded-md border bg-card p-2 shadow-xs',
        active ? 'border-blue-500/40 ring-1 ring-blue-500/10' : 'border-border/70',
      )}
    >
      <div className="flex items-start gap-1.5">
        <span className="mt-[3px] shrink-0"><PriorityBars n={bars} /></span>
        <span className="text-[9px] leading-snug text-foreground">{title}</span>
      </div>
      {labels && (
        <div className="mt-1 flex flex-wrap gap-1">
          {labels.map((l) => (
            <span key={l} className="rounded bg-muted px-1 py-0.5 text-[7px] text-muted-foreground">
              {l}
            </span>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}

function TaskColumn({
  name,
  count,
  marker,
  children,
}: {
  name: string;
  count: number;
  marker: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="w-[132px] rounded-lg bg-muted/40 p-2">
      <div className="mb-2 flex items-center gap-1.5 px-0.5 text-[8px] font-medium text-muted-foreground">
        {marker} {name}
        <span className="ml-auto">{count}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

export function DemoTasks() {
  return (
    <DemoShell wide>
      <div className="relative w-[438px] rounded-xl border border-border bg-card p-2.5 shadow-md">
        <div className="mb-2.5 flex items-center justify-between px-0.5">
          <span className="text-[10px] font-semibold text-foreground">Tasks</span>
          <span className="text-[8px] text-muted-foreground">Board</span>
        </div>
        <div className="flex gap-2.5">
          <TaskColumn
            name="Todo"
            count={2}
            marker={<span className="h-2 w-2 rounded-full border border-muted-foreground/50" />}
          >
            <BoardCard title="Add OAuth login flow" bars={3} labels={['auth', 'backend']} />
            <BoardCard title="Rate-limit the public API" bars={2} labels={['security']} />
          </TaskColumn>

          <TaskColumn
            name="In Progress"
            count={2}
            marker={
              <span className="flex h-2 w-2 items-center justify-center rounded-full border border-blue-500">
                <span className="h-1 w-1 rounded-full bg-blue-500" />
              </span>
            }
          >
            <BoardCard title="Fix cart total rounding" bars={3} active>
              <div className="mt-1.5 flex items-center gap-1.5 border-t border-border/60 pt-1.5">
                <AgentLogo name="claude" size={12} />
                <span className="text-[8px] text-muted-foreground">Claude</span>
                <span className="ml-auto flex items-center gap-1 text-[8px] text-muted-foreground">
                  <Spinner className="h-2.5 w-2.5" /> running
                </span>
              </div>
            </BoardCard>
            <BoardCard title="Migrate to Postgres 16" bars={1} labels={['infra']} />
          </TaskColumn>

          <TaskColumn
            name="Done"
            count={3}
            marker={
              <span className="flex h-2 w-2 items-center justify-center rounded-full bg-blue-500">
                <Check className="h-1.5 w-1.5 text-white" strokeWidth={3} />
              </span>
            }
          >
            <BoardCard title="Document the REST API" bars={1} labels={['docs']} />
            <BoardCard title="Set up CI pipeline" bars={2} labels={['ci']} />
            <BoardCard title="Add health-check route" bars={1} />
          </TaskColumn>
        </div>

        {/* right-click context menu → Start a session (Edit + Start only) */}
        <div className="vc-tk-menu absolute left-[74px] top-[74px] z-20 w-[118px] overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-xl">
          <div className="px-2.5 py-1.5 text-[8.5px] text-foreground">Edit</div>
          <div className="bg-blue-500/10 px-2.5 py-1.5 text-[8.5px] font-medium text-foreground">Start a session</div>
        </div>
      </div>
    </DemoShell>
  );
}

/* 8 — Put the fleet on a schedule (automations, neutral palette) -------------- */

export function DemoAutomations() {
  const jobs = [
    { label: 'Run tests → open PR', state: 'done' as const },
    { label: 'Sync dependencies', state: 'running' as const },
    { label: 'Nightly refactor sweep', state: 'queued' as const },
  ];
  return (
    <DemoShell>
      <div className="w-[300px] overflow-hidden rounded-xl border border-border bg-card p-3 shadow-md">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            Automation
          </span>
          {/* neutral "on" toggle */}
          <span className="flex h-4 w-7 items-center rounded-full bg-blue-500/80 px-0.5 shadow-inner">
            <span className="ml-auto h-3 w-3 rounded-full bg-white shadow" />
          </span>
        </div>
        <div className="mt-1 text-[9px] text-muted-foreground">Every weekday · 9:00 AM</div>

        <div className="mt-3 space-y-1.5">
          {jobs.map((r) => (
            <div key={r.label} className="rounded-lg border border-border bg-background px-2 py-1.5">
              <div className="flex items-center justify-between text-[9px]">
                <span className="text-foreground/90">{r.label}</span>
                {r.state === 'done' && (
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Check className="h-3 w-3" /> done
                  </span>
                )}
                {r.state === 'running' && (
                  <span className="flex items-center gap-1 text-foreground">
                    <Spinner className="h-2.5 w-2.5" /> running
                  </span>
                )}
                {r.state === 'queued' && (
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Clock className="h-2.5 w-2.5" /> queued
                  </span>
                )}
              </div>
              {r.state === 'running' && (
                <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
                  <div className="vc-run h-full w-1/3 rounded-full bg-gradient-to-r from-transparent via-foreground/40 to-transparent" />
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-3 flex items-center gap-1.5 border-t border-border pt-2 text-[8px] text-muted-foreground">
          <Repeat className="h-2.5 w-2.5" />
          Runs on its own — even when you don’t kick it off
        </div>
      </div>
    </DemoShell>
  );
}
