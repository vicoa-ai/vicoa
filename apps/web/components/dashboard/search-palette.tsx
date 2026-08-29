'use client';

/**
 * SearchPalette — the ⌘K workspace search overlay (multica's cmd+K, adapted).
 *
 * Searches sessions, tasks, and automations through `GET /api/v1/search`
 * (debounced, aborting stale requests). With an empty query it shows recent
 * sessions from the already-loaded sidebar list. When the endpoint is missing
 * (desktop-local daemon, older backends) it degrades to client-side filtering
 * of the loaded session list.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';
import {
  CalendarClock,
  Cog,
  Kanban,
  Keyboard,
  ListTodo,
  Loader2,
  MessageSquare,
  Plus,
  Search,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import {
  SHORTCUT_DEFS,
  comboKeycaps,
  getShortcutCombo,
  type ShortcutDef,
} from '@/lib/desktop-shortcuts';
import {
  AgentInstanceResponse,
  SearchAutomationResult,
  SearchSessionResult,
  SearchTaskResult,
  WorkspaceSearchResponse,
} from '@/lib/backend-api';
import {
  formatSidebarTime,
  getSessionTitle,
} from '@/components/dashboard/session-display';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { PriorityIcon, StatusIcon } from '@/components/dashboard/task-ui';

const RECENT_SESSION_COUNT = 7;
const LOCAL_FALLBACK_LIMIT = 20;
const SEARCH_DEBOUNCE_MS = 250;

// The keyboard-shortcut commands route to Settings → Keyboard shortcuts, which
// today only renders in the desktop app — so listing them is desktop-only, to
// never point at a settings page the web build can't open.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';
const SHOW_SHORTCUT_COMMANDS = IS_DESKTOP;

// Words that, when the query is a prefix of one, mean "show me every shortcut"
// (e.g. typing "shortcut" or "keys" lists them all as a cheat-sheet).
const SHORTCUT_GROUP_TERMS = [
  'keyboard',
  'shortcut',
  'shortcuts',
  'keybinding',
  'keybindings',
  'hotkey',
  'hotkeys',
  'keys',
];

interface PaletteCommand {
  id: string;
  label: string;
  /** Extra match terms (English + 中文) beyond the label; all lowercase. */
  keywords: string[];
  icon: LucideIcon;
  href: string;
  /** Shown with an empty query (the create actions). */
  primary?: boolean;
}

// Quick actions + page navigation — pure client-side tier, no server round
// trip. `?task=new` / `?automation=new` open the create dialog/panel via the
// pages' deep-link params.
const COMMANDS: PaletteCommand[] = [
  {
    id: 'new-session',
    label: 'New session',
    keywords: ['create', 'start', 'agent', 'spawn', '新建', '会话', '任务'],
    icon: Plus,
    href: '/dashboard/agents/new-session',
    primary: true,
  },
  {
    id: 'new-task',
    label: 'New task',
    keywords: ['create', 'todo', 'backlog', '新建', '任务', '待办'],
    icon: Plus,
    href: '/dashboard/tasks?task=new',
    primary: true,
  },
  {
    id: 'new-automation',
    label: 'New automation',
    keywords: ['create', 'schedule', 'cron', 'recurring', '新建', '自动化'],
    icon: Plus,
    href: '/dashboard/automation?automation=new',
    primary: true,
  },
  {
    id: 'go-kanban',
    label: 'Go to Kanban',
    keywords: ['board', 'agent hub', 'sessions', '看板'],
    icon: Kanban,
    href: '/dashboard/kanban',
  },
  {
    id: 'go-tasks',
    label: 'Go to Tasks',
    keywords: ['backlog', 'todo', '任务', '待办'],
    icon: ListTodo,
    href: '/dashboard/tasks',
  },
  {
    id: 'go-automations',
    label: 'Go to Automations',
    keywords: ['schedules', 'cron', '自动化'],
    icon: CalendarClock,
    href: '/dashboard/automation',
  },
  {
    id: 'go-settings',
    label: 'Go to Settings',
    keywords: ['preferences', 'shortcuts', 'account', '设置'],
    icon: Cog,
    href: '/dashboard/settings',
  },
];

type PaletteItem =
  | { kind: 'command'; command: PaletteCommand }
  | { kind: 'session'; session: SearchSessionResult }
  | { kind: 'task'; task: SearchTaskResult }
  | { kind: 'automation'; automation: SearchAutomationResult }
  | { kind: 'shortcut'; shortcut: ShortcutDef };

interface SearchPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function toSessionResult(instance: AgentInstanceResponse): SearchSessionResult {
  return {
    id: instance.id,
    name: instance.name,
    agent_type_name: instance.agent_type_name,
    status: instance.status,
    project: instance.project ?? null,
    started_at: instance.started_at,
    latest_message: instance.latest_message,
    latest_message_at: instance.latest_message_at,
    match_source: 'name',
    snippet: null,
  };
}

