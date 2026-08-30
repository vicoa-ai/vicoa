/**
 * Pure grid math for the activity heatmap — kept JSX-free so the
 * week/month/future-cell logic is unit-testable. The component in
 * activity-heatmap.tsx just maps over what this returns.
 */
import { addDays, dayKey } from '@/lib/profile-stats';

export const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

const MONTH_FULL = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Human date for a cell: "July 3" when it's the current year, "July 3, 2025"
 * otherwise (so recent days stay terse and older ones stay unambiguous).
 */
export function formatActivityDate(key: string, currentYear: number): string {
  const [year, month, day] = key.split('-').map(Number);
  const label = `${MONTH_FULL[month - 1]} ${day}`;
  return year === currentYear ? label : `${label}, ${year}`;
}

/** Hover title for a cell: "X messages on July 3" / "No messages on July 3". */
export function activityTooltip(count: number, key: string, currentYear: number): string {
  const date = formatActivityDate(key, currentYear);
  if (count <= 0) return `No messages on ${date}`;
  return `${count} message${count === 1 ? '' : 's'} on ${date}`;
}

export interface DayCell {
  key: string;
  count: number;
  /** 0 (empty) … 4 (most active). */
  level: number;
  /** After `endDate` — rendered hidden so the grid ends at today. */
  isFuture: boolean;
}

export interface HeatmapColumn {
  /** Sunday-anchored week; index 0 is oldest. */
  index: number;
  /** Month abbreviation when this column starts a new month, else null. */
  label: string | null;
  days: DayCell[];
}

/** Map a per-day session count to a 0–4 intensity bucket. */
export function levelForCount(count: number): number {
  if (count <= 0) return 0;
  if (count >= 4) return 4;
  return count; // 1 → 1, 2 → 2, 3 → 3
}

/**
 * Build `weeks` Sunday-anchored columns ending on the week that contains
 * `endDate`. Each column holds 7 day cells (Sunday at row 0). A column is
 * labelled with its month abbreviation when it introduces a new month.
 */
export function buildHeatmapColumns(
  counts: Map<string, number>,
  endDate: Date,
  weeks: number,
): HeatmapColumn[] {
  const endKey = dayKey(endDate);
  // Sunday of the end date's week is the last column; walk back `weeks - 1`.
  const lastSunday = addDays(endDate, -endDate.getDay());
  const firstSunday = addDays(lastSunday, -7 * (weeks - 1));

  const columns: HeatmapColumn[] = [];
  let prevMonth = -1;
  for (let col = 0; col < weeks; col++) {
    const colSunday = addDays(firstSunday, col * 7);
    const days: DayCell[] = [];
    for (let row = 0; row < 7; row++) {
      const day = addDays(colSunday, row);
      const key = dayKey(day);
      const count = counts.get(key) ?? 0;
      days.push({ key, count, level: levelForCount(count), isFuture: key > endKey });
    }
    const month = colSunday.getMonth();
    const label = month !== prevMonth ? MONTH_ABBR[month] : null;
    prevMonth = month;
    columns.push({ index: col, label, days });
  }
  return columns;
}
