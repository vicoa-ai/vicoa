import { describe, expect, it, vi } from 'vitest';
import type { AgentInstanceDetail, MessageResponse } from '@/lib/backend-api';
import { MessageStore } from '@/lib/message-store';

function msg(
  id: string,
  created_at: string,
  over: Partial<MessageResponse> = {},
): MessageResponse {
  return {
    id,
    content: `content-${id}`,
    sender_type: 'agent',
    created_at,
    requires_user_input: false,
    message_metadata: null,
    ...over,
  };
}

function detail(
  id: string,
  messages: MessageResponse[],
  over: Partial<AgentInstanceDetail> = {},
): AgentInstanceDetail {
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
    ...over,
  };
}

const ids = (store: MessageStore, instanceId: string) =>
  store.getSnapshot(instanceId)?.messages.map((m) => m.id);

describe('MessageStore.getSnapshot', () => {
  it('returns null for a never-written instance, even after subscribing', () => {
    const store = new MessageStore();
    expect(store.getSnapshot('i1')).toBeNull();
    store.subscribe('i1', () => {});
    expect(store.getSnapshot('i1')).toBeNull();
  });

  it('returns a stable reference between writes', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    expect(store.getSnapshot('i1')).toBe(store.getSnapshot('i1'));
  });
});

describe('MessageStore.hydrateFromDetail', () => {
  it('stores instance metadata, ordered messages, watermark, and hasOlder', () => {
    const store = new MessageStore();
    const rows = [msg('m1', '2026-07-10T01:00:00Z'), msg('m2', '2026-07-10T02:00:00Z')];
    store.hydrateFromDetail('i1', detail('i1', rows), { hasOlder: true });

    const snap = store.getSnapshot('i1');
    expect(snap?.instance?.id).toBe('i1');
    // Canonical list is snapshot.messages; the embedded copy is emptied.
    expect(snap?.instance?.messages).toEqual([]);
    expect(snap?.messages).toEqual(rows);
    expect(snap?.watermark).toBe('2026-07-10T02:00:00Z');
    expect(snap?.hasOlder).toBe(true);
    expect(snap?.lastFetchedAt).toBeGreaterThan(0);
  });

  it('on id conflict the fetched copy wins over an earlier appended row', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z', { content: 'stale' })]);
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z', { content: 'authoritative' }),
    ]));
    expect(store.getSnapshot('i1')?.messages).toHaveLength(1);
    expect(store.getSnapshot('i1')?.messages[0].content).toBe('authoritative');
  });

  it('preserves already-paginated history older than the fetched span, keeping prior hasOlder', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m3', '2026-07-10T03:00:00Z')]));
    store.prependOlder(
      'i1',
      [msg('m1', '2026-07-10T01:00:00Z'), msg('m2', '2026-07-10T02:00:00Z')],
      true,
    );
    // Background revalidate returns only the newest page (m3 onward).
    store.hydrateFromDetail(
      'i1',
      detail('i1', [msg('m3', '2026-07-10T03:00:00Z'), msg('m4', '2026-07-10T04:00:00Z')]),
      { hasOlder: false }, // page-size heuristic on the head page alone
    );
    expect(ids(store, 'i1')).toEqual(['m1', 'm2', 'm3', 'm4']);
    // The fetched page's bottom is not the list's bottom — hasOlder unchanged.
    expect(store.getSnapshot('i1')?.hasOlder).toBe(true);
  });

  it('preserves live rows newer than the fetched span', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    store.appendOrMerge('i1', [msg('m9', '2026-07-10T09:00:00Z')]); // landed mid-flight
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z'),
      msg('m2', '2026-07-10T02:00:00Z'),
    ]));
    expect(ids(store, 'i1')).toEqual(['m1', 'm2', 'm9']);
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T09:00:00Z');
  });

  it('drops rows inside the fetched span that the backend no longer returns', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('ghost', '2026-07-10T01:30:00Z')]);
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z'),
      msg('m2', '2026-07-10T02:00:00Z'),
    ]));
    expect(ids(store, 'i1')).toEqual(['m1', 'm2']);
  });

  it('preserves optimistic rows and keeps them out of the watermark', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    store.appendOptimistic('i1', msg('optimistic-1', '2026-07-10T05:00:00Z', { sender_type: 'user' }));
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z'),
      msg('m2', '2026-07-10T02:00:00Z'),
    ]));
    expect(ids(store, 'i1')).toEqual(['m1', 'm2', 'optimistic-1']);
    // Client-clock optimistic timestamp must never advance the WS watermark.
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T02:00:00Z');
  });
});

