'use client';

/**
 * Settings → Providers: which coding agents Vicoa can drive, where they're
 * installed, and how to add one. Rendered by both the desktop settings surface
 * and the web settings page.
 *
 * Vicoa has no AI of its own — each machine's daemon probes for agent CLIs and
 * reports `metadata.available_agents` (see lib/desktop-agent-scan.ts). An
 * agent is "connected" when at least one machine reports it installed; the
 * rest sit under "Add an agent" with a copyable install command and a docs
 * link. Vicoa never installs an agent itself — same posture as onboarding's
 * AgentScanStep.
 *
 * Refresh re-reads the cloud machine rows, then re-probes every online machine
 * whose daemon advertises the `scan-agents` RPC, merging each fresh result as
 * it lands (the RPC also pushes the result to the cloud row for other
 * clients). Machines on older daemons simply keep their registration-time
 * snapshot.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { CopyCommand } from '@/components/copy-command';
import { AGENT_CATALOG_FALLBACK, type AgentCatalog } from '@/lib/agent-catalog';
import type { MachineSummary } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import {
  machineSupportsAgentScan,
  readAvailableAgents,
  rpcScanAgents,
} from '@/lib/desktop-agent-scan';
import { installInfoFor } from '@/lib/desktop-agent-install';
import { lastSeenLabel, machineDisplayName } from '@/lib/machine-display';
import { openExternalUrl } from '@/lib/open-external';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';

interface AgentRow {
  id: string;
  label: string;
  /** Machines reporting this agent installed, online first. */
  machines: MachineSummary[];
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

/**
 * Show machine names inline while the list is short; past this, fold to a
 * count that expands to a per-machine list on click. Keeps a widely-installed
 * agent's row from growing into an unreadable `A · B · C · D · …` run.
 */
const INLINE_MACHINE_LIMIT = 2;