function projectBasename(project: string | null): string | null {
  if (!project) return null;
  return project.split('/').filter(Boolean).pop() ?? null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function Highlight({ text, query }: { text: string; query: string }) {
  const trimmed = query.trim();
  if (!trimmed) return <>{text}</>;
  const parts = text.split(new RegExp(`(${escapeRegExp(trimmed)})`, 'ig'));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === trimmed.toLowerCase() ? (
          <mark
            key={i}
            className="rounded-[2px] bg-yellow-200/80 text-inherit dark:bg-yellow-500/30"
          >
            {part}
          </mark>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground">
      {children}
    </div>
  );
}

const ROW_CLASS =
  'flex w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left text-sm outline-none';

export function SearchPalette({ open, onOpenChange }: SearchPaletteProps) {
  const { api, recentInstances } = useAgentDashboard();
  const router = useRouter();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<WorkspaceSearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  // Flipped on the first 404: the endpoint doesn't exist here (desktop-local
  // daemon or an older backend) — degrade to filtering loaded sessions.
  const [serverUnavailable, setServerUnavailable] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const runSearch = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
      const trimmed = value.trim();
      if (!trimmed || !api || serverUnavailable) {
        setResults(null);
        setIsLoading(false);
        setSearchError(null);
        return;
      }
      setIsLoading(true);
      setSearchError(null);
      debounceRef.current = setTimeout(async () => {
        const controller = new AbortController();
        abortRef.current = controller;
        try {
          const response = await api.search(trimmed, {
            signal: controller.signal,
          });
          if (!controller.signal.aborted) {
            setResults(response);
            setIsLoading(false);
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          const status = (err as { status?: number }).status;
          if (status === 404) {
            setServerUnavailable(true);
          } else if (status === 503) {
            // Backend statement-timeout guardrail; its detail says to
            // refine the query.
            setSearchError(
              (err as Error).message || 'Search timed out — try a longer query.',
            );
          } else {
            setSearchError('Search failed — check your connection and retry.');
          }
          setResults(null);
          setIsLoading(false);
        }
      }, SEARCH_DEBOUNCE_MS);
    },
    [api, serverUnavailable],
  );

  // Reset transient state whenever the palette closes. serverUnavailable is
  // reset too so every open retries the server once — a backend that gains
  // the endpoint mid-session (deploy, dev restart) starts working without a
  // page reload; in desktop-local mode the retry is one cheap 404.
  useEffect(() => {
    if (open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();
    setQuery('');
    setResults(null);
    setIsLoading(false);
    setSearchError(null);
    setServerUnavailable(false);
    setActiveIndex(0);
  }, [open]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // Capture-phase Escape so the palette closes ahead of other overlay
  // handlers (mirrors the session-page listeners, which are capture too).
  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      onOpenChange(false);
    };
    document.addEventListener('keydown', onEsc, true);
    return () => document.removeEventListener('keydown', onEsc, true);
  }, [open, onOpenChange]);

  const trimmedQuery = query.trim();

  const sessions = useMemo<SearchSessionResult[]>(() => {
    if (!trimmedQuery) {
      return recentInstances.slice(0, RECENT_SESSION_COUNT).map(toSessionResult);
    }
    if (serverUnavailable) {
      const q = trimmedQuery.toLowerCase();
      return recentInstances
        .filter(
          (instance) =>
            (instance.name ?? '').toLowerCase().includes(q) ||
            (instance.latest_message ?? '').toLowerCase().includes(q) ||
            (instance.project ?? '').toLowerCase().includes(q),
        )
        .slice(0, LOCAL_FALLBACK_LIMIT)
        .map(toSessionResult);
    }
    return results?.sessions ?? [];
  }, [trimmedQuery, serverUnavailable, recentInstances, results]);

  const tasks = trimmedQuery && !serverUnavailable ? (results?.tasks ?? []) : [];
  const automations =
    trimmedQuery && !serverUnavailable ? (results?.automations ?? []) : [];

  const commands = useMemo<PaletteCommand[]>(() => {
    if (!trimmedQuery) return COMMANDS.filter((command) => command.primary);
    const q = trimmedQuery.toLowerCase();
    return COMMANDS.filter(
      (command) =>
        command.label.toLowerCase().includes(q) ||
        command.keywords.some((keyword) => keyword.includes(q)),
    );
  }, [trimmedQuery]);

  // Keyboard shortcuts as a searchable cheat-sheet (desktop only). Query-gated
  // so they never crowd the default view, and matched by label, section, or by
  // typing a shortcut-y word ("shortcut", "keys") to list them all.
  const shortcuts = useMemo<ShortcutDef[]>(() => {
    if (!SHOW_SHORTCUT_COMMANDS || !trimmedQuery) return [];
    const q = trimmedQuery.toLowerCase();
    // "Show all" when the query is *about* shortcuts — either a fragment of a
    // group term ("short", "keys") or a phrase that contains one ("keyboard
    // shortcuts"). Bidirectional contains, so both short and long queries land.
    const wantsAll =
      q.length >= 2 && SHORTCUT_GROUP_TERMS.some((w) => w.includes(q) || q.includes(w));
    return SHORTCUT_DEFS.filter(
      (def) =>
        wantsAll ||
        def.label.toLowerCase().includes(q) ||
        def.section.toLowerCase().includes(q),
    );
  }, [trimmedQuery]);

  const items = useMemo<PaletteItem[]>(
    () => [
      ...commands.map((command): PaletteItem => ({ kind: 'command', command })),
      ...sessions.map((session): PaletteItem => ({ kind: 'session', session })),
      ...tasks.map((task): PaletteItem => ({ kind: 'task', task })),
      ...automations.map(
        (automation): PaletteItem => ({ kind: 'automation', automation }),
      ),
      ...shortcuts.map((shortcut): PaletteItem => ({ kind: 'shortcut', shortcut })),
    ],
    [commands, sessions, tasks, automations, shortcuts],
  );

  // Keep the active row in range as result sets change.
  useEffect(() => {
    setActiveIndex((current) =>
      items.length === 0 ? 0 : Math.min(current, items.length - 1),
    );
  }, [items]);

  useEffect(() => {
    const row = listRef.current?.querySelector(
      `[data-palette-index="${activeIndex}"]`,
    );
    row?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const openItem = useCallback(
    (item: PaletteItem) => {
      onOpenChange(false);
      if (item.kind === 'command') {
        router.push(item.command.href);
      } else if (item.kind === 'session') {
        router.push(`/dashboard/agents/${item.session.id}`);
      } else if (item.kind === 'task') {
        router.push(`/dashboard/tasks?task=${item.task.id}`);
      } else if (item.kind === 'automation') {
        router.push(`/dashboard/automation?automation=${item.automation.id}`);
      } else {
        // Shortcuts open their settings page, where they can be viewed/rebound.
        router.push('/dashboard/settings?tab=shortcuts');
      }
    },
    [onOpenChange, router],
  );

  const onInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((current) =>
          items.length === 0 ? 0 : (current + 1) % items.length,
        );
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((current) =>
          items.length === 0 ? 0 : (current - 1 + items.length) % items.length,
        );
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const item = items[activeIndex];
        if (item) openItem(item);
      }
    },
    [items, activeIndex, openItem],
  );

  if (!open) return null;

  const showEmpty =
    !isLoading && !searchError && trimmedQuery.length > 0 && items.length === 0;
  const showRecentHeading = !trimmedQuery && sessions.length > 0;

  // Rows are indexed across all groups in render order so arrow keys walk
  // commands → sessions → tasks → automations seamlessly.
  const sessionIndexOffset = commands.length;
  const taskIndexOffset = commands.length + sessions.length;
  const automationIndexOffset = commands.length + sessions.length + tasks.length;
  const shortcutIndexOffset =
    commands.length + sessions.length + tasks.length + automations.length;

  return (
    <div className="fixed inset-0 z-50">
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search workspace"
        className="fixed left-1/2 top-[15%] w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              runSearch(e.target.value);
            }}
            onKeyDown={onInputKeyDown}
            placeholder="Search sessions, tasks, automations…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
          />
          <kbd className="hidden shrink-0 rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline-block">
            esc
          </kbd>
        </div>

        <div
          ref={listRef}
          className="custom-scrollbar max-h-[min(400px,50vh)] overflow-y-auto overflow-x-hidden p-2"
        >
          {/* Commands are local — they stay put while server results load. */}
          {commands.length > 0 && (
            <div>
              <GroupHeading>Commands</GroupHeading>
              {commands.map((command, i) => {
                const active = activeIndex === i;
                const Icon = command.icon;
                return (
                  <button
                    key={command.id}
                    data-palette-index={i}
                    className={cn(ROW_CLASS, active && 'bg-accent')}
                    onMouseMove={() => setActiveIndex(i)}
                    onClick={() => openItem({ kind: 'command', command })}
                  >
                    <div className="flex w-full items-center gap-2.5">
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">
                        <Highlight text={command.label} query={trimmedQuery} />
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {isLoading && (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && searchError && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              {searchError}
            </div>
          )}

          {showEmpty && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              No results found.
            </div>
          )}

          {!isLoading && !searchError && !trimmedQuery && sessions.length === 0 && (
            <div className="px-4 py-6 text-center text-xs text-muted-foreground">
              Type to search sessions, tasks, and automations
            </div>
          )}

          {!isLoading && !searchError && sessions.length > 0 && (
            <div>
              <GroupHeading>
                {showRecentHeading ? 'Recent sessions' : 'Sessions'}
              </GroupHeading>
              {sessions.map((session, i) => {
                const index = sessionIndexOffset + i;
                const active = activeIndex === index;
                const project = projectBasename(session.project);
                return (
                  <button
                    key={session.id}
                    data-palette-index={index}
                    className={cn(ROW_CLASS, active && 'bg-accent')}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() =>
                      openItem({ kind: 'session', session })
                    }
                  >
                    <div className="flex w-full items-center gap-2.5">
                      <SessionAgentIcon
                        agentTypeName={session.agent_type_name}
                        status={session.status}
                      />
                      <span className="min-w-0 flex-1 truncate">
                        <Highlight
                          text={getSessionTitle(session)}
                          query={trimmedQuery}
                        />
                      </span>
                      {project && (
                        <span className="max-w-[140px] shrink-0 truncate text-xs text-muted-foreground">
                          <Highlight text={project} query={trimmedQuery} />
                        </span>
                      )}
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatSidebarTime(session)}
                      </span>
                    </div>
                    {session.snippet && (
                      <div className="flex w-full items-center gap-1.5 pl-[26px] text-xs text-muted-foreground">
                        <MessageSquare className="h-3 w-3 shrink-0" />
                        <span className="truncate">
                          <Highlight
                            text={session.snippet}
                            query={trimmedQuery}
                          />
                        </span>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {!isLoading && !searchError && tasks.length > 0 && (
            <div>
              <GroupHeading>Tasks</GroupHeading>
              {tasks.map((task, i) => {
                const index = taskIndexOffset + i;
                const active = activeIndex === index;
                return (
                  <button
                    key={task.id}
                    data-palette-index={index}
                    className={cn(ROW_CLASS, active && 'bg-accent')}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => openItem({ kind: 'task', task })}
                  >
                    <div className="flex w-full items-center gap-2.5">
                      <StatusIcon status={task.status} className="h-4 w-4" />
                      <span className="min-w-0 flex-1 truncate">
                        <Highlight text={task.title} query={trimmedQuery} />
                      </span>
                      <PriorityIcon priority={task.priority} />
                    </div>
                    {task.snippet && (
                      <div className="w-full truncate pl-[26px] text-xs text-muted-foreground">
                        <Highlight text={task.snippet} query={trimmedQuery} />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {!isLoading && !searchError && automations.length > 0 && (
            <div>
              <GroupHeading>Automations</GroupHeading>
              {automations.map((automation, i) => {
                const index = automationIndexOffset + i;
                const active = activeIndex === index;
                return (
                  <button
                    key={automation.id}
                    data-palette-index={index}
                    className={cn(ROW_CLASS, active && 'bg-accent')}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => openItem({ kind: 'automation', automation })}
                  >
                    <div className="flex w-full items-center gap-2.5">
                      <CalendarClock className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">
                        <Highlight
                          text={automation.title}
                          query={trimmedQuery}
                        />
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {automation.enabled ? 'Active' : 'Paused'}
                      </span>
                    </div>
                    {automation.snippet && (
                      <div className="w-full truncate pl-[26px] text-xs text-muted-foreground">
                        <Highlight
                          text={automation.snippet}
                          query={trimmedQuery}
                        />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {shortcuts.length > 0 && (
            <div>
              <GroupHeading>Keyboard shortcuts</GroupHeading>
              {shortcuts.map((def, i) => {
                const index = shortcutIndexOffset + i;
                const active = activeIndex === index;
                return (
                  <button
                    key={def.id}
                    data-palette-index={index}
                    className={cn(ROW_CLASS, active && 'bg-accent', 'cursor-pointer')}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => openItem({ kind: 'shortcut', shortcut: def })}
                  >
                    <div className="flex w-full items-center gap-2.5">
                      <Keyboard className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">
                        <Highlight text={def.label} query={trimmedQuery} />
                      </span>
                      <span className="flex shrink-0 items-center gap-1">
                        {comboKeycaps(getShortcutCombo(def.id)).map((key, keyIndex) => (
                          <kbd
                            key={keyIndex}
                            className="rounded border bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground"
                          >
                            {key}
                          </kbd>
                        ))}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 border-t px-4 py-2 text-[11px] text-muted-foreground">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          {serverUnavailable && trimmedQuery ? (
            <span className="ml-auto text-amber-600 dark:text-amber-500">
              Server search unavailable — sessions only
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
