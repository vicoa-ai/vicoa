'use client';

// The data behind <TaskDetail> (task-detail.tsx): one task, its timeline, the
// sessions it spawned and the lists its pickers read, plus every write the
// page and the peek panel make. Both variants call the same hook, so the panel
// can never drift from what the task page does with a task.
//
// No WebSocket channel, by decision (§9). The timeline revalidates on window
// focus and on a slow interval; polling hits the stateless backend app, while
// the relay is pinned to workers=1 and already carries every daemon socket.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';

import {
  AgentProfile,
  BackendApiError,
  ProjectResponse,
  ProjectRole,
  projectRoleAtLeast,
  TaskActivityResponse,
  TaskCommentResponse,
  TaskLabelResponse,
  TaskReactionSummary,
  TaskResponse,
  TaskSessionRef,
  TaskSessionResponse,
  TaskStatus,
  TaskTimelineResponse,
  UpdateTaskRequest,
  UserProfile,
} from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { labelOwnerForProject } from '@/lib/project-vocabulary';
import type { Principal } from '@/lib/principals';
import { projectMentionTarget } from '@/lib/project-mention-target';
import { runHandBack } from './hand-back';
import { subTaskProgress } from './sub-tasks';

// Slow on purpose: this is a single-player backlog, and the point of the poll
// is to catch an agent's comment landing while the tab sits open — not to
// simulate realtime. Focus revalidation covers the "came back to the tab" case.
const POLL_MS = 30_000;

/** What doesn't depend on which task is open: the viewer and the pickers' lists. */
export interface TaskReferenceData {
  me: UserProfile | null;
  labels: TaskLabelResponse[];
  setLabels: Dispatch<SetStateAction<TaskLabelResponse[]>>;
  agentProfiles: AgentProfile[];
}

/**
 * Loaded once, above the per-task state, so a panel stepping through tasks
 * doesn't fetch the viewer and the picker lists again for each one.
 */
export function useTaskReferenceData(): TaskReferenceData {
  const { api } = useAgentDashboard();
  const [me, setMe] = useState<UserProfile | null>(null);
  // The pickers need the same reference data the board dialog uses.
  const [labels, setLabels] = useState<TaskLabelResponse[]>([]);
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);

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

  return { me, labels, setLabels, agentProfiles };
}

/**
 * One task's state. Meant to live in a component keyed by `taskId` (see
 * <TaskDetail>): it holds no reset logic of its own, because a fresh mount per
 * task is what guarantees nothing of the previous task survives the switch.
 */
