/**
 * The data shapes plugins see, and the mappers from the REST responses.
 *
 * Plugins get their own small, documented, camelCase records instead of the
 * raw API types, so the app can change its internal API without breaking every
 * plugin page. Adding a field here is cheap; renaming or removing one is a
 * breaking change for plugins (bump `BRIDGE_API_VERSION`).
 */

import type {
  AgentInstanceDetail,
  AgentInstanceResponse,
  AutomationResponse,
  AutomationRunResponse,
  MessageResponse,
  PrincipalResponse,
  ProjectResponse,
  TaskCommentResponse,
  TaskResponse,
} from '@/lib/backend-api';

export interface PluginPrincipal {
  type: PrincipalResponse['type'];
  id: string | null;
  name: string | null;
}

export interface PluginProject {
  id: string;
  name: string;
  /** Task identifier prefix, e.g. "VIC". */
  key: string | null;
  color: string | null;
  icon: string | null;
  archived: boolean;
  lastActivityAt: string | null;
  /** Where the project is checked out, one entry per machine. */
  directories: { machineId: string; path: string }[];
}

export interface PluginTask {
  id: string;
  /** "VIC-42", or null for a task with no project. */
  identifier: string | null;
  projectId: string | null;
  title: string;
  description: string | null;
  status: TaskResponse['status'];
  priority: TaskResponse['priority'];
  /** Label names. */
  labels: string[];
  dueDate: string | null;
  startDate: string | null;
  parentId: string | null;
  assignee: PluginPrincipal | null;
  /** The session the task was created in, when it was. */
  createdInSessionId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PluginComment {
  id: string;
  /** Null once deleted. */
  body: string | null;
  kind: 'comment' | 'system';
  author: PluginPrincipal;
  /** The session the comment was posted from, when it was. */
  sessionId: string | null;
  parentId: string | null;
  createdAt: string;
  editedAt: string | null;
}

export interface PluginSession {
  id: string;
  name: string | null;
  status: AgentInstanceResponse['status'];
  /** The agent that runs it, e.g. "claude code". */
  agent: string | null;
  projectId: string | null;
  taskId: string | null;
  machineId: string | null;
  worktree: string | null;
  startedAt: string;
  endedAt: string | null;
  /** The newest message's text: for a finished run, usually its report. */
  lastMessage: string | null;
  lastMessageAt: string | null;
  messageCount: number;
}

export interface PluginMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  createdAt: string;
  /** The agent is waiting for an answer to this message. */
  asksForInput: boolean;
}

export interface PluginAutomation {
  id: string;
  title: string;
  prompt: string;
  projectId: string | null;
  machineId: string | null;
  directory: string;
  enabled: boolean;
  scheduleKind: AutomationResponse['schedule_kind'];
  timezone: string;
  nextRunAt: string | null;
  lastRunAt: string | null;
  lastRunStatus: AutomationResponse['last_run_status'];
  /** Set when every run continues this one session. */
  sessionId: string | null;
  /** Someone else's automation that reaches you through a shared project. */
  shared: boolean;
}

export interface PluginAutomationRun {
  id: string;
  automationId: string;
  /** The session the run started (or continued). */
  sessionId: string | null;
  plannedAt: string | null;
  firedAt: string;
  status: AutomationRunResponse['status'];
  detail: string | null;
}

const principal = (p: PrincipalResponse | null | undefined): PluginPrincipal | null =>
  p ? { type: p.type, id: p.id, name: p.name } : null;

export function mapProject(p: ProjectResponse): PluginProject {
  return {
    id: p.id,
    name: p.name,
    key: p.key,
    color: p.color,
    icon: p.icon,
    archived: p.is_archived,
    lastActivityAt: p.last_activity_at ?? null,
    directories: (p.directories ?? []).map((d) => ({ machineId: d.machine_id, path: d.local_path })),
  };
}

export function mapTask(t: TaskResponse): PluginTask {
  return {
    id: t.id,
    identifier: t.identifier,
    projectId: t.project_id,
    title: t.title,
    description: t.description,
    status: t.status,
    priority: t.priority,
    labels: (t.labels ?? []).map((l) => l.name),
    dueDate: t.due_date,
    startDate: t.start_date,
    parentId: t.parent_task_id,
    assignee: principal(t.assignee),
    createdInSessionId: t.created_in_instance_id,
    createdAt: t.created_at,
    updatedAt: t.updated_at,
  };
}

export function mapComment(c: TaskCommentResponse): PluginComment {
  return {
    id: c.id,
    body: c.deleted_at ? null : c.body,
    kind: c.kind,
    author: principal(c.author) ?? { type: 'system', id: null, name: null },
    sessionId: c.agent_instance_id,
    parentId: c.parent_comment_id,
    createdAt: c.created_at,
    editedAt: c.edited_at,
  };
}

