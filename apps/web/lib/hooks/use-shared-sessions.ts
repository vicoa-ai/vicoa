'use client';

/**
 * Sessions other people shared with the signed-in user,
 * kept apart from `useAgentDashboard().recentInstances` on purpose: that list
 * stays the user's own, so Kanban, search, unread counts and onboarding never
 * mix someone else's work in with theirs.
 *
 * The list is `GET /agent-instances?scope=shared`, polled at the idle cadence
 * and refetched whenever the relay says this user's access changed (a grant,
 * share or team membership added, changed or removed) or a watched session was
 * taken away. Rows the user is watching — the sidebar watches the open ones in
 * shared projects it lists as its own — are patched live from the relay's
 * watcher-room frames in between.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type BackendAPI from '@/lib/backend-api';
import type { AgentInstanceResponse } from '@/lib/backend-api';
import { bodyToInstancePatch } from '@/lib/hooks/use-ws-stream';
import { addsSomeoneToRow } from '@/lib/session-people';
import { POLL_IDLE_MS, useSharePoll } from '@/lib/use-share-poll';
import { getWsClient, type UpdatePayload } from '@/lib/ws-client';

const SHARED_PAGE_SIZE = 100;

export interface SharedSessions {
  instances: AgentInstanceResponse[];
  refresh: () => void;
}

export function useSharedSessions({
  api,
  onAccessChanged,
}: {
  /** Null disables it (logged out, or the local-only desktop). */
  api: BackendAPI | null;
  /** The relay said this user's access changed — refetch anything else shown. */
  onAccessChanged?: () => void;
}): SharedSessions {
  const [instances, setInstances] = useState<AgentInstanceResponse[]>([]);
  const knownIdsRef = useRef<Set<string>>(new Set());
  knownIdsRef.current = new Set(instances.map((i) => i.id));
  const instancesRef = useRef(instances);
  instancesRef.current = instances;
  const onAccessChangedRef = useRef(onAccessChanged);
  onAccessChangedRef.current = onAccessChanged;

  const load = useCallback(async () => {
    if (!api) return;
    const page = await api.listAllAgentInstancesPage({ scope: 'shared', limit: SHARED_PAGE_SIZE });
    setInstances(page.items);
  }, [api]);

  const { refresh } = useSharePoll(load, { intervalMs: POLL_IDLE_MS, enabled: api !== null });
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  // First load: the poll itself only ticks after an interval or on focus.
  useEffect(() => {
    if (api) refreshRef.current();
  }, [api]);

  useEffect(() => {
    if (!api) return;
    const client = getWsClient();
    const unsubscribe = client.subscribe((payload: UpdatePayload) => {
      const body = payload.body;
      if (body.t === 'access-changed') {
        refreshRef.current();
        onAccessChangedRef.current?.();
        return;
      }
      if ((body.t === 'instance-update' || body.t === 'instance-created') && body.grantee_view) {
        if (!knownIdsRef.current.has(body.id)) return;
        const patch = bodyToInstancePatch(body);
        setInstances((prev) => prev.map((i) => (i.id === body.id ? { ...i, ...patch } : i)));
        return;
      }
      if (body.t === 'new-message' && knownIdsRef.current.has(body.instance_id)) {
        // A first message from someone new (the viewer included): the row
        // may now have more than one person, whose faces come with the list.
        // Every row here is someone else's, so the owner is on it already.
        const row = instancesRef.current.find((i) => i.id === body.instance_id);
        if (row && addsSomeoneToRow(row, body.sender_user_id, null)) {
          refreshRef.current();
        }
      }
      if (body.t === 'new-message' && knownIdsRef.current.has(body.instance_id) && body.created_at) {
        const at = body.created_at;
        setInstances((prev) =>
          prev.map((i) =>
            i.id === body.instance_id && !(i.latest_message_at && i.latest_message_at >= at)
              ? { ...i, latest_message: body.content, latest_message_at: at }
              : i,
          ),
        );
      }
    });
    const offRevoked = client.onWatchRevoked(() => refreshRef.current());
    // A reconnect may have missed frames (and a grant change) while down.
    let wasConnected = client.isConnected();
    const offConnection = client.onConnectionChange((connected) => {
      if (connected && !wasConnected) refreshRef.current();
      wasConnected = connected;
    });
    return () => {
      unsubscribe();
      offRevoked();
      offConnection();
    };
  }, [api]);

  return { instances, refresh };
}

/**
 * Hold a watch on each of `instanceIds` (the relay's watcher rooms), adding and
 * releasing as the set changes rather than re-watching everything. For
 * sessions shared with the user only — their own need no watch.
 */
export function useWatchInstances(instanceIds: readonly string[]): void {
  const heldRef = useRef<Map<string, () => void>>(new Map());
  const key = [...instanceIds].sort().join(',');

  useEffect(() => {
    const held = heldRef.current;
    const wanted = new Set(key ? key.split(',') : []);
    for (const [id, release] of held) {
      if (!wanted.has(id)) {
        release();
        held.delete(id);
      }
    }
    const client = getWsClient();
    for (const id of wanted) {
      if (!held.has(id)) held.set(id, client.watchInstance(id));
    }
  }, [key]);

  useEffect(() => {
    const held = heldRef.current;
    return () => {
      for (const release of held.values()) release();
      held.clear();
    };
  }, []);
}