export function useTaskDetail(
  taskId: string,
  { me, labels, setLabels, agentProfiles }: TaskReferenceData,
  onLoaded?: (task: TaskResponse) => void,
) {
  const { api } = useAgentDashboard();

  const [task, setTask] = useState<TaskResponse | null>(null);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [comments, setComments] = useState<TaskCommentResponse[]>([]);
  const [activity, setActivity] = useState<TaskActivityResponse[]>([]);
  const [taskReactions, setTaskReactions] = useState<TaskReactionSummary[]>([]);
  // Every session the task's record names, most recently active first (the
  // rail's Sessions list). The ones filed under the task are `sessions`.
  const [relatedSessions, setRelatedSessions] = useState<TaskSessionResponse[]>([]);
  // The sessions filed under the task: the timeline's session cards.
  const sessions = useMemo(
    () => relatedSessions.filter((session) => session.task_relations.includes('linked')),
    [relatedSessions],
  );
  // The sessions the task and its rows name ("Created in", "via") that this
  // viewer may open. Arrives with the timeline.
  const [sessionRefs, setSessionRefs] = useState<TaskSessionRef[]>([]);
  const [allTasks, setAllTasks] = useState<TaskResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  // The failed load's HTTP status, so the panel can say "not found" briefly.
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // A load still in flight when the host moves on to another task resolves
  // into an unmounted component: its state writes are no-ops, and this keeps
  // it from telling the host about a task that is no longer open.
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  // The whole page's data. Kept in one function so focus-revalidation and the
  // interval can't drift apart from the initial load.
  const load = useCallback(async () => {
    if (!api || !taskId) return;
    try {
      const [taskRow, timeline, taskSessions, projectRows, taskRows] = await Promise.all([
        api.getTask(taskId),
        api.getTaskTimeline(taskId),
        api.listTaskSessions(taskId, { related: true }),
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
      setRelatedSessions(taskSessions);
      setProjects(projectRows);
      if (taskRows) setAllTasks(taskRows);
      setError(null);
      setErrorStatus(null);
      if (aliveRef.current) onLoadedRef.current?.(taskRow);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load task');
      const status = (err as Partial<BackendApiError> | null)?.status;
      setErrorStatus(typeof status === 'number' ? status : null);
    } finally {
      setIsLoading(false);
    }
  }, [api, taskId]);

  useEffect(() => {
    void load();
  }, [load]);

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
  const roleOf = useCallback(
    (t: TaskResponse): ProjectRole | undefined =>
      t.project_id === null ? 'owner' : projects.find((p) => p.id === t.project_id)?.role,
    [projects],
  );
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
  // `@` in the description searches the task's project folder, as in the
  // dialog the task was written in.
  const mentionTarget = useMemo(
    () => projectMentionTarget(projects.find((p) => p.id === task?.project_id)),
    [projects, task?.project_id],
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
    [api, task, patchTask, projects, setLabels],
  );

  // Every comment and reaction mutation answers with the whole timeline.
  const applyTimeline = useCallback((timeline: TaskTimelineResponse) => {
    setComments(timeline.comments);
    setActivity(timeline.activity);
    setSessionRefs(timeline.sessions);
    setTaskReactions(timeline.reactions);
  }, []);

  const postComment = useCallback(
    async (body: string, parentCommentId?: string) => {
      if (!api || !task) return;
      // The whole timeline comes back rather than the one new comment, so a
      // reply lands already spliced under its root instead of the client having
      // to guess where in the thread it goes.
      applyTimeline(await api.createTaskComment(task.id, body, parentCommentId));
    },
    [api, task, applyTimeline],
  );

  const editComment = useCallback(
    async (commentId: string, body: string) => {
      if (!api || !task) return;
      applyTimeline(await api.updateTaskComment(task.id, commentId, body));
    },
    [api, task, applyTimeline],
  );

  // A deleted comment leaves a tombstone, so its replies stay readable.
  const deleteComment = useCallback(
    async (commentId: string) => {
      if (!api || !task) return;
      try {
        applyTimeline(await api.deleteTaskComment(task.id, commentId));
      } catch (err) {
        console.error('Failed to delete comment:', err);
      }
    },
    [api, task, applyTimeline],
  );

  const toggleReaction = useCallback(
    async (targetType: 'task' | 'comment', targetId: string, emoji: string) => {
      if (!api || !task) return;
      applyTimeline(
        await api.toggleTaskReaction(task.id, {
          targetType,
          targetId,
          emoji,
        }),
      );
    },
    [api, task, applyTimeline],
  );

  // The panel's "Reply and hand back": a new thread, then In Review. Not an
  // optimistic patch like the pickers: the host moves on to the next task once
  // this resolves, so it has to mean the server took both writes.
  const handBackPosted = useRef<string | null>(null);
  const replyAndHandBack = useCallback(
    async (body: string): Promise<TaskResponse> => {
      if (!api || !task) throw new Error('Task not loaded');
      const updated = await runHandBack(body, handBackPosted, {
        postReply: (reply) => postComment(reply),
        moveToReview: () => api.updateTask(task.id, { status: 'in_review' }),
      });
      setTask(updated);
      // The status change wrote an activity row.
      void load();
      return updated;
    },
    [api, task, postComment, load],
  );

  const viewer = useMemo<Principal | null>(
    () =>
      me
        ? {
            type: 'user',
            id: me.id,
            name: me.display_name ?? me.email,
            avatarImageUri: me.avatar_image_uri,
            emoji: me.avatar_emoji,
            updatedAt: me.updated_at,
          }
        : null,
    [me],
  );

  return {
    task,
    projects,
    comments,
    activity,
    taskReactions,
    sessions,
    relatedSessions,
    sessionRefs,
    labels,
    allTasks,
    agentProfiles,
    viewer,
    error,
    errorStatus,
    isLoading,
    roleOf,
    canEdit,
    canComment,
    isOwner,
    subTasks,
    parentTask,
    siblingTasks,
    mentionTarget,
    progressById,
    load,
    patchTask,
    addSubTask,
    setSubTaskStatus,
    createLabelAndAttach,
    postComment,
    editComment,
    deleteComment,
    toggleReaction,
    replyAndHandBack,
  };
}

export type TaskDetailModel = ReturnType<typeof useTaskDetail>;
