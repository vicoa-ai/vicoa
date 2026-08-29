import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActivityResponse } from './backend-api';
import {
  fetchSessionStats,
  loadCache,
  loadProfileActivity,
  mergeActivity,
  saveCache,
  syncProfileActivity,
  toProfileActivity,
  type ActivityApi,
  type CachedActivity,
} from './profile-activity';

// Minimal in-memory localStorage so the module's window.localStorage works
// under the node test environment.
class MemStorage {
  private store = new Map<string, string>();
  getItem(k: string) { return this.store.has(k) ? this.store.get(k)! : null; }
  setItem(k: string, v: string) { this.store.set(k, String(v)); }
  removeItem(k: string) { this.store.delete(k); }
  clear() { this.store.clear(); }
}

beforeEach(() => {
  vi.stubGlobal('window', { localStorage: new MemStorage() });
});

const today = new Date(2026, 6, 13); // 2026-07-13

function response(partial: Partial<ActivityResponse> = {}): ActivityResponse {
  return {
    daily: {},
    total_sessions: 0,
    total_user_messages: 0,
    total_messages: 0,
    as_of: '2026-07-13T00:00:00.000Z',
    ...partial,
  };
}

function cache(partial: Partial<CachedActivity> = {}): CachedActivity {
  return {
    version: 2,
    userId: 'u1',
    daily: {},
    totalSessions: 0,
    totalUserMessages: 0,
    totalMessages: 0,
    syncedThrough: null,
    updatedAt: today.toISOString(),
    ...partial,
  };
}

describe('mergeActivity', () => {
  it('builds fresh state from a null cache', () => {
    const merged = mergeActivity(
      null,
      'u1',
      response({ daily: { '2026-07-13': 5 }, total_sessions: 3, total_user_messages: 20, total_messages: 47 }),
      '2026-07-13',
      today.toISOString(),
    );
    expect(merged.daily).toEqual({ '2026-07-13': 5 });
    expect(merged.totalSessions).toBe(3);
    expect(merged.totalUserMessages).toBe(20);
    expect(merged.totalMessages).toBe(47);
    expect(merged.syncedThrough).toBe('2026-07-13');
  });

  it('overwrites returned days but preserves older cached days', () => {
    const merged = mergeActivity(
      cache({ daily: { '2026-07-10': 2, '2026-07-12': 4 }, totalUserMessages: 6, totalMessages: 14, syncedThrough: '2026-07-12' }),
      'u1',
      response({ daily: { '2026-07-12': 6, '2026-07-13': 1 }, total_sessions: 6, total_user_messages: 9, total_messages: 22 }),
      '2026-07-13',
      today.toISOString(),
    );
    expect(merged.daily).toEqual({ '2026-07-10': 2, '2026-07-12': 6, '2026-07-13': 1 });
    expect(merged.totalUserMessages).toBe(9);
    expect(merged.totalMessages).toBe(22);
  });
});

describe('cache round-trip', () => {
  it('saves and loads by user, rejecting version/user mismatches', () => {
    const c = cache({ daily: { '2026-07-13': 3 }, totalSessions: 1, totalUserMessages: 3, totalMessages: 5, syncedThrough: '2026-07-13' });
    saveCache(c);
    expect(loadCache('u1')).toEqual(c);
    expect(loadCache('u2')).toBeNull(); // different user
    saveCache({ ...c, version: 99 });
    expect(loadCache('u1')).toBeNull(); // version mismatch
  });

  it('converts a cache into the UI shape', () => {
    const activity = toProfileActivity(
      cache({ daily: { '2026-07-13': 3 }, totalSessions: 2, totalUserMessages: 3, totalMessages: 4 }),
    );
    expect(activity.daily.get('2026-07-13')).toBe(3);
    expect(activity.totalSessions).toBe(2);
    expect(activity.totalUserMessages).toBe(3);
    expect(activity.totalMessages).toBe(4);
  });
});