describe('MessageStore.appendOrMerge', () => {
  it('creates a metadata-less entry for a never-hydrated instance', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    expect(store.getSnapshot('i1')?.instance).toBeNull();
    expect(ids(store, 'i1')).toEqual(['m1']);
  });

  it('dedupes by id (first write wins for duplicate delivery)', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z', { content: 'first' })]);
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z', { content: 'dupe' })]);
    expect(store.getSnapshot('i1')?.messages).toHaveLength(1);
    expect(store.getSnapshot('i1')?.messages[0].content).toBe('first');
  });

  it('inserts an out-of-order row at its created_at position and keeps the watermark at the max', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [
      msg('m1', '2026-07-10T01:00:00Z'),
      msg('m3', '2026-07-10T03:00:00Z'),
    ]);
    store.appendOrMerge('i1', [msg('m2', '2026-07-10T02:00:00Z')]);
    expect(ids(store, 'i1')).toEqual(['m1', 'm2', 'm3']);
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T03:00:00Z');
  });

  it('appends rows without a created_at at the end and never uses them as watermark', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    store.appendOrMerge('i1', [msg('m2', '')]);
    expect(ids(store, 'i1')).toEqual(['m1', 'm2']);
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T01:00:00Z');
  });
});

describe('MessageStore optimistic reconcile', () => {
  it('swap flow: real echo replaces the optimistic row (page removes, then appends)', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    store.appendOptimistic('i1', msg('optimistic-1', '2026-07-10T02:00:00Z', { sender_type: 'user' }));

    // The page's handleNewMessage on the real user echo:
    expect(store.hasMessage('i1', 'u1')).toBe(false);
    store.removeMessage('i1', 'optimistic-1');
    store.appendOrMerge('i1', [msg('u1', '2026-07-10T01:59:59Z', { sender_type: 'user' })]);

    expect(ids(store, 'i1')).toEqual(['m1', 'u1']);
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T01:59:59Z');
  });

  it('removeMessage clears the optimistic flag so a re-add is a normal row', () => {
    const store = new MessageStore();
    store.appendOptimistic('i1', msg('x', '2026-07-10T01:00:00Z'));
    store.removeMessage('i1', 'x');
    expect(store.hasMessage('i1', 'x')).toBe(false);
    store.appendOrMerge('i1', [msg('x', '2026-07-10T01:00:00Z')]);
    expect(store.getSnapshot('i1')?.watermark).toBe('2026-07-10T01:00:00Z');
  });
});

describe('MessageStore.patchMetadata', () => {
  it('replaces only the target message\'s metadata, preserving other fields, other messages, and order', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z', { message_metadata: { status: 'queued' } }),
      msg('m2', '2026-07-10T02:00:00Z', { message_metadata: { status: 'queued' } }),
    ]));

    store.patchMetadata('i1', 'm1', { status: 'consumed' });

    const snap = store.getSnapshot('i1');
    expect(snap?.messages[0]).toMatchObject({
      id: 'm1',
      content: 'content-m1',
      message_metadata: { status: 'consumed' },
    });
    // m2 untouched.
    expect(snap?.messages[1].message_metadata).toEqual({ status: 'queued' });
    // Order unchanged.
    expect(ids(store, 'i1')).toEqual(['m1', 'm2']);
  });

  it('accepts null metadata', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [
      msg('m1', '2026-07-10T01:00:00Z', { message_metadata: { status: 'queued' } }),
    ]));
    store.patchMetadata('i1', 'm1', null);
    expect(store.getSnapshot('i1')?.messages[0].message_metadata).toBeNull();
  });

  it('is a no-op for an unknown id', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    const before = store.getSnapshot('i1');
    store.patchMetadata('i1', 'does-not-exist', { status: 'consumed' });
    expect(store.getSnapshot('i1')).toBe(before); // same reference — no write happened
    expect(ids(store, 'i1')).toEqual(['m1']);
  });

  it('is a no-op for an unknown instance', () => {
    const store = new MessageStore();
    store.patchMetadata('does-not-exist', 'm1', { status: 'consumed' });
    expect(store.getSnapshot('does-not-exist')).toBeNull();
  });

  it('produces a new snapshot reference so useSyncExternalStore subscribers notify', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    const before = store.getSnapshot('i1');
    const cb = vi.fn();
    store.subscribe('i1', cb);

    store.patchMetadata('i1', 'm1', { status: 'consumed' });

    const after = store.getSnapshot('i1');
    expect(after).not.toBe(before);
    expect(after?.messages).not.toBe(before?.messages);
    expect(cb).toHaveBeenCalledTimes(1);
  });
});

