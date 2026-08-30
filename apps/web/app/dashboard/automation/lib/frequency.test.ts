import { describe, expect, it } from 'vitest';
import type { AutomationResponse } from '@/lib/backend-api';
import {
  MIN_MINUTELY_INTERVAL,
  automationToDraft,
  defaultScheduleDraft,
  draftToFrequency,
  isDraftComplete,
  isWindowValid,
  summarizeFrequency,
  type ScheduleDraft,
} from './frequency';

function customMinutely(over: Partial<ScheduleDraft> = {}): ScheduleDraft {
  return {
    ...defaultScheduleDraft(),
    repeat: 'custom',
    customUnit: 'minutely',
    interval: 15,
    ...over,
  };
}

describe('isWindowValid', () => {
  it('accepts a forward span', () => {
    expect(isWindowValid('09:00', '12:00')).toBe(true);
  });
  it('rejects equal and reversed spans (no overnight)', () => {
    expect(isWindowValid('12:00', '12:00')).toBe(false);
    expect(isWindowValid('12:00', '09:00')).toBe(false);
  });
});

describe('draftToFrequency — minutely', () => {
  it('emits a minutely frequency with no window by default', () => {
    expect(draftToFrequency(customMinutely())).toEqual({
      kind: 'custom',
      unit: 'minutely',
      interval: 15,
      window: null,
    });
  });

  it('floors the interval to the minimum', () => {
    const f = draftToFrequency(customMinutely({ interval: 2 }));
    expect(f).toMatchObject({ interval: MIN_MINUTELY_INTERVAL });
  });

  it('includes an enabled window', () => {
    const f = draftToFrequency(
      customMinutely({ windowEnabled: true, windowStart: '09:00', windowEnd: '12:00' }),
    );
    expect(f).toEqual({
      kind: 'custom',
      unit: 'minutely',
      interval: 15,
      window: { start: '09:00', end: '12:00' },
    });
  });

  it('drops a degenerate window (start ≥ end)', () => {
    const f = draftToFrequency(
      customMinutely({ windowEnabled: true, windowStart: '12:00', windowEnd: '09:00' }),
    );
    expect(f).toMatchObject({ window: null });
  });
});

describe('draftToFrequency — windowed hourly', () => {
  it('carries the window alongside interval/minute', () => {
    const draft: ScheduleDraft = {
      ...defaultScheduleDraft(),
      repeat: 'custom',
      customUnit: 'hourly',
      interval: 2,
      minute: 0,
      windowEnabled: true,
      windowStart: '09:00',
      windowEnd: '17:00',
    };
    expect(draftToFrequency(draft)).toEqual({
      kind: 'custom',
      unit: 'hourly',
      interval: 2,
      minute: 0,
      window: { start: '09:00', end: '17:00' },
    });
  });
});

describe('automationToDraft — round trip', () => {
  function resp(frequency: AutomationResponse['frequency']): AutomationResponse {
    return {
      id: 'a',
      title: 't',
      prompt: 'p',
      machine_id: 'm',
      directory: '/d',
      worktree: null,
      session_config: {},
      schedule_kind: 'recurring',
      frequency,
      timezone: 'UTC',
      next_run_at: null,
      enabled: true,
      last_run_at: null,
      last_run_status: null,
      created_at: '',
      updated_at: '',
    };
  }

  it('reconstructs a windowed minutely automation', () => {
    const draft = automationToDraft(
      resp({
        kind: 'custom',
        unit: 'minutely',
        interval: 30,
        window: { start: '08:00', end: '10:00' },
      }),
    );
    expect(draft).toMatchObject({
      repeat: 'custom',
      customUnit: 'minutely',
      interval: 30,
      windowEnabled: true,
      windowStart: '08:00',
      windowEnd: '10:00',
    });
  });

  it('reconstructs an un-windowed minutely automation', () => {
    const draft = automationToDraft(
      resp({ kind: 'custom', unit: 'minutely', interval: 5 }),
    );
    expect(draft).toMatchObject({
      customUnit: 'minutely',
      interval: 5,
      windowEnabled: false,
    });
  });
});

describe('isDraftComplete — window validation', () => {
  it('blocks an enabled-but-degenerate window', () => {
    expect(
      isDraftComplete(
        customMinutely({ windowEnabled: true, windowStart: '12:00', windowEnd: '09:00' }),
      ),
    ).toBe(false);
  });
  it('allows a valid window', () => {
    expect(
      isDraftComplete(
        customMinutely({ windowEnabled: true, windowStart: '09:00', windowEnd: '12:00' }),
      ),
    ).toBe(true);
  });
});

describe('summarizeFrequency', () => {
  it('summarizes an all-day minutely schedule', () => {
    expect(
      summarizeFrequency({ kind: 'custom', unit: 'minutely', interval: 15 }),
    ).toBe('Every 15 minutes');
  });

  it('summarizes a windowed minutely schedule', () => {
    expect(
      summarizeFrequency({
        kind: 'custom',
        unit: 'minutely',
        interval: 15,
        window: { start: '09:00', end: '12:00' },
      }),
    ).toBe('Every 15 minutes · 9:00 AM–12:00 PM');
  });

  it('drops the ":MM" phase for a windowed hourly schedule', () => {
    expect(
      summarizeFrequency({
        kind: 'custom',
        unit: 'hourly',
        interval: 2,
        minute: 30,
        window: { start: '09:00', end: '17:00' },
      }),
    ).toBe('Every 2 hours · 9:00 AM–5:00 PM');
  });
});
