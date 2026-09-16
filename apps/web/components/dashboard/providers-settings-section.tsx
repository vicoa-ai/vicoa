'use client';

/**
 * Settings → Providers: which coding agents Vicoa can drive, where they're
 * installed, and how to add one. Rendered by both the desktop settings surface
 * and the web settings page.
 *
 * Vicoa has no AI of its own — each machine's daemon probes for agent CLIs and
 * reports `metadata.available_agents` (see lib/desktop-agent-scan.ts). An
 * agent is "connected" when at least one machine reports it installed.
 *
 * "Add an agent" is the catalog the backend serves (`acp_catalog`): one click
 * writes the launch command into the chosen machine's `~/.vicoa/config.json`
 * through the daemon's `provider-add` RPC (lib/desktop-provider-config.ts).
 * It sits directly under the connected list, ahead of the built-ins Vicoa
 * ships but hasn't found — those are install *instructions*, and when they
 * came first under a heading that also said "Add an agent" the real one read
 * as absent. Vicoa never installs a binary itself (same posture as
 * onboarding's AgentScanStep): npx/uvx entries download on the first session,
 * the rest link to their install docs.
 *
 * The catalog section renders whenever a machine exists, even with nothing to
 * offer — an empty `acp_catalog` used to hide it outright, which is
 * indistinguishable from the feature not being deployed.
 *
 * "Check" is what makes an added agent trustworthy: the daemon spawns it once
 * and runs the real `initialize` → `session/new` handshake, and the row shows
 * where it stopped. Without it, "added" would only mean "the id is in a file".
 *
 * Refresh re-reads the cloud machine rows, then re-probes every online machine
 * whose daemon advertises the `scan-agents` RPC, merging each fresh result as
 * it lands (the RPC also pushes the result to the cloud row for other
 * clients). Machines on older daemons simply keep their registration-time
 * snapshot.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ChevronDown,
  ExternalLink,
  Loader2,
  PlugZap,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { CopyCommand } from '@/components/copy-command';
import {
  AGENT_CATALOG_FALLBACK,
  customAgentLabel,
  type AcpCatalogEntry,
  type AgentCatalog,
} from '@/lib/agent-catalog';
import type { MachineSummary } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import {
  machineSupportsAgentScan,
  readAvailableAgents,
  rpcScanAgents,
} from '@/lib/desktop-agent-scan';
import { installInfoFor } from '@/lib/desktop-agent-install';
import {
  describeProbe,
  machineSupportsProviderConfig,
  readAgentLabels,
  rpcProviderAdd,
  rpcProviderProbe,
  rpcProviderRemove,
  type ProviderProbeResult,
} from '@/lib/desktop-provider-config';
import { getLocalMachineId } from '@/lib/local-machine';
import { lastSeenLabel, machineDisplayName } from '@/lib/machine-display';
import { openExternalUrl } from '@/lib/open-external';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';

interface AgentRow {
  id: string;
  label: string;
  /** Built-in (Vicoa ships the integration) or added to a machine's config. */
  source: 'builtin' | 'config';
  /** Machines reporting this agent installed, online first. */
  machines: MachineSummary[];
  /** Machines whose config lists the agent (installed or not), online first. */
  addedOn: MachineSummary[];
  /** The catalog entry it was added from, when we can tell. */
  entry?: AcpCatalogEntry;
}

