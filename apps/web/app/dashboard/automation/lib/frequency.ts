import type {
  AutomationFrequency,
  AutomationResponse,
  AutomationTimeWindow,
  CreateAutomationRequest,
} from '@/lib/backend-api';

/** Floor on "every N minutes" — each fire spawns a full agent session, so we
 *  guard against runaway schedules. Mirrors _MIN_MINUTELY_INTERVAL in the
 *  backend (shared/scheduling/frequency.py). */
export const MIN_MINUTELY_INTERVAL = 5;

// Weekday convention: 0=Sunday … 6=Saturday (matches the backend + JS getDay()).
export const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const DAY_LABELS_FULL = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
];

export type RepeatMode =
  | 'once'
  | 'hourly'
  | 'daily'
  | 'weekdays'
  | 'weekly'
  | 'custom';
export type CustomUnit = 'minutely' | 'hourly' | 'daily' | 'weekly' | 'monthly';

/** A superset draft that holds every mode's fields, so switching Repeat keeps
 *  the user's other entries. Converted to the API's discriminated frequency on
 *  submit. */
export interface ScheduleDraft {
  repeat: RepeatMode;
  runAtLocal: string; // one-time: datetime-local ('yyyy-MM-ddThh:mm', local)
  time: string; // 'HH:MM' (daily/weekdays/weekly + custom daily/weekly/monthly)
  minute: number; // hourly / custom-hourly minute past the hour
  weekdays: number[]; // weekly + custom-weekly (0..6)
  customUnit: CustomUnit;
  interval: number; // custom "every N"
  monthdays: number[]; // custom monthly (1..31)
  // Optional daily time window for sub-daily units (custom minutely/hourly):
  // fire only within [windowStart, windowEnd] local time, realigned to the
  // start each day.
  windowEnabled: boolean;
  windowStart: string; // 'HH:MM'
  windowEnd: string; // 'HH:MM'
  timezone: string; // IANA
}