export function mapSession(s: AgentInstanceResponse): PluginSession {
  return {
    id: s.id,
    name: s.name,
    status: s.status,
    agent: s.agent_type_name,
    projectId: s.project_id ?? null,
    taskId: s.task_id ?? null,
    machineId: s.machine_id ?? null,
    worktree: s.worktree_name ?? null,
    startedAt: s.started_at,
    endedAt: s.ended_at,
    lastMessage: s.latest_message,
    lastMessageAt: s.latest_message_at,
    messageCount: s.chat_length,
  };
}

/** A session read through the detail endpoint (fetched with its newest message). */
export function mapSessionDetail(d: AgentInstanceDetail): PluginSession {
  const last = d.messages?.length ? d.messages[d.messages.length - 1] : null;
  return {
    id: d.id,
    name: d.name,
    status: d.status,
    agent: d.agent_type_name,
    projectId: d.project_id ?? null,
    taskId: d.task_id ?? null,
    machineId: d.machine_id ?? null,
    worktree: d.worktree_name ?? null,
    startedAt: d.started_at,
    endedAt: d.ended_at,
    lastMessage: last?.content ?? null,
    lastMessageAt: last?.created_at ?? null,
    // The detail endpoint doesn't count messages.
    messageCount: -1,
  };
}

export function mapMessage(m: MessageResponse): PluginMessage {
  return {
    id: m.id,
    role: /^(user|human)$/i.test(m.sender_type) ? 'user' : 'agent',
    text: m.content,
    createdAt: m.created_at,
    asksForInput: Boolean(m.requires_user_input),
  };
}

export function mapAutomation(a: AutomationResponse): PluginAutomation {
  return {
    id: a.id,
    title: a.title,
    prompt: a.prompt,
    projectId: a.project_id ?? null,
    machineId: a.machine_id,
    directory: a.directory,
    enabled: a.enabled,
    scheduleKind: a.schedule_kind,
    timezone: a.timezone,
    nextRunAt: a.next_run_at,
    lastRunAt: a.last_run_at,
    lastRunStatus: a.last_run_status,
    sessionId: a.agent_instance_id ?? null,
    shared: Boolean(a.owner),
  };
}

export function mapRun(r: AutomationRunResponse): PluginAutomationRun {
  return {
    id: r.id,
    automationId: r.automation_id,
    sessionId: r.agent_instance_id,
    plannedAt: r.planned_at,
    firedAt: r.fired_at,
    status: r.status,
    detail: r.detail,
  };
}

// --- Filters ---------------------------------------------------------------

const asStringList = (v: unknown): string[] | null => {
  if (typeof v === 'string') return [v];
  if (Array.isArray(v) && v.every((x) => typeof x === 'string')) return v as string[];
  return null;
};

export const clampLimit = (v: unknown, fallback: number, max: number): number => {
  const n = typeof v === 'number' && Number.isFinite(v) ? Math.floor(v) : fallback;
  return Math.max(1, Math.min(max, n));
};

export interface TaskFilter {
  projectId?: string;
  status?: string[];
  /** Every one of these labels (by name, case-insensitive). */
  labels?: string[];
  limit: number;
}

/** Normalize `vicoa.tasks.list(filter)`. `label` and `labels` both work. */
export function parseTaskFilter(raw: unknown): TaskFilter {
  const f = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const labels = [...(asStringList(f.label) ?? []), ...(asStringList(f.labels) ?? [])];
  return {
    projectId: typeof f.projectId === 'string' ? f.projectId : undefined,
    status: asStringList(f.status) ?? undefined,
    labels: labels.length ? labels : undefined,
    limit: clampLimit(f.limit, 200, 1000),
  };
}

export function filterTasks(tasks: PluginTask[], f: TaskFilter): PluginTask[] {
  const wanted = f.labels?.map((l) => l.toLowerCase());
  return tasks
    .filter((t) => !f.projectId || t.projectId === f.projectId)
    .filter((t) => !f.status || f.status.includes(t.status))
    .filter((t) => {
      if (!wanted) return true;
      const have = new Set(t.labels.map((l) => l.toLowerCase()));
      return wanted.every((l) => have.has(l));
    })
    .slice(0, f.limit);
}

export interface SessionFilter {
  /** Only sessions started at or after this ISO time. */
  since?: number;
  projectId?: string;
  taskId?: string;
  status?: string[];
  limit: number;
}

export function parseSessionFilter(raw: unknown): SessionFilter {
  const f = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const since = typeof f.since === 'string' ? Date.parse(f.since) : NaN;
  return {
    since: Number.isFinite(since) ? since : undefined,
    projectId: typeof f.projectId === 'string' ? f.projectId : undefined,
    taskId: typeof f.taskId === 'string' ? f.taskId : undefined,
    status: asStringList(f.status) ?? undefined,
    limit: clampLimit(f.limit, 50, 500),
  };
}

export function sessionMatches(s: PluginSession, f: SessionFilter): boolean {
  if (f.projectId && s.projectId !== f.projectId) return false;
  if (f.taskId && s.taskId !== f.taskId) return false;
  if (f.status && !f.status.includes(s.status)) return false;
  return true;
}
