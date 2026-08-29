import { describe, test, expect } from 'vitest';
import { ConcurrencyQueue, diffKey } from './concurrency';

describe('diffKey', () => {
  test('keys disambiguate staged vs unstaged for the same path', () => {
    expect(diffKey('src/x.ts', false)).not.toBe(diffKey('src/x.ts', true));
  });

  test('deterministic round-trip', () => {
    expect(diffKey('a/b.ts', true)).toBe(diffKey('a/b.ts', true));
  });
});

describe('ConcurrencyQueue', () => {
  test('runs up to the configured number of tasks concurrently', async () => {
    const queue = new ConcurrencyQueue(3);
    let active = 0;
    let peak = 0;

    const blockers: Array<() => void> = [];
    const promises: Promise<number>[] = [];
    for (let i = 0; i < 8; i++) {
      promises.push(
        queue.run(async () => {
          active++;
          peak = Math.max(peak, active);
          await new Promise<void>((resolve) => blockers.push(resolve));
          active--;
          return i;
        }),
      );
    }

    // Let three tasks reach the `active++` line.
    await new Promise((r) => setTimeout(r, 0));
    expect(peak).toBe(3);

    // Release everything and drain.
    while (blockers.length > 0) {
      const next = blockers.shift()!;
      next();
      await new Promise((r) => setTimeout(r, 0));
    }
    const results = await Promise.all(promises);
    expect(results.sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(peak).toBe(3);
  });

  test('a thrown task does not block the queue', async () => {
    const queue = new ConcurrencyQueue(1);
    await expect(queue.run(async () => { throw new Error('boom'); })).rejects.toThrow('boom');
    await expect(queue.run(async () => 'ok')).resolves.toBe('ok');
  });
});
