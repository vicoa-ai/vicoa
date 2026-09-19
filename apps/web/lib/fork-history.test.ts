import { describe, expect, test, vi } from 'vitest';
import type { AgentInstanceDetail, MessageResponse } from '@/lib/backend-api';
import { MessageStore } from '@/lib/message-store';
import { loadFullHistory } from './fork-history';

function msg(id: string, created_at: string): MessageResponse {
  return { id, content: `content-${id}`, sender_type: 'agent', created_at, requires_user_input: false };
}

function detail(id: string, messages: MessageResponse[]): AgentInstanceDetail {
  return {
    id,
    agent_type_id: 'at-1',
    agent_type_name: 'Claude Code',
    name: null,
    status: 'ACTIVE',
    started_at: '2026-07-10T00:00:00Z',
    ended_at: null,
    git_diff: null,
    messages,
    last_read_message_id: null,
  };
}

/** Row `n` of a synthetic session; ids and timestamps grow together. */
const row = (n: number) => msg(`m${String(n).padStart(5, '0')}`, `2026-07-10T00:00:${String(n).padStart(2, '0')}Z`);

/** A fake backend over `total` rows that answers `limit` rows before a cursor. */
function fakeBackend(total: number) {
  const rows = Array.from({ length: total }, (_, i) => row(i + 1));
  const calls: Array<{ before: string; limit: number }> = [];
  const fetchOlder = vi.fn(async (before: string, limit: number) => {
    calls.push({ before, limit });
    const index = rows.findIndex((r) => r.id === before);
    return rows.slice(Math.max(0, index - limit), index);
  });
  return { rows, calls, fetchOlder };
}

describe('loadFullHistory', () => {
  test('walks every page into the store until hasOlder clears', async () => {
    const backend = fakeBackend(1320);
    const store = new MessageStore();
    // Initial hydrate: the 200 most recent rows, flagged as having older history.
    store.hydrateFromDetail('inst', detail('inst', backend.rows.slice(-200)), { hasOlder: true });
    const prependOlder = vi.spyOn(store, 'prependOlder');

    const { pages } = await loadFullHistory({ instanceId: 'inst', store, fetchOlder: backend.fetchOlder, pageSize: 500 });

    // 1120 older rows → 500, 500, 120.
    expect(pages).toBe(3);
    expect(backend.calls.map((c) => c.limit)).toEqual([500, 500, 500]);
    expect(backend.calls.map((c) => c.before)).toEqual(['m01121', 'm00621', 'm00121']);
    expect(prependOlder).toHaveBeenCalledTimes(3);
    const snapshot = store.getSnapshot('inst');
    expect(snapshot?.hasOlder).toBe(false);
    expect(snapshot?.messages.map((m) => m.id)).toEqual(backend.rows.map((m) => m.id));
  });

  test('an exact multiple of the page size ends on an empty page', async () => {
    const backend = fakeBackend(700);
    const store = new MessageStore();
    store.hydrateFromDetail('inst', detail('inst', backend.rows.slice(-200)), { hasOlder: true });

    const { pages } = await loadFullHistory({ instanceId: 'inst', store, fetchOlder: backend.fetchOlder, pageSize: 500 });

    expect(pages).toBe(2);
    expect(store.getSnapshot('inst')?.hasOlder).toBe(false);
    expect(store.getSnapshot('inst')?.messages).toHaveLength(700);
  });

  test('nothing to do when the store already holds the whole history', async () => {
    const backend = fakeBackend(50);
    const store = new MessageStore();
    store.hydrateFromDetail('inst', detail('inst', backend.rows), { hasOlder: false });

    const { pages } = await loadFullHistory({ instanceId: 'inst', store, fetchOlder: backend.fetchOlder });

    expect(pages).toBe(0);
    expect(backend.fetchOlder).not.toHaveBeenCalled();
  });

  test('a failed page rejects and leaves the store where it was', async () => {
    const backend = fakeBackend(1320);
    const store = new MessageStore();
    store.hydrateFromDetail('inst', detail('inst', backend.rows.slice(-200)), { hasOlder: true });
    let n = 0;
    const flaky = vi.fn(async (before: string, limit: number) => {
      n += 1;
      if (n === 2) throw new Error('network');
      return backend.fetchOlder(before, limit);
    });

    await expect(loadFullHistory({ instanceId: 'inst', store, fetchOlder: flaky, pageSize: 500 })).rejects.toThrow('network');

    const snapshot = store.getSnapshot('inst');
    expect(snapshot?.messages).toHaveLength(700);
    expect(snapshot?.hasOlder).toBe(true);
  });

  test('the page cap stops a runaway walk', async () => {
    const backend = fakeBackend(5000);
    const store = new MessageStore();
    store.hydrateFromDetail('inst', detail('inst', backend.rows.slice(-200)), { hasOlder: true });

    const { pages } = await loadFullHistory({ instanceId: 'inst', store, fetchOlder: backend.fetchOlder, pageSize: 500, maxPages: 2 });

    expect(pages).toBe(2);
    expect(store.getSnapshot('inst')?.messages).toHaveLength(1200);
    expect(store.getSnapshot('inst')?.hasOlder).toBe(true);
  });
});
