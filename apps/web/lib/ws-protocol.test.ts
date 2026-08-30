import { describe, expect, it } from 'vitest';
import {
  CatchUpBuffer,
  createAppendTracker,
  createMutableTracker,
  latestTimestamp,
  reconnectDelayMs,
} from '@/lib/ws-protocol';

describe('createAppendTracker', () => {
  it('accepts the first row for an id and rejects a later row with the same id', () => {
    const tracker = createAppendTracker();
    expect(tracker.accept({ id: 'm1' })).toBe(true);
    expect(tracker.accept({ id: 'm1' })).toBe(false);
  });
});

describe('createMutableTracker', () => {
  it('accepts the first row for an id', () => {
    const tracker = createMutableTracker();
    expect(tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:00Z' })).toBe(true);
  });

  it('accepts a row whose updated_at is strictly newer than the last seen', () => {
    const tracker = createMutableTracker();
    tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:00Z' });
    expect(tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:01Z' })).toBe(true);
  });

  it('rejects a row whose updated_at equals or precedes the last seen', () => {
    const tracker = createMutableTracker();
    tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:05Z' });
    expect(tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:05Z' })).toBe(false);
    expect(tracker.accept({ id: 'i1', updated_at: '2026-05-21T10:00:01Z' })).toBe(false);
  });
});

describe('CatchUpBuffer', () => {
  it('holds live rows back until the catch-up fetch completes', () => {
    const buffer = new CatchUpBuffer(createAppendTracker());
    buffer.beginCatchUp();
    expect(buffer.bufferLive({ id: 'm2' })).toEqual([]);
  });

  it('on fetch completion delivers fetch rows first, then buffered live rows', () => {
    const buffer = new CatchUpBuffer(createAppendTracker());
    buffer.beginCatchUp();
    buffer.bufferLive({ id: 'm3' });
    expect(buffer.completeFetch([{ id: 'm1' }, { id: 'm2' }])).toEqual([
      { id: 'm1' },
      { id: 'm2' },
      { id: 'm3' },
    ]);
  });

  it('delivers live rows immediately once the fetch has completed', () => {
    const buffer = new CatchUpBuffer(createAppendTracker());
    buffer.beginCatchUp();
    buffer.completeFetch([]);
    expect(buffer.bufferLive({ id: 'm9' })).toEqual([{ id: 'm9' }]);
  });

  it('dedupes a buffered live row already present in the fetch rows', () => {
    const buffer = new CatchUpBuffer(createAppendTracker());
    buffer.beginCatchUp();
    buffer.bufferLive({ id: 'm1' });
    expect(buffer.completeFetch([{ id: 'm1' }])).toEqual([{ id: 'm1' }]);
  });

  it('keeps tracker seen-state across catch-up cycles so a reconnect re-fetch does not re-deliver', () => {
    const buffer = new CatchUpBuffer(createAppendTracker());
    buffer.beginCatchUp();
    buffer.completeFetch([{ id: 'm1' }]);
    // Reconnect: a new catch-up cycle re-fetches the safety-window overlap.
    buffer.beginCatchUp();
    expect(buffer.completeFetch([{ id: 'm1' }, { id: 'm2' }])).toEqual([{ id: 'm2' }]);
  });
});

describe('reconnectDelayMs', () => {
  it('jitters from the first attempt — attempt 0 can be below the base delay', () => {
    const samples = Array.from({ length: 200 }, () => reconnectDelayMs(0, 1000, 30000));
    expect(Math.min(...samples)).toBeLessThan(1000);
    expect(samples.every((d) => d >= 0 && d <= 1000)).toBe(true);
  });

  it('grows the jitter window exponentially but clamps it to the cap', () => {
    expect(reconnectDelayMs(2, 1000, 30000)).toBeLessThanOrEqual(4000);
    const capped = Array.from({ length: 100 }, () => reconnectDelayMs(20, 1000, 30000));
    expect(capped.every((d) => d >= 0 && d <= 30000)).toBe(true);
  });
});

describe('latestTimestamp', () => {
  it('returns the maximum value of the field across the rows', () => {
    const rows = [
      { id: 'a', created_at: '2026-05-21T10:00:00Z' },
      { id: 'b', created_at: '2026-05-21T10:00:09Z' },
      { id: 'c', created_at: '2026-05-21T10:00:04Z' },
    ];
    expect(latestTimestamp(null, rows, 'created_at')).toBe('2026-05-21T10:00:09Z');
  });

  it('never regresses below the current watermark', () => {
    const rows = [{ id: 'a', created_at: '2026-05-21T09:00:00Z' }];
    expect(latestTimestamp('2026-05-21T10:00:00Z', rows, 'created_at')).toBe(
      '2026-05-21T10:00:00Z',
    );
  });

  it('returns the current watermark unchanged for an empty row set', () => {
    expect(latestTimestamp('2026-05-21T10:00:00Z', [], 'created_at')).toBe(
      '2026-05-21T10:00:00Z',
    );
    expect(latestTimestamp(null, [], 'created_at')).toBeNull();
  });
});
