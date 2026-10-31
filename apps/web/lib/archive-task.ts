import type { ArchivePreview, ArchiveTaskAction, ArchiveTaskChoice, TaskStatus } from '@/lib/backend-api';

/** SWR key for the caller's preferences (Settings → Tasks reads and writes it). */
export const USER_PREFERENCES_KEY = 'user-preferences';

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

/** The choice to preselect: what the server says a plain archive should lean to. */
export function defaultArchiveChoice(preview: Pick<ArchivePreview, 'default'>): ArchiveTaskChoice {
  return preview.default;
}

/**
 * Body of `PUT /agent-instances/{id}/status` for an archive. Without a choice
 * the server decides from the user's standing preference, which is also what an
 * older client that cannot ask gets.
 */
export function archiveStatusBody(taskStatus?: ArchiveTaskChoice): {
  status: 'COMPLETED';
  task_status?: ArchiveTaskChoice;
} {
  return taskStatus ? { status: 'COMPLETED', task_status: taskStatus } : { status: 'COMPLETED' };
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
    description: 'The task follows the session, unless another session on it is still open.',
  },
  {
    value: 'leave',
    label: 'Leave the task alone',
    description: 'Archiving a session never changes its task.',
  },
];
