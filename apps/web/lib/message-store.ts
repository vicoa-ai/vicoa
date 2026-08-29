/**
 * Instance-keyed message cache for the chat page — perf-ladder steps 2–3 of
 * `plans/todos/desktop-app.md` ("Session switching must feel instant"):
 * a store owns the messages, the page paints whatever the store already has,
 * then revalidates in the background.
 *
 * Module-level singleton with the same lifetime pattern as `getWsClient()` —
 * it lives above the route, so navigating between sessions keeps every
 * already-loaded conversation in memory and switching back repaints without
 * a network round-trip.
 *
 * The store is transport-agnostic: callers push rows in (REST hydrate, WS
 * live frames / catch-up, pagination); it never fetches, never imports
 * runtime config, and never branches on desktop vs web.
 *
 * Merge rules (the parent plan's "optimistic render must dedupe" section):
 * - The backend is authoritative. `hydrateFromDetail` replaces the
 *   `created_at` span its page covers; on an id conflict the fetched copy
 *   wins over anything applied earlier.
 * - Optimistic user messages are explicitly flagged and survive hydrates —
 *   they leave only via `removeMessage` (the page swaps them out when the
 *   real echo arrives, or on send failure).
 * - Already-paginated older history (before the hydrate span) and live rows
 *   newer than it are preserved, so a background refresh of the newest page
 *   never truncates the list.
 *
 * The append-tracker in `ws-protocol.ts` implements the same first-write-wins
 * id rule but hides its seen-set, and the store needs non-mutating `has`
 * lookups (`hasMessage`) plus removal — so entries carry a plain id Set;
 * `latestTimestamp` is reused for the watermark.
 */

import type { AgentInstanceDetail, MessageResponse } from '@/lib/backend-api';
import { latestTimestamp, type EntityRow } from '@/lib/ws-protocol';

/**
 * `latestTimestamp` over message rows. `MessageResponse` is an interface, so
 * it lacks the index signature `EntityRow` asks for, but the fields actually
 * read (`id`, `created_at: string`) are present — the cast is structural only.
 * Rows without a timestamp are skipped (an empty string must not become the
 * watermark: a catch-up "after ''" would refetch the whole history).
 */
function newestCreatedAt(
  current: string | null,
  rows: MessageResponse[],
): string | null {
  const stamped = rows.filter((m) => m.created_at);
  return latestTimestamp(current, stamped as unknown as EntityRow[], 'created_at');
}

/** Immutable per-instance snapshot, `useSyncExternalStore`-compatible: the
 *  reference only changes when a write lands for that instance. */
export interface MessageStoreSnapshot {
  /**
   * Instance metadata from the last authoritative fetch. Its embedded
   * `messages` array is emptied on hydrate — the canonical, ordered list is
   * the `messages` field below.
   */
  instance: AgentInstanceDetail | null;
  /** Ordered by `created_at`; optimistic entries ride at their insert spot. */
  messages: MessageResponse[];
  /**
   * `created_at` of the newest non-optimistic message — the WS catch-up
   * watermark. Optimistic rows carry client-clock timestamps and must never
   * advance it, or a fast client clock would skip real rows on reconnect.
   */
  watermark: string | null;
  /** Whether older history likely exists before `messages[0]`. */
  hasOlder: boolean;
  /** Epoch ms of the last `hydrateFromDetail`; 0 before the first one. */
  lastFetchedAt: number;
}

interface Entry {
  snapshot: MessageStoreSnapshot;
  /** Ids of every message currently in `snapshot.messages`. */
  ids: Set<string>;
  /** Subset of `ids` flagged optimistic (pending sends, page-generated ids). */
  optimisticIds: Set<string>;
  /**
   * `message-update` metadata patches that arrived before their row. Unlike
   * `new-message`, updates bypass the WS ordering buffer, so a fast
   * queued→consumed/cancelled patch can race ahead of the `new-message` that
   * creates its row. Stashed here and applied by `appendOrMerge` when the row
   * lands, so the patch is never lost (which would leave the message stuck at
   * its original `queued` status).
   */
  pendingMetadata: Map<string, Record<string, unknown> | null>;
  /** LRU clock value of the last touch (write or subscribe). */
  touch: number;
}

export interface HydrateOptions {
  /**
   * Caller's page-size heuristic: whether history likely continues past the
   * oldest fetched row. Ignored when deeper already-paginated history is
   * being preserved (the fetched page's bottom is then not the list's bottom).
   */
  hasOlder?: boolean;
}

const MAX_ENTRIES = 20;

const EMPTY_SNAPSHOT: MessageStoreSnapshot = {
  instance: null,
  messages: [],
  watermark: null,
  hasOlder: false,
  lastFetchedAt: 0,
};

export class MessageStore {
  private entries = new Map<string, Entry>();
  /** Kept outside `entries` so subscribing never materializes an entry —
   *  `getSnapshot` must stay `null` (stable) until the first write. */
  private subscribers = new Map<string, Set<() => void>>();
  private clock = 0;