/** Whether a custom unit is sub-daily (interval-based, window-eligible). */
export function isSubDailyUnit(unit: CustomUnit): boolean {
  return unit === 'minutely' || unit === 'hourly';
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** '14:30' → '2:30 PM' for summaries; inputs stay 24h HH:MM. */
export function formatTime12(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  if (Number.isNaN(h)) return hhmm;
  const period = h < 12 ? 'AM' : 'PM';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${pad2(m || 0)} ${period}`;
}

export function defaultScheduleDraft(): ScheduleDraft {
  return {
    repeat: 'daily',
    runAtLocal: '',
    time: '09:00',
    minute: 0,
    weekdays: [1],
    customUnit: 'daily',
    interval: 1,
    monthdays: [1],
    windowEnabled: false,
    windowStart: '09:00',
    windowEnd: '17:00',
    timezone: browserTimezone(),
  };
}

/** The window slice of a draft, or null when disabled/degenerate (start≥end).
 *  Non-window units never emit one. */
function draftWindow(draft: ScheduleDraft): AutomationTimeWindow | null {
  if (!draft.windowEnabled) return null;
  if (!isWindowValid(draft.windowStart, draft.windowEnd)) return null;
  return { start: draft.windowStart, end: draft.windowEnd };
}

/** 'HH:MM' → minutes since midnight (NaN-safe → -1). */
function hmToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return -1;
  return h * 60 + m;
}

/** A window is usable only when the end is strictly after the start
 *  (overnight spans aren't supported). */
export function isWindowValid(start: string, end: string): boolean {
  const s = hmToMinutes(start);
  const e = hmToMinutes(end);
  return s >= 0 && e >= 0 && e > s;
}

/** Reconstruct the draft's window fields from a stored frequency window. */
function windowToDraft(
  window: AutomationTimeWindow | null | undefined,
): Pick<ScheduleDraft, 'windowEnabled' | 'windowStart' | 'windowEnd'> {
  if (!window) return { windowEnabled: false, windowStart: '09:00', windowEnd: '17:00' };
  return { windowEnabled: true, windowStart: window.start, windowEnd: window.end };
}

/** Reconstruct a draft from a stored automation (best-effort for fields the
 *  chosen mode doesn't carry). */
export function automationToDraft(a: AutomationResponse): ScheduleDraft {
  const base = defaultScheduleDraft();
  base.timezone = a.timezone || base.timezone;

  if (a.schedule_kind === 'once') {
    return {
      ...base,
      repeat: 'once',
      runAtLocal: a.next_run_at ? toLocalInput(new Date(a.next_run_at)) : '',
    };
  }

  const f = a.frequency;
  if (!f) return { ...base, repeat: 'daily' };

  if (f.kind === 'hourly') return { ...base, repeat: 'hourly', minute: f.minute };
  if (f.kind === 'daily') return { ...base, repeat: 'daily', time: f.time };
  if (f.kind === 'weekdays') return { ...base, repeat: 'weekdays', time: f.time };
  if (f.kind === 'weekly') {
    return { ...base, repeat: 'weekly', weekdays: f.weekdays, time: f.time };
  }
  // custom
  if (f.unit === 'minutely') {
    return {
      ...base,
      repeat: 'custom',
      customUnit: 'minutely',
      interval: f.interval,
      ...windowToDraft(f.window),
    };
  }
  if (f.unit === 'hourly') {
    return {
      ...base,
      repeat: 'custom',
      customUnit: 'hourly',
      interval: f.interval,
      minute: f.minute,
      ...windowToDraft(f.window),
    };
  }
  if (f.unit === 'daily') {
    return {
      ...base,
      repeat: 'custom',
      customUnit: 'daily',
      interval: f.interval,
      time: f.time,
    };
  }
  if (f.unit === 'weekly') {
    return {
      ...base,
      repeat: 'custom',
      customUnit: 'weekly',
      interval: f.interval,
      weekdays: f.weekdays,
      time: f.time,
    };
  }
  return {
    ...base,
    repeat: 'custom',
    customUnit: 'monthly',
    interval: f.interval,
    monthdays: f.monthdays,
    time: f.time,
  };
}

/** Build the API's discriminated frequency (recurring only). */
export function draftToFrequency(draft: ScheduleDraft): AutomationFrequency | null {
  switch (draft.repeat) {
    case 'hourly':
      return { kind: 'hourly', minute: draft.minute };
    case 'daily':
      return { kind: 'daily', time: draft.time };
    case 'weekdays':
      return { kind: 'weekdays', time: draft.time };
    case 'weekly':
      return { kind: 'weekly', weekdays: draft.weekdays, time: draft.time };
    case 'custom':
      switch (draft.customUnit) {
        case 'minutely':
          return {
            kind: 'custom',
            unit: 'minutely',
            interval: Math.max(MIN_MINUTELY_INTERVAL, draft.interval),
            window: draftWindow(draft),
          };
        case 'hourly':
          return {
            kind: 'custom',
            unit: 'hourly',
            interval: draft.interval,
            minute: draft.minute,
            window: draftWindow(draft),
          };
        case 'daily':
          return {
            kind: 'custom',
            unit: 'daily',
            interval: draft.interval,
            time: draft.time,
          };
        case 'weekly':
          return {
            kind: 'custom',
            unit: 'weekly',
            interval: draft.interval,
            weekdays: draft.weekdays,
            time: draft.time,
          };
        case 'monthly':
          return {
            kind: 'custom',
            unit: 'monthly',
            interval: draft.interval,
            monthdays: draft.monthdays,
            time: draft.time,
          };
      }
    // eslint-disable-next-line no-fallthrough
    default:
      return null;
  }
}

/** The schedule slice of a create/update request. */
export function draftToScheduleApi(
  draft: ScheduleDraft,
): Pick<
  CreateAutomationRequest,
  'schedule_kind' | 'run_at' | 'frequency' | 'timezone'
> {
  if (draft.repeat === 'once') {
    return {
      schedule_kind: 'once',
      run_at: draft.runAtLocal ? new Date(draft.runAtLocal).toISOString() : null,
      frequency: null,
      timezone: draft.timezone || browserTimezone(),
    };
  }
  return {
    schedule_kind: 'recurring',
    run_at: null,
    frequency: draftToFrequency(draft),
    timezone: draft.timezone || browserTimezone(),
  };
}

export function isDraftComplete(draft: ScheduleDraft): boolean {
  if (draft.repeat === 'once') return !!draft.runAtLocal;
  if (draft.repeat === 'weekly') return draft.weekdays.length > 0;
  if (draft.repeat === 'custom') {
    if (draft.customUnit === 'weekly') return draft.weekdays.length > 0;
    if (draft.customUnit === 'monthly') return draft.monthdays.length > 0;
    // A window is optional, but an enabled one must be a valid span.
    if (
      isSubDailyUnit(draft.customUnit) &&
      draft.windowEnabled &&
      !isWindowValid(draft.windowStart, draft.windowEnd)
    ) {
      return false;
    }
  }
  return true;
}

function joinDays(days: number[]): string {
  return [...days]
    .sort((a, b) => a - b)
    .map((d) => DAY_LABELS[d] ?? d)
    .join(', ');
}

function pluralN(n: number, unit: string): string {
  return n === 1 ? unit : `${n} ${unit}s`;
}

/** Append a " · 9:00 AM–12:00 PM" span to a sub-daily summary when windowed. */
function withWindow(
  base: string,
  window: AutomationTimeWindow | null | undefined,
): string {
  if (!window) return base;
  return `${base} · ${formatTime12(window.start)}–${formatTime12(window.end)}`;
}

export function summarizeFrequency(f: AutomationFrequency): string {
  switch (f.kind) {
    case 'hourly':
      return `Hourly at :${pad2(f.minute)}`;
    case 'daily':
      return `Daily at ${formatTime12(f.time)}`;
    case 'weekdays':
      return `Weekdays at ${formatTime12(f.time)}`;
    case 'weekly':
      return `Weekly on ${joinDays(f.weekdays)} at ${formatTime12(f.time)}`;
    case 'custom':
      switch (f.unit) {
        case 'minutely':
          return withWindow(`Every ${pluralN(f.interval, 'minute')}`, f.window);
        case 'hourly':
          // A window supersedes the ":MM" phase (fires are aligned to the
          // window start), so only show ":MM" for the all-day case.
          if (f.window) {
            const every =
              f.interval === 1 ? 'Hourly' : `Every ${f.interval} hours`;
            return withWindow(every, f.window);
          }
          return f.interval === 1
            ? `Hourly at :${pad2(f.minute)}`
            : `Every ${f.interval} hours at :${pad2(f.minute)}`;
        case 'daily':
          return `Every ${pluralN(f.interval, 'day')} at ${formatTime12(f.time)}`;
        case 'weekly':
          return `Every ${pluralN(f.interval, 'week')} on ${joinDays(f.weekdays)} at ${formatTime12(f.time)}`;
        case 'monthly':
          return `Every ${pluralN(f.interval, 'month')} on day ${[...f.monthdays].sort((a, b) => a - b).join(', ')} at ${formatTime12(f.time)}`;
      }
  }
  return 'Custom';
}

/** One-line summary for the list / header. */
export function summarizeSchedule(a: AutomationResponse): string {
  if (a.schedule_kind === 'once') {
    return a.next_run_at
      ? `Once · ${new Date(a.next_run_at).toLocaleString()}`
      : 'Once';
  }
  return a.frequency ? summarizeFrequency(a.frequency) : 'Recurring';
}
