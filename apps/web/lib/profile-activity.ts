/**
 * Profile activity data layer: fetches the server-aggregated daily activity
 * (see BackendAPI.getActivity) and keeps an incremental, per-user localStorage
 * cache so we don't re-pull history on every profile open.
 *
 * Why a cache works: past days are immutable — only recent days gain messages —
 * so we sync just the delta (`?since=<lastSyncedDay>`) and let the server's
 * authoritative counts overwrite those days in the cache. Totals come straight
 * from the response.
 *
 * When the endpoint isn't deployed yet, the caller falls back to
 * `fetchSessionStats`, a comprehensive (paginated) session-level derivation.
 */
import type { ActivityResponse } from './backend-api';
import { computeProfileStats, dayKey, type ProfileSessionLike } from './profile-stats';

export const ACTIVITY_CACHE_VERSION = 2;
const CACHE_PREFIX = 'vicoa.profile-activity.v2.';

/**
 * What the profile UI consumes, independent of source. Message counts are
 * `null` on the session-level fallback, which can't split user vs agent — the
 * UI renders those tiles as "—" until the server aggregate is available.
 */
export interface ProfileActivity {
  daily: Map<string, number>;
  totalSessions: number;
  totalUserMessages: number | null;
  totalMessages: number | null;
}

/** Persisted per-user cache (server data only). `daily` is a plain object for JSON. */
export interface CachedActivity {
  version: number;
  userId: string;
  daily: Record<string, number>;
  totalSessions: number;
  totalUserMessages: number;
  totalMessages: number;
  /** `YYYY-MM-DD` inclusive — everything up to here is already merged in. */
  syncedThrough: string | null;
  updatedAt: string;
}

/** The subset of BackendAPI this module needs (keeps it decoupled + testable). */
export interface ActivityApi {
  getActivity(since?: string): Promise<ActivityResponse>;
  listAllAgentInstancesPage(options: {
    limit?: number;
    offset?: number;
    activeOnly?: boolean;
  }): Promise<{ items: ProfileSessionLike[]; total: number; hasMore: boolean }>;
}

function cacheKey(userId: string): string {
  return CACHE_PREFIX + userId;
}

export function loadCache(userId: string): CachedActivity | null {
  try {
    const raw = window.localStorage.getItem(cacheKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedActivity;
    if (parsed.version !== ACTIVITY_CACHE_VERSION || parsed.userId !== userId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveCache(cache: CachedActivity): void {
  try {
    window.localStorage.setItem(cacheKey(cache.userId), JSON.stringify(cache));
  } catch {
    // Storage full/unavailable — the cache is an optimization, not a source of
    // truth, so a failed write just means the next open re-syncs.
  }
}

export function toProfileActivity(cache: CachedActivity): ProfileActivity {
  return {
    daily: new Map(Object.entries(cache.daily)),
    totalSessions: cache.totalSessions,
    totalUserMessages: cache.totalUserMessages,
    totalMessages: cache.totalMessages,
  };
}

/**
 * Pure merge of a fresh response into the cached state. Days present in the
 * response OVERWRITE the cached ones (the server is authoritative for any day
 * it returns — a partial `since` sync returns final past days plus the growing
 * current day); older cached days are preserved. Totals come from the response.
 */
export function mergeActivity(
  cached: CachedActivity | null,
  userId: string,
  response: ActivityResponse,
  today: string,
  nowIso: string,
): CachedActivity {
  const daily: Record<string, number> = { ...(cached?.daily ?? {}) };
  for (const [day, count] of Object.entries(response.daily)) {
    daily[day] = count;
  }
  return {
    version: ACTIVITY_CACHE_VERSION,
    userId,
    daily,
    totalSessions: response.total_sessions,
    totalUserMessages: response.total_user_messages,
    totalMessages: response.total_messages,
    syncedThrough: today,
    updatedAt: nowIso,
  };
}

/**
 * Sync the server activity into the cache and return the merged view.
 * Incremental: asks only for days since the last synced day. Throws if the
 * endpoint is unavailable (caller decides whether to fall back).
 */
export async function syncProfileActivity(
  api: Pick<ActivityApi, 'getActivity'>,
  userId: string,
  today: Date,
): Promise<ProfileActivity> {
  const cached = loadCache(userId);
  const response = await api.getActivity(cached?.syncedThrough ?? undefined);
  const merged = mergeActivity(cached, userId, response, dayKey(today), today.toISOString());
  saveCache(merged);
  return toProfileActivity(merged);
}

const SESSION_PAGE_SIZE = 100;
const SESSION_MAX_PAGES = 20; // hard cap so a heavy account can't page forever
const SESSION_LOOKBACK_DAYS = 366; // sessions are newest-first; stop past ~1 year

/**
 * Fallback when the activity endpoint isn't deployed: page the full session
 * list (comprehensive — the whole recent-year window, not just the sidebar's
 * first page) and derive stats from session dates. Approximate vs. real
 * message-days, but keeps the profile populated until the endpoint lands.
 */
export async function fetchSessionStats(
  api: Pick<ActivityApi, 'listAllAgentInstancesPage'>,
  today: Date,
): Promise<ProfileActivity> {
  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() - SESSION_LOOKBACK_DAYS);

  const sessions: ProfileSessionLike[] = [];
  let total = 0;
  let offset = 0;
  for (let page = 0; page < SESSION_MAX_PAGES; page++) {
    const res = await api.listAllAgentInstancesPage({
      limit: SESSION_PAGE_SIZE,
      offset,
      activeOnly: false,
    });
    total = res.total;
    sessions.push(...res.items);
    if (!res.hasMore || res.items.length === 0) break;
    const oldest = res.items[res.items.length - 1]?.started_at;
    if (oldest && new Date(oldest) < cutoff) break;
    offset += res.items.length;
  }

  const stats = computeProfileStats(sessions, total, today);
  return {
    daily: stats.dayCounts,
    totalSessions: stats.sessions,
    // The session list has no user/agent split (only chat_length = all
    // messages), so message tiles stay "—" until the server aggregate lands.
    totalUserMessages: null,
    totalMessages: null,
  };
}

/**
 * Load profile activity for the given user: prefer the server aggregate
 * (cached, incremental); on any failure keep a stale cache if we have one,
 * else fall back to the comprehensive session-level derivation. `userId` is
 * null in local mode (no cloud account) → straight to the fallback.
 */
export async function loadProfileActivity(
  api: ActivityApi,
  userId: string | null,
  today: Date,
): Promise<ProfileActivity> {
  if (userId) {
    try {
      return await syncProfileActivity(api, userId, today);
    } catch {
      const cached = loadCache(userId);
      if (cached) return toProfileActivity(cached);
      // no cache + endpoint unavailable → fall through to session fallback
    }
  }
  return fetchSessionStats(api, today);
}
