'use client';

// Task detail as a real route (collaboration §8.3), not a dialog: a markdown
// description, a properties rail, and a timeline that interleaves comments,
// generated activity and the agent sessions the task spawned.
//
// `task-dialog.tsx` stays — it is the fast create/edit path off the board. This
// is the deep-link surface: it is what "VIC-42" resolves to, what a comment
// cross-reference opens, and (in P4) what a shared board link lands on.
//
// No WebSocket channel, by decision (§9). The timeline revalidates on window
// focus and on a slow interval; polling hits the stateless backend app, while
// the relay is pinned to workers=1 and already carries every daemon socket.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Plus } from 'lucide-react';

import {
  AgentInstanceResponse,
  AgentProfile,
  ProjectResponse,
  TaskActivityResponse,
  TaskCommentResponse,
  TaskLabelResponse,
  TaskReactionSummary,
  TaskResponse,
  UpdateTaskRequest,
  UserProfile,
} from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { EditableDescription, EditableTitle } from './inline-fields';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Principal } from '@/lib/principals';
import {
  AssigneePickerPill,
  DatePickerPill,
  LabelPickerPill,
  ParentPickerPill,
  PriorityPickerPill,
  ProjectPickerPill,
  PropertyRows,
  StatusPickerPill,
  toDateOnly,
  dateOnlyToLocalDate,
} from '@/components/dashboard/task-ui';
import { ReactionRow, TaskTimeline } from './task-timeline';
import { CommentComposer } from './comment-composer';

// Slow on purpose: this is a single-player backlog, and the point of the poll
// is to catch an agent's comment landing while the tab sits open — not to
// simulate realtime. Focus revalidation covers the "came back to the tab" case.
const POLL_MS = 30_000;

// Properties that stay out of the rail until they carry a value or the user
// picks them from "Other properties". Status / priority / assignee / project /
// labels are always shown — they are the ones you scan for.
const OPTIONAL_PROPERTIES: {
  key: string;
  label: string;
  isSet: (task: TaskResponse) => boolean;
}[] = [
  { key: 'due_date', label: 'Due date', isSet: (t) => t.due_date !== null },
  { key: 'start_date', label: 'Start date', isSet: (t) => t.start_date !== null },
  { key: 'parent', label: 'Parent task', isSet: (t) => t.parent_task_id !== null },
];

function RailGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="px-2 text-xs text-muted-foreground/60">{label}</div>
      <PropertyRows>{children}</PropertyRows>
    </div>
  );
}

