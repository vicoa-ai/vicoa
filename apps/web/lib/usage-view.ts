import type { SessionUsage, SessionUsageWindow } from '@/lib/backend-api';

/**
 * Pure presentation logic for the chat usage indicator — formatting, color
 * thresholds, and the collapsed/expanded view derivation. Kept out of the
 * component so it's unit-testable in the node vitest environment.
 */

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}m`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export function formatCost(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

const RESET_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Viewer-local clock: "1:40pm" / "11pm" (minutes dropped when on the hour).
function formatClock(d: Date): string {
  const m = d.getMinutes();
  const ampm = d.getHours() < 12 ? 'am' : 'pm';
  const h = d.getHours() % 12 || 12;
  return m === 0 ? `${h}${ampm}` : `${h}:${String(m).padStart(2, '0')}${ampm}`;
}

/**
 * Absolute reset time in the viewer's local zone: "Resets 1:40pm" when it lands
 * today, "Resets Aug 19 at 11pm" later this year, "Resets Aug 19, 2027 at 11pm"
 * across a year boundary, and "Resetting now" once it has elapsed.
 */
export function formatReset(iso: string | null | undefined, now: number = Date.now()): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  if (then.getTime() - now <= 0) return 'Resetting now';

  const nowDate = new Date(now);
  const time = formatClock(then);
  const sameDay =
    then.getFullYear() === nowDate.getFullYear() &&
    then.getMonth() === nowDate.getMonth() &&
    then.getDate() === nowDate.getDate();
  if (sameDay) return `Resets ${time}`;

  const year = then.getFullYear() === nowDate.getFullYear() ? '' : `, ${then.getFullYear()}`;
  return `Resets ${RESET_MONTHS[then.getMonth()]} ${then.getDate()}${year} at ${time}`;
}

export interface UsageView {
  context: NonNullable<SessionUsage['context']> | null;
  /** Context fill 0-100, or null when the max window size is unknown. */
  contextPct: number | null;
  windows: SessionUsageWindow[];
  credits: { unit: string; remaining: number } | null;
  /** Highest used_pct across limit windows, for the collapsed fallback. */
  tightest: number | null;
  hasAnything: boolean;
}

export function deriveUsageView(usage: SessionUsage | null | undefined): UsageView {
  const rawContext = usage?.context ?? null;
  const windows = usage?.limits?.windows ?? [];
  const credits = usage?.limits?.credits ?? null;

  const contextPct =
    rawContext && rawContext.max_tokens && rawContext.max_tokens > 0
      ? Math.min(100, (rawContext.used_tokens / rawContext.max_tokens) * 100)
      : null;

  // A context blob with no usable signal has nothing worth showing: no known
  // window (so no ring/percentage) AND no tokens used yet. The backend keeps
  // `used_tokens: 0` as a real reading, so a brand-new or logged-out session
  // arrives as `{used_tokens: 0, max_tokens: null, cost_usd: 0}` — dropping it
  // here stops the composer from rendering a bare "0" / "Context window 0
  // tokens" chip. A known max (ring) or any tokens used keeps it visible.
  const context = rawContext && (contextPct !== null || rawContext.used_tokens > 0) ? rawContext : null;

  const tightest = windows.reduce<number | null>(
    (max, w) => (max === null || w.used_pct > max ? w.used_pct : max),
    null,
  );

  return {
    context,
    contextPct,
    windows,
    credits,
    tightest,
    hasAnything: context !== null || windows.length > 0 || credits !== null,
  };
}
