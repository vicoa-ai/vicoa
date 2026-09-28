/**
 * Prompting a session someone shared with you (collaboration §8.2, a slice of
 * P6 pulled forward): whether the read-only viewer shows a composer, whether
 * it may send right now, and who wrote each message once more than one person
 * has.
 *
 * The backend already lets an editor (WRITE) post to a shared session and
 * routes the message to the owner's daemon; this is only the client's half.
 * There is still no socket for a grantee, so replies arrive by polling.
 */

import type { AgentInstanceDetail, MessageResponse } from './backend-api';
import { parseQueuePayload, isPendingQueueStatus } from '@/components/dashboard/queue-status';
import { isClosedByDesign, isReachable, resolveLiveState } from './session-liveness';

export interface ComposeState {
  canSend: boolean;
  /** Why sending is off, for the line under a disabled composer. */
  reason: string | null;
}

/**
 * Null when the caller may not prompt this session at all (below editor), so
 * the viewer draws no composer. Otherwise whether a message can reach the
 * agent now: a grantee cannot resume a stopped agent (that runs on the owner's
 * machine), so a session that is over or not running refuses up front rather
 * than taking a message nothing will read.
 */
export function sharedComposeState(
  session: AgentInstanceDetail,
  now: number = Date.now(),
): ComposeState | null {
  if (session.access_level !== 'WRITE') return null;
  if (isClosedByDesign(session.status)) {
    return { canSend: false, reason: 'This session has ended.' };
  }
  // A grantee's row carries no `machine_id` (redacted), which the resolver
  // reads as "host unknown". The server derived `live_state` with the machine
  // in hand, so defer to it unless the session's own heartbeat settles it.
  const resolved = resolveLiveState(session, undefined, now);
  const state = resolved === 'unknown' ? (session.live_state ?? 'unknown') : resolved;
  if (!isReachable(state)) {
    return {
      canSend: false,
      reason: "The owner's agent isn't running, so a message can't reach it right now.",
    };
  }
  return { canSend: true, reason: null };
}

/** A user message still waiting in the queue (sent while the agent was busy). */
export function isPendingSend(message: MessageResponse): boolean {
  return isPendingQueueStatus(parseQueuePayload(message)?.status);
}

function isUser(message: MessageResponse): boolean {
  return message.sender_type.toUpperCase() === 'USER';
}

/**
 * Who wrote each user message, but only once a session has more than one
 * writer (§8.2): a solo session reads exactly as it always has. Display names
 * only, never an address; the caller's own messages read "You".
 */
export function senderLabeler(
  messages: MessageResponse[],
  viewerId: string | null,
): ((message: MessageResponse) => string | null) | undefined {
  const writers = new Set<string>();
  // A message that arrived live may carry the writer's id but no name; any
  // other message of theirs that has one names it.
  const names = new Map<string, string>();
  for (const m of messages) {
    if (!isUser(m) || !m.sender_user_id) continue;
    writers.add(m.sender_user_id);
    const name = m.sender_user_display_name?.trim();
    if (name) names.set(m.sender_user_id, name);
  }
  if (writers.size < 2) return undefined;
  return (message) => {
    if (!isUser(message) || !message.sender_user_id) return null;
    if (viewerId && message.sender_user_id === viewerId) return 'You';
    return (
      message.sender_user_display_name?.trim() ||
      names.get(message.sender_user_id) ||
      'Vicoa user'
    );
  };
}

/**
 * Fold a fetched page into what is on screen: rows already shown are replaced
 * by their fresher copy (a queued message's stamp changes once the agent takes
 * it), new rows are appended. Returns `prev` itself when nothing changed, so
 * a steady-state poll does not re-render.
 */
export function mergeMessages(
  prev: MessageResponse[],
  fresh: MessageResponse[],
): MessageResponse[] {
  if (fresh.length === 0) return prev;
  const byId = new Map(fresh.map((m) => [m.id, m]));
  let changed = false;
  const updated = prev.map((m) => {
    const next = byId.get(m.id);
    if (!next) return m;
    if (JSON.stringify(next.message_metadata ?? null) !== JSON.stringify(m.message_metadata ?? null)) {
      changed = true;
      return next;
    }
    return m;
  });
  const seen = new Set(prev.map((m) => m.id));
  const added = fresh.filter((m) => !seen.has(m.id));
  if (!changed && added.length === 0) return prev;
  return [...updated, ...added];
}
