'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { ReportIssueDialog } from '@/components/dashboard/report-issue-dialog';
import useSWR from 'swr';
import type { AuthUser } from '@/lib/auth/user';
import Image from 'next/image';
import Link from 'next/link';
import { ChevronDown, Download, MessageCircleMore, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Terminal } from '@/components/terminal';

type OsTab = 'mac-linux' | 'windows';
type AgentId = 'claude' | 'codex' | 'opencode';

interface StepCardProps {
  step: number;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

function StepCard({ step, title, subtitle, children }: StepCardProps) {
  return (
    <Card className="group relative overflow-hidden border border-border/60 bg-gradient-to-br from-card/90 to-card/50 p-5 shadow-md backdrop-blur hover:shadow-lg hover:border-border transition-all duration-300">
      <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      <div className="relative flex items-start gap-4">
        <div className="h-7 w-7 shrink-0 rounded-lg text-primary flex items-center justify-center text-sm ring-1 ring-primary/30">
          {step}
        </div>
        <div className="flex-1 space-y-3">
          <h2 className="text-base font-normal">
            {title}
            {subtitle && <span className="ml-2 text-muted-foreground/50 font-normal">({subtitle})</span>}
          </h2>
          {children}
        </div>
      </div>
    </Card>
  );
}

const agents: {
  id: AgentId;
  label: string;
  description: string;
  installMac: string;
  installWindows: string | null;
}[] = [
  {
    id: 'claude',
    label: 'Claude Code',
    description: "",
    installMac: 'curl -fsSL https://claude.ai/install.sh | bash',
    installWindows: 'winget install Anthropic.Claude',
  },
  {
    id: 'codex',
    label: 'Codex',
    description: "",
    installMac: 'npm i -g @openai/codex',
    installWindows: null,
  },
  {
    id: 'opencode',
    label: 'OpenCode',
    description: '',
    installMac: 'npm i -g opencode-ai',
    installWindows: 'npm i -g opencode-ai',
  },
];

function AgentStep({ osTab }: { osTab: OsTab }) {
  const [selected, setSelected] = useState<AgentId>('claude');
  const agent = agents.find((a) => a.id === selected)!;
  const installCmd = osTab === 'windows' ? agent.installWindows : agent.installMac;
  const windowsUnavailable = osTab === 'windows' && installCmd === null;

  const windowsPrereqs = osTab === 'windows' ? ['winget install OpenJS.NodeJS'] : [];

  return (
    <div className="space-y-3">
      {/* Underline tabs */}
      <div className="flex border-b border-border/60">
        {agents.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setSelected(a.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              selected === a.id
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{agent.description}</p>
      {windowsPrereqs.length > 0 && (
        <Terminal
          commands={windowsPrereqs}
          className="max-w-none w-full -ml-2"
        />
      )}
      {windowsUnavailable ? (
        <p className="text-xs text-muted-foreground italic">Not needed on Windows.</p>
      ) : (
        <Terminal
          commands={[installCmd!]}
          className="max-w-none w-full -ml-2"
        />
      )}
    </div>
  );
}

function DesktopAppStep() {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Everything stays in sync across mobile, web, and desktop. Just download and start using.
      </p>
      <Link
        href="/download"
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 transition-colors"
      >
        <Download className="h-4 w-4" />
        Download Now
      </Link>
    </div>
  );
}

function MobileAppDownload() {
  return (
    <div className="flex items-center gap-8">
      {/* Left: store badges */}
      <div className="flex flex-col gap-6">
        <Link
          href="http://apps.apple.com/sg/app/id6751626168"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Image
            src="/images/appstore.webp"
            alt="Download on the App Store"
            width={140}
            height={42}
            className="hover:opacity-80 transition-opacity"
          />
        </Link>
        <Link
          href="https://play.google.com/store/apps/details?id=app.vicoa"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Image
            src="/images/android-google-play.webp"
            alt="Get it on Google Play"
            width={140}
            height={42}
            className="hover:opacity-80 transition-opacity"
          />
        </Link>
      </div>

      {/* Right: QR code */}
      <a
        href="https://vicoa.app.link/download"
        target="_blank"
        rel="noopener noreferrer"
        className="group/qr relative bg-gradient-to-br from-muted/80 to-muted/40 p-3 rounded-lg border border-border/60 inline-flex hover:border-primary/40 hover:shadow-md transition-all duration-300"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 group-hover/qr:opacity-100 rounded-lg transition-opacity duration-300" />
        <Image
          src="/images/vicoa-app-qrcode.png"
          alt="QR Code to download Vicoa app"
          width={110}
          height={110}
          className="relative z-10"
        />
      </a>
    </div>
  );
}

const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error('Failed to fetch');
  }
  return res.json();
});

// Same compile-time desktop signal as middleware.ts / dashboard-layout.tsx.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

/**
 * Desktop home: the CLI/mobile onboarding steps above make no sense inside
 * the desktop app (the daemon is already running), and desktop-local has no
 * Supabase session for the SWR fetches. Point at the sidebar / New Session
 * instead — sensible with zero instances too.
 */
function DesktopDashboardHome() {
  return (
    <section className="flex-1 h-full flex items-center justify-center font-mono">
      <div className="flex flex-col items-center text-center px-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted-foreground/10 text-muted-foreground">
          <MessageCircleMore className="h-7 w-7" strokeWidth={1.75} />
        </div>
        <p className="mt-4 text-base font-medium text-foreground">Start a coding session</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Pick a session from the sidebar, or start a new one.
        </p>
        <Link
          href="/dashboard/agents/new-session"
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-4 py-2 text-sm text-foreground hover:bg-muted/60 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Session
        </Link>
      </div>
    </section>
  );
}