export default function TaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const taskId = params?.taskId;
  const router = useRouter();
  const { api } = useAgentDashboard();

  const [task, setTask] = useState<TaskResponse | null>(null);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [comments, setComments] = useState<TaskCommentResponse[]>([]);
  const [activity, setActivity] = useState<TaskActivityResponse[]>([]);
  const [taskReactions, setTaskReactions] = useState<TaskReactionSummary[]>([]);
  const [sessions, setSessions] = useState<AgentInstanceResponse[]>([]);
  const [me, setMe] = useState<UserProfile | null>(null);
  // The pickers need the same reference data the board dialog uses.
  const [labels, setLabels] = useState<TaskLabelResponse[]>([]);
  const [allTasks, setAllTasks] = useState<TaskResponse[]>([]);
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  // Properties the user asked for that have no value yet. A property shows
  // when it is set OR revealed — the rail stays short by default instead of
  // being a wall of "Unassigned / None / None".
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // The whole page's data. Kept in one function so focus-revalidation and the
  // interval can't drift apart from the initial load.
  const load = useCallback(async () => {
    if (!api || !taskId) return;
    try {
      const [taskRow, timeline, taskSessions, projectRows] = await Promise.all([
        api.getTask(taskId),
        api.getTaskTimeline(taskId),
        api.listTaskSessions(taskId),
        api.listProjects(),
      ]);
      setTask(taskRow);
      setComments(timeline.comments);
      setActivity(timeline.activity);
      setTaskReactions(timeline.reactions);
      setSessions(taskSessions);
      setProjects(projectRows);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load task');
    } finally {
      setIsLoading(false);
    }
  }, [api, taskId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!api) return;
    void api.getCurrentUserProfile().then(setMe).catch(() => setMe(null));
    // Reference data for the property pickers. Loaded once, and failing to load
    // it degrades a picker to empty rather than breaking the page.
    void api.listTaskLabels().then(setLabels).catch(() => setLabels([]));
    void api.listTasks().then(setAllTasks).catch(() => setAllTasks([]));
    void api
      .listAgentProfiles()
      .then(setAgentProfiles)
      .catch(() => setAgentProfiles([]));
  }, [api]);

  // Refresh-on-focus + a slow interval, the §9 model for tasks.
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') void loadRef.current();
    };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
      clearInterval(timer);
    };
  }, []);

  const patchTask = useCallback(
    async (patch: UpdateTaskRequest) => {
      if (!api || !task) return;
      const previous = task;
      setTask({ ...task, ...patch } as TaskResponse);
      try {
        setTask(await api.updateTask(task.id, patch));
        // A field change writes activity server-side, so the timeline is stale
        // the moment the PATCH lands.
        void load();
      } catch {
        setTask(previous);
      }
    },
    [api, task, load],
  );

  // Mirrors the dialog's label affordance: type a name, get a label, attached.
  const createLabelAndAttach = useCallback(
    async (name: string) => {
      if (!api || !task) return;
      const label = await api.createTaskLabel({ name, color: '#6b7280' });
      setLabels((prev) => [...prev, label]);
      await patchTask({ label_ids: [...task.labels.map((l) => l.id), label.id] });
    },
    [api, task, patchTask],
  );

  const postComment = useCallback(
    async (body: string) => {
      if (!api || !task) return;
      const timeline = await api.createTaskComment(task.id, body);
      setComments(timeline.comments);
      setActivity(timeline.activity);
      setTaskReactions(timeline.reactions);
    },
    [api, task],
  );

  const toggleReaction = useCallback(
    async (targetType: 'task' | 'comment', targetId: string, emoji: string) => {
      if (!api || !task) return;
      const timeline = await api.toggleTaskReaction(task.id, {
        targetType,
        targetId,
        emoji,
      });
      setComments(timeline.comments);
      setActivity(timeline.activity);
      setTaskReactions(timeline.reactions);
    },
    [api, task],
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8 text-sm text-muted-foreground">Loading…</div>
    );
  }

  if (error || !task) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-6 py-8">
        <p className="text-sm text-muted-foreground">{error ?? 'Task not found'}</p>
        <button
          type="button"
          onClick={() => router.push('/dashboard/tasks')}
          className="cursor-pointer text-sm underline underline-offset-4"
        >
          Back to tasks
        </button>
      </div>
    );
  }

  const viewer: Principal | null = me
    ? {
        type: 'user',
        id: me.id,
        name: me.display_name ?? me.email,
        avatarImageUri: me.avatar_image_uri,
        emoji: me.avatar_emoji,
        updatedAt: me.updated_at,
      }
    : null;

  // A property earns a slot when it has a value or the user asked for it.
  const isShown = (key: string) => revealed.has(key) || OPTIONAL_PROPERTIES.find((p) => p.key === key)?.isSet(task);
  const hidden = OPTIONAL_PROPERTIES.filter((p) => !isShown(p.key));

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <button
        type="button"
        onClick={() => router.push('/dashboard/tasks')}
        className="mb-4 flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        Tasks
      </button>

      <div className="flex gap-10">
        <div className="min-w-0 flex-1 space-y-6">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {/* The identifier is absent for a task that predates the backfill
                  or whose project has no key — render nothing rather than a
                  placeholder that looks like a real reference. */}
              {task.identifier && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] tracking-tight">
                  {task.identifier}
                </span>
              )}
              <span>{projects.find((p) => p.id === task.project_id)?.name ?? 'Inbox'}</span>
            </div>
            <EditableTitle
              value={task.title}
              onSave={(title) => void patchTask({ title })}
            />
            <EditableDescription
              value={task.description}
              onSave={(description) => void patchTask({ description })}
            />
            {/* The task itself is reactable, like an issue's opening post. */}
            <ReactionRow
              reactions={taskReactions}
              onToggle={(emoji) => void toggleReaction('task', task.id, emoji)}
            />
          </div>

          <div className="space-y-3 border-t pt-6">
            <TaskTimeline
              comments={comments}
              activity={activity}
              sessions={sessions}
              viewer={viewer}
              onToggleCommentReaction={(commentId, emoji) =>
                void toggleReaction('comment', commentId, emoji)
              }
            />
            <CommentComposer onSubmit={postComment} />
          </div>
        </div>

        <aside className="w-60 shrink-0 space-y-5">
          {/* Grouped, not labelled per field: one heading over a column of
              icon + value rows reads as a property list, whereas an uppercase
              caption above every single pill is eight captions to skip past.
              The row shape comes from <PropertyRows>. */}
          <RailGroup label="Properties">
            <StatusPickerPill
              status={task.status}
              onSelect={(status) => void patchTask({ status })}
            />
            <PriorityPickerPill
              priority={task.priority}
              onSelect={(priority) => void patchTask({ priority })}
            />
            <AssigneePickerPill
              assignee={task.assignee}
              viewer={viewer}
              agentProfiles={agentProfiles}
              onSelect={(next) =>
                void patchTask({
                  assignee_type: next?.type ?? null,
                  assignee_id: next?.id ?? null,
                })
              }
            />
            {isShown('due_date') && (
              <DatePickerPill
                label="Due date"
                value={task.due_date ? toDateOnly(new Date(task.due_date)) : ''}
                onChange={(value) =>
                  void patchTask({
                    due_date: value ? dateOnlyToLocalDate(value)?.toISOString() ?? null : null,
                  })
                }
              />
            )}
            {isShown('start_date') && (
              <DatePickerPill
                label="Start date"
                icon="start"
                value={task.start_date ? toDateOnly(new Date(task.start_date)) : ''}
                onChange={(value) =>
                  void patchTask({
                    start_date: value
                      ? dateOnlyToLocalDate(value)?.toISOString() ?? null
                      : null,
                  })
                }
              />
            )}
            {isShown('parent') && (
              <ParentPickerPill
                tasks={allTasks}
                currentTaskId={task.id}
                parentId={task.parent_task_id}
                onSelect={(parentId) => void patchTask({ parent_task_id: parentId })}
              />
            )}
            {hidden.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
                  >
                    <Plus className="size-3.5" />
                    Other properties
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-44">
                  {hidden.map((property) => (
                    <DropdownMenuItem
                      key={property.key}
                      className="cursor-pointer"
                      onSelect={() =>
                        setRevealed((prev) => new Set(prev).add(property.key))
                      }
                    >
                      {property.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </RailGroup>

          <RailGroup label="Project">
            <ProjectPickerPill
              projects={projects}
              projectId={task.project_id}
              onSelect={(projectId) => void patchTask({ project_id: projectId })}
            />
          </RailGroup>

          <RailGroup label="Labels">
            <LabelPickerPill
              labels={labels}
              selectedIds={task.labels.map((l) => l.id)}
              onToggle={(labelId) => {
                const current = task.labels.map((l) => l.id);
                void patchTask({
                  label_ids: current.includes(labelId)
                    ? current.filter((id) => id !== labelId)
                    : [...current, labelId],
                });
              }}
              onCreate={(name) => void createLabelAndAttach(name)}
            />
          </RailGroup>

          {/* Sessions are a count on purpose: each already renders as a card in
              the timeline, and listing them twice says the same thing twice. */}
          <RailGroup label="Sessions">
            <span className="px-2 text-sm text-muted-foreground">
              {sessions.length === 0 ? 'None yet' : `${sessions.length} linked`}
            </span>
          </RailGroup>
        </aside>
      </div>
    </div>
  );
}
