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
import { ArrowLeft, Play, Plus } from 'lucide-react';

import {
  AgentInstanceResponse,
  AgentProfile,
  ProjectResponse,
  ProjectRole,
  projectRoleAtLeast,
  TaskActivityResponse,
  TaskCommentResponse,
  TaskLabelResponse,
  TaskReactionSummary,
  TaskResponse,
  TaskSessionRef,
  TaskStatus,
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
import { agentsForProject, labelOwnerForProject, labelsForProject } from '@/lib/project-vocabulary';
import type { Principal } from '@/lib/principals';
import {
  AssigneePickerPill,
  DatePickerPill,
  LabelPickerPill,
  ParentPickerPill,
  PriorityPickerPill,
  ProjectPickerPill,
  PropertyRows,
  projectLabel,
  StatusPickerPill,
  toDateOnly,
  dateOnlyToLocalDate,
} from '@/components/dashboard/task-ui';
import { CreatedInSession, ReactionRow, TaskTimeline } from './task-timeline';
import { CommentComposer } from './comment-composer';
import { ParentTaskLink, SubTasksSection, subTaskProgress } from './sub-tasks';
import { TaskDetailSkeleton } from './task-detail-skeleton';
import { StartSessionDialog } from '../start-session-dialog';
import { cn } from '@/lib/utils';

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
  // The sessions the task and its rows name ("Created in", "via") that this
  // viewer may open. Arrives with the timeline.
  const [sessionRefs, setSessionRefs] = useState<TaskSessionRef[]>([]);
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
  // Set when "Start session" is fired on a task that has sub-tasks — opens the
  // picker so the user can choose which ride along (same flow as the board).
  const [sessionDialog, setSessionDialog] = useState<{
    task: TaskResponse;
    subtasks: TaskResponse[];
  } | null>(null);

  // The whole page's data. Kept in one function so focus-revalidation and the
  // interval can't drift apart from the initial load.
  const load = useCallback(async () => {
    if (!api || !taskId) return;
    try {
      const [taskRow, timeline, taskSessions, projectRows, taskRows] = await Promise.all([
        api.getTask(taskId),
        api.getTaskTimeline(taskId),
        api.listTaskSessions(taskId),
        api.listProjects(),
        // The sub-task list and the parent picker both read this. Polled with
        // the rest so a sub-task an agent closes shows here, but a failure only
        // keeps the last list rather than breaking the page.
        api.listTasks().catch(() => null),
      ]);
      setTask(taskRow);
      setComments(timeline.comments);
      setActivity(timeline.activity);
      setSessionRefs(timeline.sessions);
      setTaskReactions(timeline.reactions);
      setSessions(taskSessions);
      setProjects(projectRows);
      if (taskRows) setAllTasks(taskRows);
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

  // The caller's standing on this task's board (collaboration §4), for
  // read-side role hiding. The backend enforces the same floors; this only
  // keeps a viewer from being offered controls that would 403. An unfiled
  // task is visible to its owner alone. A project missing from the list reads
  // as the least privilege, never as owner.
  const roleOf = (t: TaskResponse): ProjectRole | undefined =>
    t.project_id === null ? 'owner' : projects.find((p) => p.id === t.project_id)?.role;
  const taskRole: ProjectRole | undefined = task ? roleOf(task) : undefined;
  const canEdit = projectRoleAtLeast(taskRole, 'editor');
  const canComment = projectRoleAtLeast(taskRole, 'commenter');
  const isOwner = taskRole === 'owner';

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

  // Tree context, all off the flat list: this task's children (in board
  // order), its parent and that parent's children for the "Sub-task of" link,
  // and each task's own child progress for sub-tasks that are parents too.
  const subTasks = useMemo(
    () =>
      task
        ? allTasks
            .filter((t) => t.parent_task_id === task.id)
            .sort((a, b) => a.position - b.position)
        : [],
    [allTasks, task],
  );
  const parentTask = useMemo(
    () => (task?.parent_task_id ? allTasks.find((t) => t.id === task.parent_task_id) ?? null : null),
    [allTasks, task],
  );
  const siblingTasks = useMemo(
    () =>
      task?.parent_task_id
        ? allTasks.filter((t) => t.parent_task_id === task.parent_task_id)
        : [],
    [allTasks, task],
  );
  const progressById = useMemo(() => {
    const byParent = new Map<string, TaskResponse[]>();
    for (const t of allTasks) {
      if (!t.parent_task_id) continue;
      byParent.set(t.parent_task_id, [...(byParent.get(t.parent_task_id) ?? []), t]);
    }
    return new Map([...byParent].map(([id, children]) => [id, subTaskProgress(children)]));
  }, [allTasks]);

  // Same shape as the board's add: the child takes the parent's project and
  // lands at the end of the board order.
  const addSubTask = useCallback(
    async (title: string) => {
      if (!api || !task) return;
      const maxPosition = allTasks.reduce((max, t) => Math.max(max, t.position), 0);
      const created = await api.createTask({
        title,
        parent_task_id: task.id,
        project_id: task.project_id,
        position: maxPosition + 1,
      });
      setAllTasks((prev) => [...prev, created]);
    },
    [api, task, allTasks],
  );

  const setSubTaskStatus = useCallback(
    async (child: TaskResponse, status: TaskStatus) => {
      if (!api) return;
      const replace = (next: TaskResponse) =>
        setAllTasks((prev) => prev.map((t) => (t.id === next.id ? next : t)));
      replace({ ...child, status });
      try {
        replace(await api.updateTask(child.id, { status }));
      } catch {
        replace(child);
      }
    },
    [api],
  );

  // Mirrors the dialog's label affordance: type a name, get a label, attached.
  const createLabelAndAttach = useCallback(
    async (name: string) => {
      if (!api || !task) return;
      const project = projects.find((p) => p.id === task.project_id);
      const label = await api.createTaskLabel({
        name,
        color: '#6b7280',
        team_id: labelOwnerForProject(project),
      });
      setLabels((prev) => [...prev, label]);
      await patchTask({ label_ids: [...task.labels.map((l) => l.id), label.id] });
    },
    [api, task, patchTask, projects],
  );

  const postComment = useCallback(
    async (body: string, parentCommentId?: string) => {
      if (!api || !task) return;
      const timeline = await api.createTaskComment(task.id, body, parentCommentId);
      // The whole timeline comes back rather than the one new comment, so a
      // reply lands already spliced under its root instead of the client having
      // to guess where in the thread it goes.
      setComments(timeline.comments);
      setActivity(timeline.activity);
      setSessionRefs(timeline.sessions);
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
      setSessionRefs(timeline.sessions);
      setTaskReactions(timeline.reactions);
    },
    [api, task],
  );

  // "Start session" seeds a new agent session from this task — the same path
  // as the board's context-menu action: with sub-tasks, open the picker first;
  // without, go straight to the New Session page.
  const startSession = useCallback(() => {
    if (!task) return;
    const children = allTasks.filter((t) => t.parent_task_id === task.id);
    if (children.length === 0) {
      router.push(`/dashboard/sessions/new?taskId=${task.id}`);
      return;
    }
    setSessionDialog({ task, subtasks: children });
  }, [router, task, allTasks]);

  // Picker confirmed: carry the chosen sub-task ids to the New Session page,
  // which seeds them into the prompt and advances their status with the parent.
  const confirmStartSession = useCallback(
    (selectedIds: string[]) => {
      if (!sessionDialog) return;
      const params = new URLSearchParams({ taskId: sessionDialog.task.id });
      if (selectedIds.length > 0) params.set('subtasks', selectedIds.join(','));
      setSessionDialog(null);
      router.push(`/dashboard/sessions/new?${params.toString()}`);
    },
    [router, sessionDialog],
  );

  if (isLoading) return <TaskDetailSkeleton />;

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
              <span>{projectLabel(projects.find((p) => p.id === task.project_id))}</span>
            </div>
            <EditableTitle
              value={task.title}
              onSave={(title) => void patchTask({ title })}
              readOnly={!canEdit}
            />
            <ParentTaskLink task={task} parent={parentTask} siblings={siblingTasks} />
            <CreatedInSession
              sessionRef={sessionRefs.find((ref) => ref.id === task.created_in_instance_id)}
            />
            <EditableDescription
              value={task.description}
              onSave={(description) => void patchTask({ description })}
              readOnly={!canEdit}
            />
            {/* The task itself is reactable, like an issue's opening post. */}
            <ReactionRow
              reactions={taskReactions}
              viewer={viewer}
              onToggle={
                canComment ? (emoji) => void toggleReaction('task', task.id, emoji) : undefined
              }
            />
          </div>

          <SubTasksSection
            key={task.id}
            subTasks={subTasks}
            progressById={progressById}
            viewer={viewer}
            canAdd={canEdit}
            canEditTask={(t) => projectRoleAtLeast(roleOf(t), 'editor')}
            onAdd={addSubTask}
            onStatusChange={(t, status) => void setSubTaskStatus(t, status)}
          />

          <div className="space-y-3 border-t pt-6">
            <TaskTimeline
              comments={comments}
              activity={activity}
              sessions={sessions}
              sessionRefs={sessionRefs}
              viewer={viewer}
              onToggleCommentReaction={
                canComment
                  ? (commentId, emoji) => void toggleReaction('comment', commentId, emoji)
                  : undefined
              }
              onReply={
                canComment
                  ? (parentCommentId, body) => postComment(body, parentCommentId)
                  : undefined
              }
            />
            {/* The bottom composer always starts a new thread; replying is
                the affordance inside a thread. */}
            {canComment ? (
              <CommentComposer onSubmit={(body) => postComment(body)} />
            ) : (
              <p className="text-xs text-muted-foreground">
                You can view this task. Commenting needs commenter access to its project.
              </p>
            )}
          </div>
        </div>

        {/* Below editor the whole rail is inert: a disabled fieldset turns
            every picker trigger inside it into a plain, unclickable label. */}
        <fieldset
          disabled={!canEdit}
          className={cn(
            'w-60 shrink-0 space-y-5',
            !canEdit && '[&_button]:cursor-default',
          )}
        >
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
              agentProfiles={agentsForProject(
                agentProfiles,
                projects.find((p) => p.id === task.project_id),
              )}
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
            {canEdit && hidden.length > 0 && (
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
              labels={labelsForProject(
                labels,
                projects.find((p) => p.id === task.project_id),
                task.labels,
              )}
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
            {/* Only the owner starts sessions from a task: a session runs on
                your own machine and links back to the task, and the link is
                an owner-side write (§4's owner-only lens). */}
            {isOwner && (
              <button
                type="button"
                onClick={startSession}
                className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
              >
                <Play className="size-3.5" />
                Start session
              </button>
            )}
          </RailGroup>
        </fieldset>
      </div>

      <StartSessionDialog
        open={!!sessionDialog}
        parentTask={sessionDialog?.task ?? null}
        subtasks={sessionDialog?.subtasks ?? []}
        onClose={() => setSessionDialog(null)}
        onConfirm={confirmStartSession}
      />
    </div>
  );
}