describe('MessageStore.patchMetadata pending (races ahead of new-message)', () => {
  it('applies a patch that arrived before its row once the row lands', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    // consumed update bypasses the ordering buffer and lands before the row
    store.patchMetadata('i1', 'q1', { queue: { status: 'consumed' } });
    // ...then the row's new-message arrives carrying its stale queued status
    store.appendOrMerge('i1', [
      msg('q1', '2026-07-10T02:00:00Z', {
        sender_type: 'user',
        message_metadata: { queue: { status: 'queued' } },
      }),
    ]);
    const row = store.getSnapshot('i1')?.messages.find((m) => m.id === 'q1');
    expect(row?.message_metadata).toEqual({ queue: { status: 'consumed' } });
  });

  it('does not create a phantom row when patching an absent id', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    const before = store.getSnapshot('i1');
    store.patchMetadata('i1', 'ghost', { queue: { status: 'consumed' } });
    // Stashing must not write a snapshot or materialize a row.
    expect(store.getSnapshot('i1')).toBe(before);
    expect(ids(store, 'i1')).toEqual(['m1']);
  });

  it('applies a stashed null patch on insert', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    store.patchMetadata('i1', 'q1', null);
    store.appendOrMerge('i1', [
      msg('q1', '2026-07-10T02:00:00Z', { message_metadata: { queue: { status: 'queued' } } }),
    ]);
    const row = store.getSnapshot('i1')?.messages.find((m) => m.id === 'q1');
    expect(row?.message_metadata).toBeNull();
  });

  it('keeps the latest of several patches stashed before the row lands', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    store.patchMetadata('i1', 'q1', { queue: { status: 'queued' } });
    store.patchMetadata('i1', 'q1', { queue: { status: 'consumed' } });
    store.appendOrMerge('i1', [msg('q1', '2026-07-10T02:00:00Z')]);
    const row = store.getSnapshot('i1')?.messages.find((m) => m.id === 'q1');
    expect(row?.message_metadata).toEqual({ queue: { status: 'consumed' } });
  });

  it('preserves a pending patch across a hydrate that omits the row', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    store.patchMetadata('i1', 'q1', { queue: { status: 'consumed' } });
    // A background refetch lands before the row exists on the backend page.
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    store.appendOrMerge('i1', [
      msg('q1', '2026-07-10T02:00:00Z', { message_metadata: { queue: { status: 'queued' } } }),
    ]);
    const row = store.getSnapshot('i1')?.messages.find((m) => m.id === 'q1');
    expect(row?.message_metadata).toEqual({ queue: { status: 'consumed' } });
  });
});