export default function DashboardPage() {
  if (IS_DESKTOP) return <DesktopDashboardHome />;
  return <WebDashboardPage />;
}

function WebDashboardPage() {
  const [osTab, setOsTab] = useState<OsTab>('mac-linux');
  const [reportIssueOpen, setReportIssueOpen] = useState(false);
  const [showCli, setShowCli] = useState(false);
  // WebDashboardPage only renders when !IS_DESKTOP, but keep the keys null on
  // desktop defensively so these never 401 in local mode.
  const { data: supabaseUser } = useSWR<AuthUser>(IS_DESKTOP ? null : '/api/supabase-user', fetcher);
  const userEmail = supabaseUser?.email || undefined;

  return (
    <section className="flex-1 bg-gradient-to-b from-background via-background to-muted/20">
      <div className="mx-auto w-full max-w-3xl px-4 py-8 lg:px-8 lg:py-10">
        {/* Hero */}
        <div className="text-center mb-8">
          {/* <div className="flex justify-center mb-5">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 blur-2xl rounded-full" />
              <Image
                src="/images/vicoa-light.webp"
                alt="Vibe Code Anywhere (Vicoa) Logo"
                width={0}
                height={0}
                sizes="100vw"
                className="h-14 w-auto relative z-10"
              />
            </div>
          </div> */}
          <h1 className="text-xl lg:text-2xl mb-4 font-mono tracking-tight">
            Connect to Vicoa App
          </h1>
          <p className="text-base text-muted-foreground/80 mx-auto">
            Bridge your mobile app with coding agents on your computer.
          </p>
          <p className="mt-6 text-xs text-muted-foreground/50">
            Having trouble?{' '}
            <button
              type="button"
              onClick={() => setReportIssueOpen(true)}
              className="underline underline-offset-2 hover:text-muted-foreground transition-colors"
            >
              Report an issue
            </button>
            {' '}or read the{' '}
            <Link
              href="/docs/getting-started"
              className="underline underline-offset-2 hover:text-muted-foreground transition-colors"
            >
              Getting Started doc
            </Link>
          </p>
        </div>

        {/* OS Tabs */}
        <div className="max-w-xl mx-auto mb-6">
          <div className="flex rounded-lg border border-border/60 bg-muted/30 p-1 gap-1">
            {(['mac-linux', 'windows'] as OsTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setOsTab(tab)}
                className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-all ${
                  osTab === tab
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab === 'mac-linux' ? 'macOS / Linux' : 'Windows'}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-5 max-w-xl mx-auto">
          <StepCard step={1} title="Download the desktop app">
            <DesktopAppStep />
          </StepCard>

          <StepCard step={2} title="Install a coding agent" subtitle="if needed">
            <AgentStep osTab={osTab} />
          </StepCard>

          <StepCard step={3} title="Start a coding session">
            <p className="text-sm text-foreground">
              Open the Vicoa desktop app and click <strong>+ New Session</strong> in the left
              sidebar.
            </p>
            <p className="text-xs text-muted-foreground/60">
              Your session shows up here and on your phone.{' '}
              <Link
                href="/docs/agents/index"
                className="cursor-pointer text-muted-foreground/60 hover:text-muted-foreground underline underline-offset-2 transition-colors"
              >
                Learn more
              </Link>
            </p>
          </StepCard>

          <StepCard step={4} title="Get the mobile app">
            <MobileAppDownload />
            <p className="text-xs text-muted-foreground/60">
              Log in with the same account and you should see your coding sessions there.
            </p>
          </StepCard>
        </div>

        {/* Secondary path: the CLI, for servers / headless boxes and Linux. */}
        <div className="max-w-xl mx-auto mt-6">
          <button
            type="button"
            onClick={() => setShowCli((v) => !v)}
            className="flex w-full items-center justify-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
          >
            Prefer the terminal? Set up with the CLI instead
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform', showCli && 'rotate-180')}
            />
          </button>

          {showCli && (
            <div className="mt-4 space-y-5">
              <StepCard step={1} title="Install the Vicoa CLI">
                <Terminal commands={['npm i -g @vicoa/cli']} className="max-w-none w-full -ml-2" />
                <p className="text-xs text-muted-foreground/60">Requires Node.js 18+.</p>
              </StepCard>

              <StepCard step={2} title="Start a coding session">
                <Terminal
                  commands={[osTab === 'windows' ? 'vicoa daemon' : 'vicoa']}
                  className="max-w-none w-full -ml-2"
                />
                {osTab === 'windows' ? (
                  <p className="text-sm text-foreground">
                    Then click <strong>+ New Session</strong> in the left sidebar to start a
                    session.{' '}
                    <Link
                      href="/docs/start-remote-session"
                      className="cursor-pointer text-muted-foreground/60 hover:text-muted-foreground underline underline-offset-2 transition-colors"
                    >
                      Learn more
                    </Link>
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground/60">
                    A coding session will appear in the left sidebar.{' '}
                    <Link
                      href="/docs/agents/index"
                      className="cursor-pointer text-muted-foreground/60 hover:text-muted-foreground underline underline-offset-2 transition-colors"
                    >
                      Learn more
                    </Link>
                  </p>
                )}
              </StepCard>
            </div>
          )}
        </div>
      </div>

      <ReportIssueDialog
        open={reportIssueOpen}
        onOpenChange={setReportIssueOpen}
        userEmail={userEmail}
      />
    </section>
  );
}
