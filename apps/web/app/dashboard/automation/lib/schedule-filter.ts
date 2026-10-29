import type { AutomationResponse } from '@/lib/backend-api';

/** How often a recurring automation fires, whichever Repeat mode set it up:
 *  "Daily" and "Custom → every 3 days" are both daily. */
export type ScheduleCadence = 'minutely' | 'hourly' | 'daily' | 'weekly' | 'monthly';

/** What the list can narrow recurring automations to: one cadence, or every
 *  one set up with the Custom Repeat mode (whatever its cadence, so a custom
 *  row matches its cadence too). */
export type RecurringOption = ScheduleCadence | 'custom';

/** The list's schedule filter: one-time or recurring, or one option of
 *  recurring. */
export type ScheduleFilter = 'all' | 'once' | 'recurring' | RecurringOption;

/** Recurring's options in menu order: cadences shortest first, then Custom. */
export const RECURRING_OPTIONS: RecurringOption[] = [
  'minutely',
  'hourly',
  'daily',
  'weekly',
  'monthly',
  'custom',
];

export const SCHEDULE_FILTER_LABELS: Record<ScheduleFilter, string> = {
  all: 'All',
  once: 'Once',
  recurring: 'Recurring',
  // Same words as the Repeat / Repeats pickers in the form.
  minutely: 'Minutely',
  hourly: 'Hourly',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  custom: 'Custom',
};

/** The cadence a recurring automation fires at; null for a one-time one (or a
 *  recurring row with no frequency, which the backend never stores). */
export function scheduleCadence(a: AutomationResponse): ScheduleCadence | null {
  if (a.schedule_kind !== 'recurring' || !a.frequency) return null;
  const f = a.frequency;
  switch (f.kind) {
    case 'hourly':
      return 'hourly';
    // Weekdays fires every day, Monday to Friday.
    case 'daily':
    case 'weekdays':
      return 'daily';
    case 'weekly':
      return 'weekly';
    case 'custom':
      return f.unit;
  }
}

function isCustom(a: AutomationResponse): boolean {
  return a.schedule_kind === 'recurring' && a.frequency?.kind === 'custom';
}

export function matchesScheduleFilter(a: AutomationResponse, filter: ScheduleFilter): boolean {
  switch (filter) {
    case 'all':
      return true;
    case 'once':
      return a.schedule_kind === 'once';
    case 'recurring':
      return a.schedule_kind === 'recurring';
    case 'custom':
      return isCustom(a);
    default:
      return scheduleCadence(a) === filter;
  }
}

/** Recurring's options worth offering: those some row matches, plus the picked
 *  one so the check mark stays visible after its last row goes. */
export function recurringOptions(
  rows: AutomationResponse[],
  picked: ScheduleFilter,
): RecurringOption[] {
  const present = new Set<RecurringOption | null>(rows.map(scheduleCadence));
  if (rows.some(isCustom)) present.add('custom');
  return RECURRING_OPTIONS.filter((o) => present.has(o) || o === picked);
}
