'use client';

import type { RepeatMode, ScheduleDraft } from '../lib/frequency';
import { FieldGroup, FieldRow } from './field-row';
import { CustomFrequency } from './custom-frequency';
import { NumberStepper, ValueDropdown, WeekdayPicker } from './controls';
import { DateField, TimeField } from './datetime-fields';

const REPEAT_OPTIONS: { id: RepeatMode; label: string }[] = [
  { id: 'once', label: 'Once' },
  { id: 'hourly', label: 'Hourly' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekdays', label: 'Weekdays' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'custom', label: 'Custom' },
];

function splitLocal(runAtLocal: string): { date: string; time: string } {
  const [date = '', time = ''] = runAtLocal.split('T');
  return { date, time };
}

function todayLocalDate(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function FrequencySection({
  draft,
  patch,
}: {
  draft: ScheduleDraft;
  patch: (p: Partial<ScheduleDraft>) => void;
}) {
  const once = splitLocal(draft.runAtLocal);

  const setOnceDate = (date: string) =>
    patch({ runAtLocal: date ? `${date}T${once.time || '09:00'}` : '' });
  const setOnceTime = (time: string) =>
    patch({ runAtLocal: `${once.date || todayLocalDate()}T${time}` });

  return (
    <FieldGroup title="Frequency">
      <FieldRow label="Repeat">
        <ValueDropdown
          value={draft.repeat}
          options={REPEAT_OPTIONS}
          onChange={(repeat) => patch({ repeat })}
          title="Repeat"
        />
      </FieldRow>

      {draft.repeat === 'once' && (
        <>
          <FieldRow label="Date">
            <DateField value={once.date} onChange={setOnceDate} />
          </FieldRow>
          <FieldRow label="Time">
            <TimeField value={once.time || '09:00'} onChange={setOnceTime} />
          </FieldRow>
        </>
      )}

      {draft.repeat === 'hourly' && (
        <FieldRow label="At minute">
          <NumberStepper
            value={draft.minute}
            min={0}
            max={59}
            onChange={(minute) => patch({ minute })}
          />
        </FieldRow>
      )}

      {(draft.repeat === 'daily' || draft.repeat === 'weekdays') && (
        <FieldRow label="At">
          <TimeField value={draft.time} onChange={(time) => patch({ time })} />
        </FieldRow>
      )}

      {draft.repeat === 'weekly' && (
        <>
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

      {draft.repeat === 'custom' && <CustomFrequency draft={draft} patch={patch} />}
    </FieldGroup>
  );
}
