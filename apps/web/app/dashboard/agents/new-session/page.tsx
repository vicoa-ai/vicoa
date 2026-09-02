'use client';

import { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
import { preload } from 'react-dom';
import { useRouter, useSearchParams } from 'next/navigation';
import Image from 'next/image';
import posthog from 'posthog-js';
import { getWsClient, RpcError, type MachineBody } from '@/lib/ws-client';
import { useMachineStream } from '@/lib/hooks/use-ws-stream';
import { Button } from '@/components/ui/button';
import {
  RefreshCw,
  Loader2,
  Circle,
  ChevronDown,
  ArrowUp,
  Check,
  Folder,
  ListTodo,
  Monitor,
  X,
} from 'lucide-react';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import type { MachineSummary, ProjectResponse, TaskResponse } from '@/lib/backend-api';
import { TaskPickerPopover } from '@/components/dashboard/task-picker-popover';
import { MentionTextarea } from '@/components/mention-textarea';
import { AgentTypeIcon, getAgentLogoSrc } from '@/components/dashboard/agent-type-icon';
import { ChipDropdown, ModeIcon, TickItem } from '@/components/dashboard/session-config-dropdown';
import { rpcGitStatus } from '@/components/files-git-panel/rpc';
import { FilesGitPanel, FilesGitPanelToggle, usePanelState } from '@/components/files-git-panel';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toAbsolutePath } from '@/lib/utils';
import {
  isMachineOnline as isMachineOnlineShared,
  sortMachinesOnlineFirst as sortMachinesOnlineFirstShared,
} from '@/lib/session-liveness';
import {
  AGENT_CATALOG_FALLBACK,
  agentById,
  agentPickerLabel,
  catalogWithCachedModels,
  defaultsFor,
  loadPersistedSelection,
  reconcileAgainst,
  savePersistedSelection,
  toSpawnMetadata,
  type AgentCatalog,
  type CatalogEnumEntry,
  type CatalogModel,
  type PersistedWorktree,
  type SessionConfig,
} from '@/lib/agent-catalog';
import { DirectoryPickerPopover } from '@/components/dashboard/directory-picker-popover';
import { AddToChatMenu } from '@/components/dashboard/add-to-chat-menu';
import { ChatUsageIndicator } from '@/components/chat-usage-indicator';
import { fetchClaudeUsageWindows } from '@/lib/claude-usage';
import { SlashCommandSuggestions } from '@/components/dashboard/slash-command-suggestions';
import { useSlashCommands } from '@/lib/hooks/use-slash-commands';
import type { SlashCommand, AgentType } from '@/lib/constants/slash-commands';
import { applySlashCommandSelection, commandInsertText, detectSlashCommand, slashCommandMatches } from '@/lib/slash-command-utils';
import { WorktreePickerPopover } from '@/components/dashboard/worktree-picker-popover';
import {
  machineSupportsWorktree,
  resolveWorktreeSpawn,
  type WorktreeMode,
} from '@/lib/worktree-selection';
import { loadPromptDraft, savePromptDraft, clearPromptDraft } from '@/lib/new-session-draft';
import { currentPathname, openCreatedSession } from '@/lib/new-session-navigation';
import { getDesktopConfig } from '@/lib/runtime-config';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopCollapsedLead, DesktopWindowControlsSpacer } from '@/components/desktop/window-chrome';
import { comboInline, getShortcutCombo, matchesShortcut } from '@/lib/desktop-shortcuts';
import { getDesktopShellBridge } from '@/lib/desktop-shell';
import { collectComposerDrop, folderPathToMention } from '@/lib/chat-drop';
import { FolderRefChip } from '@/components/folder-ref-chip';
import { postInstanceMessage } from '@/lib/agent-instance-api';
import { MAX_ATTACHMENTS_PER_MESSAGE, MAX_ATTACHMENT_BYTES, type ChatUploadedAttachment } from '@/components/chat-input';
import { formatFileSize } from '@/components/chat-attachments';
import { GitBranch, File as FileIcon, FolderPlus } from 'lucide-react';

const MACHINE_REFRESH_INTERVAL_MS = 30_000;

/** One attachment picked before the session exists: preview now, upload later.
 *
 * Unlike the chat input's `PendingUpload` there is no `uploading` / `meta`
 * state, because nothing can be uploaded at pick time — `POST /api/attachments`
 * requires an `agent_instance_id`, and on this page no instance exists until
 * `spawn-session` returns. See `handleSubmit` for the deferred-upload order. */
interface PendingImage {
  key: string;
  previewUrl: string;
  file: File;
  isImage: boolean;
}

/**
 * Tell the chat page whether a first message is on its way, so it shows the
 * "Starting your session" loader instead of the idle "Session ready" state
 * (web's equivalent of mobile's hasInitialPrompt nav arg).
 */
function markSessionHasPrompt(instanceId: string, hasPrompt: boolean) {
  try {
    if (instanceId) {
      sessionStorage.setItem(`vicoa.session.${instanceId}.hasPrompt`, hasPrompt ? '1' : '0');
    }
  } catch { /* sessionStorage unavailable — chat page falls back to idle */ }
}

/**
 * Hand a new worktree's setup commands (from the spawn-session result) to the
 * session view, which auto-opens a terminal and runs them there — visibly. Same
 * one-app-run sessionStorage hand-off as markSessionHasPrompt; the FilesGitPanel
 * reads and clears it once, so setup never re-runs on a later visit.
 *
 * `trusted` is the daemon's verdict on the committed vicoa.json (false for a repo
 * the user hasn't approved on this machine → the panel confirms before running);
 * `sourceRepo` is the checkout the commands came from, needed to grant trust.
 */
function markSessionSetupCommands(
  instanceId: string,
  payload: {
    commands: string[];
    trusted: boolean;
    sourceRepo: string;
    env: Record<string, string>;
  },
) {
  try {
    if (instanceId && payload.commands.length > 0) {
      sessionStorage.setItem(
        `vicoa.session.${instanceId}.setupCommands`,
        JSON.stringify(payload),
      );
    }
  } catch { /* sessionStorage unavailable — setup just won't auto-run */ }
}

/** Upload one picked image against a now-existing instance. Resolves to the
 * attachment id, or null when the upload failed — the caller sends whatever
 * made it through rather than failing the (already created) session. */
async function uploadImageAttachment(instanceId: string, file: File): Promise<string | null> {
  try {
    const formData = new FormData();
    formData.append('agent_instance_id', instanceId);
    formData.append('file', file);
    const response = await fetch('/api/attachments', { method: 'POST', body: formData });
    if (!response.ok) throw new Error(`upload failed (${response.status})`);
    const meta = (await response.json()) as ChatUploadedAttachment;
    return meta.id;
  } catch (error) {
    console.error('Attachment upload failed:', error);
    return null;
  }
}

// Shared className for every dropdown popup on this page. The defaults from
// shadcn's DropdownMenuContent (border + shadow-md) sit too close visually
// to the muted-toned trigger buttons; we lift the popup with a thicker,
// higher-contrast border and a bigger drop shadow so it clearly reads as a
// surface ABOVE the trigger rather than an extension of it.
const LIFTED_DROPDOWN_CLASSES =
  'w-[var(--radix-dropdown-menu-trigger-width)] py-1 font-mono ' +
  'border border-foreground/15 shadow-xl';
const LIFTED_DROPDOWN_SIDE_OFFSET = 8;

/** Setup chips above the prompt box (machine · directory · worktree).
    Same surface as the prompt box; hover ≈ the dropdown-item highlight
    composited over it. */
const SETUP_CHIP_CLASS =
  'flex h-7 min-w-0 items-center gap-1.5 rounded-lg bg-background dark:bg-menu px-2.5 text-xs font-mono text-foreground/90 transition-colors hover:bg-menu-elevated disabled:cursor-not-allowed disabled:opacity-50';

/**
 * Compose the initial prompt seeded from a task (plan §6): the task title +
 * body on top, the chosen sub-tasks as a numbered checklist below, then any
 * extra text the user typed. Empty sections are omitted, so a task with no
 * body/sub-tasks/extra simply yields its title.
 */
function composeTaskPrompt(
  task: TaskResponse,
  subtasks: TaskResponse[],
  extra: string,
): string {
  const parts: string[] = [task.title];
  const body = task.description?.trim();
  if (body) parts.push(body);
  if (subtasks.length > 0) {
    const lines = subtasks.map((sub, i) => {
      const subBody = sub.description?.trim();
      return subBody ? `${i + 1}. ${sub.title}\n${subBody}` : `${i + 1}. ${sub.title}`;
    });
    parts.push(`Subtasks:\n${lines.join('\n\n')}`);
  }
  if (extra) parts.push(extra);
  return parts.join('\n\n').trim();
}

/**
 * Fold a live `machine-update` (a canonical WS row) into the machine list and
 * re-sort online-first — the same shape the 30s poll produces, but applied the
 * instant a daemon connects or heartbeats instead of up to 30s later.
 *
 * The WS body and the REST `MachineSummary` disagree on two field names
 * (`id`→`machine_id`, `machine_metadata`→`metadata`) and the body omits the
 * top-level `recent_directories`; we map the names and recover recent dirs from
 * the metadata blob (where the backend stores them), falling back to an existing
 * row's list so a heartbeat frame never blanks them.
 */
function mergeMachineUpdate(list: MachineSummary[], body: MachineBody): MachineSummary[] {
  const existing = list.find((m) => m.machine_id === body.id);
  const metadata = body.machine_metadata ?? existing?.metadata ?? null;
  const recentFromMeta =
    metadata && Array.isArray((metadata as Record<string, unknown>).recent_directories)
      ? ((metadata as Record<string, unknown>).recent_directories as unknown[]).map(String)
      : undefined;
  const merged: MachineSummary = {
    ...(existing ?? { machine_id: body.id, recent_directories: [] }),
    machine_id: body.id,
    display_name: body.display_name,
    hostname: body.hostname,
    platform: body.platform,
    home_dir: body.home_dir,
    last_heartbeat_at: body.last_heartbeat_at,
    metadata,
    recent_directories: recentFromMeta ?? existing?.recent_directories ?? [],
  };
  const next = existing
    ? list.map((m) => (m.machine_id === body.id ? merged : m))
    : [...list, merged];
  return sortMachinesOnlineFirstShared(next);
}

function NewSessionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // `?directory=` preselects the project folder (the sidebar's per-project "+").
  // Held in a ref and consumed once, so a later machine reload falls back to
  // that machine's own default instead of snapping back to the link's folder.
  const directoryParam = searchParams.get('directory');
  const pendingDirectoryRef = useRef<string | null>(directoryParam);
  // The sidebar's per-worktree "+" links here with `?directory=<worktree path>
  // &worktreeBranch=<branch>`; we preselect that worktree instead of starting
  // on "current branch". Consumed once (see the clear effect below), so a later
  // directory change falls back to the normal "none" default.
  const pendingWorktreeRef = useRef<{ path: string; branch: string } | null>(
    (() => {
      const dir = searchParams.get('directory');
      const branch = searchParams.get('worktreeBranch');
      return dir && branch ? { path: dir, branch } : null;
    })(),
  );
  // `?taskId=` (the Tasks page's "Start session" action) preselects the Task
  // chip. Read reactively rather than snapshotted into a ref at first render
  // like the two above: this page renders inside a Suspense boundary under PPR
  // (`experimental.ppr`, next.config.ts), so `useSearchParams()` can resolve a
  // render late and a first-render snapshot latches `null` and drops the link.
  // `consumedTaskIdRef` keeps it single-shot — once loaded, clearing the chip
  // must not re-select the task on the next render.
  const taskIdParam = searchParams.get('taskId');
  // Sub-task ids chosen in the Tasks "Start session" dialog, carried via URL.
  const subtaskIdsParam = searchParams.get('subtasks');
  const selectedSubtaskIds = useMemo(
    () =>
      new Set(
        (subtaskIdsParam ?? '')
          .split(',')
          .map((id) => id.trim())
          .filter(Boolean),
      ),
    [subtaskIdsParam],
  );
  const consumedTaskIdRef = useRef<string | null>(null);
  // `${taskId}:${machineId}` pairs whose project folder has already been
  // applied — see the resolution effect below.
  const appliedTaskDirectoriesRef = useRef<Set<string>>(new Set());
  // Persisted setup restore (machine/dir already handled inline; these carry the
  // one-shot worktree + task restores):
  //  - a persisted worktree can't be applied until its machine+directory land,
  //    so it's armed here in loadMachines and consumed by the clear/restore
  //    effect once they match (mirrors pendingWorktreeRef for the sidebar link);
  //  - restoredTaskId dedupes the persisted-task fetch to one shot and lets the
  //    async result bail if the user has since picked/cleared a task.
  const pendingWorktreeRestoreRef = useRef<
    { machineId: string; directory: string; mode: WorktreeMode; path: string | null; branch: string | null } | null
  >(null);
  const restoredTaskIdRef = useRef<string | null>(null);
  // Gates the reactive setup-persist effect: stays false until the first machine
  // load restores machine+directory, so we never overwrite the stored setup with
  // empty pre-hydration state.
  const hydratedRef = useRef(false);
  const { api, refreshData } = useAgentDashboard();
  // Right panel (files/git/terminal) for the selected project folder, before a
  // session exists — mirrors the chat page's panel.
  const panel = usePanelState('new-session');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const promptContainerRef = useRef<HTMLDivElement>(null);

  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const [isLoadingMachines, setIsLoadingMachines] = useState(false);
  const [selectedMachineId, setSelectedMachineId] = useState<string>('');
  const [directory, setDirectory] = useState('');
  // Worktree selection (only when the machine advertises worktree support).
  // `none` keeps today's spawn-in-directory behavior.
  const [worktreeMode, setWorktreeMode] = useState<WorktreeMode>('none');
  const [selectedWorktreePath, setSelectedWorktreePath] = useState<string | null>(null);
  // Branch of the selected existing worktree, for the chip label (the path
  // basename is just the repo name, so it can't stand in for the branch).
  const [selectedWorktreeBranch, setSelectedWorktreeBranch] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');
  // Task seeding this session (plan §6): its title/description + chosen sub-tasks
  // top the first prompt, and the spawned instance is linked back via task_id.
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);
  // Sub-tasks chosen in the Start-session dialog: seeded into the prompt and
  // advanced to in_progress with the parent when the session starts.
  const [subtasks, setSubtasks] = useState<TaskResponse[]>([]);
  // Projects, only for resolving the selected task's linked folder below.
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Catalog seeds from the baked-in fallback so dropdowns render instantly
  // on cold start; the live catalog refreshes in the background (plan §3.11).
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [perAgentConfigs, setPerAgentConfigs] = useState<Record<string, SessionConfig>>({});
  const [activeAgent, setActiveAgent] = useState<string>('claude');
  // Selected machine's cached real per-agent model lists, fetched lazily so the
  // picker can show actual models instead of catalog placeholders.
  const [cachedAgentModels, setCachedAgentModels] = useState<Record<string, { id: string; label: string }[]>>({});

  // Slash-command + mention state for the prompt box (mirrors the chat input).
  const [showSlashCommands, setShowSlashCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const commandListRef = useRef<HTMLDivElement>(null);
  // Caret the slash menu is anchored to (the "/word" the query came from),
  // captured on the last change so selection replaces the right word even after
  // the textarea blurs on a suggestion click; live selectionStart wins when the
  // field is still focused.
  const slashCaretRef = useRef(0);
  const currentCaret = useCallback(
    () => textareaRef.current?.selectionStart ?? slashCaretRef.current,
    [],
  );
  // Bumped by the Add-to-chat "+" menu's "Mention files" action.
  const [mentionSignal, setMentionSignal] = useState(0);

  // Images attached to the first message. Held locally (File + object-URL
  // preview) and uploaded only once the session exists — see `handleSubmit`.
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  pendingImagesRef.current = pendingImages;
  // Pending folder references (absolute paths) — desktop "Add folder". Chips,
  // not uploads: expanded to `@path/` text and folded into the prompt on submit.
  const [pendingFolderRefs, setPendingFolderRefs] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Drag-drop onto the composer (mirrors the chat page): dropped files/images
  // become pending attachments and a dropped folder is referenced by @path/
  // (desktop) or its files upload (web) — see `collectComposerDrop`.
  // `dragDepthRef` counts enter/leave across nested children so the overlay
  // doesn't flicker as the cursor crosses them.
  const [isDropTarget, setIsDropTarget] = useState(false);
  const dragDepthRef = useRef(0);
  // Safety net: a drag that ends outside the page (Escape, dropped elsewhere,
  // or dragged back to the file explorer) never fires our own leave/drop, so
  // clear the overlay on any window-level end. `dragend`/`drop` cover a drop
  // somewhere in the window, but an OS file drag that leaves WITHOUT dropping
  // fires neither — `dragend` targets the drag's source node, which lives
  // outside our document. The one event that does fire when the pointer exits
  // the viewport is a window-level `dragleave` whose `relatedTarget` is null
  // (an internal element-to-element move always carries the entered element).
  useEffect(() => {
    if (!isDropTarget) return;
    const reset = () => {
      dragDepthRef.current = 0;
      setIsDropTarget(false);
    };
    const onWindowDragLeave = (e: DragEvent) => {
      if (!e.relatedTarget) reset();
    };
    window.addEventListener('drop', reset);
    window.addEventListener('dragend', reset);
    window.addEventListener('dragleave', onWindowDragLeave);
    return () => {
      window.removeEventListener('drop', reset);
      window.removeEventListener('dragend', reset);
      window.removeEventListener('dragleave', onWindowDragLeave);
    };
  }, [isDropTarget]);

  // Revoke any leftover preview object URLs on unmount.
  useEffect(() => () => {
    pendingImagesRef.current.forEach((img) => URL.revokeObjectURL(img.previewUrl));
  }, []);

  // Transient, self-clearing notice for rejected picks (too large / too many).
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const attachmentErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flashAttachmentError = useCallback((msg: string) => {
    setAttachmentError(msg);
    if (attachmentErrorTimer.current) clearTimeout(attachmentErrorTimer.current);
    attachmentErrorTimer.current = setTimeout(() => setAttachmentError(null), 5000);
  }, []);
  useEffect(() => () => {
    if (attachmentErrorTimer.current) clearTimeout(attachmentErrorTimer.current);
  }, []);

  // The catalog the picker renders: base catalog with the selected machine's
  // cached models merged in (falls back to base when nothing is cached).
  const effectiveCatalog = useMemo(
    () => catalogWithCachedModels(catalog, cachedAgentModels),
    [catalog, cachedAgentModels],
  );

  const sessionConfig: SessionConfig = perAgentConfigs[activeAgent] ?? defaultsFor(effectiveCatalog, activeAgent);
  // Map the (possibly ACP) selected agent onto the three command-bearing types.
  const slashAgentType: AgentType =
    sessionConfig.agent === 'codex' ? 'codex' : sessionConfig.agent === 'opencode' ? 'opencode' : 'claude';
  // Read the machine's live command/skill set the same way the chat composer
  // does: an unconditional `scan-commands` RPC for the selected directory.
  //
  // We deliberately DON'T pass `machine` here. Doing so gates the RPC on the
  // daemon advertising the `command-index` capability in its stored metadata,
  // but that metadata is unreliable — only register/agent-scan persist it (the
  // heartbeat drops the write), so a live daemon that DOES serve `scan-commands`
  // can still look incapable. When the gate false-negatives, the store silently
  // demotes to the CLI-synced DB copy, a single per-(user, agent) row that is
  // NOT scoped to the selected repo — so the current repo's project-local skills
  // (e.g. `<repo>/.claude/skills`) vanish, while the chat page (no gate) shows
  // them. The store still falls back to that DB copy on `no_handler`, so dropping
  // the gate only costs the one-time 3s grace window against a genuinely old daemon.
  const slashMachine = machines.find((m) => m.machine_id === selectedMachineId) || null;
  const slashOnline = slashMachine ? isMachineOnlineShared(slashMachine) : false;
  const { commands: slashCommands } = useSlashCommands({
    agentType: slashAgentType,
    machineId: slashOnline ? (slashMachine?.machine_id ?? null) : null,
    projectPath: toAbsolutePath(directory.trim() || undefined, slashMachine?.home_dir),
  });
  const hasSkills = slashAgentType === 'claude' || slashAgentType === 'opencode' || slashAgentType === 'codex';
  const activeAgentDef = useMemo(() => agentById(effectiveCatalog, sessionConfig.agent), [effectiveCatalog, sessionConfig.agent]);
  const activeModelDef = useMemo<CatalogModel | undefined>(
    () => activeAgentDef?.models?.find((m) => m.id === sessionConfig.model),
    [activeAgentDef, sessionConfig.model],
  );

  // Per-model filter: agent-level lists are the superset (labels + order);
  // opt_in entries (xhigh, auto) only appear when the active model names
  // them in its per-model array. Common entries are always shown.
  const visibleThinking: CatalogEnumEntry[] = useMemo(() => {
    if (!activeAgentDef?.thinking_efforts?.length) return [];
    const optIns = new Set(activeModelDef?.thinking_efforts ?? []);
    return activeAgentDef.thinking_efforts.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [activeAgentDef, activeModelDef]);

  const visibleReasoning: CatalogEnumEntry[] = activeAgentDef?.reasoning_efforts ?? [];

  const visiblePermission: CatalogEnumEntry[] = useMemo(() => {
    if (!activeAgentDef?.permission_modes?.length) return [];
    const optIns = new Set(activeModelDef?.permission_modes ?? []);
    return activeAgentDef.permission_modes.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [activeAgentDef, activeModelDef]);

  const visibleModes: CatalogEnumEntry[] = activeAgentDef?.modes ?? [];

  // Shared with the session list and the backend's own threshold — see
  // lib/session-liveness.ts. Previously a local copy using a 2-minute window,
  // which disagreed with both the other copy and the server.
  const isMachineOnline = useCallback(
    (machine: MachineSummary) => isMachineOnlineShared(machine),
    []
  );

  const getDisplayName = useCallback((machine: MachineSummary) => {
    return machine.display_name || machine.hostname || `Machine ${machine.machine_id.slice(0, 6)}`;
  }, []);

  const getRecentDirectories = useCallback((machine: MachineSummary): string[] => {
    if (Array.isArray(machine.recent_directories)) return machine.recent_directories;
    const meta = machine.metadata as Record<string, unknown> | null | undefined;
    if (meta && Array.isArray(meta.recent_directories)) {
      return (meta.recent_directories as unknown[]).map(String);
    }
    return [];
  }, []);

  const initialDirectoryForMachine = useCallback((machine: MachineSummary) => {
    const recent = getRecentDirectories(machine);
    if (recent.length > 0) return recent[0];
    const meta = machine.metadata as Record<string, unknown> | null | undefined;
    if (meta && typeof meta.home_dir === 'string' && meta.home_dir.length > 0) return meta.home_dir;
    return '~/';
  }, [getRecentDirectories]);

  // Hydrate persisted per-agent configs once on mount.
  useEffect(() => {
    const persisted = loadPersistedSelection();
    const next: Record<string, SessionConfig> = {};
    for (const agent of AGENT_CATALOG_FALLBACK.agents) {
      const stored = persisted.perAgent[agent.id];
      next[agent.id] = stored
        ? reconcileAgainst(stored, AGENT_CATALOG_FALLBACK)
        : defaultsFor(AGENT_CATALOG_FALLBACK, agent.id);
    }
    setPerAgentConfigs(next);
    if (persisted.lastAgent && next[persisted.lastAgent]) {
      setActiveAgent(persisted.lastAgent);
    }
  }, []);

  // Background catalog fetch — reconcile per-agent configs against the live
  // catalog when it arrives so opt_in additions and label changes propagate.
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api.getAgentCatalog()
      .then((fresh) => {
        if (cancelled) return;
        setCatalog(fresh);
        setPerAgentConfigs((prev) => {
          const next: Record<string, SessionConfig> = {};
          for (const agent of fresh.agents) {
            const prior = prev[agent.id];
            next[agent.id] = prior
              ? reconcileAgainst(prior, fresh)
              : defaultsFor(fresh, agent.id);
          }
          return next;
        });
      })
      .catch(() => { /* fallback already in state */ });
    return () => { cancelled = true; };
  }, [api]);

  // Warm the browser cache for every agent logo as soon as the catalog is
  // known. The Agent dropdown only mounts its items when opened, so without
  // this the non-selected logos would fetch-and-flash on first open; preloading
  // their real (unoptimized) SVG paths means they're already painted by then.
  useEffect(() => {
    for (const agent of catalog.agents) {
      const logo = getAgentLogoSrc(agent.id);
      if (logo) preload(logo.src, { as: 'image' });
    }
  }, [catalog]);

  // Fetch the selected machine's cached per-agent model lists so the picker can
  // show its real models. Best-effort: empty on error / no cache → catalog
  // defaults. Clears first so we never show another machine's models in flight.
  useEffect(() => {
    if (!api || !selectedMachineId) { setCachedAgentModels({}); return; }
    const machineId = selectedMachineId;
    let cancelled = false;
    setCachedAgentModels({});
    api.getMachineAgentModels(machineId)
      .then((models) => { if (!cancelled) setCachedAgentModels(models); })
      .catch(() => { /* keep catalog defaults */ });
    return () => { cancelled = true; };
  }, [api, selectedMachineId]);

  const persistSelection = useCallback(
    (overrides?: Partial<{ machineId: string; agent: string; configs: Record<string, SessionConfig> }>) => {
      savePersistedSelection({
        lastMachineId: overrides?.machineId ?? selectedMachineId,
        lastAgent: overrides?.agent ?? activeAgent,
        perAgent: overrides?.configs ?? perAgentConfigs,
      });
    },
    [selectedMachineId, activeAgent, perAgentConfigs],
  );

  // Patch a single field on the active agent's config. When `model` changes,
  // reconcile so per-model-gated values (e.g. `auto` after switching off
  // Opus 4.7+) snap back to the new model's default.
  const updateField = useCallback((patch: Partial<SessionConfig>) => {
    setPerAgentConfigs((prev) => {
      const current = prev[activeAgent] ?? defaultsFor(effectiveCatalog, activeAgent);
      const merged: SessionConfig = { ...current, ...patch, agent: activeAgent };
      const next = patch.model !== undefined ? reconcileAgainst(merged, effectiveCatalog) : merged;
      const updated = { ...prev, [activeAgent]: next };
      savePersistedSelection({
        lastMachineId: selectedMachineId,
        lastAgent: activeAgent,
        perAgent: updated,
      });
      return updated;
    });
  }, [activeAgent, effectiveCatalog, selectedMachineId]);

  // Switching agents is a different shape: the new agent has its own
  // remembered config, so just flip the active key.
  const switchAgent = useCallback((nextAgentId: string) => {
    setActiveAgent(nextAgentId);
    setPerAgentConfigs((prev) => {
      if (prev[nextAgentId]) return prev;
      return { ...prev, [nextAgentId]: defaultsFor(effectiveCatalog, nextAgentId) };
    });
    persistSelection({ agent: nextAgentId });
  }, [effectiveCatalog, persistSelection]);

  // Select/clear the task chip and persist the choice. Marking restoredTaskIdRef
  // supersedes any pending restore so a slow getTask can't overwrite the pick.
  const handleTaskChange = useCallback((task: TaskResponse | null) => {
    setSelectedTask(task);
    restoredTaskIdRef.current = task?.id ?? '';
    savePersistedSelection({ lastTaskId: task?.id });
  }, []);

  // Sort machines so online ones come first, then most-recently-seen first —
  // the dropdown lists them in this order, and the default selection picks the
  // first online (i.e. the freshest online machine) when there's no good
  // persisted choice.
  const sortMachinesOnlineFirst = useCallback(
    (list: MachineSummary[]) => sortMachinesOnlineFirstShared(list),
    [],
  );

  const loadMachines = useCallback(async () => {
    if (!api) {
      setErrorMessage('Unable to connect to the API. Ensure you are signed in.');
      return;
    }
    try {
      setIsLoadingMachines(true);
      setErrorMessage(null);
      const response = await api.listMachines();
      const sorted = sortMachinesOnlineFirst(response);
      setMachines(sorted);
      if (sorted.length > 0) {
        const persisted = loadPersistedSelection();
        const persistedMatch = sorted.find((m) => m.machine_id === persisted.lastMachineId);
        const firstOnline = sorted.find(isMachineOnline);
        // Prefer persisted if it's still online; otherwise the first online;
        // otherwise the first machine in the list (which is offline).
        const preferredMachine =
          persistedMatch && isMachineOnline(persistedMatch)
            ? persistedMatch
            : firstOnline ?? sorted[0];
        setSelectedMachineId(preferredMachine.machine_id);
        const pendingDirectory = pendingDirectoryRef.current;
        pendingDirectoryRef.current = null;
        // Restore the directory last used on THIS machine (persisted per
        // `lastMachineId`); a `?directory=` link still wins, and a different
        // machine falls back to its own default.
        const persistedDirectory =
          persisted.lastMachineId === preferredMachine.machine_id ? persisted.lastDirectory : undefined;
        const restoredDirectory =
          pendingDirectory ?? persistedDirectory ?? initialDirectoryForMachine(preferredMachine);
        setDirectory(restoredDirectory);
        // Only when the persisted directory is what we actually restored (no
        // link override) do we carry its worktree + task context:
        if (!pendingDirectory && persistedDirectory !== undefined && restoredDirectory === persistedDirectory) {
          // Arm the worktree restore for the clear/restore effect to apply once
          // machine+directory match (skipped for a plain 'none' selection).
          if (persisted.lastWorktree && persisted.lastWorktree.mode !== 'none') {
            pendingWorktreeRestoreRef.current = {
              machineId: preferredMachine.machine_id,
              directory: restoredDirectory,
              mode: persisted.lastWorktree.mode as WorktreeMode,
              path: persisted.lastWorktree.path ?? null,
              branch: persisted.lastWorktree.branch ?? null,
            };
          }
          // Mark the persisted task's folder as already-applied so the
          // task→project-directory effect leaves the restored directory alone
          // (the user's explicit last directory is authoritative).
          if (persisted.lastTaskId) {
            appliedTaskDirectoriesRef.current.add(`${persisted.lastTaskId}:${preferredMachine.machine_id}`);
          }
        }
        hydratedRef.current = true;
      } else {
        setSelectedMachineId('');
        setDirectory('~/');
        // The empty-list notice is derived at render (see `showNoMachinesNotice`)
        // so it clears the instant a daemon connects and returns when the last
        // one drops — rather than being latched here and going stale.
      }
    } catch {
      setMachines([]);
      setSelectedMachineId('');
      setErrorMessage('Failed to load machines. Please try again.');
    } finally {
      setIsLoadingMachines(false);
    }
  }, [api, initialDirectoryForMachine, isMachineOnline, sortMachinesOnlineFirst]);

  const silentRefreshMachines = useCallback(async () => {
    if (!api) return;
    try {
      const response = await api.listMachines();
      setMachines(sortMachinesOnlineFirst(response));
      // A successful fetch clears any stale load error ("Failed to load
      // machines…" / a past spawn failure); the empty-list case is handled by
      // the derived notice, not this banner.
      setErrorMessage(null);
    } catch { /* ignore */ }
  }, [api, sortMachinesOnlineFirst]);

  useEffect(() => { loadMachines(); }, [loadMachines]);

  // Realtime machine list over the shared WebSocket: a daemon connecting or
  // heartbeating broadcasts a `machine-update`, which we fold into the list at
  // once instead of waiting up to 30s for the poll. Reconnect (e.g. tab
  // refocus) re-runs the catch-up fetch, so the list is never stale on return.
  // Disconnect has no frame — that transition is handled by the liveness tick
  // below, not here.
  useMachineStream({
    enabled: !!api,
    onMachineUpdated: useCallback((body: MachineBody) => {
      setMachines((prev) => mergeMachineUpdate(prev, body));
    }, []),
  });

  // When machines appear while the page is open but nothing is selected — the
  // page opened with zero machines (composer disabled) and a daemon has since
  // connected over the WS — run the full loader so the same persisted
  // machine/directory/worktree/task restore path applies, rather than
  // duplicating it. loadMachines selects a machine, so this can't re-fire once
  // it lands (and won't fire in the normal case where a machine is already
  // selected).
  useEffect(() => {
    if (isLoadingMachines || selectedMachineId || machines.length === 0) return;
    void loadMachines();
  }, [machines.length, selectedMachineId, isLoadingMachines, loadMachines]);

  // Liveness clock. `isMachineOnline` is a function of elapsed time since the
  // last heartbeat, and the backend emits NO event when a daemon goes offline —
  // it simply stops beating. Without a periodic re-render the online dot would
  // keep claiming a dead machine is up until the next poll happened to re-render
  // the component. A cheap tick (no network) forces the online→offline flip on
  // schedule; connect is already instant via the WS stream above.
  const [, forceLivenessTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => forceLivenessTick((n) => n + 1), 15_000);
    return () => clearInterval(id);
  }, []);

  // Consume `?taskId=` once: fetch the task and preselect the Task chip. The
  // user can still deselect it or add extra prompt text before submitting.
  //
  // Deliberately NOT cancel-guarded. `api` is already non-null when this page
  // mounts (AgentDashboardProvider lives in the dashboard layout and survives
  // the client-side nav from /dashboard/tasks), so the fetch starts on the
  // mount pass — the one React StrictMode double-invokes in dev. A guard that
  // discards the first run's response strands the chip empty: the second run
  // returns synchronously at the `consumed` check below, long before the first
  // response lands, so there is nothing left to retry. `consumedTaskIdRef` is
  // the whole dedupe — one fetch per id, its result always applied.
  useEffect(() => {
    if (!api || !taskIdParam || consumedTaskIdRef.current === taskIdParam) return;
    consumedTaskIdRef.current = taskIdParam;
    api
      .getTask(taskIdParam)
      .then(setSelectedTask)
      .catch((error) => {
        // Re-arm so a transient failure can be retried on the next render.
        consumedTaskIdRef.current = null;
        console.error('Failed to load the linked task:', error);
      });
  }, [api, taskIdParam]);

  // Restore the task chip selected on a previous visit (persisted, cleared on
  // submit). A `?taskId=` link wins, so this only runs without one. Single-shot
  // via restoredTaskIdRef; the async result bails if the user has since
  // picked/cleared a task, and a deleted task self-heals by forgetting it.
  useEffect(() => {
    if (!api || taskIdParam || restoredTaskIdRef.current !== null) return;
    const persistedTaskId = loadPersistedSelection().lastTaskId;
    if (!persistedTaskId) return;
    restoredTaskIdRef.current = persistedTaskId;
    api
      .getTask(persistedTaskId)
      .then((task) => {
        if (restoredTaskIdRef.current === persistedTaskId) setSelectedTask(task);
      })
      .catch(() => {
        savePersistedSelection({ lastTaskId: undefined });
      });
  }, [api, taskIdParam]);

  // Resolve the sub-tasks the user picked in the Tasks "Start session" dialog
  // (their ids arrive via `?subtasks=`). There's no parent_task_id filter on the
  // list endpoint, so fetch the task's project and keep the chosen children
  // (sub-tasks inherit the parent's project when created in Tasks). Only applies
  // to the task named in the URL — switching tasks via the chip picker clears it.
  useEffect(() => {
    if (
      !api ||
      !selectedTask ||
      selectedTask.id !== taskIdParam ||
      selectedSubtaskIds.size === 0
    ) {
      setSubtasks([]);
      return;
    }
    let cancelled = false;
    api
      .listTasks({ projectId: selectedTask.project_id })
      .then((all) => {
        if (cancelled) return;
        const children = all
          .filter((t) => t.parent_task_id === selectedTask.id && selectedSubtaskIds.has(t.id))
          .sort(
            (a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at),
          );
        setSubtasks(children);
      })
      .catch((error) => {
        if (!cancelled) console.error('Failed to load sub-tasks for the prompt:', error);
      });
    return () => {
      cancelled = true;
    };
  }, [api, selectedTask, taskIdParam, selectedSubtaskIds]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .listProjects()
      .then((list) => { if (!cancelled) setProjects(list); })
      .catch(() => { /* no project links → machine defaults stand */ });
    return () => { cancelled = true; };
  }, [api]);

  // A project can be linked to a folder per machine (Tasks → ⚙ → Projects).
  // When a task is selected — from `?taskId=` or the chip picker — point this
  // session at its project's folder. Precedence:
  //   1. an explicit `?directory=` wins (the user clicked a specific folder in
  //      the sidebar, so the link must not override it);
  //   2. the link for the machine that's already selected;
  //   3. a link on any *online* machine, switching to it — an offline-only
  //      link is left alone so the existing "machine offline" messaging stays
  //      authoritative rather than stranding the user there;
  //   4. otherwise the machine's own default directory stands.
  // Applied at most once per (task, machine) pair so a folder the user edits
  // afterwards is never clobbered, while switching machines still re-resolves.
  useEffect(() => {
    if (!selectedTask || directoryParam || machines.length === 0) return;
    const key = `${selectedTask.id}:${selectedMachineId}`;
    if (appliedTaskDirectoriesRef.current.has(key)) return;

    const links = projects.find((p) => p.id === selectedTask.project_id)?.directories ?? [];
    if (links.length === 0) return;

    const forCurrentMachine = links.find((d) => d.machine_id === selectedMachineId);
    if (forCurrentMachine) {
      appliedTaskDirectoriesRef.current.add(key);
      setDirectory(forCurrentMachine.local_path);
      return;
    }

    const onlineLink = links.find((d) =>
      machines.some((m) => m.machine_id === d.machine_id && isMachineOnline(m)),
    );
    if (!onlineLink) return;
    appliedTaskDirectoriesRef.current.add(key);
    setSelectedMachineId(onlineLink.machine_id);
    setDirectory(onlineLink.local_path);
    persistSelection({ machineId: onlineLink.machine_id });
  }, [
    selectedTask,
    projects,
    machines,
    selectedMachineId,
    directoryParam,
    isMachineOnline,
    persistSelection,
  ]);

  useEffect(() => {
    const id = setInterval(silentRefreshMachines, MACHINE_REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [silentRefreshMachines]);

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.focus();
  }, []);

  // Restore an unsent prompt drafted on a previous visit; re-run the auto-resize
  // so a multi-line draft isn't clipped to one row. A `?prompt=` seed (e.g. the
  // Skills tab's "install/create a skill" button) takes precedence and is
  // consumed once — see the effect below.
  const seededPromptRef = useRef(false);
  useEffect(() => {
    if (seededPromptRef.current) return;
    const draft = loadPromptDraft();
    if (draft) {
      setPrompt(draft);
      requestAnimationFrame(autoResizeTextarea);
    }
    // Run once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Seed the prompt from a `?prompt=` param (deep link from another tab, e.g.
  // Skills → "Install or create a skill: "). Single-shot, and it strips only the
  // `prompt` param afterward so a refresh/back doesn't re-seed over the user's
  // edits while leaving any sibling params (taskId, directory) intact.
  useEffect(() => {
    if (seededPromptRef.current) return;
    const seed = searchParams.get('prompt');
    if (!seed) return;
    seededPromptRef.current = true;
    setPrompt(seed);
    savePromptDraft(seed);
    requestAnimationFrame(autoResizeTextarea);
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    params.delete('prompt');
    const qs = params.toString();
    router.replace(`/dashboard/agents/new-session${qs ? `?${qs}` : ''}`, { scroll: false });
    // autoResizeTextarea is a stable post-mount callback; listing it would force
    // this before its declaration below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, router]);

  // A worktree selection is tied to a specific machine + directory; clear it
  // whenever either changes so a stale path can't carry into a different repo.
  // Exception: a pending preselection from the sidebar's per-worktree "+" — when
  // the directory it targets first lands, apply it instead of clearing (consumed
  // once so subsequent directory edits clear normally).
  useEffect(() => {
    const preselect = pendingWorktreeRef.current;
    if (preselect && preselect.path === directory) {
      pendingWorktreeRef.current = null;
      setWorktreeMode('existing');
      setSelectedWorktreePath(preselect.path);
      setSelectedWorktreeBranch(preselect.branch);
      return;
    }
    // A persisted worktree restore (armed in loadMachines) applies once its
    // machine+directory land; any other change falls through to the clear below.
    const restore = pendingWorktreeRestoreRef.current;
    if (restore && restore.machineId === selectedMachineId && restore.directory === directory) {
      pendingWorktreeRestoreRef.current = null;
      setWorktreeMode(restore.mode);
      setSelectedWorktreePath(restore.path);
      setSelectedWorktreeBranch(restore.branch);
      return;
    }
    // Non-matching machine/directory change: drop any armed restore so a stale
    // one can't fire if the user later returns to that exact path.
    pendingWorktreeRestoreRef.current = null;
    setWorktreeMode('none');
    setSelectedWorktreePath(null);
    setSelectedWorktreeBranch(null);
  }, [selectedMachineId, directory]);

  // Re-apply the sidebar's per-project / per-worktree "+" link when it changes
  // while this page is ALREADY mounted. On a fresh navigation, loadMachines
  // (directory) and the worktree effect above (branch) consume these params
  // once at mount via pendingDirectoryRef/pendingWorktreeRef. But clicking a
  // different group's "+" pushes the same route with a new `?directory=`, which
  // does NOT remount the page — `useSearchParams()` updates, yet those refs are
  // already spent, so without this the URL changes and the chips don't. We
  // re-arm the same pendingWorktreeRef the mount path uses, then set the
  // directory; the worktree clear/restore effect above fires on that change and
  // applies the branch (or resets to `none` for a plain project link) in step.
  //
  // `appliedDirectoryLinkRef` is seeded with the mount-time link so this skips
  // what loadMachines already applied, and dedupes repeat clicks of the same
  // "+". Deliberately does NOT strip the param (a refresh should re-preselect,
  // matching cold-nav) or touch the machine (the "+" carries no machine, same
  // as the cold-nav path).
  const worktreeBranchParam = searchParams.get('worktreeBranch');
  const appliedDirectoryLinkRef = useRef<string | null>(
    directoryParam ? `${directoryParam}|${worktreeBranchParam ?? ''}` : null,
  );
  useEffect(() => {
    if (!directoryParam) return;
    const key = `${directoryParam}|${worktreeBranchParam ?? ''}`;
    if (appliedDirectoryLinkRef.current === key) return;
    appliedDirectoryLinkRef.current = key;
    pendingWorktreeRef.current = worktreeBranchParam
      ? { path: directoryParam, branch: worktreeBranchParam }
      : null;
    setDirectory(directoryParam);
  }, [directoryParam, worktreeBranchParam]);

  // Persist the machine/directory/worktree setup whenever it changes, so it is
  // restored on the next visit (agent + per-agent config persist separately via
  // updateField/switchAgent; task persists in its own handlers). Gated on
  // hydration so the empty pre-load state never overwrites the stored setup, and
  // `savePersistedSelection` merges so this leaves the agent fields untouched.
  useEffect(() => {
    if (!hydratedRef.current) return;
    savePersistedSelection({
      lastMachineId: selectedMachineId,
      lastDirectory: directory,
      lastWorktree:
        worktreeMode === 'none'
          ? undefined
          : { mode: worktreeMode, path: selectedWorktreePath, branch: selectedWorktreeBranch },
    });
  }, [selectedMachineId, directory, worktreeMode, selectedWorktreePath, selectedWorktreeBranch]);

  const autoResizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const newHeight = Math.max(36, Math.min(textarea.scrollHeight, 128));
      textarea.style.height = newHeight + 'px';
    }
  }, []);

  useEffect(() => { autoResizeTextarea(); }, [prompt, autoResizeTextarea]);

  // ⌘L (Ctrl+L on Windows) focuses the prompt — same shortcut the chat page
  // uses (desktop only; rebindable in Settings → Keyboard shortcuts). Capture
  // phase so a focused terminal/mention list can't eat it. `showFocusHint`
  // gates the placeholder-side hint to desktop, set post-mount so the SSR pass
  // stays consistent.
  const [showFocusHint, setShowFocusHint] = useState(false);
  useEffect(() => {
    if (getDesktopConfig() === null) return;
    setShowFocusHint(true);
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'focus-chat')) return;
      event.preventDefault();
      textareaRef.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, []);

  // Scroll the highlighted slash command into view on keyboard navigation.
  useEffect(() => {
    if (showSlashCommands && commandListRef.current) {
      const el = commandListRef.current.children[selectedCommandIndex] as HTMLElement | undefined;
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedCommandIndex, showSlashCommands]);

  // Close the slash dropdown on outside click / Escape.
  useEffect(() => {
    if (!showSlashCommands) return;
    const onClick = (e: MouseEvent) => {
      if (promptContainerRef.current && !promptContainerRef.current.contains(e.target as Node)) {
        setShowSlashCommands(false);
      }
    };
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowSlashCommands(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onEscape);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onEscape);
    };
  }, [showSlashCommands]);

  // Prompt change: keep the existing resize, then run the same "/" prefix
  // slash-command detection the chat input uses.
  const handlePromptChange = useCallback((value: string) => {
    setPrompt(value);
    savePromptDraft(value);
    autoResizeTextarea();
    // Caret-aware slash detection (mirrors the chat input): fires on a
    // "/command" word typed mid-draft and filters by that word alone, so an
    // existing draft or a typed argument no longer suppresses the menu.
    const caret = textareaRef.current?.selectionStart ?? value.length;
    const { active, query } = detectSlashCommand(value, caret);
    if (active) {
      slashCaretRef.current = caret;
      const matches = slashCommands.filter((cmd) => slashCommandMatches(cmd, query));
      setFilteredCommands(matches);
      setShowSlashCommands(matches.length > 0);
      setSelectedCommandIndex(0);
    } else {
      setShowSlashCommands(false);
    }
  }, [autoResizeTextarea, slashCommands]);

  // Add-to-chat "+" → "Mention files": insert "@" + open the mention panel.
  const handleInsertMention = useCallback(() => {
    setShowSlashCommands(false);
    setMentionSignal((n) => n + 1);
  }, []);

  // Add-to-chat "+" → "Add folder": desktop only. Native OS folder picker →
  // add the chosen folder as a chip (deduped); it becomes an @path/ reference
  // in the prompt on submit. Hidden on web (no real filesystem paths).
  const handleInsertFolder = useCallback(() => {
    const bridge = getDesktopShellBridge();
    if (!bridge) return;
    setShowSlashCommands(false);
    void bridge.pickFolder().then((path) => {
      if (!path) return;
      setPendingFolderRefs((prev) => (prev.includes(path) ? prev : [...prev, path]));
    });
  }, []);

  const removeFolderRef = useCallback((path: string) => {
    setPendingFolderRefs((prev) => prev.filter((p) => p !== path));
  }, []);

  // Add-to-chat "+" → "Add files": open the system file picker. Deferred a
  // frame so the dropdown closes before the (focus-stealing) dialog opens.
  const handleAddFiles = useCallback(() => {
    requestAnimationFrame(() => fileInputRef.current?.click());
  }, []);

  // Core add path shared by the file picker and the drag-drop handler: applies
  // the per-message count/size caps, then holds each survivor as a local
  // preview (uploaded only once the session exists — see `handleSubmit`).
  const addPickedFiles = useCallback((picked: File[]) => {
    if (picked.length === 0) return;
    const room = MAX_ATTACHMENTS_PER_MESSAGE - pendingImagesRef.current.length;
    if (room <= 0) {
      flashAttachmentError(`You can attach up to ${MAX_ATTACHMENTS_PER_MESSAGE} files per message.`);
      return;
    }
    const withinSize = picked.filter((file) => file.size <= MAX_ATTACHMENT_BYTES);
    const selected = withinSize.slice(0, room);
    if (withinSize.length < picked.length) {
      flashAttachmentError(`Files over ${MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB were skipped.`);
    } else if (selected.length < picked.length) {
      flashAttachmentError(`Only ${MAX_ATTACHMENTS_PER_MESSAGE} files can be attached per message.`);
    }
    for (const file of selected) {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setPendingImages((prev) => [...prev, {
        key,
        file,
        previewUrl: URL.createObjectURL(file),
        isImage: file.type.startsWith('image/'),
      }]);
    }
  }, [flashAttachmentError]);

  const handleFilesSelected = useCallback((files: FileList | null) => {
    if (files) addPickedFiles(Array.from(files));
    // Allow re-picking the same file later.
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [addPickedFiles]);

  // Add desktop-resolved folder paths from a drop as chips (deduped), the same
  // shape the "Add folder" action produces — expanded to @path/ on submit.
  const addDroppedFolderRefs = useCallback((paths: string[]) => {
    if (paths.length === 0) return;
    setPendingFolderRefs((prev) => {
      const next = [...prev];
      for (const path of paths) if (!next.includes(path)) next.push(path);
      return next;
    });
  }, []);

  const removeImage = useCallback((key: string) => {
    setPendingImages((prev) => {
      const target = prev.find((img) => img.key === key);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((img) => img.key !== key);
    });
  }, []);

  // Add-to-chat "+" → commands: insert "/" and surface the full command list.
  const handleInsertSlash = useCallback(() => {
    const next = prompt.trim().length === 0 ? '/' : `/ ${prompt}`;
    setPrompt(next);
    savePromptDraft(next);
    setFilteredCommands(slashCommands);
    setShowSlashCommands(slashCommands.length > 0);
    setSelectedCommandIndex(0);
    // Caret parks right after the "/" (before any preserved draft) so the next
    // keystroke filters the command word — where the menu is anchored.
    slashCaretRef.current = 1;
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus({ preventScroll: true });
        el.setSelectionRange(1, 1);
      }
    });
  }, [prompt, slashCommands]);

  const handleSubmit = useCallback(async () => {
    if (!api || !selectedMachineId || !directory.trim() || isSubmitting) return;

    // Where the user launched from. Spawning is async (RPC + waitForEntity), and
    // if they navigate away before it finishes we must not yank them to the new
    // session — see openCreatedSession below.
    const startPath = currentPathname();

    try {
      setIsSubmitting(true);
      setErrorMessage(null);

      const trimmedPrompt = prompt.trim();
      // A selected task seeds the prompt: task title/body + open sub-tasks on
      // top, any extra typed prompt below (plan §6).
      const composedPrompt = selectedTask
        ? composeTaskPrompt(selectedTask, subtasks, trimmedPrompt)
        : trimmedPrompt;
      // Folder chips expand to `@path/` references (project-relative when inside
      // the chosen directory) folded onto the end of the prompt.
      const machine = machines.find((m) => m.machine_id === selectedMachineId) || null;
      const projectPath = toAbsolutePath(directory.trim() || undefined, machine?.home_dir);
      const folderText = pendingFolderRefs
        .map((p) => `@${folderPathToMention(p, projectPath)}`)
        .join(' ');
      const finalPrompt = [composedPrompt, folderText].filter(Boolean).join(' ');
      const images = pendingImages;

      // With images attached the prompt can NOT ride along in the spawn
      // metadata: attachments upload against an agent_instance_id that doesn't
      // exist yet, so the prompt has to wait and travel with them as the first
      // chat message once the session is up (see below).
      // No images → unchanged: the prompt spawns with the session, and no
      // prompt at all starts the session with no initial message (the chat
      // shows "Session ready / Waiting for messages"); don't inject a "Hi".
      const metadata = toSpawnMetadata(
        sessionConfig,
        images.length > 0 ? undefined : finalPrompt || undefined,
      );

      // Map the worktree selection onto the spawn directory + optional param.
      const spawn = resolveWorktreeSpawn({
        mode: worktreeMode,
        baseDirectory: directory.trim(),
        selectedWorktreePath,
      });

      const result = await getWsClient().callRpc(
        selectedMachineId,
        'spawn-session',
        {
          directory: spawn.directory,
          agent: sessionConfig.agent,
          metadata,
          ...(spawn.worktree ? { worktree: spawn.worktree } : {}),
        },
      );
      if (result.error) {
        setErrorMessage(String(result.error));
        setIsSubmitting(false);
        return;
      }
      persistSelection();
      clearPromptDraft();
      // The task is consumed by this spawn — forget it so the next visit starts
      // task-free (machine/directory/worktree intentionally persist as context).
      restoredTaskIdRef.current = '';
      savePersistedSelection({ lastTaskId: undefined });
      // Drop the previews now that the session is committed; the `File`s are
      // captured in `images` above, so they survive this reset for the upload.
      images.forEach((img) => URL.revokeObjectURL(img.previewUrl));
      setPendingImages([]);
      setPendingFolderRefs([]);

      // `source` deliberately omitted: the super property registered in
      // instrumentation-client.ts supplies it, and event properties OVERRIDE
      // super properties — so hardcoding 'web' here counted every desktop
      // session as a web one. Deleting it is the whole fix: identical value on
      // web, correct value on desktop, no new key, no query migration.
      posthog.capture('session_created', { agent_type: sessionConfig.agent });
      if (typeof window !== 'undefined' &&
          localStorage.getItem('vicoa.hasCreatedFirstRemoteSession') !== '1') {
        localStorage.setItem('vicoa.hasCreatedFirstRemoteSession', '1');
        posthog.capture('first_remote_session_created', { agent_type: sessionConfig.agent });
      }

      const newInstanceId = String(result.agent_instance_id ?? '');
      // A prompt or images both mean a first message is on its way.
      markSessionHasPrompt(newInstanceId, !!finalPrompt || images.length > 0);
      // A fresh worktree may carry setup commands (committed vicoa.json) for the
      // session view to auto-run in its terminal. Absent for non-worktree spawns.
      markSessionSetupCommands(newInstanceId, {
        commands: Array.isArray(result.setup_commands)
          ? result.setup_commands.filter((c): c is string => typeof c === 'string')
          : [],
        trusted: result.setup_trusted === true,
        sourceRepo: spawn.directory,
        // VICOA_* hook env resolved by the daemon; the session view exports it
        // before typing setup into the terminal (that shell doesn't inherit it).
        env:
          result.setup_env && typeof result.setup_env === 'object'
            ? Object.fromEntries(
                Object.entries(result.setup_env as Record<string, unknown>).filter(
                  (entry): entry is [string, string] => typeof entry[1] === 'string',
                ),
              )
            : {},
      });
      await getWsClient().waitForEntity('agent_instances', newInstanceId);

      // Link the run to its task (§8b): the row exists now (waitForEntity),
      // and the backend re-evaluates the status linkage on this PATCH, so an
      // already-ACTIVE session still moves the task to in_progress. Failure
      // here must not strand the session — worst case the task stays unlinked.
      if (selectedTask && newInstanceId) {
        try {
          await api.updateAgentInstance(newInstanceId, { task_id: selectedTask.id });
        } catch (error) {
          console.error('Failed to link the session to its task:', error);
        }
        // Advance the chosen sub-tasks in step with the parent (the link above
        // flips it to in_progress). Best-effort per child — a failed PATCH must
        // not strand the already-created session.
        if (subtasks.length > 0) {
          await Promise.all(
            subtasks.map((sub) =>
              api
                .updateTask(sub.id, { status: 'in_progress' })
                .catch((error) => console.error('Failed to advance sub-task status:', error)),
            ),
          );
        }
      }

      // Deferred upload: only now does an instance id exist to bind the images
      // to. The session is ALREADY created at this point, so nothing below may
      // strand the user — a partial failure sends whatever uploaded, a total
      // failure still sends the text, and we navigate either way.
      if (images.length > 0 && newInstanceId) {
        const uploaded = await Promise.all(
          images.map((img) => uploadImageAttachment(newInstanceId, img.file)),
        );
        // Order is preserved so the images arrive as the user arranged them.
        const attachmentIds = uploaded.filter((id): id is string => id !== null);
        const failedCount = images.length - attachmentIds.length;
        let problem = failedCount > 0
          ? `${failedCount} image${failedCount > 1 ? 's' : ''} couldn't be uploaded — the session started without ${failedCount > 1 ? 'them' : 'it'}.`
          : null;

        if (attachmentIds.length > 0 || finalPrompt) {
          try {
            // Empty content is valid when attachments ride along (matches the
            // chat input, which sends images with no text).
            await postInstanceMessage(newInstanceId, finalPrompt, attachmentIds);
          } catch (error) {
            console.error('Failed to send the first message:', error);
            markSessionHasPrompt(newInstanceId, false);
            problem = 'The session started, but its first message could not be sent — please resend it in the chat.';
          }
        } else {
          // Every upload failed and there was no text: nothing left to send, so
          // let the chat show its idle state rather than a loader that never ends.
          markSessionHasPrompt(newInstanceId, false);
        }
        if (problem) alert(problem);
      }

      refreshData();
      // Only open the session if the user is still on the page they launched
      // from; if they moved on during the spawn, leave them where they are (the
      // session is already in the sidebar via refreshData).
      openCreatedSession(router, startPath, `/dashboard/agents/${newInstanceId}`);
    } catch (error) {
      let message = 'Failed to start session. Please verify the daemon is running.';
      if (error instanceof RpcError) {
        if (error.code === 'no_handler') {
          message = 'That machine is offline. Make sure the Vicoa daemon is running.';
        } else if (error.code === 'timeout') {
          message = "The daemon didn't respond in time. It may be busy — try again.";
        } else if (error.code === 'target_disconnected') {
          message = 'The daemon disconnected before responding. Try again in a moment.';
        }
      }
      setErrorMessage(message);
      setIsSubmitting(false);
    }
  }, [api, selectedMachineId, directory, sessionConfig, prompt, selectedTask, subtasks, pendingImages, pendingFolderRefs, machines, isSubmitting, worktreeMode, selectedWorktreePath, persistSelection, refreshData, router]);

  // Insert the highlighted command into the prompt (vs. the chat input, which
  // sends immediately — starting a session is heavier, so we let the user
  // review before submitting).
  const insertSelectedCommand = useCallback(() => {
    const cmd = filteredCommands[selectedCommandIndex];
    if (!cmd) return;
    const { value: next, cursor } = applySlashCommandSelection(prompt, commandInsertText(cmd), currentCaret());
    setPrompt(next);
    savePromptDraft(next);
    setShowSlashCommands(false);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) { el.focus({ preventScroll: true }); el.setSelectionRange(cursor, cursor); }
    });
  }, [filteredCommands, selectedCommandIndex, prompt, currentCaret]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashCommands && filteredCommands.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedCommandIndex((p) => (p < filteredCommands.length - 1 ? p + 1 : 0));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedCommandIndex((p) => (p > 0 ? p - 1 : filteredCommands.length - 1));
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        insertSelectedCommand();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlashCommands(false);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const currentMachine = machines.find((m) => m.machine_id === selectedMachineId) || null;
  const recentDirectories = currentMachine ? getRecentDirectories(currentMachine) : [];
  const isOnline = currentMachine ? isMachineOnline(currentMachine) : false;
  // Derived empty-machine notice — recomputed every render (incl. the liveness
  // tick), so it clears the instant a daemon connects and reappears when the
  // last one drops. Suppressed while a real error banner is showing.
  const showNoMachinesNotice =
    !!api && !isLoadingMachines && machines.length === 0 && !errorMessage;
  const canSubmit = !isSubmitting && !!api && !!selectedMachineId && !!directory.trim() && isOnline;

  // Live Claude plan usage (Session/Weekly limits) for the selected machine,
  // fetched from its daemon when the page opens — so limits are visible before
  // committing to a session. Claude-only: the daemon reads the Claude Code
  // OAuth credential; other agents have no on-demand source.
  const claudeUsageFetch = useMemo(() => {
    if (sessionConfig.agent !== 'claude' || !selectedMachineId || !isOnline) return undefined;
    const machineId = selectedMachineId;
    return () => fetchClaudeUsageWindows(machineId);
  }, [sessionConfig.agent, selectedMachineId, isOnline]);

  // Current branch of the selected directory (worktree chip label). Best
  // effort: offline machine / not a repo / RPC error just keeps the fallback.
  const [currentBranch, setCurrentBranch] = useState<string | null>(null);
  // Whether that directory is a git repo — gates the worktree chip, since
  // worktrees are meaningless in a plain folder. `null` means unknown (offline
  // machine or a failed probe) and keeps the chip visible, so a transport
  // hiccup can't strip the option off a real repo. The previous answer is held
  // while a probe is in flight so the chip doesn't blink when moving between
  // two non-repo folders.
  const [isGitRepo, setIsGitRepo] = useState<boolean | null>(null);
  useEffect(() => {
    setCurrentBranch(null);
    const cwd = directory.trim();
    if (!selectedMachineId || !cwd || !isOnline) {
      setIsGitRepo(null);
      return;
    }
    let cancelled = false;
    rpcGitStatus(selectedMachineId, cwd)
      .then((status) => {
        if (cancelled) return;
        setCurrentBranch(status.branch);
        setIsGitRepo(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setCurrentBranch(null);
        // Only the daemon's definitive `not_a_repo` hides the chip; any other
        // failure falls back to unknown.
        setIsGitRepo(e instanceof RpcError && e.code === 'not_a_repo' ? false : null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMachineId, directory, isOnline]);

  const modelEntries = activeAgentDef?.models ?? null;
  const agentEntries = catalog.agents.map((a) => ({ id: a.id, label: agentPickerLabel(a.id, a.label) }));

  // Drag-drop is offered only while a session can actually be started (a
  // machine picked, online, a working directory set) — same gate as the "Add
  // files" affordance — so a drop never lands where it can't be sent.
  const isFileDrag = (e: React.DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes('Files');
  const handleDropDragEnter = (e: React.DragEvent) => {
    if (!canSubmit || !isFileDrag(e)) return;
    e.preventDefault();
    dragDepthRef.current += 1;
    setIsDropTarget(true);
  };
  const handleDropDragOver = (e: React.DragEvent) => {
    if (!canSubmit || !isFileDrag(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };
  const handleDropDragLeave = (e: React.DragEvent) => {
    if (!canSubmit || !isFileDrag(e)) return;
    dragDepthRef.current -= 1;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setIsDropTarget(false);
    }
  };
  const handleDropFiles = (e: React.DragEvent) => {
    if (!canSubmit || !isFileDrag(e)) return;
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDropTarget(false);
    // Snapshots the transfer synchronously, then resolves across awaits.
    void collectComposerDrop(e.dataTransfer).then(({ files, folderPaths }) => {
      if (folderPaths.length > 0) addDroppedFolderRefs(folderPaths);
      if (files.length > 0) addPickedFiles(files);
    });
  };

  return (
    <div className="h-full flex">
      <div
        className="relative h-full flex-1 flex flex-col min-w-0"
        onDragEnter={handleDropDragEnter}
        onDragOver={handleDropDragOver}
        onDragLeave={handleDropDragLeave}
        onDrop={handleDropFiles}
      >
      {isDropTarget && (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-background/70 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-primary/60 bg-background/80 px-8 py-6 text-center shadow-lg">
            <FolderPlus className="h-7 w-7 text-primary" />
            <span className="text-sm font-medium text-foreground">Drop to attach</span>
          </div>
        </div>
      )}
      {/* Header. On desktop this is the window's top strip: a drag region that
          hosts the collapsed-sidebar lead (brand + expand — clears the macOS
          traffic lights when the sidebar is hidden) and reserves the Windows
          controls when the right panel is closed. Interactive children opt out
          with NO_DRAG. */}
      <div style={DRAG_REGION} className="flex items-center justify-between pl-2 xl:pl-6 pr-2 py-2 flex-shrink-0">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <DesktopCollapsedLead />
          <h1 className="text-sm font-normal font-mono text-muted-foreground">New Session</h1>
        </div>
        <div style={NO_DRAG} className="flex items-center gap-0.5">
          <FilesGitPanelToggle open={panel.open} onToggle={panel.toggleOpen} />
          {!panel.open && <DesktopWindowControlsSpacer />}
        </div>
      </div>

      {/* Main area — banners at the top, hero centered in the remaining space.
          All selectors live as chips around the prompt box below. */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 pb-32 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20">
        <div className="max-w-4xl mx-auto flex h-full flex-col">
          {(errorMessage || showNoMachinesNotice || (currentMachine && !isOnline)) && (
            <div className="space-y-4">
              {errorMessage && (
                <div className="bg-destructive/10 text-destructive text-sm px-3 py-2 rounded-lg font-mono">
                  {errorMessage}
                </div>
              )}
              {showNoMachinesNotice && (
                <div className="bg-muted text-muted-foreground text-sm px-3 py-2 rounded-lg font-mono">
                  No machines connected. Run{' '}
                  <code className="text-foreground">vicoa daemon</code> to connect this machine.
                </div>
              )}
              {currentMachine && !isOnline && (
                <div className="bg-orange-500/10 text-orange-600 dark:text-orange-500 text-sm px-3 py-2 rounded-lg font-mono">
                  This machine is currently offline. Sessions can only be started on online machines.
                </div>
              )}
            </div>
          )}
          <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6">
            <Image
              src="/images/vicoa-light.webp"
              alt=""
              aria-hidden
              width={0}
              height={0}
              sizes="100vw"
              className="h-12 w-auto opacity-90"
            />
            <h1 className="text-center font-mono text-2xl font-light text-foreground">
              What should we build
              {directory.trim() ? (
                <>
                  {' '}in{' '}
                  <span className="underline decoration-muted-foreground/50 decoration-dotted underline-offset-8">
                    {directory.replace(/\/+$/, '').split('/').pop() || directory}
                  </span>
                </>
              ) : null}
              ?
            </h1>
          </div>
        </div>
      </div>

      {/* Chat-style input pinned to bottom */}
      <div className="flex-shrink-0 p-4">
        <div className="max-w-4xl mx-auto">
          {/* Setup chips: machine · working dir · worktree (when supported) */}
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild disabled={isLoadingMachines || !api || machines.length === 0}>
                <button type="button" title="Machine" className={SETUP_CHIP_CLASS}>
                  <Monitor className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                  {isLoadingMachines ? (
                    <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                  ) : currentMachine ? (
                    <>
                      <span className="max-w-32 truncate">{getDisplayName(currentMachine)}</span>
                      <Circle
                        className={`h-1.5 w-1.5 flex-shrink-0 ${isOnline ? 'fill-green-500 text-green-500' : 'fill-muted-foreground/30 text-muted-foreground/30'}`}
                        strokeWidth={0}
                      />
                    </>
                  ) : (
                    <span className="text-muted-foreground">No machines</span>
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="w-64 font-mono">
                {machines.map((m) => {
                  const online = isMachineOnline(m);
                  const isCurrentlySelected = m.machine_id === selectedMachineId;
                  return (
                    <DropdownMenuItem
                      key={m.machine_id}
                      onClick={() => {
                        setSelectedMachineId(m.machine_id);
                        setDirectory(initialDirectoryForMachine(m));
                        persistSelection({ machineId: m.machine_id });
                      }}
                      className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
                    >
                      <span className={`inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full ${online ? 'bg-green-500' : 'bg-muted-foreground/30'}`} />
                      <span className={`flex-1 truncate ${!online ? 'text-muted-foreground' : ''}`}>{getDisplayName(m)}</span>
                      {isCurrentlySelected && <Check className="h-3.5 w-3.5 ml-auto flex-shrink-0" />}
                    </DropdownMenuItem>
                  );
                })}
                <DropdownMenuItem
                  disabled={isLoadingMachines || !api}
                  onSelect={(event) => {
                    event.preventDefault();
                    loadMachines();
                  }}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer text-muted-foreground"
                >
                  {isLoadingMachines ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                  Refresh machines
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <DirectoryPickerPopover
              value={directory}
              onChange={setDirectory}
              recentDirectories={recentDirectories}
              disabled={!api || machines.length === 0 || !isOnline}
            >
              <button
                type="button"
                title={directory.trim() || 'Working directory'}
                className={SETUP_CHIP_CLASS}
                disabled={!api || machines.length === 0 || !isOnline}
              >
                <Folder className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                <span className={`max-w-44 truncate ${directory.trim() ? '' : 'text-muted-foreground/60'}`}>
                  {directory.trim()
                    ? (directory.replace(/\/+$/, '').split('/').pop() || directory)
                    : 'Choose folder'}
                </span>
              </button>
            </DirectoryPickerPopover>

            {currentMachine && machineSupportsWorktree(currentMachine) && isGitRepo !== false && (
              <WorktreePickerPopover
                machineId={selectedMachineId}
                cwd={directory}
                mode={worktreeMode}
                selectedPath={selectedWorktreePath}
                onSelect={(m, path, branch) => {
                  setWorktreeMode(m);
                  setSelectedWorktreePath(path);
                  setSelectedWorktreeBranch(branch || null);
                }}
                side="top"
                disabled={!api || !isOnline || !directory.trim()}
              >
                <button
                  type="button"
                  title="Worktree"
                  className={SETUP_CHIP_CLASS}
                  disabled={!api || !isOnline || !directory.trim()}
                >
                  <GitBranch className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                  <span className="max-w-36 truncate">
                    {worktreeMode === 'none'
                      ? (currentBranch ?? 'Current branch')
                      : worktreeMode === 'new'
                        ? 'New worktree'
                        : (selectedWorktreeBranch
                            ?? selectedWorktreePath?.split('/').filter(Boolean).pop()
                            ?? 'Worktree')}
                  </span>
                </button>
              </WorktreePickerPopover>
            )}

            <TaskPickerPopover
              selectedTask={selectedTask}
              onSelect={handleTaskChange}
              disabled={!api}
            >
              <button
                type="button"
                title={selectedTask ? selectedTask.title : 'Seed this session from a task'}
                className={SETUP_CHIP_CLASS}
                disabled={!api}
              >
                <ListTodo className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                <span className={`max-w-36 truncate ${selectedTask ? '' : 'text-muted-foreground/60'}`}>
                  {selectedTask ? selectedTask.title : 'Choose task'}
                </span>
                {selectedTask && (
                  <X
                    className="h-3 w-3 flex-shrink-0 text-muted-foreground hover:text-foreground"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTaskChange(null);
                    }}
                  />
                )}
              </button>
            </TaskPickerPopover>
          </div>

          <div ref={promptContainerRef} className="w-full bg-composer border border-border/50 rounded-3xl px-4 py-3 relative font-mono flex gap-3 shadow-sm">
            {/* Slash command suggestions */}
            {showSlashCommands && (
              <SlashCommandSuggestions
                commands={filteredCommands}
                selectedIndex={selectedCommandIndex}
                listRef={commandListRef}
                onSelect={(cmd) => {
                  const { value: next, cursor } = applySlashCommandSelection(prompt, commandInsertText(cmd), currentCaret());
                  setPrompt(next);
                  savePromptDraft(next);
                  setShowSlashCommands(false);
                  requestAnimationFrame(() => {
                    const el = textareaRef.current;
                    if (el) { el.focus({ preventScroll: true }); el.setSelectionRange(cursor, cursor); }
                  });
                }}
                onHover={setSelectedCommandIndex}
              />
            )}
            <div className="flex-1 min-w-0">
              {/* Rejected-pick notice (too large / too many) */}
              {attachmentError && (
                <div className="mb-2 text-[11px] text-destructive">{attachmentError}</div>
              )}

              {/* Pending attachments — previews only; these upload after the
                  session exists (see handleSubmit). Folder chips reference a
                  path and fold into the prompt on submit. */}
              {(pendingImages.length > 0 || pendingFolderRefs.length > 0) && (
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  {pendingFolderRefs.map((path) => (
                    <FolderRefChip key={path} path={path} onRemove={() => removeFolderRef(path)} />
                  ))}
                  {pendingImages.map((image) => (
                    <div key={image.key} className="relative">
                      {image.isImage ? (
                        <span className="block rounded-lg overflow-hidden" title={image.file.name}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={image.previewUrl}
                            alt={image.file.name}
                            className="w-14 h-14 object-cover"
                          />
                        </span>
                      ) : (
                        <span
                          className="flex items-center gap-2 h-14 w-40 px-3 rounded-lg border border-border bg-muted-foreground/5"
                          title={image.file.name}
                        >
                          <FileIcon className="w-4 h-4 flex-shrink-0 text-muted-foreground" />
                          <span className="flex min-w-0 flex-col text-left">
                            <span className="truncate text-[11px] font-medium">{image.file.name}</span>
                            <span className="text-[10px] text-muted-foreground">{formatFileSize(image.file.size)}</span>
                          </span>
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => removeImage(image.key)}
                        className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-background border border-border flex items-center justify-center hover:bg-accent"
                        title="Remove attachment"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Hidden file picker for the "Add files" action (all types; the
                  backend enforces the blocklist and size cap) */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => handleFilesSelected(e.target.files)}
              />

              <div className="group/newprompt relative flex items-center gap-2 w-full mb-0.5">
                {/* Right-aligned placeholder-side hint; gone once typing. On
                    desktop it advertises the focus shortcut while unfocused,
                    then swaps to the send hint once the field has focus. */}
                {!prompt && (
                  <span className="pointer-events-none absolute right-2 top-[18px] -translate-y-1/2 font-mono text-xs text-muted-foreground/40">
                    {showFocusHint ? (
                      <>
                        <span className="group-focus-within/newprompt:hidden">{comboInline(getShortcutCombo('focus-chat'))} to focus</span>
                        <span className="hidden group-focus-within/newprompt:inline">⏎ start · ⇧⏎ new line</span>
                      </>
                    ) : (
                      '⏎ start · ⇧⏎ new line'
                    )}
                  </span>
                )}
                <MentionTextarea
                  ref={textareaRef}
                  value={prompt}
                  onChange={handlePromptChange}
                  projectPath={toAbsolutePath(directory.trim() || undefined, currentMachine?.home_dir)}
                  machineId={isOnline ? (currentMachine?.machine_id ?? null) : null}
                  machine={currentMachine}
                  mentionsEnabled={!!directory.trim() && isOnline}
                  openMentionSignal={mentionSignal}
                  onMentionOpenChange={(open) => { if (open) setShowSlashCommands(false); }}
                  onKeyDown={handleKeyDown}
                  placeholder="Type messages, @files, /skills or commands"
                  rows={1}
                  disabled={isSubmitting || !canSubmit}
                  className="w-full bg-transparent border-0 py-2 px-2 text-sm resize-none focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-50 leading-5 placeholder:text-muted-foreground/30"
                  style={{
                    height: '36px',
                    minHeight: '36px',
                    maxHeight: '128px',
                    overflowY: prompt && textareaRef.current && textareaRef.current.scrollHeight > 128 ? 'auto' : 'hidden',
                    scrollbarWidth: 'thin',
                    scrollbarColor: 'hsl(var(--border)) transparent',
                  }}
                />
              </div>

              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground flex-1 min-w-0 mr-2">
                  <AddToChatMenu
                    onAddFiles={handleAddFiles}
                    onAddFolder={getDesktopShellBridge() && !!directory.trim() && isOnline ? handleInsertFolder : undefined}
                    onMentionFiles={handleInsertMention}
                    onCommands={handleInsertSlash}
                    hasSkills={hasSkills}
                    disabled={isSubmitting || !canSubmit}
                  />
                  {/* Agent config chips — same pattern as the chat page. */}
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <ChipDropdown
                      title="Agent"
                      contentClassName="w-52"
                      chip={
                        <>
                          <AgentTypeIcon agentTypeName={sessionConfig.agent} size={12} whiteForOpenAI />
                          <span className="min-w-0 truncate">
                            {agentEntries.find((a) => a.id === sessionConfig.agent)?.label ?? sessionConfig.agent}
                          </span>
                        </>
                      }
                    >
                      {(close) =>
                        agentEntries.map((a) => (
                          <TickItem
                            key={a.id}
                            label={a.label}
                            leading={<AgentTypeIcon agentTypeName={a.id} size={12} whiteForOpenAI />}
                            isSelected={a.id === sessionConfig.agent}
                            isPending={false}
                            onClick={() => { switchAgent(a.id); close(); }}
                          />
                        ))
                      }
                    </ChipDropdown>
                    {modelEntries && modelEntries.length > 0 && (
                      <ChipDropdown
                        title="Model"
                        contentClassName="w-56"
                        chip={
                          <span className="min-w-0 truncate">
                            {modelEntries.find((m) => m.id === sessionConfig.model)?.label ?? sessionConfig.model ?? 'Model'}
                          </span>
                        }
                      >
                        {(close) =>
                          modelEntries.map((m) => (
                            <TickItem
                              key={m.id}
                              label={m.label}
                              isSelected={m.id === sessionConfig.model}
                              isPending={false}
                              onClick={() => { updateField({ model: m.id }); close(); }}
                            />
                          ))
                        }
                      </ChipDropdown>
                    )}
                    {visibleThinking.length > 0 && (
                      <ChipDropdown
                        title="Effort"
                        contentClassName="w-44"
                        chip={
                          <span className="min-w-0 truncate">
                            {visibleThinking.find((e) => e.id === sessionConfig.thinking_effort)?.label ?? 'Effort'}
                          </span>
                        }
                      >
                        {(close) =>
                          visibleThinking.map((e) => (
                            <TickItem
                              key={e.id}
                              label={e.label}
                              isSelected={e.id === sessionConfig.thinking_effort}
                              isPending={false}
                              onClick={() => { updateField({ thinking_effort: e.id }); close(); }}
                            />
                          ))
                        }
                      </ChipDropdown>
                    )}
                    {visibleReasoning.length > 0 && (
                      <ChipDropdown
                        title="Effort"
                        contentClassName="w-44"
                        chip={
                          <span className="min-w-0 truncate">
                            {visibleReasoning.find((e) => e.id === sessionConfig.reasoning_effort)?.label ?? 'Effort'}
                          </span>
                        }
                      >
                        {(close) =>
                          visibleReasoning.map((e) => (
                            <TickItem
                              key={e.id}
                              label={e.label}
                              isSelected={e.id === sessionConfig.reasoning_effort}
                              isPending={false}
                              onClick={() => { updateField({ reasoning_effort: e.id }); close(); }}
                            />
                          ))
                        }
                      </ChipDropdown>
                    )}
                    {visiblePermission.length > 0 && (
                      <ChipDropdown
                        title="Permission mode"
                        contentClassName="w-52"
                        chip={
                          <>
                            <ModeIcon value={sessionConfig.permission_mode ?? 'default'} className="h-3.5 w-3.5 flex-shrink-0" />
                            <span className="min-w-0 truncate">
                              {visiblePermission.find((p) => p.id === sessionConfig.permission_mode)?.label ?? 'Permission'}
                            </span>
                          </>
                        }
                      >
                        {(close) =>
                          visiblePermission.map((p) => (
                            <TickItem
                              key={p.id}
                              label={p.label}
                              leading={<ModeIcon value={p.id} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                              isSelected={p.id === sessionConfig.permission_mode}
                              isPending={false}
                              onClick={() => { updateField({ permission_mode: p.id }); close(); }}
                            />
                          ))
                        }
                      </ChipDropdown>
                    )}
                    {visibleModes.length > 0 && (
                      <ChipDropdown
                        title="Mode"
                        contentClassName="w-44"
                        chip={
                          <>
                            <ModeIcon value={sessionConfig.opencode_mode ?? 'build'} className="h-3.5 w-3.5 flex-shrink-0" />
                            <span className="min-w-0 truncate">
                              {visibleModes.find((m) => m.id === sessionConfig.opencode_mode)?.label ?? 'Mode'}
                            </span>
                          </>
                        }
                      >
                        {(close) =>
                          visibleModes.map((m) => (
                            <TickItem
                              key={m.id}
                              label={m.label}
                              leading={<ModeIcon value={m.id} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                              isSelected={m.id === sessionConfig.opencode_mode}
                              isPending={false}
                              onClick={() => { updateField({ opencode_mode: m.id }); close(); }}
                            />
                          ))
                        }
                      </ChipDropdown>
                    )}
                  </div>
                  {/* Claude account limits (Session/Weekly), fetched from the
                      selected machine's daemon on page load. Self-hides until
                      data arrives (and entirely for non-Claude agents or
                      offline machines). Keyed by machine so switching resets
                      the fetched snapshot. */}
                  {claudeUsageFetch && (
                    <ChatUsageIndicator
                      key={selectedMachineId}
                      usage={null}
                      fetchLimits={claudeUsageFetch}
                      fetchOnMount
                    />
                  )}
                </div>
                <Button
                  type="button"
                  size="icon"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  className="shrink-0 rounded-full w-7 h-7 p-0 border-0 focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:border-transparent focus-visible:outline-none"
                >
                  {isSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowUp className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>
      {panel.open && (
        <FilesGitPanel
          machineId={selectedMachineId || null}
          cwd={directory.trim() || null}
          homeDir={currentMachine?.home_dir ?? null}
          instanceId="new-session"
          panel={panel}
        />
      )}
    </div>
  );
}

export default function NewSessionPage() {
  // useSearchParams needs a Suspense boundary during prerender. The fallback is
  // a VISIBLE loader, not an empty div: on the desktop app this route is the
  // landing page after sign-in/paywall, and an empty fallback is indistinguishable
  // from the "blank main page" bug — a spinner tells a stuck user (and us) that
  // the segment is still resolving rather than dead.
  return (
    <Suspense
      fallback={
        <div className="flex h-full flex-col items-center justify-center bg-background">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <NewSessionContent />
    </Suspense>
  );
}
