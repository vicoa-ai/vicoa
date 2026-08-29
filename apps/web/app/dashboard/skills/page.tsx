'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Layers2, Check, ChevronDown, Monitor, Plus, Search, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';
import { readAvailableAgents } from '@/lib/desktop-agent-scan';
import { AGENT_CATALOG_FALLBACK, agentById, type AgentCatalog } from '@/lib/agent-catalog';
import type { MachineSummary } from '@/lib/backend-api';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopCollapsedLead } from '@/components/desktop/window-chrome';
import { cn } from '@/lib/utils';
import {
  describeSkillError,
  isMachineUnreachable,
  listSkills,
  machineSupportsSkills,
  SKILL_SUPPORTED_AGENTS,
  uninstallSkill,
  type ListSkillsResult,
  type SkillAgentType,
  type SkillSummary,
} from './lib/skills-rpc';
import { getSkillsCache, setSkillsCache, skillsKey } from './lib/skills-cache';
import { skillMatchesQuery } from './lib/skills-view';
import { AgentSkillsSection } from './components/agent-skills-section';
import { InstallSkillDialog } from './components/install-skill-dialog';
import { NewSkillDialog } from './components/new-skill-dialog';
import { SkillAgentTabs } from './components/skill-agent-tabs';
import { SkillDetailDialog } from './components/skill-detail-dialog';

// Keep the machine "online" dot fresh (heartbeats decay vs. the wall clock).
const MACHINE_REFRESH_INTERVAL_MS = 30_000;

const CREATE_SKILL_PROMPT = 'Install or create a skill: ';

function machineLabel(m: MachineSummary): string {
  return m.display_name || m.hostname || `Machine ${m.machine_id.slice(0, 8)}`;
}

interface ShownAgent {
  type: SkillAgentType;
  label: string;
}

