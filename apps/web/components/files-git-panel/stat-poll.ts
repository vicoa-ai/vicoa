/**
 * Pacing for the editor's `stat-file` freshness poll.
 *
 * The poll runs on a fixed tick while a tab is open, but it only makes sense
 * when the daemon can answer. When the machine is offline the relay waits out
 * its 3s no-handler grace and fails every call — one WARNING per tab per tick
 * in the server log, for nothing. So a transport-level failure pauses the
 * poll for a growing window (5s → 60s) and any success resets it; per-file
 * errors (deleted, permission) don't pause anything, the next tick retries.
 */

/** Wire codes that mean "the daemon is unreachable" — the relay found no
 * handler / lost it mid-call, the request timed out, or our own socket is
 * down. Anything else came *from* the daemon and is about the file. */
const UNREACHABLE_CODES: ReadonlySet<string> = new Set([
  'no_handler',
  'target_disconnected',
  'timeout',
  'not_connected',
]);

export function isDaemonUnreachable(code: string): boolean {
  return UNREACHABLE_CODES.has(code);
}

export const POLL_BACKOFF_MIN_MS = 5_000;
export const POLL_BACKOFF_MAX_MS = 60_000;

export class PollBackoff {
  private delayMs = 0;
  private resumeAt = 0;

  constructor(
    private readonly minMs = POLL_BACKOFF_MIN_MS,
    private readonly maxMs = POLL_BACKOFF_MAX_MS,
  ) {}

  /** True while a previous failure is still holding the poll off. */
  paused(now = Date.now()): boolean {
    return now < this.resumeAt;
  }

  /** Record an unreachable-daemon failure: double the hold (from `minMs`, capped at `maxMs`). */
  fail(now = Date.now()): void {
    this.delayMs = this.delayMs === 0 ? this.minMs : Math.min(this.delayMs * 2, this.maxMs);
    this.resumeAt = now + this.delayMs;
  }

  /** The daemon answered (or the user came back to the page): poll freely again. */
  reset(): void {
    this.delayMs = 0;
    this.resumeAt = 0;
  }
}
