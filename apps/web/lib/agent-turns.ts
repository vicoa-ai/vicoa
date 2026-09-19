/**
 * Turn boundaries in the rendered transcript.
 *
 * A turn is the run of agent messages since the last user message. Only its
 * LAST message carries the hover footer — one copy/fork per turn instead of one
 * per message, which is what keeps the transcript tight (every footer reserves
 * a row, so a footer per message pushed consecutive agent rows 28px apart).
 * Copying that footer yields the whole turn's prose, not just the final chunk.
 *
 * The same grouping feeds the fork transcript (lib/fork-session.ts), which
 * appends each turn's edited files after its last line of prose.
 */

export type TurnMessageKind =
  /** Ends the current turn. */
  | 'user'
  /** Agent prose — part of the turn, and a candidate footer anchor. */
  | 'agent'
  /** Tool runs, reasoning cards: inside the turn, but never a footer anchor. */
  | 'other';

export interface TurnMessageEntry {
  id: string;
  kind: TurnMessageKind;
  /** Visible text, concatenated into the turn's clipboard payload. */
  text: string;
}

export interface Turn<T> {
  /** The user message that opened the turn; null for a leading agent run. */
  user: T | null;
  /** Every agent-side entry of the turn (prose and other), in order. */
  entries: T[];
}

/**
 * Split a transcript into turns: each user entry opens one, and everything
 * agent-side that follows belongs to it until the next user entry. A user
 * message answered by nothing still yields a turn (with no entries) so callers
 * see every user message; a leading agent run gets a turn with `user: null`.
 */
export function groupTurns<T extends { kind: TurnMessageKind }>(entries: T[]): Turn<T>[] {
  const turns: Turn<T>[] = [];
  let current: Turn<T> | null = null;
  for (const entry of entries) {
    if (entry.kind === 'user') {
      current = { user: entry, entries: [] };
      turns.push(current);
      continue;
    }
    if (!current) {
      current = { user: null, entries: [] };
      turns.push(current);
    }
    current.entries.push(entry);
  }
  return turns;
}

/**
 * Map each turn-ending agent message id to that whole turn's concatenated
 * prose. Ids absent from the map are mid-turn (or not agent messages) and get
 * no footer.
 */
export function computeTurnEnds(entries: TurnMessageEntry[]): Map<string, string> {
  const ends = new Map<string, string>();
  for (const turn of groupTurns(entries)) {
    const prose = turn.entries.filter((entry) => entry.kind === 'agent');
    if (prose.length === 0) continue;
    const text = prose
      .map((entry) => entry.text.trim())
      .filter(Boolean)
      .join('\n\n');
    ends.set(prose[prose.length - 1].id, text);
  }
  return ends;
}
