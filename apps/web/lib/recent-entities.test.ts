import { describe, expect, test } from 'vitest';

import { RecentEntities } from '@/lib/recent-entities';

describe('RecentEntities', () => {
  test('remembers a pair it has seen, and only that pair', () => {
    const seen = new RecentEntities();
    seen.note('agent_instances', 'a');
    expect(seen.has('agent_instances', 'a')).toBe(true);
    expect(seen.has('agent_instances', 'b')).toBe(false);
    expect(seen.has('messages', 'a')).toBe(false);
  });

  test('forgets the oldest pair past its capacity', () => {
    const seen = new RecentEntities(2);
    seen.note('agent_instances', 'a');
    seen.note('agent_instances', 'b');
    seen.note('agent_instances', 'c');
    expect(seen.has('agent_instances', 'a')).toBe(false);
    expect(seen.has('agent_instances', 'b')).toBe(true);
    expect(seen.has('agent_instances', 'c')).toBe(true);
  });

  test('a pair seen again counts as recent', () => {
    const seen = new RecentEntities(2);
    seen.note('agent_instances', 'a');
    seen.note('agent_instances', 'b');
    seen.note('agent_instances', 'a');
    seen.note('agent_instances', 'c');
    expect(seen.has('agent_instances', 'a')).toBe(true);
    expect(seen.has('agent_instances', 'b')).toBe(false);
  });
});
