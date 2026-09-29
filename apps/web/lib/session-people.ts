// Who to draw for a session with more than one person in it (collaboration
// §8.2): the author bylines in the transcript and the faces on a sidebar row.
//
// Both follow the rule that keeps multiplayer chrome from taxing the solo
// case: a session one person writes in — one's own or someone else's — draws
// no faces, anywhere.

import type { AgentInstanceResponse, MessageResponse, PrincipalResponse } from '@/lib/backend-api';

/**
 * The people a sidebar row shows: everyone who has written in the session
 * (the owner first), but only once there is more than one of them. A session
 * one person writes in — one's own or someone else's — shows no faces.
 */
export function sessionRowPeople(
  instance: Pick<AgentInstanceResponse, 'participants'>,
): PrincipalResponse[] {
  const participants = instance.participants ?? [];
  return participants.length > 1 ? participants : [];
}

export type BylineMessage = Pick<
  MessageResponse,
  'id' | 'sender_type' | 'sender_user_id' | 'sender_user_display_name'
>;

/** A transcript row as far as authorship is concerned. */
export type AuthoredItem = { type: 'message'; message: BylineMessage } | { type: string };

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

/**
 * Who wrote a user message, in a session more than one person writes in —
 * null for a solo session, so nothing is drawn. A message with no sender was
 * typed into the owner's terminal: theirs. A row still in flight
 * (`optimistic-…`) has no sender yet but is the viewer's own, so it is named
 * as theirs when `viewerId` is known (the byline then does not pop in when the
 * echo swaps the row). A sender the participant list does not know yet (their
 * first message, before the page refetches the session) is named from the
 * message itself, with initials until the list catches up.
 */
export function messageAuthorResolver(
  participants: readonly PrincipalResponse[] | null | undefined,
  viewerId: string | null = null,
): ((message: BylineMessage) => PrincipalResponse | null) | null {
  if (!participants || participants.length < 2) return null;
  const byId = new Map(participants.map((person) => [person.id, person] as const));
  const owner = participants[0];
  const viewer = viewerId ? (byId.get(viewerId) ?? null) : null;
  return (message) => {
    if (message.id.startsWith('optimistic-')) return viewer;
    if (!message.sender_user_id) return owner;
    return (
      byId.get(message.sender_user_id) ?? {
        type: 'user',
        id: message.sender_user_id,
        name: message.sender_user_display_name ?? null,
        avatar_image_uri: null,
        emoji: null,
        updated_at: null,
      }
    );
  };
}

/**
 * Which user messages open a byline (avatar + name) and whose it is: the
 * first of each run of consecutive messages by one person, the way a group
 * chat names a sender once per run rather than on every bubble. Anything
 * between two of their messages — the agent's reply, a tool run, a date
 * separator — ends the run, so in practice every prompt after an agent turn
 * is named. Empty for a solo session (see `messageAuthorResolver`).
 */
export function transcriptBylines(
  items: readonly AuthoredItem[],
  authorOf: ReturnType<typeof messageAuthorResolver>,
): Map<string, PrincipalResponse> {
  const bylines = new Map<string, PrincipalResponse>();
  if (!authorOf) return bylines;
  let previousAuthor: string | null = null;
  for (const item of items) {
    const message = 'message' in item && item.type === 'message' ? item.message : null;
    const author = message && USER_SENDER_TYPES.has(message.sender_type) ? authorOf(message) : null;
    if (!message || !author) {
      previousAuthor = null;
      continue;
    }
    const key = author.id ?? '';
    if (key !== previousAuthor) bylines.set(message.id, author);
    previousAuthor = key;
  }
  return bylines;
}

/**
 * Whether a message just sent in a listed session brings someone new into it:
 * a sender who is neither its owner nor already among its participants. The
 * list row then needs refetching, since it may have just become a session
 * with more than one person. On one's own rows the owner is the viewer, so
 * those wait until `viewerId` is known.
 */
export function addsSomeoneToRow(
  instance: Pick<AgentInstanceResponse, 'owner' | 'participants'>,
  senderUserId: string | null | undefined,
  viewerId: string | null,
): boolean {
  // No sender: typed into the owner's terminal.
  if (!senderUserId) return false;
  const ownerId = instance.owner ? instance.owner.id : viewerId;
  if (!ownerId || senderUserId === ownerId) return false;
  return !(instance.participants ?? []).some((person) => person.id === senderUserId);
}