  /** Current snapshot, or null if this instance has never been written. */
  getSnapshot(instanceId: string): MessageStoreSnapshot | null {
    return this.entries.get(instanceId)?.snapshot ?? null;
  }

  /** Non-mutating id lookup (optimistic rows included). */
  hasMessage(instanceId: string, messageId: string): boolean {
    return this.entries.get(instanceId)?.ids.has(messageId) ?? false;
  }

  subscribe(instanceId: string, callback: () => void): () => void {
    let set = this.subscribers.get(instanceId);
    if (!set) {
      set = new Set();
      this.subscribers.set(instanceId, set);
    }
    set.add(callback);
    const entry = this.entries.get(instanceId);
    if (entry) entry.touch = ++this.clock;
    return () => {
      set.delete(callback);
      if (set.size === 0) this.subscribers.delete(instanceId);
    };
  }

  /**
   * Authoritative refresh from `GET /agent-instances/{id}` (newest page).
   * Replaces the span the fetched page covers; preserves the paginated
   * prefix older than it, live rows newer than it, and optimistic rows.
   */
  hydrateFromDetail(
    instanceId: string,
    detail: AgentInstanceDetail,
    options: HydrateOptions = {},
  ): void {
    const prior = this.entries.get(instanceId);
    const fetched = detail.messages ?? [];
    const fetchedIds = new Set(fetched.map((m) => m.id));
    const oldestAt = fetched[0]?.created_at ?? null;
    const newestAt = fetched.at(-1)?.created_at ?? null;

    const prefix: MessageResponse[] = [];
    const tail: MessageResponse[] = [];
    if (prior) {
      for (const m of prior.snapshot.messages) {
        if (fetchedIds.has(m.id)) continue; // backend copy wins on id conflict
        if (prior.optimisticIds.has(m.id)) {
          tail.push(m); // pending send — survives until reconciled/removed
        } else if (oldestAt !== null && m.created_at < oldestAt) {
          prefix.push(m); // already-paginated older history
        } else if (newestAt !== null && m.created_at > newestAt) {
          tail.push(m); // live row that arrived during the fetch flight
        }
        // else: inside the authoritative span but absent from it → dropped.
      }
    }

    const messages = [...prefix, ...fetched, ...tail];
    const ids = new Set(messages.map((m) => m.id));
    const optimisticIds = new Set(
      [...(prior?.optimisticIds ?? [])].filter((id) => ids.has(id)),
    );
    // Carry over patches still waiting on rows this fetch didn't include; rows
    // it did include already hold their authoritative metadata, so drop those.
    const pendingMetadata = new Map(
      [...(prior?.pendingMetadata ?? [])].filter(([id]) => !ids.has(id)),
    );
    const entry: Entry = {
      snapshot: {
        instance: { ...detail, messages: [] },
        messages,
        watermark: newestCreatedAt(
          null,
          messages.filter((m) => !optimisticIds.has(m.id)),
        ),
        // With a preserved prefix the fetched page's bottom is not the list's
        // bottom — whether more history exists is unchanged by this refresh.
        hasOlder:
          prefix.length > 0
            ? (prior?.snapshot.hasOlder ?? false)
            : (options.hasOlder ?? false),
        lastFetchedAt: Date.now(),
      },
      ids,
      optimisticIds,
      pendingMetadata,
      touch: ++this.clock,
    };
    this.entries.set(instanceId, entry);
    this.evictIfNeeded();
    this.notify(instanceId);
  }

