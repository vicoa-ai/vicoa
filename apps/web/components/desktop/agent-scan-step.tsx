'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AgentInstallChoices, AgentInstallSteps } from '@/components/dashboard/agent-install';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { AGENT_CATALOG_FALLBACK } from '@/lib/agent-catalog';
import { getBackendAPI, type MachineSummary } from '@/lib/backend-api';
import {
  buildScannedAgents,
  fetchLocalHealth,
  isFinalStuckReason,
  machineSupportsAgentScan,
  probeThisMachine,
  readAvailableAgents,
  rpcScanAgents,
  type ScanStuckReason,
  type ScannedAgent,
} from '@/lib/desktop-agent-scan';
import { restartDesktopDaemon } from '@/lib/desktop-daemon';
import { getDesktopConfig } from '@/lib/runtime-config';
import { installInfoFor, installOsForPlatform, type InstallOs } from '@/lib/desktop-agent-install';
import {
  trackScanCompleted,
  trackScanRescanned,
  trackScanViewed,
} from '@/lib/desktop-telemetry';
import { cn } from '@/lib/utils';

/**
 * "Which coding agents are on this machine?" — the step that proves Vicoa
 * actually works here before we ask for anything.
 *
 * The daemon probes once at registration and posts the result to the cloud
 * machine row, so the first read is free. Refresh re-probes over RPC (only on an
 * explicit press — it is not cheap) and is hidden entirely unless the daemon
 * advertises the capability, because an older one answers `no_handler`.
 *
 * Vicoa never installs an agent: missing rows expand to a copy-able command and
 * a docs link. Skip is live in every phase — no onboarding step may trap a user.
 */

/** How long to wait for the machine to appear before declaring the scan empty. */
const EMPTY_TIMEOUT_MS = 5000;
/**
 * How long "Starting up…" may spin before the step says what is wrong and
 * offers Try again. Of the desktop users whose machine showed up after the
 * 5s mark (Aug to Nov 2026), 9 in 10 had it within 18s on Windows and 13s on
 * Mac, and about 1 in 30 took longer than 30s. Those few see the message
 * briefly; the poll keeps running, so it still turns into the agent list.
 */
const STUCK_TIMEOUT_MS = 30_000;
/** Poll cadence while waiting for the daemon to finish cloud registration. */
const POLL_INTERVAL_MS = 2000;

type Phase = 'scanning' | 'found' | 'empty' | 'stuck';

/**
 * Copy for a step that has stopped waiting. Each one says what is going on
 * and what the user can do; skipping is always on screen next to it.
 */
function stuckHeading(reason: ScanStuckReason): { title: string; body: string } {
  switch (reason) {
    case 'machine_limit':
      return {
        title: 'Upgrade to connect this computer',
        body: 'Your plan has no room for another computer, so Vicoa can\'t check which AI agents are on this one. Free up a machine in Settings → Machines, or upgrade to connect this one.',
      };
    case 'auth_failed':
      return {
        title: 'Sign in again to connect this computer',
        body: 'Vicoa couldn\'t confirm your sign-in on this computer. Try again. If it keeps happening, skip this step, then sign out and sign back in.',
      };
    case 'not_desktop':
      return {
        title: 'Open Vicoa on your computer',
        body: 'This step checks which AI agents are installed on the computer running the Vicoa desktop app, so it only works in the app.',
      };
    case 'not_connected':
      return {
        title: 'Vicoa can\'t connect this computer yet',
        body: 'Vicoa is running but hasn\'t connected this computer to your account. Check your internet connection and try again, or skip this step and check later in Settings → Providers.',
      };
    case 'not_started':
      return {
        title: 'Vicoa didn\'t finish starting',
        body: 'Its background service isn\'t running, so Vicoa can\'t check which AI agents are on this computer. Try again, or skip this step and check later in Settings → Providers.',
      };
  }
}

/**
 * Copy for each state.
 *
 * The load-bearing idea, repeated in every variant: **Vicoa has no AI of its
 * own — it runs coding agents that already live on your Mac.** Without that, a
 * list of eight half-greyed product names is meaningless, and a user with two
 * of them reasonably assumes they're missing six.
 *
 * "AI agent" is the product's own word for these (the sign-in screen sells
 * "Run a team of coding agents"), so it's what we use here too — anchored to
 * named products like Claude Code so it never floats as abstract jargon. Say
 * plainly that one is enough, and never imply the list is a checklist.
 */