interface ProbeState {
  machineId: string;
  result: ProviderProbeResult | null;
  error: string | null;
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

function MachineList({ machines }: { machines: MachineSummary[] }) {
  return (
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
            <span className="truncate text-foreground/80">{machineDisplayName(machine)}</span>
            <span className="shrink-0 text-muted-foreground/70">{lastSeenLabel(machine)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** The result line under a row after Check ran (or while it runs). */
function ProbeLine({ probe, running }: { probe: ProbeState | undefined; running: boolean }) {
  if (running) {
    return (
      <div className="flex items-center gap-1.5 pb-3 pl-[46px] pr-4 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Starting the agent and running the ACP handshake…
      </div>
    );
  }
  if (!probe) return null;
  if (probe.error) {
    return (
      <div className="pb-3 pl-[46px] pr-4 text-xs text-warning">Check failed: {probe.error}</div>
    );
  }
  if (!probe.result) return null;
  const ok = probe.result.ok;
  return (
    <div className={cn('pb-3 pl-[46px] pr-4 text-xs', ok ? 'text-muted-foreground' : 'text-warning')}>
      <span className={cn('mr-1.5 inline-block h-1.5 w-1.5 rounded-full', ok ? 'bg-green-500' : 'bg-warning')} />
      {describeProbe(probe.result)}
      {ok && probe.result.models && probe.result.models.length > 0 && (
        <div className="mt-1 truncate text-muted-foreground/70" title={probe.result.models.map((m) => m.id).join(', ')}>
          {probe.result.models.map((m) => m.label).join(' · ')}
        </div>
      )}
      {!ok && probe.result.stderr && probe.result.stderr.length > 0 && (
        <pre className="custom-scrollbar mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap rounded bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
          {probe.result.stderr.join('\n')}
        </pre>
      )}
    </div>
  );
}

interface RowActions {
  /** Machine the Check / Remove buttons act on, if any online one can. */
  actionMachine: MachineSummary | null;
  probe: ProbeState | undefined;
  probing: boolean;
  removing: boolean;
  onCheck: () => void;
  onRemove: () => void;
}

function ConnectedAgentRow({ row, actions }: { row: AgentRow; actions: RowActions }) {
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
          <div className="flex items-center gap-1.5 truncate text-[13px] text-foreground">
            <span className="truncate">{row.label}</span>
            {row.source === 'config' && (
              <span className="shrink-0 rounded border border-border/60 px-1 py-px text-[10px] text-muted-foreground">
                ACP
              </span>
            )}
          </div>
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
        <RowButtons row={row} actions={actions} />
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
          Ready
        </span>
      </div>
      {foldable && expanded && <MachineList machines={machines} />}
      <ProbeLine probe={actions.probe} running={actions.probing} />
    </div>
  );
}

function RowButtons({ row, actions }: { row: AgentRow; actions: RowActions }) {
  if (!actions.actionMachine) return null;
  return (
    <span className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        onClick={actions.onCheck}
        disabled={actions.probing}
        title={`Start ${row.label} on ${machineDisplayName(actions.actionMachine)} and run the ACP handshake`}
        className="inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
      >
        {actions.probing ? <Loader2 className="h-3 w-3 animate-spin" /> : <PlugZap className="h-3 w-3" />}
        Check
      </button>
      {row.source === 'config' && (
        <button
          type="button"
          onClick={actions.onRemove}
          disabled={actions.removing}
          title={`Remove ${row.label} from ${machineDisplayName(actions.actionMachine)}'s config`}
          className="inline-flex cursor-pointer items-center rounded-md p-1 text-muted-foreground/70 transition-colors hover:bg-muted/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          aria-label="Remove"
        >
          {actions.removing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
        </button>
      )}
    </span>
  );
}

/**
 * An agent added to a machine's config whose launcher the daemon could not
 * find: the ACP equivalent of InstallableAgentRow, with the catalog's install
 * link instead of a hardcoded command, plus Check / Remove.
 */
function AddedAgentRow({
  row,
  actions,
  expanded,
  onToggle,
}: {
  row: AgentRow;
  actions: RowActions;
  expanded: boolean;
  onToggle: () => void;
}) {
  const where = row.addedOn.map(machineDisplayName).join(' · ');
  const command = row.entry?.command.join(' ');
  return (
    <div>
      <div className="flex items-center gap-3 px-4 py-3">
        <AgentTypeIcon agentTypeName={row.id} size={18} whiteForOpenAI />
        <button type="button" onClick={onToggle} className="min-w-0 flex-1 cursor-pointer text-left">
          <div className="truncate text-[13px] text-foreground">{row.label}</div>
          <div className="truncate text-xs text-muted-foreground" title={where}>
            Added on {where}
          </div>
        </button>
        <RowButtons row={row} actions={actions} />
        <button
          type="button"
          onClick={onToggle}
          className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-muted-foreground/70"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-border" />
          Not detected
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
        </button>
      </div>
      {expanded && (
        <div className="space-y-2 px-4 pb-3.5 pl-[46px] text-xs text-muted-foreground">
          {command && (
            <div>
              Launches with <code className="rounded bg-muted/60 px-1 py-px font-mono text-[11px]">{command}</code>
              {row.entry?.command[0] === 'npx' && ' — needs Node.js on that machine; the package downloads on first use.'}
              {row.entry?.command[0] === 'uvx' && ' — needs uv on that machine; the package downloads on first use.'}
            </div>
          )}
          {row.entry?.install_url && (
            <button
              type="button"
              onClick={() => openExternalUrl(row.entry!.install_url)}
              className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              Install guide
              <ExternalLink className="h-3 w-3" />
            </button>
          )}
          {!row.entry && <div>Install its CLI on that machine, then press Check.</div>}
        </div>
      )}
      <ProbeLine probe={actions.probe} running={actions.probing} />
    </div>
  );
}

/** A not-yet-detected built-in agent: expands to its install command + setup guide. */
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

/** One catalog entry the target machine does not have yet. */
function CatalogRow({
  entry,
  adding,
  onAdd,
}: {
  entry: AcpCatalogEntry;
  adding: boolean;
  onAdd: () => void;
}) {
  const launcher = entry.command[0];
  const oneClick = launcher === 'npx' || launcher === 'uvx';
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <AgentTypeIcon agentTypeName={entry.id} size={18} whiteForOpenAI />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[13px] text-foreground">
          <span className="truncate">{entry.label}</span>
          {entry.version && (
            <span className="shrink-0 text-[11px] text-muted-foreground/70">{entry.version}</span>
          )}
        </div>
        <div className="truncate text-xs text-muted-foreground" title={entry.description}>
          {entry.description}
        </div>
      </div>
      <button
        type="button"
        onClick={() => openExternalUrl(entry.install_url)}
        title={oneClick ? `Runs via ${launcher}; docs` : 'Install instructions'}
        className="inline-flex shrink-0 cursor-pointer items-center rounded-md p-1 text-muted-foreground/70 transition-colors hover:bg-muted/50 hover:text-foreground"
        aria-label={`${entry.label} docs`}
      >
        <ExternalLink className="h-3 w-3" />
      </button>
      <Button
        variant="outline"
        size="sm"
        className="h-7 shrink-0 cursor-pointer px-2.5 text-xs"
        disabled={adding}
        onClick={onAdd}
      >
        {adding ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Add'}
      </Button>
    </div>
  );
}

function matchesSearch(entry: AcpCatalogEntry, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [entry.id, entry.label, entry.description].some((v) => v.toLowerCase().includes(q));
}

/** Update one machine's cloud-row copy of `available_agents` / `agent_labels` in place. */
function patchMachineAgents(
  machines: MachineSummary[] | null,
  machineId: string,
  available: Record<string, boolean> | undefined,
  labels: Record<string, string | null>,
): MachineSummary[] | null {
  if (!machines) return machines;
  return machines.map((m) => {
    if (m.machine_id !== machineId) return m;
    const metadata = { ...(m.metadata ?? {}) };
    if (available) metadata.available_agents = available;
    const current = { ...readAgentLabels(m) };
    for (const [id, label] of Object.entries(labels)) {
      if (label === null) delete current[id];
      else current[id] = label;
    }
    metadata.agent_labels = current;
    return { ...m, metadata };
  });
}

export function ProvidersSettingsSection() {
  const router = useRouter();
  const { api } = useAgentDashboard();
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [machines, setMachines] = useState<MachineSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [targetChoice, setTargetChoice] = useState<string | null>(null);
  const [addingId, setAddingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [probingId, setProbingId] = useState<string | null>(null);
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [actionError, setActionError] = useState<string | null>(null);

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
          setMachines((prev) => patchMachineAgents(prev, machine.machine_id, fresh, {}));
        }),
      );
    } catch {
      setLoadError(true);
    } finally {
      setRefreshing(false);
    }
  }, [api, refreshing]);

  // Machines whose daemon can edit its own provider config, online first.
  // The Add target defaults to this machine (desktop) or the first of them.
  const configurable = useMemo(
    () =>
      sortMachinesOnlineFirst(
        (machines ?? []).filter((m) => isMachineOnline(m) && machineSupportsProviderConfig(m)),
      ),
    [machines],
  );
  const target = useMemo(() => {
    if (configurable.length === 0) return null;
    const chosen = targetChoice && configurable.find((m) => m.machine_id === targetChoice);
    if (chosen) return chosen;
    const local = getLocalMachineId();
    return configurable.find((m) => m.machine_id === local) ?? configurable[0];
  }, [configurable, targetChoice]);

  const acpCatalog = useMemo(() => catalog.acp_catalog ?? [], [catalog]);

  const rows = useMemo(() => {
    const builtinIds = new Set(catalog.agents.map((a) => a.id));
    const byCatalogId = new Map(acpCatalog.map((e) => [e.id, e] as const));
    const all = machines ?? [];
    // Every id any machine reports, so a provider that exists only in one
    // machine's config still gets a row.
    const customIds = new Set<string>();
    const labels: Record<string, string> = {};
    for (const m of all) {
      Object.assign(labels, readAgentLabels(m));
      for (const id of Object.keys(readAvailableAgents(m) ?? {})) {
        if (!builtinIds.has(id)) customIds.add(id);
      }
    }
    const rowFor = (id: string, label: string, source: AgentRow['source']): AgentRow => ({
      id,
      label,
      source,
      machines: sortMachinesOnlineFirst(all.filter((m) => readAvailableAgents(m)?.[id] === true)),
      addedOn: sortMachinesOnlineFirst(all.filter((m) => readAvailableAgents(m)?.[id] !== undefined)),
      entry: byCatalogId.get(id),
    });
    const builtin = catalog.agents.map((a) => rowFor(a.id, a.label, 'builtin'));
    const custom = [...customIds]
      .sort()
      .map((id) => rowFor(id, labels[id] ?? byCatalogId.get(id)?.label ?? customAgentLabel(id), 'config'));
    const everything = [...builtin, ...custom];
    return {
      connected: everything.filter((row) => row.machines.length > 0),
      addedMissing: custom.filter((row) => row.machines.length === 0),
      others: builtin.filter((row) => row.machines.length === 0),
    };
  }, [acpCatalog, catalog, machines]);

  // Catalog entries the target machine does not list yet.
  const addable = useMemo(() => {
    const present = target ? new Set(Object.keys(readAvailableAgents(target) ?? {})) : new Set<string>();
    return acpCatalog.filter((e) => !present.has(e.id)).filter((e) => matchesSearch(e, search));
  }, [acpCatalog, search, target]);

  const actionMachineFor = useCallback(
    (row: AgentRow): MachineSummary | null => {
      // Prefer the Add target when it knows the agent, so Check and Add agree
      // on which machine they mean; else any online machine that has it.
      const candidates = row.source === 'config' ? row.addedOn : row.machines;
      const online = candidates.filter((m) => isMachineOnline(m) && machineSupportsProviderConfig(m));
      if (target && online.some((m) => m.machine_id === target.machine_id)) return target;
      return online[0] ?? null;
    },
    [target],
  );

  const check = useCallback(
    async (row: AgentRow) => {
      const machine = actionMachineFor(row);
      if (!machine || probingId) return;
      setProbingId(row.id);
      setProbes((prev) => {
        const next = { ...prev };
        delete next[row.id];
        return next;
      });
      try {
        const result = await rpcProviderProbe(machine.machine_id, row.id);
        setProbes((prev) => ({ ...prev, [row.id]: { machineId: machine.machine_id, result, error: null } }));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setProbes((prev) => ({ ...prev, [row.id]: { machineId: machine.machine_id, result: null, error: message } }));
      } finally {
        setProbingId((cur) => (cur === row.id ? null : cur));
      }
    },
    [actionMachineFor, probingId],
  );

  const add = useCallback(
    async (entry: AcpCatalogEntry) => {
      if (!target || addingId) return;
      setAddingId(entry.id);
      setActionError(null);
      try {
        const result = await rpcProviderAdd(target.machine_id, entry);
        setMachines((prev) =>
          patchMachineAgents(prev, target.machine_id, result.available_agents, {
            [entry.id]: result.label ?? entry.label,
          }),
        );
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        setAddingId((cur) => (cur === entry.id ? null : cur));
      }
    },
    [addingId, target],
  );

  const remove = useCallback(
    async (row: AgentRow) => {
      const machine = actionMachineFor(row);
      if (!machine || removingId) return;
      setRemovingId(row.id);
      setActionError(null);
      try {
        const result = await rpcProviderRemove(machine.machine_id, row.id);
        setMachines((prev) =>
          patchMachineAgents(prev, machine.machine_id, result.available_agents, { [row.id]: null }),
        );
        setProbes((prev) => {
          const next = { ...prev };
          delete next[row.id];
          return next;
        });
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        setRemovingId((cur) => (cur === row.id ? null : cur));
      }
    },
    [actionMachineFor, removingId],
  );

  const actionsFor = (row: AgentRow): RowActions => ({
    actionMachine: actionMachineFor(row),
    probe: probes[row.id],
    probing: probingId === row.id,
    removing: removingId === row.id,
    onCheck: () => void check(row),
    onRemove: () => void remove(row),
  });

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
            rows.connected.map((row) => (
              <ConnectedAgentRow key={row.id} row={row} actions={actionsFor(row)} />
            ))
          )}
        </SectionCard>
        {loadError && (
          <p className="mt-2 text-xs text-warning">
            Couldn’t reach the server — this list may be out of date.
          </p>
        )}
        {actionError && <p className="mt-2 text-xs text-warning">{actionError}</p>}
      </div>

      {rows.addedMissing.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm text-foreground/90">Added, not detected yet</h2>
          <SectionCard>
            {rows.addedMissing.map((row) => (
              <AddedAgentRow
                key={row.id}
                row={row}
                actions={actionsFor(row)}
                expanded={expandedId === row.id}
                onToggle={() => setExpandedId((cur) => (cur === row.id ? null : row.id))}
              />
            ))}
          </SectionCard>
          <p className="mt-2 text-xs text-muted-foreground/70">
            These are in a machine’s config but their launcher wasn’t found there. Install it, then press Check.
          </p>
        </div>
      )}

      {hasMachines && (
        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm text-foreground/90">Add an agent</h2>
            {target && configurable.length > 1 && (
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                Add to
                <select
                  value={target.machine_id}
                  onChange={(e) => setTargetChoice(e.target.value)}
                  className="cursor-pointer rounded-md border border-border/60 bg-transparent px-1.5 py-0.5 text-xs text-foreground"
                >
                  {configurable.map((m) => (
                    <option key={m.machine_id} value={m.machine_id}>
                      {machineDisplayName(m)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {target && configurable.length === 1 && (
              <span className="text-xs text-muted-foreground">Add to {machineDisplayName(target)}</span>
            )}
          </div>
          {acpCatalog.length === 0 ? (
            <SectionCard>
              <div className="px-4 py-4 text-xs text-muted-foreground">
                This server doesn’t publish an agent catalog yet, so there’s nothing to install from here.
                You can still add any ACP agent by hand in{' '}
                <code className="rounded bg-muted/60 px-1 py-px font-mono text-[11px]">~/.vicoa/config.json</code>{' '}
                — see the{' '}
                <button
                  type="button"
                  onClick={() => openExternalUrl('https://vicoa.ai/docs/agents/custom-agents')}
                  className="cursor-pointer underline underline-offset-4 transition-colors hover:text-foreground"
                >
                  custom agents guide
                </button>
                .
              </div>
            </SectionCard>
          ) : !target ? (
            <SectionCard>
              <div className="px-4 py-4 text-xs text-muted-foreground">
                {configurable.length === 0 && (machines?.length ?? 0) > 0
                  ? 'None of your machines is online with a daemon new enough to edit its own agent config. Update the Vicoa CLI or desktop app on one, then reopen this page.'
                  : 'Connect a machine to add an agent to it.'}{' '}
                You can also add agents by hand in{' '}
                <code className="rounded bg-muted/60 px-1 py-px font-mono text-[11px]">~/.vicoa/config.json</code>.
              </div>
            </SectionCard>
          ) : (
            <>
              <div className="mb-2 flex items-center gap-2 rounded-lg border border-border/60 bg-foreground/[0.02] px-3">
                <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search agents"
                  className="h-8 min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground/60"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                />
              </div>
              <div className="custom-scrollbar max-h-[420px] overflow-y-auto rounded-xl border border-border/60 bg-foreground/[0.03]">
                {addable.length === 0 ? (
                  <div className="px-4 py-4 text-xs text-muted-foreground">
                    {search ? 'No agents match.' : 'Every catalog agent is already on this machine.'}
                  </div>
                ) : (
                  <div className="divide-y divide-border/50">
                    {addable.map((entry) => (
                      <CatalogRow
                        key={entry.id}
                        entry={entry}
                        adding={addingId === entry.id}
                        onAdd={() => void add(entry)}
                      />
                    ))}
                  </div>
                )}
              </div>
              <p className="mt-2 text-xs text-muted-foreground/70">
                Add writes the launch command to that machine’s config; Vicoa doesn’t install anything. npx/uvx
                agents download on first use, the rest need their CLI installed. Press Check afterwards to be
                sure it works.
              </p>
            </>
          )}
        </div>
      )}
      {rows.others.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm text-foreground/90">Install on a machine yourself</h2>
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
            Vicoa ships support for these but hasn’t found them on any of your machines. Run the install
            command in a terminal there, then press Refresh.
          </p>
        </div>
      )}

    </section>
  );
}
