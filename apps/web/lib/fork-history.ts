/**
 * Loading a session's complete history before a fork.
 *
 * The chat page hydrates the 200 most recent rows and lazy-loads older pages
 * only as the user scrolls up, so the message store usually holds the tail of
 * a session — a real one is 400–1 300 rows, one per tool call. A fork built
 * from that view silently starts from the last few turns. This walks the
 * cursor back to the beginning first, through the same store the transcript
 * renders from, so the view is complete too and the store's dedupe/`hasOlder`
 * rules apply unchanged.
 */

import type { MessageResponse } from '@/lib/backend-api';

/** Rows per page — the same page the CLI's `session show --all` walks with. */
export const FORK_HISTORY_PAGE_SIZE = 500;
/** Runaway guard; 20 000 rows is far past anything the budget trim keeps. */
export const FORK_HISTORY_MAX_PAGES = 40;

export interface ForkHistoryStore {
  getSnapshot(instanceId: string): { messages: MessageResponse[]; hasOlder: boolean } | null;
  prependOlder(instanceId: string, msgs: MessageResponse[], hasMore: boolean): void;
}

/**
 * Prepend older pages into the store until it reports no more history (or a
 * page comes back empty). Rejects on the first failed page and leaves the
 * store as it was up to that point — the caller must then abort the fork
 * rather than build from a partial view, which is the bug this exists to fix.
 */
export async function loadFullHistory(opts: {
  instanceId: string;
  store: ForkHistoryStore;
  /** Fetch the `limit` rows before `beforeMessageId`, oldest first. */
  fetchOlder: (beforeMessageId: string, limit: number) => Promise<MessageResponse[]>;
  pageSize?: number;
  maxPages?: number;
}): Promise<{ pages: number }> {
  const pageSize = opts.pageSize ?? FORK_HISTORY_PAGE_SIZE;
  const maxPages = opts.maxPages ?? FORK_HISTORY_MAX_PAGES;
  let pages = 0;
  while (pages < maxPages) {
    const entry = opts.store.getSnapshot(opts.instanceId);
    if (!entry?.hasOlder) break;
    // Optimistic rows have no backend id, so they cannot anchor a cursor.
    const oldest = entry.messages.find((m) => !m.id.startsWith('optimistic-'));
    if (!oldest) break;
    const page = await opts.fetchOlder(oldest.id, pageSize);
    pages += 1;
    // A fully-duplicate page clears hasOlder inside the store even when the
    // size heuristic (full page ⇒ assume more remain) says otherwise.
    opts.store.prependOlder(opts.instanceId, page, page.length >= pageSize);
    if (page.length === 0) break;
  }
  return { pages };
}
