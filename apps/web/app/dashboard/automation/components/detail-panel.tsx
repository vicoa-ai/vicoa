'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { cn, toAbsolutePath } from '@/lib/utils';
import { isMachineOnline } from '@/lib/session-liveness';
import { notifyOnboardingProgress } from '@/lib/onboarding-progress';
import { Button } from '@/components/ui/button';
import { MentionPromptField } from '@/components/mention-prompt-field';
import type { AgentType } from '@/lib/constants/slash-commands';
import {
  AGENT_CATALOG_FALLBACK,
  defaultsFor,
  reconcileAgainst,
  type AgentCatalog,
  type SessionConfig,
} from '@/lib/agent-catalog';
import type {
  AutomationResponse,
  getBackendAPI,
  MachineSummary,
} from '@/lib/backend-api';
import {
  automationToDraft,
  defaultScheduleDraft,
  draftToScheduleApi,
  isDraftComplete,
  summarizeSchedule,
  type ScheduleDraft,
} from '../lib/frequency';
import type { AutomationTemplate } from '../lib/templates';
import { DetailsSection, type WorktreeDraft } from './details-section';
import { FrequencySection } from './frequency-section';
import { RunHistorySection } from './run-history-section';

type Api = ReturnType<typeof getBackendAPI>;

function recentDirsFor(m: MachineSummary | undefined): string[] {
  return m && Array.isArray(m.recent_directories) ? m.recent_directories : [];
}

function initialDirectory(m: MachineSummary | undefined): string {
  return recentDirsFor(m)[0] ?? m?.home_dir ?? '~/';
}

