/**
 * Pure derivation of profile activity stats from a user's agent sessions.
 * Kept JSX-free and dependency-free so the streak/bucketing logic is
 * unit-testable. Consumed by the desktop settings ProfileSection.
 */

/** The session fields the stats derivation needs (subset of AgentInstanceResponse). */
export interface ProfileSessionLike {
  /** ISO timestamp the session started. */
  started_at: string;
  /** ISO timestamp of the session's latest message (null when none). */
  latest_message_at?: string | null;
  /** Number of messages in the session (AgentInstanceResponse.chat_length). */
  chat_length: number;
}

export interface ProfileStats {
  /** All-time session count (from the paginated `total`, not just what we fetched). */
  sessions: number;
  /** Total messages across the sessions provided. */
  messages: number;
  /** Consecutive active days ending today (or yesterday if today has no session yet). */
  currentStreak: number;
  /** Longest run of consecutive active days over the provided history. */
  longestStreak: number;
  /** Local `YYYY-MM-DD` → number of sessions started that day. */
  dayCounts: Map<string, number>;
}

/** Local calendar-day key, e.g. `2026-07-13`. */
export function dayKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Parse a `YYYY-MM-DD` key back into a local-midnight Date. */
export function dateFromKey(key: string): Date {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/**
 * Add `n` calendar days. Uses the Date(y, m, d+n) constructor rather than
 * millisecond arithmetic so it stays correct across DST transitions (where a
 * "day" is 23 or 25 hours).
 */
export function addDays(date: Date, n: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

/**
 * Current + longest streak of consecutive active days (a day is active when its
 * count is > 0). Current counts back from today, or yesterday if today is idle.
 */
export function computeStreaks(
  dayCounts: Map<string, number>,
  today: Date,
): { currentStreak: number; longestStreak: number } {
  const activeDays = new Set(
    [...dayCounts.entries()].filter(([, count]) => count > 0).map(([key]) => key),
  );
  if (activeDays.size === 0) return { currentStreak: 0, longestStreak: 0 };

  // Longest run: 'YYYY-MM-DD' sorts chronologically, so walk in order and grow
  // the run whenever the previous day + 1 equals the current key.
  const sortedKeys = [...activeDays].sort();
  let longestStreak = 0;
  let run = 0;
  let prevKey: string | null = null;
  for (const key of sortedKeys) {
    if (prevKey !== null && dayKey(addDays(dateFromKey(prevKey), 1)) === key) {
      run += 1;
    } else {
      run = 1;
    }
    if (run > longestStreak) longestStreak = run;
    prevKey = key;
  }

  // Current run: count back from today. If today has no session yet, start from
  // yesterday so an in-progress day doesn't read as a broken streak.
  let currentStreak = 0;
  let cursor = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (!activeDays.has(dayKey(cursor))) cursor = addDays(cursor, -1);
  while (activeDays.has(dayKey(cursor))) {
    currentStreak += 1;
    cursor = addDays(cursor, -1);
  }

  return { currentStreak, longestStreak };
}

/**
 * Derive the four profile tiles + the heatmap day buckets from a user's
 * sessions. `totalSessions` is the caller's session count; `messages` sums
 * `chat_length`; `dayCounts`/streaks treat a day as active when a session
 * started or had its latest message that day (see the loop).
 */
export function computeProfileStats(
  sessions: ProfileSessionLike[],
  totalSessions: number,
  today: Date,
): ProfileStats {
  const dayCounts = new Map<string, number>();
  let messages = 0;
  for (const session of sessions) {
    messages += Math.max(0, session.chat_length ?? 0);
    // A day counts as active if the session started or had its latest message
    // that day. The list payload carries no per-message timestamps, so these
    // two are the closest proxy for "a day with any message" (deduped within a
    // session so a same-day start+message counts once).
    const activeDays = new Set<string>();
    for (const ts of [session.started_at, session.latest_message_at]) {
      if (!ts) continue;
      const d = new Date(ts);
      if (!Number.isNaN(d.getTime())) activeDays.add(dayKey(d));
    }
    for (const key of activeDays) {
      dayCounts.set(key, (dayCounts.get(key) ?? 0) + 1);
    }
  }
  const { currentStreak, longestStreak } = computeStreaks(dayCounts, today);
  return { sessions: totalSessions, messages, currentStreak, longestStreak, dayCounts };
}

/** Compact display for large counts: 1234 → "1.2K", 2_300_000 → "2.3M". */
export function formatCompact(value: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

/** "1 day" / "N days". */
export function formatDays(value: number): string {
  return `${value} ${value === 1 ? 'day' : 'days'}`;
}