  /**
   * Merge live / catch-up rows: id-dedup (first write wins — an id conflict
   * with an existing row means duplicate delivery), inserted in `created_at`
   * order. Rows without a `created_at` append at the end. Creates the entry
   * if the instance has never been hydrated (metadata stays null until it is).
   */
  appendOrMerge(instanceId: string, msgs: MessageResponse[]): void {
    const entry = this.entries.get(instanceId) ?? this.createEmptyEntry(instanceId);
    const fresh = msgs.filter((m) => !entry.ids.has(m.id));
    if (fresh.length === 0) return;

    const messages = [...entry.snapshot.messages];
    for (const raw of fresh) {
      // Fold in any metadata patch that raced ahead of this row (see
      // `pendingMetadata`), so the row lands with its latest status instead of
      // the stale one its `new-message` carried.
      const pending = entry.pendingMetadata.get(raw.id);
      const msg = pending !== undefined ? { ...raw, message_metadata: pending } : raw;
      if (pending !== undefined) entry.pendingMetadata.delete(raw.id);
      messages.splice(this.insertionIndex(messages, msg), 0, msg);
      entry.ids.add(msg.id);
    }
    entry.snapshot = {
      ...entry.snapshot,
      messages,
      watermark: newestCreatedAt(entry.snapshot.watermark, fresh),
    };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  /**
   * Append a page-generated optimistic user message. Flagged so hydrates
   * preserve it and the watermark ignores its client-clock timestamp.
   */
  appendOptimistic(instanceId: string, msg: MessageResponse): void {
    const entry = this.entries.get(instanceId) ?? this.createEmptyEntry(instanceId);
    if (entry.ids.has(msg.id)) return;
    const messages = [...entry.snapshot.messages];
    messages.splice(this.insertionIndex(messages, msg), 0, msg);
    entry.ids.add(msg.id);
    entry.optimisticIds.add(msg.id);
    entry.snapshot = { ...entry.snapshot, messages };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  /**
   * Older-history pagination: prepend rows the store hasn't seen. When the
   * whole page was already known, history is exhausted regardless of the
   * caller's page-size heuristic. No-op before the first hydrate.
   */
  prependOlder(instanceId: string, msgs: MessageResponse[], hasMore: boolean): void {
    const entry = this.entries.get(instanceId);
    if (!entry) return;
    const fresh = msgs.filter((m) => !entry.ids.has(m.id));
    if (fresh.length === 0) {
      if (entry.snapshot.hasOlder) {
        entry.snapshot = { ...entry.snapshot, hasOlder: false };
        entry.touch = ++this.clock;
        this.notify(instanceId);
      }
      return;
    }
    for (const m of fresh) entry.ids.add(m.id);
    entry.snapshot = {
      ...entry.snapshot,
      messages: [...fresh, ...entry.snapshot.messages],
      hasOlder: hasMore,
    };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  /** Shallow-merge instance metadata (status, pinned_at, name, …). No-op
   *  until the first hydrate has provided the base object. */
  patchInstance(
    instanceId: string,
    patch: Partial<Omit<AgentInstanceDetail, 'messages'>>,
  ): void {
    const entry = this.entries.get(instanceId);
    if (!entry?.snapshot.instance) return;
    entry.snapshot = {
      ...entry.snapshot,
      instance: { ...entry.snapshot.instance, ...patch },
    };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  /**
   * Patch an existing message's `message_metadata` in place (WS
   * `message-update`, §2.4) — powers the queued/consumed/cancelled
   * indicators and (later) sub-agent grouping. Replaces only that field on
   * that row; does not reorder the list or touch any other message. No-op
   * if the id isn't present (not yet hydrated / already evicted).
   */
  patchMetadata(
    instanceId: string,
    id: string,
    metadata: Record<string, unknown> | null,
  ): void {
    const entry = this.entries.get(instanceId);
    if (!entry) return;
    if (!entry.ids.has(id)) {
      // Row not delivered yet — its `new-message` is still in the WS ordering
      // buffer. Stash the patch; `appendOrMerge` applies it on insert so the
      // update isn't lost.
      entry.pendingMetadata.set(id, metadata);
      return;
    }
    const index = entry.snapshot.messages.findIndex((m) => m.id === id);
    if (index === -1) return;
    const messages = [...entry.snapshot.messages];
    messages[index] = { ...messages[index], message_metadata: metadata };
    entry.snapshot = { ...entry.snapshot, messages };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  /** Remove a message by id (used to retire optimistic rows). */
  removeMessage(instanceId: string, messageId: string): void {
    const entry = this.entries.get(instanceId);
    if (!entry?.ids.has(messageId)) return;
    entry.ids.delete(messageId);
    entry.optimisticIds.delete(messageId);
    entry.snapshot = {
      ...entry.snapshot,
      messages: entry.snapshot.messages.filter((m) => m.id !== messageId),
    };
    entry.touch = ++this.clock;
    this.notify(instanceId);
  }

  private createEmptyEntry(instanceId: string): Entry {
    const entry: Entry = {
      snapshot: { ...EMPTY_SNAPSHOT },
      ids: new Set(),
      optimisticIds: new Set(),
      pendingMetadata: new Map(),
      touch: ++this.clock,
    };
    this.entries.set(instanceId, entry);
    this.evictIfNeeded();
    return entry;
  }

  /** Sorted-insert position: after every row with `created_at` <= the new
   *  row's (stable for ties). Missing timestamps sort to the end. */
  private insertionIndex(messages: MessageResponse[], msg: MessageResponse): number {
    if (!msg.created_at) return messages.length;
    let i = messages.length;
    while (i > 0) {
      const at = messages[i - 1].created_at;
      if (!at || at <= msg.created_at) break;
      i -= 1;
    }
    return i;
  }

  /** Bound memory: keep at most MAX_ENTRIES, evicting the least-recently
   *  touched entries that have no subscribers (never the mounted session). */
  private evictIfNeeded(): void {
    while (this.entries.size > MAX_ENTRIES) {
      let victim: string | null = null;
      let oldest = Infinity;
      for (const [id, entry] of this.entries) {
        if (this.subscribers.has(id)) continue;
        if (entry.touch < oldest) {
          oldest = entry.touch;
          victim = id;
        }
      }
      if (victim === null) return; // everything over cap is subscribed
      this.entries.delete(victim);
    }
  }

  private notify(instanceId: string): void {
    const set = this.subscribers.get(instanceId);
    if (!set) return;
    for (const callback of [...set]) callback();
  }
}

let sharedStore: MessageStore | null = null;

/** Shared store instance (plain module singleton, like `getWsClient()`). */
export function getMessageStore(): MessageStore {
  if (!sharedStore) sharedStore = new MessageStore();
  return sharedStore;
}