export function headingFor(
  phase: Phase,
  installedCount: number,
  canRefresh: boolean,
  stuckReason: ScanStuckReason = 'not_started'
): { title: string; body: string } {
  if (phase === 'stuck') return stuckHeading(stuckReason);

  if (phase === 'scanning') {
    return {
      title: 'Searching for AI Agents',
      body: 'Vicoa runs with AI agents you already have, like Claude Code, Codex, OpenCode, and more. Looking for yours now.',
    };
  }

  if (phase === 'empty') {
    // Never "couldn't reach this computer": the user is sitting at it, and the
    // daemon simply hasn't finished booting.
    return {
      title: 'Getting things ready',
      body: 'Vicoa is still starting up in the background. This usually takes a few seconds.',
    };
  }

  if (installedCount === 0) {
    return {
      title: 'Install an AI agent to get started',
      // Only name Refresh when that button actually renders — it's gated on the
      // daemon advertising the RPC, so an older one shows no such button and
      // this text would be pointing at nothing.
      body: canRefresh
        ? 'Vicoa runs the AI agents installed on your computer, like Claude Code or Codex. Pick the one that matches a plan you already have, install it, then click Refresh.'
        : 'Vicoa runs the AI agents installed on your computer, like Claude Code or Codex. Pick the one that matches a plan you already have, install it, then restart Vicoa.',
    };
  }

  return {
    title: "You're ready to go",
    body:
      installedCount === 1
        ? 'Vicoa will run with this agent on your computer, so you can start a session here and pick it up on your phone.'
        : 'Vicoa will run with these agents on your computer, so you can start a session here and pick it up on your phone.',
  };
}

function AgentRow({ agent, isFirst, os }: { agent: ScannedAgent; isFirst: boolean; os: InstallOs }) {
  const [expanded, setExpanded] = useState(false);
  const info = installInfoFor(agent.id);

  return (
    <div className={cn(!isFirst && 'border-t border-border/50')}>
      <button
        type="button"
        disabled={agent.installed}
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
          !agent.installed && 'cursor-pointer hover:bg-foreground/[0.02]'
        )}
      >
        <AgentTypeIcon agentTypeName={agent.id} size={18} whiteForOpenAI />
        <span
          className={cn(
            'min-w-0 flex-1 truncate text-[13px]',
            agent.installed ? 'text-foreground' : 'text-muted-foreground'
          )}
        >
          {agent.label}
        </span>

        {agent.installed ? (
          <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
            Ready
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground/70">
            <span className="h-1.5 w-1.5 rounded-full bg-border" />
            Not installed
            {info && (
              <ChevronDown
                className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')}
              />
            )}
          </span>
        )}
      </button>

      {expanded && info && (
        <div className="px-4 pb-3.5">
          <AgentInstallSteps agentId={agent.id} os={os} />
        </div>
      )}
    </div>
  );
}

function SkeletonRow({ isFirst }: { isFirst: boolean }) {
  return (
    <div className={cn('flex items-center gap-3 px-4 py-3', !isFirst && 'border-t border-border/50')}>
      <div className="h-[18px] w-[18px] shrink-0 animate-pulse rounded bg-foreground/10" />
      <div className="h-3 w-32 animate-pulse rounded bg-foreground/10" />
    </div>
  );
}

