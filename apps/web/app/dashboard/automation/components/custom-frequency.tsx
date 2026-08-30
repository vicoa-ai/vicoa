'use client';

import { Switch } from '@/components/ui/switch';
import {
  MIN_MINUTELY_INTERVAL,
  isWindowValid,
  type CustomUnit,
  type ScheduleDraft,
} from '../lib/frequency';
import { FieldRow } from './field-row';
import { MonthdayPicker, NumberStepper, ValueDropdown, WeekdayPicker } from './controls';
import { TimeField } from './datetime-fields';

const UNIT_OPTIONS: { id: CustomUnit; label: string }[] = [
  { id: 'minutely', label: 'Minutely' },
  { id: 'hourly', label: 'Hourly' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'monthly', label: 'Monthly' },
];

/**
 * Optional "only during a daily time window" rows for sub-daily units. When on,
 * fires are confined to [From, To] local time and realigned to From each day.
 */
function WindowRows({
  draft,
  patch,
}: {
  draft: ScheduleDraft;
  patch: (p: Partial<ScheduleDraft>) => void;
}) {
  const invalid =
    draft.windowEnabled && !isWindowValid(draft.windowStart, draft.windowEnd);
  return (
    <>
      <FieldRow label="Time window">
        <span className="text-sm text-muted-foreground">
          {draft.windowEnabled ? 'Custom' : 'All day'}
        </span>
        <Switch
          checked={draft.windowEnabled}
          onCheckedChange={(windowEnabled) => patch({ windowEnabled })}
        />
      </FieldRow>

      {draft.windowEnabled && (
        <>
          <FieldRow label="From">
            <TimeField
              value={draft.windowStart}
              onChange={(windowStart) => patch({ windowStart })}
            />
          </FieldRow>
          <FieldRow label="To">
            <TimeField
              value={draft.windowEnd}
              onChange={(windowEnd) => patch({ windowEnd })}
            />
          </FieldRow>
          {invalid && (
            <div className="px-3.5 py-2 text-xs text-destructive">
              The end time must be after the start time.
            </div>
          )}
        </>
      )}
    </>
  );
}

/**
 * The Custom-repeat editor (rows nested inside the Frequency group): pick a unit
 * — Minutely / Hourly / Daily / Weekly / Monthly — then its interval + day/time
 * details. Sub-daily units (minutely/hourly) can additionally be confined to a
 * daily time window. Modeled on ChatGPT's Custom scheduler.
 */
export function CustomFrequency({
  draft,
  patch,
}: {
  draft: ScheduleDraft;
  patch: (p: Partial<ScheduleDraft>) => void;
}) {
  const { customUnit } = draft;

  const setUnit = (unit: CustomUnit) => {
    const next: Partial<ScheduleDraft> = { customUnit: unit };
    // "Every N minutes" carries a floor; bump a stale interval up on switch so
    // the UI never shows a value the backend would silently clamp.
    if (unit === 'minutely' && draft.interval < MIN_MINUTELY_INTERVAL) {
      next.interval = 15;
    }
    patch(next);
  };

  return (
    <>
      <FieldRow label="Repeats">
        <ValueDropdown
          value={customUnit}
          options={UNIT_OPTIONS}
          onChange={setUnit}
          title="Repeats"
        />
      </FieldRow>

      {customUnit === 'minutely' && (
        <>
          <FieldRow label="Every">
            <NumberStepper
              value={draft.interval}
              min={MIN_MINUTELY_INTERVAL}
              max={1439}
              suffix={draft.interval === 1 ? 'minute' : 'minutes'}
              onChange={(interval) => patch({ interval })}
            />
          </FieldRow>
          <WindowRows draft={draft} patch={patch} />
        </>
      )}

      {customUnit === 'hourly' && (
        <>
          <FieldRow label="Every">
            <NumberStepper
              value={draft.interval}
              min={1}
              max={168}
              suffix={draft.interval === 1 ? 'hour' : 'hours'}
              onChange={(interval) => patch({ interval })}
            />
          </FieldRow>
          {/* A window supersedes the ":MM" phase, so only offer it all-day. */}
          {!draft.windowEnabled && (
            <FieldRow label="At minute">
              <NumberStepper
                value={draft.minute}
                min={0}
                max={59}
                onChange={(minute) => patch({ minute })}
              />
            </FieldRow>
          )}
          <WindowRows draft={draft} patch={patch} />
        </>
      )}

      {customUnit === 'daily' && (
        <>
          <FieldRow label="Every">
            <NumberStepper
              value={draft.interval}
              min={1}
              max={365}
              suffix={draft.interval === 1 ? 'day' : 'days'}
              onChange={(interval) => patch({ interval })}
            />
          </FieldRow>
          <FieldRow label="At">
            <TimeField value={draft.time} onChange={(time) => patch({ time })} />
          </FieldRow>
        </>
      )}

      {customUnit === 'weekly' && (
        <>
          <FieldRow label="Every">
            <NumberStepper
              value={draft.interval}
              min={1}
              max={52}
              suffix={draft.interval === 1 ? 'week' : 'weeks'}
              onChange={(interval) => patch({ interval })}
            />
          </FieldRow>
          <FieldRow label="On">
            <WeekdayPicker
              value={draft.weekdays}
              onChange={(weekdays) => patch({ weekdays })}
            />
          </FieldRow>
          <FieldRow label="At">
            <TimeField value={draft.time} onChange={(time) => patch({ time })} />
          </FieldRow>
        </>
      )}

      {customUnit === 'monthly' && (
        <>
          <FieldRow label="Every">
            <NumberStepper
              value={draft.interval}
              min={1}
              max={24}
              suffix={draft.interval === 1 ? 'month' : 'months'}
              onChange={(interval) => patch({ interval })}
            />
          </FieldRow>
          <FieldRow label="On days">
            <MonthdayPicker
              value={draft.monthdays}
              onChange={(monthdays) => patch({ monthdays })}
            />
          </FieldRow>
          <FieldRow label="At">
            <TimeField value={draft.time} onChange={(time) => patch({ time })} />
          </FieldRow>
        </>
      )}
    </>
  );
}
