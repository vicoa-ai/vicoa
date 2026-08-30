import { describe, expect, it } from 'vitest';
import {
  addDays,
  computeProfileStats,
  dateFromKey,
  dayKey,
  formatCompact,
  formatDays,
  type ProfileSessionLike,
} from './profile-stats';

// Build a session started at local midnight on the given key (+ optional messages).
function session(key: string, chatLength = 0): ProfileSessionLike {
  return { started_at: dateFromKey(key).toISOString(), chat_length: chatLength };
}

describe('dayKey / dateFromKey / addDays', () => {
  it('round-trips a local calendar day', () => {
    const d = new Date(2026, 6, 13); // 2026-07-13 local
    expect(dayKey(d)).toBe('2026-07-13');
    expect(dayKey(dateFromKey('2026-07-13'))).toBe('2026-07-13');
  });

  it('steps calendar days across a month boundary', () => {
    expect(dayKey(addDays(dateFromKey('2026-01-31'), 1))).toBe('2026-02-01');
    expect(dayKey(addDays(dateFromKey('2026-03-01'), -1))).toBe('2026-02-28');
  });
});

describe('computeProfileStats', () => {
  const today = new Date(2026, 6, 13); // 2026-07-13

  it('uses the passed-in total for sessions and sums chat_length for messages', () => {
    const stats = computeProfileStats(
      [session('2026-07-13', 5), session('2026-07-12', 3)],
      42, // all-time total from the paginated API
      today,
    );
    expect(stats.sessions).toBe(42);
    expect(stats.messages).toBe(8);
  });

  it('buckets multiple sessions on the same day', () => {
    const stats = computeProfileStats(
      [session('2026-07-13'), session('2026-07-13'), session('2026-07-10')],
      3,
      today,
    );
    expect(stats.dayCounts.get('2026-07-13')).toBe(2);
    expect(stats.dayCounts.get('2026-07-10')).toBe(1);
  });

  it('counts the current streak of consecutive days ending today', () => {
    const stats = computeProfileStats(
      [session('2026-07-13'), session('2026-07-12'), session('2026-07-11')],
      3,
      today,
    );
    expect(stats.currentStreak).toBe(3);
  });

  it('keeps the current streak alive when today has no session yet (counts through yesterday)', () => {
    const stats = computeProfileStats(
      [session('2026-07-12'), session('2026-07-11')],
      2,
      today,
    );
    expect(stats.currentStreak).toBe(2);
  });

  it('breaks the current streak when neither today nor yesterday is active', () => {
    const stats = computeProfileStats(
      [session('2026-07-10'), session('2026-07-09')],
      2,
      today,
    );
    expect(stats.currentStreak).toBe(0);
  });

  it('finds the longest run even when it is in the past', () => {
    const stats = computeProfileStats(
      [
        // A 4-day run in June, then an isolated recent day.
        session('2026-06-01'),
        session('2026-06-02'),
        session('2026-06-03'),
        session('2026-06-04'),
        session('2026-07-13'),
      ],
      5,
      today,
    );
    expect(stats.longestStreak).toBe(4);
    expect(stats.currentStreak).toBe(1);
  });

  it('counts both the start day and the latest-message day as active', () => {
    const stats = computeProfileStats(
      [
        {
          started_at: dateFromKey('2026-07-11').toISOString(),
          latest_message_at: dateFromKey('2026-07-12').toISOString(),
          chat_length: 3,
        },
      ],
      1,
      today,
    );
    expect(stats.dayCounts.get('2026-07-11')).toBe(1);
    expect(stats.dayCounts.get('2026-07-12')).toBe(1);
    // Active days 11 & 12; today (13) has nothing, so the streak counts through
    // yesterday (12) → 2 days.
    expect(stats.currentStreak).toBe(2);
    expect(stats.longestStreak).toBe(2);
  });

  it('does not double-count when start and latest message land on the same day', () => {
    const stats = computeProfileStats(
      [
        {
          started_at: dateFromKey('2026-07-13').toISOString(),
          latest_message_at: dateFromKey('2026-07-13').toISOString(),
          chat_length: 2,
        },
      ],
      1,
      today,
    );
    expect(stats.dayCounts.get('2026-07-13')).toBe(1);
  });

  it('returns zeroed streaks for an empty history', () => {
    const stats = computeProfileStats([], 0, today);
    expect(stats.currentStreak).toBe(0);
    expect(stats.longestStreak).toBe(0);
    expect(stats.dayCounts.size).toBe(0);
    expect(stats.messages).toBe(0);
  });

  it('ignores sessions with an unparseable started_at for bucketing', () => {
    const stats = computeProfileStats(
      [{ started_at: 'not-a-date', chat_length: 4 }, session('2026-07-13', 1)],
      2,
      today,
    );
    // Message count still includes the bad row; day buckets skip it.
    expect(stats.messages).toBe(5);
    expect(stats.dayCounts.size).toBe(1);
  });
});

describe('formatting helpers', () => {
  it('formats compact counts', () => {
    expect(formatCompact(42)).toBe('42');
    expect(formatCompact(1234)).toBe('1.2K');
    expect(formatCompact(2_300_000)).toBe('2.3M');
  });

  it('pluralizes day labels', () => {
    expect(formatDays(1)).toBe('1 day');
    expect(formatDays(0)).toBe('0 days');
    expect(formatDays(12)).toBe('12 days');
  });
});
