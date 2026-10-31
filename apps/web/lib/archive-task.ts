import { archiveTaskAction, type ArchiveTaskAction } from '@/lib/archive-task-pref';
import type {
  AgentInstanceResponse,
  TaskResponse,
  TaskStatus,
  getBackendAPI,
} from '@/lib/backend-api';

/**
 * What archiving a session should do to the task it works on: leave it be, or
 * set it to a status. The server never moves a task when its session is
 * archived; the web asks (or follows Settings → Tasks) and then changes the
 * task itself, with an ordinary task update.
 */
export type ArchiveTaskChoice = 'no_change' | 'todo' | 'in_progress' | 'in_review' | 'done';

/** The archive dialog's choices, in the order the board lists its columns. */
export const ARCHIVE_TASK_CHOICES: readonly ArchiveTaskChoice[] = [
  'no_change',
  'todo',
  'in_progress',
  'in_review',
  'done',
];

/** The task status a choice sets, or null for "No change". */
export function archiveChoiceStatus(choice: ArchiveTaskChoice): TaskStatus | null {
  return choice === 'no_change' ? null : choice;
}

/**
 * Task statuses an archive offers to move on: work under way. A task nobody
 * has started, or one already blocked, done or cancelled, is left without
 * asking.
 */
const ASK_ABOUT: ReadonlySet<TaskStatus> = new Set<TaskStatus>(['in_progress', 'in_review']);

/**
 * Session statuses that are still part of the work on a task: running, or
 * waiting on the user. REVIEWED (read and put down) and the ended statuses
 * do not count.
 */
const OPEN_SESSION_STATUSES: ReadonlySet<string> = new Set([
  'STARTING',
  'ACTIVE',
  'AWAITING_INPUT',
  'PAUSED',
]);

export interface ArchiveTaskContext {
  task: TaskResponse;
  /** Other sessions on the task still running or waiting on the user. */
  otherOpenSessions: number;
}

/** Done when this was the task's last open session; otherwise No change. */
export function defaultArchiveChoice(context: Pick<ArchiveTaskContext, 'otherOpenSessions'>): ArchiveTaskChoice {
  return context.otherOpenSessions > 0 ? 'no_change' : 'done';
}

/** Sessions on the task that are still open, leaving out the ones being archived. */
export function countOtherOpenSessions(
  sessions: readonly Pick<AgentInstanceResponse, 'id' | 'status'>[],
  archiving: readonly string[],
): number {
  return sessions.filter((s) => !archiving.includes(s.id) && OPEN_SESSION_STATUSES.has(s.status))
    .length;
}

type TaskApi = Pick<ReturnType<typeof getBackendAPI>, 'getTask' | 'listTaskSessions' | 'updateTask'>;

/**
 * The task `archiving` works on and how many other sessions are still on it,
 * or null when the task is not one an archive offers to move on.
 */
export async function loadArchiveTaskContext(
  api: TaskApi,
  taskId: string,
  archiving: readonly string[],
): Promise<ArchiveTaskContext | null> {
  const [task, sessions] = await Promise.all([api.getTask(taskId), api.listTaskSessions(taskId)]);
  if (!ASK_ABOUT.has(task.status)) return null;
  return { task, otherOpenSessions: countOtherOpenSessions(sessions, archiving) };
}

/**
 * What the standing answer does without asking: `mark_done` closes the task
 * when this was its last open session. `ask` is the dialog's job and `leave`
 * does nothing, so both are null here.
 */
export function standingTaskStatus(
  action: ArchiveTaskAction,
  context: ArchiveTaskContext | null,
): TaskStatus | null {
  return action === 'mark_done' && context && context.otherOpenSessions === 0 ? 'done' : null;
}

/**
 * After archiving several sessions at once (a whole worktree), apply the
 * standing answer to their tasks. Nothing can be asked mid-batch, so only
 * `mark_done` acts: each task whose open sessions were all in the batch is
 * marked done, once. Resolves to the tasks it could not update.
 */
export async function applyStandingAnswerToTasks(
  api: TaskApi,
  archived: readonly { id: string; task_id?: string | null }[],
  action: ArchiveTaskAction = archiveTaskAction(),
): Promise<string[]> {
  if (action !== 'mark_done') return [];
  const ids = archived.map((s) => s.id);
  const taskIds = [...new Set(archived.flatMap((s) => (s.task_id ? [s.task_id] : [])))];
  const failed: string[] = [];
  await Promise.all(
    taskIds.map(async (taskId) => {
      try {
        const status = standingTaskStatus(action, await loadArchiveTaskContext(api, taskId, ids));
        if (status) await api.updateTask(taskId, { status });
      } catch (error) {
        console.error('Failed to update the task after archiving:', error);
        failed.push(taskId);
      }
    }),
  );
  return failed;
}

export const ARCHIVE_TASK_ACTIONS: readonly {
  value: ArchiveTaskAction;
  label: string;
  description: string;
}[] = [
  {
    value: 'ask',
    label: 'Ask me each time',
    description: "Choose the task's status when you archive a session that is working on it.",
  },
  {
    value: 'mark_done',
    label: 'Mark the task done',
    description: 'Archiving marks the task done, unless another session on it is still open.',
  },
  {
    value: 'leave',
    label: 'Leave the task alone',
    description: 'Archiving a session never changes its task.',
  },
];