export function DetailPanel({
  api,
  automation,
  template = null,
  machines,
  catalog = AGENT_CATALOG_FALLBACK,
  onSaved,
  onClose,
  runHistoryRefreshKey,
}: {
  api: Api;
  /** null → create mode. */
  automation: AutomationResponse | null;
  /** Seeds create mode (title/prompt/schedule); ignored when editing. */
  template?: AutomationTemplate | null;
  machines: MachineSummary[];
  catalog?: AgentCatalog;
  onSaved: (a: AutomationResponse) => void;
  onClose: () => void;
  runHistoryRefreshKey?: number;
}) {
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [machineId, setMachineId] = useState('');
  const [directory, setDirectory] = useState('');
  const [worktree, setWorktree] = useState<WorktreeDraft>({ mode: 'none', path: null });
  const [sessionConfig, setSessionConfig] = useState<SessionConfig>(() =>
    defaultsFor(catalog, 'claude'),
  );
  const [schedule, setSchedule] = useState<ScheduleDraft>(() => defaultScheduleDraft());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Tracks unsaved edits so the Save button only appears when there's something
  // to save (create mode always shows Create).
  const [dirty, setDirty] = useState(false);

  // Re-seed when the selected automation changes (or create mode opens).
  useEffect(() => {
    setError(null);
    setDirty(false);
    if (automation) {
      setTitle(automation.title);
      setPrompt(automation.prompt);
      setMachineId(automation.machine_id);
      setDirectory(automation.directory);
      setWorktree({
        mode: automation.worktree?.mode ?? 'none',
        path: automation.worktree?.path ?? null,
      });
      setSessionConfig(
        reconcileAgainst(automation.session_config as unknown as SessionConfig, catalog),
      );
      setSchedule(automationToDraft(automation));
    } else {
      // A template may already know a machine/directory (e.g. seeded from a
      // task's linked project); honor it when it maps to a connected machine,
      // else fall back to the first machine's default directory.
      const templateMachine = template?.machineId
        ? machines.find((m) => m.machine_id === template.machineId)
        : undefined;
      const m = templateMachine ?? machines[0];
      setTitle(template?.title ?? '');
      setPrompt(template?.prompt ?? '');
      setMachineId(m?.machine_id ?? '');
      setDirectory(
        templateMachine && template?.directory ? template.directory : initialDirectory(m),
      );
      setWorktree({ mode: 'none', path: null });
      setSessionConfig(defaultsFor(catalog, 'claude'));
      setSchedule(
        template?.schedule
          ? { ...defaultScheduleDraft(), ...template.schedule }
          : defaultScheduleDraft(),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [automation?.id, template?.id]);

  // Every user edit marks the form dirty; `touch` wraps a setter to do so.
  const touch = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v);
    setDirty(true);
  };

  const patchSchedule = (p: Partial<ScheduleDraft>) => {
    setSchedule((prev) => ({ ...prev, ...p }));
    setDirty(true);
  };

  const onMachineChange = (id: string) => {
    setMachineId(id);
    setDirectory(initialDirectory(machines.find((m) => m.machine_id === id)));
    setWorktree({ mode: 'none', path: null });
    setDirty(true);
  };

  // Mention/command context for the prompt field: the selected machine's live
  // index when it's online, else the CLI-synced DB copy (the machine an
  // automation targets is often asleep between runs).
  const selectedMachine = machines.find((m) => m.machine_id === machineId) ?? null;
  const machineOnline = selectedMachine ? isMachineOnline(selectedMachine) : false;
  const promptProjectPath = toAbsolutePath(directory.trim() || undefined, selectedMachine?.home_dir);
  const promptAgentType: AgentType =
    sessionConfig.agent === 'codex'
      ? 'codex'
      : sessionConfig.agent === 'opencode'
        ? 'opencode'
        : 'claude';

  const canSave =
    !!title.trim() &&
    !!prompt.trim() &&
    !!machineId &&
    !!directory.trim() &&
    isDraftComplete(schedule) &&
    !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    const base = {
      title: title.trim(),
      prompt: prompt.trim(),
      machine_id: machineId,
      directory: directory.trim(),
      worktree: { mode: worktree.mode, path: worktree.path },
      session_config: sessionConfig as unknown as Record<string, unknown>,
      ...draftToScheduleApi(schedule),
    };
    try {
      const saved = automation
        ? await api.updateAutomation(automation.id, base)
        : await api.createAutomation({ ...base, enabled: true });
      setDirty(false);
      onSaved(saved);
      if (!automation) notifyOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save automation');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
        <span className="text-xs text-muted-foreground">
          {automation ? (automation.enabled ? 'Active' : 'Paused') : 'New automation'}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {(!automation || dirty) && (
            <Button
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={handleSave}
              disabled={!canSave}
            >
              {saving ? 'Saving…' : automation ? 'Save' : 'Create'}
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Body */}
      <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <input
          value={title}
          placeholder="Automation title"
          onChange={(e) => {
            setTitle(e.target.value);
            setDirty(true);
          }}
          className="w-full bg-transparent text-lg font-medium outline-none placeholder:text-muted-foreground/50"
        />
        <MentionPromptField
          value={prompt}
          onChange={(value) => {
            setPrompt(value);
            setDirty(true);
          }}
          agentType={promptAgentType}
          projectPath={promptProjectPath}
          machineId={machineOnline ? machineId : null}
          machine={selectedMachine}
          mentionsEnabled={!!directory.trim()}
          placeholder="Describe what the agent should do… @ for files, / for skills"
          className={cn(
            'min-h-[80px] w-full resize-y rounded-lg border border-border/60 bg-card/40 px-3 py-2',
            'text-sm outline-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-ring',
          )}
        />

        <DetailsSection
          machines={machines}
          machineId={machineId}
          onMachineChange={onMachineChange}
          directory={directory}
          onDirectoryChange={touch(setDirectory)}
          worktree={worktree}
          onWorktreeChange={touch(setWorktree)}
          sessionConfig={sessionConfig}
          onSessionConfigChange={touch(setSessionConfig)}
          catalog={catalog}
        />

        <FrequencySection draft={schedule} patch={patchSchedule} />

        {automation && (
          <RunHistorySection
            api={api}
            automationId={automation.id}
            title={automation.title}
            refreshKey={runHistoryRefreshKey}
          />
        )}

        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <p className="px-1 text-[11px] text-muted-foreground/70">
          {summarizeSchedule({
            schedule_kind: schedule.repeat === 'once' ? 'once' : 'recurring',
            frequency: draftToScheduleApi(schedule).frequency ?? null,
            next_run_at: automation?.next_run_at ?? null,
          } as AutomationResponse)}
        </p>
      </div>
    </div>
  );
}
