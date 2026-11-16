'use client';

// Keeps a task surface (the task page, the peek panel, the board) current
// while an agent works on its tasks, without a socket of its own. Two signals:
//
// 1. A dispatch still on its way (queued, being started, or spawned with its
//    session not registered yet) has nothing to push it to the page, so the
//    page asks again: after 2s at first, backing off to the normal 30s poll
//    while it keeps waiting (an agent at its cap or an offline computer can
//    hold it queued for hours). Any change of state starts over at 2s.
// 2. Once there is a session, the dashboard's live session list (the stream
//    the sidebar draws from) says when its status moves. A turn starting or
//    ending is when an agent's comments and status changes land, so the page
//    reloads then.

import { useEffect, useMemo, useRef } from 'react';

import type { TaskDispatchSummary } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';

const FIRST_DELAY_MS = 2_000;
const MAX_DELAY_MS = 30_000;

/** A dispatch whose next state only a fresh fetch can show. */
export function dispatchSettling(dispatch: TaskDispatchSummary | null | undefined): boolean {
  if (!dispatch) return false;
  if (dispatch.state === 'queued' || dispatch.state === 'dispatching') return true;
  return dispatch.state === 'started' && dispatch.session_status === null;
}

/** The delay after `delay`: half again as long, up to the normal poll. */
export function nextDelay(delay: number): number {
  return Math.min(Math.round(delay * 1.5), MAX_DELAY_MS);
}

/** Watched sessions whose status differs from the one last seen. New ones don't count. */
export function changedStatuses(seen: Map<string, string>, current: Map<string, string>): boolean {
  for (const [id, status] of current) {
    const before = seen.get(id);
    if (before !== undefined && before !== status) return true;
  }
  return false;
}

/** One reload; a failure leaves the page as it was until the next one. */
async function quietly(reload: () => unknown): Promise<void> {
  try {
    await reload();
  } catch {
    // The next reload, or the page's own poll, tries again.
  }
}

export function useTaskLiveRefresh({
  dispatches,
  sessionIds,
  reload,
}: {
  /** The latest dispatch of each task on screen. */
  dispatches: ReadonlyArray<TaskDispatchSummary | null | undefined>;
  /** Sessions whose status changes should reload (the dispatches' own are added). */
  sessionIds: ReadonlyArray<string>;
  reload: () => unknown;
}): void {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  // As strings, so a new array with the same contents changes nothing.
  const settlingKey = dispatches
    .filter(dispatchSettling)
    .map((d) => `${d?.id}:${d?.state}`)
    .sort()
    .join('|');

  useEffect(() => {
    if (!settlingKey) return;
    let delay = FIRST_DELAY_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const schedule = () => {
      timer = setTimeout(async () => {
        // A hidden tab skips the fetch; the focus refresh catches it up.
        if (document.visibilityState === 'visible') await quietly(reloadRef.current);
        if (stopped) return;
        delay = nextDelay(delay);
        schedule();
      }, delay);
    };
    schedule();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [settlingKey]);

  const { recentInstances } = useAgentDashboard();
  const watchedKey = [
    ...sessionIds,
    ...dispatches.map((d) => d?.agent_instance_id ?? null).filter((id): id is string => !!id),
  ]
    .sort()
    .join('|');
  const statusKey = useMemo(() => {
    const watched = new Set(watchedKey.split('|').filter(Boolean));
    return recentInstances
      .filter((instance) => watched.has(instance.id))
      .map((instance) => `${instance.id}=${instance.status}`)
      .sort()
      .join('|');
  }, [recentInstances, watchedKey]);

  const seenRef = useRef(new Map<string, string>());
  useEffect(() => {
    const current = new Map(
      statusKey
        .split('|')
        .filter(Boolean)
        .map((pair) => pair.split('=') as [string, string]),
    );
    const changed = changedStatuses(seenRef.current, current);
    for (const [id, status] of current) seenRef.current.set(id, status);
    if (changed) void quietly(reloadRef.current);
  }, [statusKey]);
}