export default function SkillsPage() {
  const { api } = useAgentDashboard();
  const router = useRouter();

  const [machines, setMachines] = useState<MachineSummary[]>(
    () => getSkillsCache()?.machines ?? [],
  );
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(
    () => getSkillsCache()?.selectedMachineId ?? null,
  );
  const [skillsMap, setSkillsMap] = useState<Record<string, ListSkillsResult>>(
    () => getSkillsCache()?.skills ?? {},
  );
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [rpcError, setRpcError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [newSkillOpen, setNewSkillOpen] = useState(false);
  const [installOpen, setInstallOpen] = useState(false);
  const [installAgent, setInstallAgent] = useState<SkillAgentType>('claude');
  // Which agent's skills the grid shows. Follows the tab bar; falls back to the
  // first detected agent when unset or the selection drops off a new machine.
  const [activeAgent, setActiveAgent] = useState<SkillAgentType | null>(null);
  // Free-text filter over the shown skills (name + description).
  const [query, setQuery] = useState('');
  const [uninstalling, setUninstalling] = useState<{ agent: SkillAgentType; name: string } | null>(
    null,
  );
  const [deleteTarget, setDeleteTarget] = useState<{ agent: SkillAgentType; skill: SkillSummary } | null>(
    null,
  );
  const [detailTarget, setDetailTarget] = useState<{ agent: SkillAgentType; skill: SkillSummary } | null>(
    null,
  );

  const selectedMachine = useMemo(
    () => machines.find((m) => m.machine_id === selectedMachineId) ?? null,
    [machines, selectedMachineId],
  );

  // Which agents' skills to show: the machine's detected agents ∩ the ones the
  // daemon can manage, labeled from the catalog. `null` available (older daemon
  // that never reported) falls back to the full supported set.
  const shownAgents = useMemo<ShownAgent[]>(() => {
    const available = selectedMachine ? readAvailableAgents(selectedMachine) : null;
    const ids = SKILL_SUPPORTED_AGENTS.filter((id) =>
      available === null ? true : available[id] === true,
    );
    return ids.map((id) => ({ type: id, label: agentById(catalog, id)?.label ?? id }));
  }, [selectedMachine, catalog]);

  // The agent whose skills the grid shows: the tab selection when it's still a
  // detected agent, else the first one (a fresh machine may not offer the last
  // pick). Counts feed the per-tab badges.
  const effectiveAgent = useMemo<SkillAgentType | null>(
    () =>
      activeAgent && shownAgents.some((a) => a.type === activeAgent)
        ? activeAgent
        : (shownAgents[0]?.type ?? null),
    [activeAgent, shownAgents],
  );

  // A blocking note that replaces the sections (no machines / offline / too-old
  // CLI / no supported agents), or null when the tab can load skills.
  const note = useMemo<{ title: string; body: string } | null>(() => {
    if (machines.length === 0) {
      return {
        title: 'No machines connected',
        body: 'Run the Vicoa CLI on a machine to see and install its agent skills here.',
      };
    }
    if (!selectedMachine) return null;
    if (!isMachineOnline(selectedMachine)) {
      return {
        title: machineLabel(selectedMachine),
        body: 'Machine is offline — reconnect it to view or install skills.',
      };
    }
    if (!machineSupportsSkills(selectedMachine)) {
      return {
        title: machineLabel(selectedMachine),
        body: 'This machine’s Vicoa CLI is too old to manage skills — update it.',
      };
    }
    if (shownAgents.length === 0) {
      return {
        title: machineLabel(selectedMachine),
        body: 'No supported agents (Claude Code, Codex, OpenCode) were detected on this machine.',
      };
    }
    return null;
  }, [machines.length, selectedMachine, shownAgents.length]);

  const canManage = note === null && Boolean(selectedMachineId);

  // Machine list + default selection.
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    (async () => {
      try {
        const list = sortMachinesOnlineFirst(await api.listMachines());
        if (cancelled) return;
        setMachines(list);
        setSelectedMachineId((prev) =>
          prev && list.some((m) => m.machine_id === prev)
            ? prev
            : (list[0]?.machine_id ?? null),
        );
      } catch {
        /* keep cached machines */
      }
      api.getAgentCatalog().then((c) => !cancelled && setCatalog(c)).catch(() => {});
    })();
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    if (!api) return;
    const id = setInterval(async () => {
      try {
        setMachines(sortMachinesOnlineFirst(await api.listMachines()));
      } catch {
        /* ignore */
      }
    }, MACHINE_REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [api]);

  const loadSkills = useCallback(async (machineId: string, agentTypes: SkillAgentType[]) => {
    setRpcError(null);
    setAgentsLoading(true);
    const results = await Promise.allSettled(agentTypes.map((t) => listSkills(machineId, t)));
    const next: Record<string, ListSkillsResult> = {};
    let firstError: unknown = null;
    results.forEach((res, i) => {
      if (res.status === 'fulfilled') {
        next[skillsKey(machineId, agentTypes[i])] = res.value;
      } else if (!firstError) {
        firstError = res.reason;
      }
    });
    if (Object.keys(next).length === 0 && firstError) {
      setRpcError(
        isMachineUnreachable(firstError)
          ? 'Machine went offline — reconnect it to view skills.'
          : describeSkillError(firstError),
      );
    }
    setSkillsMap((prev) => ({ ...prev, ...next }));
    setAgentsLoading(false);
  }, []);

  const agentTypesKey = shownAgents.map((a) => a.type).join(',');
  useEffect(() => {
    if (!canManage || !selectedMachineId || !agentTypesKey) return;
    void loadSkills(selectedMachineId, agentTypesKey.split(','));
  }, [canManage, selectedMachineId, agentTypesKey, loadSkills]);

  useEffect(() => {
    setSkillsCache({ machines, selectedMachineId, skills: skillsMap });
  }, [machines, selectedMachineId, skillsMap]);

  const handleInstalled = useCallback(
    (agent: SkillAgentType, skill: SkillSummary) => {
      if (!selectedMachineId) return;
      const key = skillsKey(selectedMachineId, agent);
      setSkillsMap((prev) => {
        const cur = prev[key] ?? { skills: [], supported: true };
        const rest = cur.skills.filter((s) => s.name !== skill.name);
        const skills = [...rest, skill].sort((a, b) => a.name.localeCompare(b.name));
        return { ...prev, [key]: { ...cur, skills } };
      });
    },
    [selectedMachineId],
  );

  const doUninstall = useCallback(
    async (agent: SkillAgentType, skill: SkillSummary) => {
      if (!selectedMachineId) return;
      const key = skillsKey(selectedMachineId, agent);
      setUninstalling({ agent, name: skill.name });
      setBanner(null);
      const before = skillsMap[key];
      setSkillsMap((prev) => {
        const cur = prev[key];
        if (!cur) return prev;
        return { ...prev, [key]: { ...cur, skills: cur.skills.filter((s) => s.name !== skill.name) } };
      });
      try {
        await uninstallSkill(selectedMachineId, agent, skill.name);
      } catch (err) {
        setBanner(describeSkillError(err));
        if (before) setSkillsMap((prev) => ({ ...prev, [key]: before }));
      } finally {
        setUninstalling(null);
      }
    },
    [selectedMachineId, skillsMap],
  );

  const openInstall = useCallback((agent?: SkillAgentType) => {
    setInstallAgent(agent ?? 'claude');
    setInstallOpen(true);
  }, []);

  const createWithAgent = useCallback(() => {
    router.push(`/dashboard/agents/new-session?prompt=${encodeURIComponent(CREATE_SKILL_PROMPT)}`);
  }, [router]);

  // "Try now": open a new session with the skill's `/`-command seeded into the
  // prompt (the composer resolves it against the agent's installed skills).
  const trySkill = useCallback(
    (skill: SkillSummary) => {
      setDetailTarget(null);
      router.push(`/dashboard/agents/new-session?prompt=${encodeURIComponent(`/${skill.name} `)}`);
    },
    [router],
  );

  return (
    <main className="flex h-full flex-col overflow-hidden">
      {/* On desktop this header doubles as the window titlebar (drag region). */}
      <div
        style={DRAG_REGION}
        className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4"
      >
        <DesktopCollapsedLead />
        <Layers2 className="h-4 w-4 shrink-0 text-muted-foreground" />
        <h1 className="shrink-0 text-sm font-medium">Skills</h1>
        <div style={NO_DRAG} className="ml-auto flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-7 max-w-[220px] gap-1.5 text-xs"
                disabled={machines.length === 0}
              >
                <Monitor className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">
                  {selectedMachine ? machineLabel(selectedMachine) : 'No machines'}
                </span>
                <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 text-xs">
              {machines.map((m) => (
                <DropdownMenuItem
                  key={m.machine_id}
                  onSelect={() => setSelectedMachineId(m.machine_id)}
                  className="gap-2"
                >
                  <span
                    className={cn(
                      'size-1.5 shrink-0 rounded-full',
                      isMachineOnline(m) ? 'bg-green-500' : 'bg-muted-foreground/40',
                    )}
                  />
                  <span className="truncate">{machineLabel(m)}</span>
                  {m.machine_id === selectedMachineId && <Check className="ml-auto h-3 w-3" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => setNewSkillOpen(true)}
            disabled={!api}
          >
            <Plus className="size-3.5" />
            New Skill
          </Button>
        </div>
      </div>

      {/* Search + agent filter tabs. Tab counts reflect the current query so
          you can see which agent has matches while typing. */}
      {!note && !rpcError && shownAgents.length > 0 && (
        <>
          <div className="px-4 pb-3 pt-6">
            <div className="relative mx-auto max-w-3xl">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search skills…"
                className="h-9 rounded-xl bg-muted/50 pl-9 text-xs focus-visible:border-input focus-visible:ring-0 dark:bg-muted/40"
              />
            </div>
          </div>
          <SkillAgentTabs
            agents={shownAgents}
            active={effectiveAgent}
            counts={Object.fromEntries(
              shownAgents.map((a) => {
                const list = selectedMachineId
                  ? skillsMap[skillsKey(selectedMachineId, a.type)]?.skills
                  : undefined;
                return [
                  a.type,
                  list ? list.filter((s) => skillMatchesQuery(s, query)).length : undefined,
                ];
              }),
            )}
            onSelect={setActiveAgent}
          />
        </>
      )}

      {banner && (
        <div className="border-b border-border bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {banner}
        </div>
      )}

      <div className="custom-scrollbar flex-1 overflow-y-auto px-4 py-4">
        {note ? (
          <EmptyNote title={note.title} body={note.body} onCreate={createWithAgent} />
        ) : rpcError ? (
          <EmptyNote title={machineLabel(selectedMachine!)} body={rpcError} />
        ) : effectiveAgent ? (
          <div className="mx-auto max-w-3xl">
            <AgentSkillsSection
              state={
                selectedMachineId
                  ? skillsMap[skillsKey(selectedMachineId, effectiveAgent)]
                  : undefined
              }
              loading={agentsLoading}
              query={query}
              onSelect={(skill) => setDetailTarget({ agent: effectiveAgent, skill })}
              onAdd={() => setNewSkillOpen(true)}
            />
          </div>
        ) : null}
      </div>

      <NewSkillDialog
        open={newSkillOpen}
        canInstall={canManage}
        onOpenChange={setNewSkillOpen}
        onInstall={() => {
          setNewSkillOpen(false);
          openInstall(effectiveAgent ?? undefined);
        }}
        onCreateWithAgent={() => {
          setNewSkillOpen(false);
          createWithAgent();
        }}
      />

      <InstallSkillDialog
        open={installOpen}
        machineId={selectedMachineId}
        agents={shownAgents.map((a) => ({ value: a.type, label: a.label }))}
        defaultAgent={installAgent}
        onOpenChange={setInstallOpen}
        onInstalled={handleInstalled}
      />

      <SkillDetailDialog
        open={detailTarget !== null}
        machineId={selectedMachineId}
        agent={detailTarget?.agent ?? null}
        skill={detailTarget?.skill ?? null}
        onOpenChange={(open) => {
          if (!open) setDetailTarget(null);
        }}
        onUninstall={(skill) => {
          const agent = detailTarget?.agent;
          setDetailTarget(null);
          if (agent) setDeleteTarget({ agent, skill });
        }}
        onTry={trySkill}
      />

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Uninstall skill</DialogTitle>
            <DialogDescription>
              This deletes the skill directory from{' '}
              {selectedMachine ? machineLabel(selectedMachine) : 'this machine'}. It will no longer
              be available to the agent or in the composer&apos;s <code>/</code> menu.
            </DialogDescription>
          </DialogHeader>
          {deleteTarget && (
            <div className="rounded-md border bg-muted/50 p-3">
              <div className="font-mono text-sm">{deleteTarget.skill.name}</div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="text-destructive-foreground"
              disabled={uninstalling !== null}
              onClick={() => {
                const target = deleteTarget;
                setDeleteTarget(null);
                if (target) void doUninstall(target.agent, target.skill);
              }}
            >
              Uninstall
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

function EmptyNote({
  title,
  body,
  onCreate,
}: {
  title: string;
  body: string;
  onCreate?: () => void;
}) {
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
      {onCreate && (
        <Button variant="outline" size="sm" className="mt-4 gap-1.5" onClick={onCreate}>
          <Sparkles className="size-3.5" />
          Create with agent
        </Button>
      )}
    </div>
  );
}