export function AgentScanStep({
  onContinue,
}: {
  onContinue: (skipped: boolean, installedCount: number) => void;
}) {
  const [machine, setMachine] = useState<MachineSummary | null>(null);
  const [agents, setAgents] = useState<ScannedAgent[] | null>(null);
  const [hasTimedOut, setHasTimedOut] = useState(false);
  const [waitedTooLong, setWaitedTooLong] = useState(false);
  /** What the latest look found instead of this machine; null once it's found. */
  const [wait, setWait] = useState<{ reason: ScanStuckReason; detail: string } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Bumped on refresh to restart the empty-timeout, so a re-probe shows the
  // scanning skeleton again instead of flashing the empty state.
  const [scanEpoch, setScanEpoch] = useState(0);
  /** The open row in the "pick by plan" list shown when nothing is installed;
   *  none until the user picks one. */
  const [choiceId, setChoiceId] = useState<string | null>(null);
  /** (epoch:phase) pairs already reported, so a re-render can't double-fire. */
  const reportedPhases = useRef<Set<string>>(new Set());

  const installedCount = agents?.filter((a) => a.installed).length ?? 0;
  const phase: Phase = agents
    ? 'found'
    : wait && (waitedTooLong || isFinalStuckReason(wait.reason))
      ? 'stuck'
      : hasTimedOut
        ? 'empty'
        : 'scanning';

  useEffect(() => {
    trackScanViewed();
  }, []);

  // Report the scan's outcome as it settles, once per (epoch, phase).
  //
  // Reporting the 'empty' timeout is the point of the `phase` property: without
  // it a machine that never resolves fires nothing at all, so "saw the scan and
  // it never finished" is indistinguishable from "finished with zero agents" —
  // and those are completely different problems (a broken install vs. a user
  // who needs to install an agent).
  //
  // The poll deliberately does not stop at the timeout, so a slow daemon
  // reports 'empty' and later 'found'. Both are true; 'found' is the
  // authoritative outcome.
  useEffect(() => {
    if (phase === 'scanning') return;
    const key = `${scanEpoch}:${phase}`;
    if (reportedPhases.current.has(key)) return;
    reportedPhases.current.add(key);
    trackScanCompleted(agents, phase, phase === 'stuck' ? wait?.reason : undefined);
  }, [phase, agents, scanEpoch, wait]);

  // Poll until the machine appears. The daemon restarts right after sign-in
  // (setApiKey → restart → reload), so the renderer can easily beat its cloud
  // registration to the punch. Stops the moment it resolves.
  //
  // `stopped` is scoped to this effect run rather than a ref: a ref set true on
  // teardown is never reset, so a remount (StrictMode does exactly this in dev)
  // would leave polling permanently dead.
  useEffect(() => {
    if (machine) return;
    let stopped = false;
    let timer: number | undefined;

    const onDesktop = getDesktopConfig() !== null;

    const tick = async () => {
      const probe = await probeThisMachine({
        onDesktop,
        fetchHealth: fetchLocalHealth,
        listMachines: () => getBackendAPI(true).listMachines(),
      });
      if (stopped) return;
      if (probe.kind === 'found') {
        setWait(null);
        setMachine(probe.machine);
        const scanned = buildScannedAgents(
          AGENT_CATALOG_FALLBACK.agents,
          readAvailableAgents(probe.machine)
        );
        setAgents(scanned);
        // The scan_completed capture lives in the phase effect above, not here
        // — this branch only sees the 'found' half of the outcome.
        return;
      }
      setWait((prev) =>
        prev?.reason === probe.reason && prev.detail === probe.detail
          ? prev
          : { reason: probe.reason, detail: probe.detail }
      );
      // A browser has no daemon that might still come up, so one look is the
      // whole answer.
      if (probe.reason === 'not_desktop') return;
      timer = window.setTimeout(tick, POLL_INTERVAL_MS);
    };

    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [machine, scanEpoch]);

  useEffect(() => {
    if (machine) return;
    setHasTimedOut(false);
    setWaitedTooLong(false);
    const empty = window.setTimeout(() => setHasTimedOut(true), EMPTY_TIMEOUT_MS);
    const stuck = window.setTimeout(() => setWaitedTooLong(true), STUCK_TIMEOUT_MS);
    return () => {
      window.clearTimeout(empty);
      window.clearTimeout(stuck);
    };
  }, [machine, scanEpoch]);

  // Try again: restart the daemon and wait from the top. Restarting is what a
  // retry can actually change here; the poll was already looking the whole
  // time. Off desktop the restart is a no-op, but this button isn't shown there.
  const retry = useCallback(() => {
    setWait(null);
    setScanEpoch((n) => n + 1);
    void restartDesktopDaemon();
  }, []);

  const refresh = useCallback(async () => {
    if (!machine || refreshing) return;
    setRefreshing(true);
    // Count at press time — the state the user was looking at when they decided
    // to press ("I had none, I installed one, let me re-check"). Whether it
    // worked is answered by installed_count on desktop_onboarding_completed.
    trackScanRescanned(installedCount);
    try {
      const fresh = await rpcScanAgents(machine.machine_id);
      setAgents(buildScannedAgents(AGENT_CATALOG_FALLBACK.agents, fresh));
    } catch {
      // Daemon down or mid-restart. Fall back to re-reading the cloud row:
      // worst case it's the same answer and the user can press again.
      setMachine(null);
      setAgents(null);
      setScanEpoch((n) => n + 1);
    } finally {
      setRefreshing(false);
    }
  }, [machine, refreshing, installedCount]);

  const canRefresh = machineSupportsAgentScan(machine);
  const heading = headingFor(phase, installedCount, canRefresh, wait?.reason);
  const os = installOsForPlatform(machine?.platform);

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-xl flex-1 flex-col justify-center gap-5 px-6 py-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-foreground">{heading.title}</h1>
        <p className="text-sm leading-relaxed text-muted-foreground">{heading.body}</p>
      </div>

      {phase === 'found' && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {/* Deliberately NOT "2 of 8 installed" — that frames the list as a
              checklist to finish, when one tool is genuinely enough. */}
          <span>
            {installedCount > 0
              ? `${installedCount} ready to use`
              : 'None found on this computer yet'}
          </span>
          {canRefresh && (
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground disabled:opacity-60"
            >
              <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
        </div>
      )}

      {/* All 10 agents can't fit the 560px minimum window height, so the list
          scrolls while the action button stays put. `min-h-0` lets this box
          shrink before anything else does — without it the list holds its
          height and pushes the button off the bottom of the window. The fade
          keeps a part-scrolled row reading as "more below" rather than as a
          clipped, broken card. */}
      {phase === 'found' && installedCount === 0 && agents ? (
        // Nothing installed: lead with the plan each agent runs on rather than
        // a list of ten names. Scrolls on its own for the same 560px reason.
        <div className="custom-scrollbar -mx-1 min-h-0 overflow-y-auto px-1">
          <AgentInstallChoices agents={agents} os={os} selectedId={choiceId} onSelect={setChoiceId} />
        </div>
      ) : phase === 'stuck' ? (
        // The server's own sentence (which limit, how many machines), quoted
        // as is. The heading already says what to do, so nothing else goes here.
        wait?.detail ? <p className="text-sm text-foreground/90">{wait.detail}</p> : null
      ) : (
      <div className="relative flex min-h-0 flex-col">
        <div className="custom-scrollbar max-h-[45vh] flex-1 overflow-y-auto rounded-xl border border-border/60 bg-foreground/[0.03]">
          {phase === 'scanning' &&
            Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} isFirst={i === 0} />)}

          {phase === 'empty' && (
            <div className="flex items-center gap-2.5 px-4 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Starting up…
            </div>
          )}

          {phase === 'found' &&
            agents?.map((agent, i) => <AgentRow key={agent.id} agent={agent} isFirst={i === 0} os={os} />)}
        </div>
        <div className="pointer-events-none absolute inset-x-px bottom-px h-6 rounded-b-xl bg-gradient-to-t from-background to-transparent" />
      </div>
      )}

      {/* One button, not two. A "Skip" beside "Continue" did the identical
          thing when nothing was found, and meant nothing once something was —
          so the label carries the situation instead. It always advances, so
          this step can never trap anyone. */}
      <div className="flex items-center justify-end gap-3">
        {phase === 'stuck' && wait?.reason !== 'not_desktop' && (
          <Button variant="outline" onClick={retry}>
            <RefreshCw className="h-3.5 w-3.5" />
            Try again
          </Button>
        )}
        <Button
          onClick={() => onContinue(installedCount === 0, installedCount)}
          className="min-w-[140px]"
          variant={installedCount > 0 ? 'default' : 'secondary'}
        >
          {installedCount > 0 ? 'Continue' : "I'll do this later"}
        </Button>
      </div>
    </div>
  );
}