function ConnectedAgentRow({ row }: { row: AgentRow }) {
  const [expanded, setExpanded] = useState(false);
  const { machines } = row;
  const foldable = machines.length > INLINE_MACHINE_LIMIT;
  const summary = foldable
    ? `On ${machines.length} machines`
    : `On ${machines.map(machineDisplayName).join(' · ')}`;

  return (
    <div>
      <div className="flex items-center gap-3 px-4 py-3">
        <AgentTypeIcon agentTypeName={row.id} size={18} whiteForOpenAI />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] text-foreground">{row.label}</div>
          {foldable ? (
            <button
              type="button"
              onClick={() => setExpanded((cur) => !cur)}
              className="inline-flex max-w-full cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <span className="truncate">{summary}</span>
              <ChevronDown
                className={cn('h-3 w-3 shrink-0 transition-transform', expanded && 'rotate-180')}
              />
            </button>
          ) : (
            <div className="truncate text-xs text-muted-foreground" title={summary}>
              {summary}
            </div>
          )}
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
          Ready
        </span>
      </div>
      {foldable && expanded && (
        <div className="space-y-1.5 pb-3 pl-[46px] pr-4">
          {machines.map((machine) => {
            const online = isMachineOnline(machine);
            return (
              <div key={machine.machine_id} className="flex items-center gap-2 text-xs">
                <span
                  className={cn(
                    'h-1.5 w-1.5 shrink-0 rounded-full',
                    online ? 'bg-green-500' : 'bg-border',
                  )}
                />
                <span className="truncate text-foreground/80">
                  {machineDisplayName(machine)}
                </span>
                <span className="shrink-0 text-muted-foreground/70">
                  {lastSeenLabel(machine)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** A not-yet-detected agent: expands to its install command + setup guide. */
function InstallableAgentRow({
  row,
  expanded,
  onToggle,
}: {
  row: AgentRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  const info = installInfoFor(row.id);
  return (
    <div>
      <button
        type="button"
        disabled={!info}
        onClick={onToggle}
        className={cn(
          'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
          info && 'cursor-pointer hover:bg-foreground/[0.02]',
        )}
      >
        <AgentTypeIcon agentTypeName={row.id} size={18} whiteForOpenAI />
        <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
          {row.label}
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground/70">
          <span className="h-1.5 w-1.5 rounded-full bg-border" />
          Not detected
          {info && (
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')}
            />
          )}
        </span>
      </button>
      {expanded && info && (
        <div className="space-y-2 px-4 pb-3.5">
          <CopyCommand command={info.command} />
          <button
            type="button"
            onClick={() => openExternalUrl(info.docsUrl)}
            className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            Setup guide
            <ExternalLink className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export function ProvidersSettingsSection() {
  const router = useRouter();
  const { api } = useAgentDashboard();
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [machines, setMachines] = useState<MachineSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Live catalog, so agents added server-side appear without a web deploy.
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .getAgentCatalog()
      .then((fresh) => {
        if (!cancelled && fresh?.agents?.length) setCatalog(fresh);
      })
      .catch(() => {
        /* keep the baked-in fallback */
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      setMachines(await api.listMachines());
      setLoadError(false);
    } catch {
      setLoadError(true);
      setMachines((prev) => prev ?? []);
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    if (!api || refreshing) return;
    setRefreshing(true);
    try {
      const list = await api.listMachines();
      setMachines(list);
      setLoadError(false);
      const scannable = list.filter(
        (machine) => isMachineOnline(machine) && machineSupportsAgentScan(machine),
      );
      await Promise.allSettled(
        scannable.map(async (machine) => {
          const fresh = await rpcScanAgents(machine.machine_id);
          setMachines(
            (prev) =>
              prev?.map((m) =>
                m.machine_id === machine.machine_id
                  ? { ...m, metadata: { ...(m.metadata ?? {}), available_agents: fresh } }
                  : m,
              ) ?? prev,
          );
        }),
      );
    } catch {
      setLoadError(true);
    } finally {
      setRefreshing(false);
    }
  }, [api, refreshing]);

  const rows = useMemo(() => {
    const all: AgentRow[] = catalog.agents.map((agent) => ({
      id: agent.id,
      label: agent.label,
      machines: sortMachinesOnlineFirst(
        (machines ?? []).filter((m) => readAvailableAgents(m)?.[agent.id] === true),
      ),
    }));
    return {
      connected: all.filter((row) => row.machines.length > 0),
      others: all.filter((row) => row.machines.length === 0),
    };
  }, [catalog, machines]);

  const loading = machines === null;
  const hasMachines = (machines?.length ?? 0) > 0;

  return (
    <section>
      <h1 className="text-2xl font-light tracking-tight text-foreground">Providers</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Vicoa runs coding agents installed on your machines. Agents detected on a connected machine appear here automatically; You just need one to get started.
      </p>

      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm text-foreground/90">Connected agents</h2>
          {hasMachines && (
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={refreshing}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground disabled:opacity-60"
            >
              <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
        </div>
        <SectionCard>
          {loading ? (
            <div className="flex items-center gap-2.5 px-4 py-5 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Looking for your agents…
            </div>
          ) : !hasMachines ? (
            <div className="flex flex-col items-start gap-3 px-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-[13px] text-foreground">No machines connected</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Vicoa detects agents on machines running the desktop app or the Vicoa CLI.
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 text-xs"
                onClick={() => router.push('/dashboard/settings?tab=machines')}
              >
                Add a machine
              </Button>
            </div>
          ) : rows.connected.length === 0 ? (
            <div className="px-4 py-5 text-sm text-muted-foreground">
              No agents detected on your machines yet — install one below, then press Refresh.
            </div>
          ) : (
            rows.connected.map((row) => <ConnectedAgentRow key={row.id} row={row} />)
          )}
        </SectionCard>
        {loadError && (
          <p className="mt-2 text-xs text-warning">
            Couldn’t reach the server — this list may be out of date.
          </p>
        )}
      </div>

      {rows.others.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm text-foreground/90">Add an agent</h2>
          <SectionCard>
            {rows.others.map((row) => (
              <InstallableAgentRow
                key={row.id}
                row={row}
                expanded={expandedId === row.id}
                onToggle={() => setExpandedId((cur) => (cur === row.id ? null : row.id))}
              />
            ))}
          </SectionCard>
          <p className="mt-2 text-xs text-muted-foreground/70">
            Run the install command in a terminal on a connected machine, then press Refresh.
          </p>
        </div>
      )}
    </section>
  );
}
