/**
 * Questions an agent asked on a task, as the board and the thread show them
 * (plans/todos/task-questions-waiting-on.md). A question is stored state on the
 * task (`open_questions`) and its comment (`question`), never read from text,
 * so "Waiting on Nick" is only ever as wrong as the server.
 */

import type {
  PrincipalResponse,
  TaskCommentResponse,
  TaskResponse,
} from '@/lib/backend-api';
import type { WaitingAgent } from '@/lib/task-mentions';

/** The people a task waits on, oldest question first, each once. */
export function waitingOnPeople(task: Pick<TaskResponse, 'open_questions'>): PrincipalResponse[] {
  const seen = new Set<string>();
  const out: PrincipalResponse[] = [];
  for (const question of task.open_questions ?? []) {
    const key = question.addressee.id ?? `?${out.length}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(question.addressee);
  }
  return out;
}

/** Whether the task waits on the viewer. */
export function isWaitingOn(
  task: Pick<TaskResponse, 'open_questions'>,
  viewerId: string | null,
): boolean {
  if (!viewerId) return false;
  return (task.open_questions ?? []).some((q) => q.addressee.id === viewerId);
}

/**
 * "Waiting on you", "Waiting on Nick", "Waiting on you and Ada", "Waiting on 3
 * people". Null when it waits on nobody.
 */
export function waitingOnLabel(
  people: PrincipalResponse[],
  viewerId: string | null,
): string | null {
  if (people.length === 0) return null;
  if (people.length > 2) return `Waiting on ${people.length} people`;
  // The viewer reads first: it is the half of the label they act on.
  const ordered = [...people].sort(
    (a, b) => Number(b.id === viewerId && !!viewerId) - Number(a.id === viewerId && !!viewerId),
  );
  const names = ordered.map((p) =>
    viewerId && p.id === viewerId ? 'you' : p.name?.trim() || 'someone',
  );
  return `Waiting on ${names.join(' and ')}`;
}

/** A comment's question, while it is still open. */
export function openQuestion(comment: TaskCommentResponse) {
  const question = comment.question;
  if (!question || question.closed_at || comment.deleted_at) return null;
  return question;
}

/**
 * The agents with an open question to the viewer, from a task's thread: whom
 * the viewer's next comment answers (lib/task-mentions `agentsToWake`).
 */
export function askersFromComments(
  comments: TaskCommentResponse[],
  viewerId: string | null,
): WaitingAgent[] {
  if (!viewerId) return [];
  const out: WaitingAgent[] = [];
  for (const comment of comments) {
    const question = openQuestion(comment);
    if (!question || question.addressee.id !== viewerId) continue;
    const author = comment.author;
    if (author.type !== 'agent' || !author.id) continue;
    if (out.some((a) => a.id === author.id)) continue;
    out.push({ id: author.id, name: author.name?.trim() || 'the agent' });
  }
  return out;
}

/** The same, from the task's `open_questions` (where no thread is loaded). */
export function askersFromTask(
  task: Pick<TaskResponse, 'open_questions'>,
  viewerId: string | null,
): WaitingAgent[] {
  if (!viewerId) return [];
  const out: WaitingAgent[] = [];
  for (const question of task.open_questions ?? []) {
    const by = question.asked_by;
    if (question.addressee.id !== viewerId || by.type !== 'agent' || !by.id) continue;
    if (out.some((a) => a.id === by.id)) continue;
    out.push({ id: by.id, name: by.name?.trim() || 'the agent' });
  }
  return out;
}
