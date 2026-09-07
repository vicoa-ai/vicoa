/**
 * Turn boundaries in the rendered transcript.
 *
 * A turn is the run of agent messages since the last user message. Only its
 * LAST message carries the hover footer — one copy/fork per turn instead of one
 * per message, which is what keeps the transcript tight (every footer reserves
 * a row, so a footer per message pushed consecutive agent rows 28px apart).
 * Copying that footer yields the whole turn's prose, not just the final chunk.
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

/**
 * Map each turn-ending agent message id to that whole turn's concatenated
 * prose. Ids absent from the map are mid-turn (or not agent messages) and get
 * no footer.
 */
export function computeTurnEnds(entries: TurnMessageEntry[]): Map<string, string> {
  const ends = new Map<string, string>();
  let run: TurnMessageEntry[] = [];

  const flush = () => {
    if (run.length === 0) return;
    const text = run
      .map((entry) => entry.text.trim())
      .filter(Boolean)
      .join('\n\n');
    ends.set(run[run.length - 1].id, text);
    run = [];
  };

  for (const entry of entries) {
    if (entry.kind === 'user') {
      flush();
      continue;
    }
    if (entry.kind === 'agent') run.push(entry);
  }
  // The transcript's trailing turn has no user message after it to close it.
  flush();

  return ends;
}