describe('syncProfileActivity', () => {
  it('sends the last synced day as `since` and caches the merge', async () => {
    saveCache(cache({ daily: { '2026-07-11': 2 }, totalUserMessages: 2, totalMessages: 3, syncedThrough: '2026-07-11' }));
    const getActivity = vi.fn(async () =>
      response({ daily: { '2026-07-13': 4 }, total_user_messages: 5, total_messages: 9 }),
    );
    const activity = await syncProfileActivity({ getActivity }, 'u1', today);
    expect(getActivity).toHaveBeenCalledWith('2026-07-11'); // incremental
    expect(activity.daily.get('2026-07-11')).toBe(2); // preserved
    expect(activity.daily.get('2026-07-13')).toBe(4); // merged
    expect(activity.totalMessages).toBe(9);
    expect(loadCache('u1')?.syncedThrough).toBe('2026-07-13'); // persisted
  });
});

describe('fetchSessionStats (fallback)', () => {
  it('derives sessions/heatmap from the list but leaves message counts null', async () => {
    const api: Pick<ActivityApi, 'listAllAgentInstancesPage'> = {
      listAllAgentInstancesPage: vi.fn(async () => ({
        items: [
          { started_at: new Date(2026, 6, 13).toISOString(), latest_message_at: null, chat_length: 5 },
          { started_at: new Date(2026, 6, 12).toISOString(), latest_message_at: null, chat_length: 3 },
        ],
        total: 2,
        hasMore: false,
      })),
    };
    const activity = await fetchSessionStats(api, today);
    expect(activity.totalSessions).toBe(2);
    expect(activity.totalUserMessages).toBeNull(); // can't split user/agent
    expect(activity.totalMessages).toBeNull();
    expect(activity.daily.get('2026-07-13')).toBe(1);
  });
});

describe('loadProfileActivity', () => {
  const sessionApi = () => ({
    listAllAgentInstancesPage: vi.fn(async () => ({
      items: [{ started_at: today.toISOString(), latest_message_at: null, chat_length: 2 }],
      total: 1,
      hasMore: false,
    })),
  });

  it('uses the server aggregate when available', async () => {
    const api: ActivityApi = {
      ...sessionApi(),
      getActivity: vi.fn(async () =>
        response({ daily: { '2026-07-13': 9 }, total_sessions: 4, total_user_messages: 40, total_messages: 88 }),
      ),
    };
    const activity = await loadProfileActivity(api, 'u1', today);
    expect(activity.totalUserMessages).toBe(40);
    expect(activity.totalMessages).toBe(88);
    expect(activity.daily.get('2026-07-13')).toBe(9);
  });

  it('keeps a stale cache when the endpoint fails', async () => {
    saveCache(cache({ daily: { '2026-07-12': 7 }, totalSessions: 3, totalUserMessages: 7, totalMessages: 15, syncedThrough: '2026-07-12' }));
    const api: ActivityApi = {
      ...sessionApi(),
      getActivity: vi.fn(async () => { throw new Error('404'); }),
    };
    const activity = await loadProfileActivity(api, 'u1', today);
    expect(activity.totalMessages).toBe(15); // from stale cache, not the session fallback
    expect(api.listAllAgentInstancesPage).not.toHaveBeenCalled();
  });

  it('falls back to session stats (null message counts) when the endpoint fails without a cache', async () => {
    const api: ActivityApi = {
      ...sessionApi(),
      getActivity: vi.fn(async () => { throw new Error('404'); }),
    };
    const activity = await loadProfileActivity(api, 'u1', today);
    expect(activity.totalSessions).toBe(1);
    expect(activity.totalMessages).toBeNull();
    expect(api.listAllAgentInstancesPage).toHaveBeenCalled();
  });

  it('goes straight to the session fallback in local mode (no userId)', async () => {
    const api: ActivityApi = {
      ...sessionApi(),
      getActivity: vi.fn(async () => response()),
    };
    const activity = await loadProfileActivity(api, null, today);
    expect(activity.totalSessions).toBe(1);
    expect(activity.totalMessages).toBeNull();
    expect(api.getActivity).not.toHaveBeenCalled();
  });
});
