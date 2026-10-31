import { archiveTaskAction, type ArchiveTaskAction } from '@/lib/archive-task-pref';
import type { ArchivePreview, ArchiveTaskChoice, TaskStatus } from '@/lib/backend-api';

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
 * Body of `PUT /agent-instances/{id}/status` for an archive. An archive that
 * names no choice follows this device's standing answer: `leave` sends
 * `no_change`, anything else sends nothing and the server's default mapping
 * applies. Every web archive builds its body here, so none of them can skip it.
 */
export function archiveStatusBody(
  taskStatus?: ArchiveTaskChoice,
  action: ArchiveTaskAction = archiveTaskAction(),
): {
  status: 'COMPLETED';
  task_status?: ArchiveTaskChoice;
} {
  const choice = taskStatus ?? (action === 'leave' ? 'no_change' : undefined);
  return choice ? { status: 'COMPLETED', task_status: choice } : { status: 'COMPLETED' };
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
