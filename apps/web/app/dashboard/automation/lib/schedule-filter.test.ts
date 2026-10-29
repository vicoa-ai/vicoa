import { describe, expect, it } from 'vitest';
import type { AutomationFrequency, AutomationResponse } from '@/lib/backend-api';
import { matchesScheduleFilter, recurringOptions, scheduleCadence } from './schedule-filter';

const once = (id = 'once') =>
  ({ id, schedule_kind: 'once', frequency: null }) as AutomationResponse;
const recurring = (frequency: AutomationFrequency, id = 'rec') =>
  ({ id, schedule_kind: 'recurring', frequency }) as AutomationResponse;

describe('scheduleCadence', () => {
  it('buckets every Repeat mode by how often it fires', () => {
    expect(scheduleCadence(recurring({ kind: 'hourly', minute: 0 }))).toBe('hourly');
    expect(scheduleCadence(recurring({ kind: 'daily', time: '09:00' }))).toBe('daily');
    expect(scheduleCadence(recurring({ kind: 'weekdays', time: '09:00' }))).toBe('daily');
    expect(
      scheduleCadence(recurring({ kind: 'weekly', weekdays: [1], time: '09:00' })),
    ).toBe('weekly');
    expect(
      scheduleCadence(recurring({ kind: 'custom', unit: 'minutely', interval: 15 })),
    ).toBe('minutely');
    expect(
      scheduleCadence(recurring({ kind: 'custom', unit: 'hourly', interval: 2, minute: 0 })),
    ).toBe('hourly');
    expect(
      scheduleCadence(recurring({ kind: 'custom', unit: 'daily', interval: 3, time: '09:00' })),
    ).toBe('daily');
    expect(
      scheduleCadence(
        recurring({ kind: 'custom', unit: 'monthly', interval: 1, monthdays: [1], time: '09:00' }),
      ),
    ).toBe('monthly');
  });

  it('has no cadence for a one-time automation', () => {
    expect(scheduleCadence(once())).toBeNull();
  });
});

describe('matchesScheduleFilter', () => {
  const daily = recurring({ kind: 'daily', time: '09:00' });

  it('splits one-time from recurring', () => {
    expect(matchesScheduleFilter(once(), 'once')).toBe(true);
    expect(matchesScheduleFilter(once(), 'recurring')).toBe(false);
    expect(matchesScheduleFilter(daily, 'recurring')).toBe(true);
    expect(matchesScheduleFilter(daily, 'once')).toBe(false);
  });

  it('narrows recurring to one cadence', () => {
    expect(matchesScheduleFilter(daily, 'daily')).toBe(true);
    expect(matchesScheduleFilter(daily, 'weekly')).toBe(false);
    expect(matchesScheduleFilter(once(), 'daily')).toBe(false);
  });

  it('takes every Custom row under Custom, which still counts by its cadence', () => {
    const everyThreeDays = recurring({ kind: 'custom', unit: 'daily', interval: 3, time: '09:00' });
    expect(matchesScheduleFilter(everyThreeDays, 'custom')).toBe(true);
    expect(matchesScheduleFilter(everyThreeDays, 'daily')).toBe(true);
    expect(matchesScheduleFilter(daily, 'custom')).toBe(false);
    expect(matchesScheduleFilter(once(), 'custom')).toBe(false);
  });

  it('lets everything through on "all"', () => {
    expect(matchesScheduleFilter(once(), 'all')).toBe(true);
    expect(matchesScheduleFilter(daily, 'all')).toBe(true);
  });
});

describe('recurringOptions', () => {
  const rows = [
    once(),
    recurring({ kind: 'weekly', weekdays: [1], time: '09:00' }, 'w'),
    recurring({ kind: 'hourly', minute: 0 }, 'h'),
  ];

  it('offers only the cadences the rows have, shortest first', () => {
    expect(recurringOptions(rows, 'all')).toEqual(['hourly', 'weekly']);
  });

  it('offers Custom last, once a row is set up with it', () => {
    const withCustom = [
      ...rows,
      recurring({ kind: 'custom', unit: 'minutely', interval: 30 }, 'm'),
    ];
    expect(recurringOptions(withCustom, 'all')).toEqual(['minutely', 'hourly', 'weekly', 'custom']);
  });

  it('keeps the picked option even when no row has it', () => {
    expect(recurringOptions(rows, 'monthly')).toEqual(['hourly', 'weekly', 'monthly']);
    expect(recurringOptions(rows, 'custom')).toEqual(['hourly', 'weekly', 'custom']);
  });
});
