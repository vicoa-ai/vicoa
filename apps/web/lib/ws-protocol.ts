/**
 * Pure-function WebSocket protocol helpers for vicoa-web (websocket-migration
 * plan §2.6, §2.10). Merge/dedupe semantics and reconnect timing live here,
 * separated from socket I/O (`ws-client.ts`) and React (`use-ws-stream.ts`) so
 * they are unit-testable without mocking WebSocket or the UI framework.
 */

/** A canonical entity row carried in an `update` body or `fetch_*` response. */
export interface EntityRow {
  id: string;
  [key: string]: unknown;
}

/**
 * Decides whether an incoming row is fresh and should be applied. The §2.6
 * merge model has two rules — append-only (messages) and mutable-by-updated_at
 * (instances, machines) — each expressed as a tracker.
 */
export interface RowTracker {
  /** True if the row is new/applicable; updates internal seen-state when so. */
  accept(row: EntityRow): boolean;
}

/**
 * Append-only dedupe (§2.6): first write wins. A second row with an id already
 * seen is a duplicate (e.g. the reconnect safety-window overlap) and dropped.
 */
export function createAppendTracker(): RowTracker {
  const seen = new Set<string>();
  return {
    accept(row: EntityRow): boolean {
      if (seen.has(row.id)) return false;
      seen.add(row.id);
      return true;
    },
  };
}

/**
 * Buffers live `update` rows that arrive while a catch-up `fetch_*` is still in
 * flight (§2.6), so history renders in order. Live rows are held back until the
 * fetch response lands, then fetch rows are delivered first, followed by the
 * buffered live rows — all filtered through the entity's `RowTracker` so a row
 * delivered by both paths is emitted once. The tracker's seen-state outlives a
 * `beginCatchUp()`, so the reconnect safety-window overlap is not re-delivered.
 */
export class CatchUpBuffer<T extends EntityRow = EntityRow> {
  private readonly tracker: RowTracker;
  private buffered: T[] = [];
  private fetchComplete = false;

  constructor(tracker: RowTracker) {
    this.tracker = tracker;
  }

  /** Start a fresh catch-up cycle (called on every (re)connect). */
  beginCatchUp(): void {
    this.buffered = [];
    this.fetchComplete = false;
  }

  /** Take a live row; return rows ready to deliver (empty while catching up). */
  bufferLive(row: T): T[] {
    if (this.fetchComplete) {
      return this.tracker.accept(row) ? [row] : [];
    }
    this.buffered.push(row);
    return [];
  }

  /** Catch-up response arrived: deliver its rows, then the buffered live rows. */
  completeFetch(rows: T[]): T[] {
    const delivered = [...rows, ...this.buffered].filter((row) =>
      this.tracker.accept(row),
    );
    this.buffered = [];
    this.fetchComplete = true;
    return delivered;
  }
}

/**
 * Mutable-entity merge (§2.6): an incoming row replaces local state only when
 * its `updated_at` is strictly later than the last seen value for that id.
 * Equal or earlier `updated_at` is a stale/out-of-order frame and dropped — the
 * canonical-row bodies (§2.4) make replacing whole local state safe.
 */
export function createMutableTracker(): RowTracker {
  const lastUpdatedAt = new Map<string, string>();
  return {
    accept(row: EntityRow): boolean {
      const incoming = String(row.updated_at ?? '');
      const seen = lastUpdatedAt.get(row.id);
      if (seen !== undefined && incoming <= seen) return false;
      lastUpdatedAt.set(row.id, incoming);
      return true;
    },
  };
}

/**
 * Full-jitter reconnect backoff (§2.10): `random(0, min(cap, base * 2^attempt))`,
 * applied from attempt 0 so even the first reconnect is jittered and a mass
 * disconnect herd spreads over the window instead of retrying in lockstep.
 */
export function reconnectDelayMs(
  attempt: number,
  base = 1000,
  cap = 30000,
): number {
  const ceiling = Math.min(cap, base * 2 ** attempt);
  return Math.random() * ceiling;
}

/**
 * Advances a reconnect watermark: the maximum of the current watermark and the
 * given field across `rows`. ISO 8601 timestamps compare correctly as strings.
 * Used for the `messages` `created_at` cursor and the instance/machine
 * `updated_at` cursor (§2.6).
 */
export function latestTimestamp(
  current: string | null,
  rows: EntityRow[],
  field: string,
): string | null {
  let max = current;
  for (const row of rows) {
    const value = row[field];
    if (typeof value === 'string' && (max === null || value > max)) {
      max = value;
    }
  }
  return max;
}