describe('MessageStore.prependOlder', () => {
  it('is a no-op before the first write', () => {
    const store = new MessageStore();
    store.prependOlder('i1', [msg('m1', '2026-07-10T01:00:00Z')], true);
    expect(store.getSnapshot('i1')).toBeNull();
  });

  it('prepends fresh rows and takes hasOlder from the hasMore hint', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m3', '2026-07-10T03:00:00Z')]), { hasOlder: true });
    store.prependOlder('i1', [msg('m1', '2026-07-10T01:00:00Z'), msg('m2', '2026-07-10T02:00:00Z')], false);
    expect(ids(store, 'i1')).toEqual(['m1', 'm2', 'm3']);
    expect(store.getSnapshot('i1')?.hasOlder).toBe(false);
  });

  it('clears hasOlder when the whole page is already known, regardless of the hint', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]), { hasOlder: true });
    store.prependOlder('i1', [msg('m1', '2026-07-10T01:00:00Z')], true);
    expect(store.getSnapshot('i1')?.hasOlder).toBe(false);
    expect(ids(store, 'i1')).toEqual(['m1']);
  });
});

describe('MessageStore.patchInstance', () => {
  it('shallow-merges metadata', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', []));
    store.patchInstance('i1', { status: 'AWAITING_INPUT', pinned_at: '2026-07-10T05:00:00Z' });
    expect(store.getSnapshot('i1')?.instance?.status).toBe('AWAITING_INPUT');
    expect(store.getSnapshot('i1')?.instance?.pinned_at).toBe('2026-07-10T05:00:00Z');
  });

  it('is a no-op before the first hydrate provides the base object', () => {
    const store = new MessageStore();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    store.patchInstance('i1', { status: 'COMPLETED' });
    expect(store.getSnapshot('i1')?.instance).toBeNull();
  });
});

describe('MessageStore subscribe/notify', () => {
  it('notifies subscribers of the written instance only', () => {
    const store = new MessageStore();
    const onI1 = vi.fn();
    const onI2 = vi.fn();
    store.subscribe('i1', onI1);
    store.subscribe('i2', onI2);

    store.hydrateFromDetail('i1', detail('i1', []));
    expect(onI1).toHaveBeenCalledTimes(1);
    expect(onI2).not.toHaveBeenCalled();

    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    expect(onI1).toHaveBeenCalledTimes(2);
  });

  it('does not notify when a write changes nothing (duplicate append)', () => {
    const store = new MessageStore();
    const cb = vi.fn();
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    store.subscribe('i1', cb);
    store.appendOrMerge('i1', [msg('m1', '2026-07-10T01:00:00Z')]);
    expect(cb).not.toHaveBeenCalled();
  });

  it('stops notifying after unsubscribe', () => {
    const store = new MessageStore();
    const cb = vi.fn();
    const unsubscribe = store.subscribe('i1', cb);
    unsubscribe();
    store.hydrateFromDetail('i1', detail('i1', []));
    expect(cb).not.toHaveBeenCalled();
  });

  it('produces a new immutable snapshot per write (useSyncExternalStore contract)', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('i1', detail('i1', [msg('m1', '2026-07-10T01:00:00Z')]));
    const before = store.getSnapshot('i1');
    store.appendOrMerge('i1', [msg('m2', '2026-07-10T02:00:00Z')]);
    const after = store.getSnapshot('i1');
    expect(after).not.toBe(before);
    expect(before?.messages.map((m) => m.id)).toEqual(['m1']); // untouched
    expect(after?.messages.map((m) => m.id)).toEqual(['m1', 'm2']);
  });
});

describe('MessageStore LRU cap', () => {
  it('evicts the least-recently-touched unsubscribed entry beyond 20', () => {
    const store = new MessageStore();
    for (let i = 1; i <= 21; i += 1) {
      store.hydrateFromDetail(`i${i}`, detail(`i${i}`, []));
    }
    expect(store.getSnapshot('i1')).toBeNull(); // oldest evicted
    expect(store.getSnapshot('i2')).not.toBeNull();
    expect(store.getSnapshot('i21')).not.toBeNull();
  });

  it('never evicts a subscribed entry (the mounted session)', () => {
    const store = new MessageStore();
    store.hydrateFromDetail('mounted', detail('mounted', []));
    store.subscribe('mounted', () => {});
    for (let i = 1; i <= 21; i += 1) {
      store.hydrateFromDetail(`i${i}`, detail(`i${i}`, []));
    }
    expect(store.getSnapshot('mounted')).not.toBeNull();
    expect(store.getSnapshot('i1')).toBeNull();
  });
});
