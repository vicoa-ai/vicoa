import { describe, test, expect } from 'vitest';
import { PollBackoff, isDaemonUnreachable } from './stat-poll';

describe('isDaemonUnreachable', () => {
  test('relay / transport failures pause the poll', () => {
    for (const code of ['no_handler', 'target_disconnected', 'timeout', 'not_connected']) {
      expect(isDaemonUnreachable(code)).toBe(true);
    }
  });

  test('errors the daemon itself returned are about the file, not the link', () => {
    for (const code of ['path_not_found', 'permission_denied', 'outside_project', 'not_a_file']) {
      expect(isDaemonUnreachable(code)).toBe(false);
    }
  });
});

describe('PollBackoff', () => {
  test('starts unpaused', () => {
    const b = new PollBackoff(5_000, 60_000);
    expect(b.paused(0)).toBe(false);
  });

  test('a failure holds the poll for the minimum, then doubles up to the cap', () => {
    const b = new PollBackoff(5_000, 60_000);
    b.fail(0);
    expect(b.paused(4_999)).toBe(true);
    expect(b.paused(5_000)).toBe(false);

    b.fail(5_000); // 10s
    expect(b.paused(14_999)).toBe(true);
    expect(b.paused(15_000)).toBe(false);

    b.fail(15_000); // 20s
    b.fail(35_000); // 40s
    b.fail(75_000); // 80s → capped at 60s
    expect(b.paused(134_999)).toBe(true);
    expect(b.paused(135_000)).toBe(false);

    b.fail(135_000); // stays at the cap
    expect(b.paused(194_999)).toBe(true);
    expect(b.paused(195_000)).toBe(false);
  });

  test('reset clears the hold and the escalation', () => {
    const b = new PollBackoff(5_000, 60_000);
    b.fail(0);
    b.fail(5_000);
    b.fail(15_000);
    b.reset();
    expect(b.paused(15_001)).toBe(false);
    b.fail(20_000); // back to the minimum, not the escalated 40s
    expect(b.paused(24_999)).toBe(true);
    expect(b.paused(25_000)).toBe(false);
  });
});
