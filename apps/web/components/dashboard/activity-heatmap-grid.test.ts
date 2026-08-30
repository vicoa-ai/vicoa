import { describe, expect, it } from 'vitest';
import {
  activityTooltip,
  buildHeatmapColumns,
  formatActivityDate,
  levelForCount,
} from './activity-heatmap-grid';

describe('levelForCount', () => {
  it('buckets counts into 0–4', () => {
    expect(levelForCount(0)).toBe(0);
    expect(levelForCount(1)).toBe(1);
    expect(levelForCount(2)).toBe(2);
    expect(levelForCount(3)).toBe(3);
    expect(levelForCount(4)).toBe(4);
    expect(levelForCount(99)).toBe(4);
  });
});

describe('formatActivityDate', () => {
  it('omits the year for the current year, includes it otherwise', () => {
    expect(formatActivityDate('2026-07-03', 2026)).toBe('July 3');
    expect(formatActivityDate('2025-07-03', 2026)).toBe('July 3, 2025');
    expect(formatActivityDate('2026-12-25', 2026)).toBe('December 25');
  });
});

describe('activityTooltip', () => {
  it('pluralizes messages and reads "No messages" for empty days', () => {
    expect(activityTooltip(5, '2026-07-03', 2026)).toBe('5 messages on July 3');
    expect(activityTooltip(1, '2026-07-03', 2026)).toBe('1 message on July 3');
    expect(activityTooltip(0, '2025-07-03', 2026)).toBe('No messages on July 3, 2025');
  });
});

describe('buildHeatmapColumns', () => {
  // Monday 2026-07-13; its week's Sunday is 2026-07-12.
  const endDate = new Date(2026, 6, 13);

  it('produces `weeks` columns of 7 days each', () => {
    const cols = buildHeatmapColumns(new Map(), endDate, 53);
    expect(cols).toHaveLength(53);
    expect(cols.every((c) => c.days.length === 7)).toBe(true);
  });

  it('anchors the last column on the end date and hides future days', () => {
    const cols = buildHeatmapColumns(new Map(), endDate, 53);
    const last = cols[cols.length - 1];
    // Row 0 is the Sunday of the end date's week.
    expect(last.days[0].key).toBe('2026-07-12');
    // Monday (today) is visible; Tue–Sat are in the future and hidden.
    expect(last.days[1].key).toBe('2026-07-13');
    expect(last.days[1].isFuture).toBe(false);
    expect(last.days[2].isFuture).toBe(true); // 2026-07-14
    expect(last.days[6].isFuture).toBe(true); // 2026-07-18
  });

  it('maps counts onto the right day cells with intensity levels', () => {
    const counts = new Map<string, number>([
      ['2026-07-13', 5], // today → level 4
      ['2026-07-12', 1], // Sunday → level 1
    ]);
    const last = buildHeatmapColumns(counts, endDate, 53)[52];
    expect(last.days[0]).toMatchObject({ key: '2026-07-12', count: 1, level: 1 });
    expect(last.days[1]).toMatchObject({ key: '2026-07-13', count: 5, level: 4 });
  });

  it('labels a column only when it introduces a new month', () => {
    const cols = buildHeatmapColumns(new Map(), endDate, 53);
    const labelled = cols.filter((c) => c.label !== null);
    // ~12–13 month boundaries across a year; first column always labelled.
    expect(cols[0].label).not.toBeNull();
    expect(labelled.length).toBeGreaterThanOrEqual(12);
    expect(labelled.length).toBeLessThanOrEqual(13);
    // No two adjacent columns share a label (labels mark boundaries).
    for (let i = 1; i < cols.length; i++) {
      if (cols[i].label !== null) {
        expect(cols[i].label).not.toBe(cols[i - 1].label);
      }
    }
  });
});
