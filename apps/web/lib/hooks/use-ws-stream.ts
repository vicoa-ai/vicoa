'use client';

/**
 * React bindings over the shared user-scoped WebSocket client (websocket-
 * migration plan §4 Phase 4a) — `useMessageStream` and `useInstanceStream`,
 * the realtime hooks that replaced the retired SSE streams.
 *
 * Both hooks attach to the single connection in `ws-client.ts` and filter its
 * stream locally (§2.3). Order-sensitive merge/dedupe is delegated to the pure
 * helpers in `ws-protocol.ts`.
 */

import { useEffect, useRef, useState } from 'react';
import {
  getBackendAPI,
  type AgentInstanceDetail,
  type AgentInstanceResponse,
  type AgentStatus,
  type MessageResponse,
} from '@/lib/backend-api';
import { getMessageStore } from '@/lib/message-store';
import {
  getWsClient,
  type InstanceBody,
  type MachineBody,
  type MessagesAfter,
  type NewMessageBody,
  type UpdatePayload,
} from '@/lib/ws-client';
import {
  CatchUpBuffer,
  createAppendTracker,
  createMutableTracker,
  latestTimestamp,
} from '@/lib/ws-protocol';

function bodyToMessage(body: NewMessageBody): MessageResponse {
  return {
    id: body.id,
    content: body.content,
    sender_type: body.sender_type,
    created_at: body.created_at ?? '',
    requires_user_input: body.requires_user_input,
    message_metadata: body.message_metadata,
  };
}

function bodyToInstancePatch(
  body: InstanceBody,
): Partial<AgentInstanceResponse> & { id: string } {
  return {
    id: body.id,
    status: body.status as keyof AgentStatus,
    name: body.name,
    project: body.project,
    home_dir: body.home_dir,
    ...(body.started_at ? { started_at: body.started_at } : {}),
    ended_at: body.ended_at,
  };
}

/**
 * A new instance's `update` body is the canonical row only — it lacks the
 * joined presentation fields the sidebar needs (§2.4). Compose a full
 * `AgentInstanceResponse` from the REST detail; `latest_message`/`chat_length`
 * are legitimately empty for a freshly created session.
 */
function detailToInstanceResponse(detail: AgentInstanceDetail): AgentInstanceResponse {
  return {
    id: detail.id,
    agent_type_id: detail.agent_type_id,
    agent_type_name: detail.agent_type_name,
    name: detail.name,
    status: detail.status,
    started_at: detail.started_at,
    ended_at: detail.ended_at,
    latest_message: null,
    latest_message_at: null,
    chat_length: detail.messages.length,
    project: detail.project,
    home_dir: detail.home_dir,
    // Without this a session spawned into a fresh worktree would sit in the
    // project's unheadered bucket until the next REST refresh — exactly the
    // moment the user is looking for it.
    worktree_name: detail.worktree_name,
  };
}

interface UseMessageStreamOptions {
  instanceId: string;
  enabled?: boolean;
  /** `created_at` of the newest message already rendered (from the REST load). */
  initialWatermark?: string | null;
  onMessage?: (message: MessageResponse) => void;
  onStatusUpdate?: (status: string) => void;
  /** Full `instance_metadata` from an instance-update — carries the usage blob. */
  onInstanceMetadata?: (metadata: Record<string, unknown> | null) => void;
  onError?: (error: Error) => void;
  onConnectionStateChange?: (connected: boolean) => void;
}

/**
 * Delivers one session's user/agent messages and status changes over the
 * shared WebSocket. On every (re)connect it runs a `fetch_messages_request`
 * catch-up from a `created_at` watermark; live updates that arrive mid-fetch
 * are buffered and merged in order (§2.6).
 */
export function useMessageStream({
  instanceId,
  enabled = true,
  initialWatermark = null,
  onMessage,
  onStatusUpdate,
  onInstanceMetadata,
  onError,
  onConnectionStateChange,
}: UseMessageStreamOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const cb = useRef({ onMessage, onStatusUpdate, onInstanceMetadata, onError, onConnectionStateChange });
  cb.current = { onMessage, onStatusUpdate, onInstanceMetadata, onError, onConnectionStateChange };

  // Read by value at effect setup only — never an effect dep, or the stream
  // would re-subscribe on every new message (the watermark advances per message).
  const initialWatermarkRef = useRef(initialWatermark);
  initialWatermarkRef.current = initialWatermark;

  useEffect(() => {
    if (!enabled || !instanceId) return;

    const client = getWsClient();
    const buffer = new CatchUpBuffer<NewMessageBody>(createAppendTracker());
    const statusTracker = createMutableTracker();
    // Bumped on every (re)connect; a stale paginating catch-up checks it and bails.
    let cycle = 0;
    let watermark: string | null = initialWatermarkRef.current;

    const deliver = (body: NewMessageBody) => {
      watermark = latestTimestamp(watermark, [body], 'created_at');
      cb.current.onMessage?.(bodyToMessage(body));
    };

    const runCatchUp = async () => {
      const myCycle = cycle;
      let after: MessagesAfter | null = watermark
        ? { created_at: watermark, id: null }
        : null;
      const rows: NewMessageBody[] = [];
      for (;;) {
        let result;
        try {
          result = await client.fetchMessages(instanceId, after);
        } catch {
          // The previous "return; the next connect re-runs catch-up" path
          // assumed catch-up failure == socket disconnect, but a
          // fetch_messages_request can time out (15 s) while the socket
          // stays OPEN — slow backend, paused worker, anything. When that
          // happens without a reconnect, buffer.fetchComplete stays false
          // and every subsequent live new-message piles up in buffered[]
          // forever, never reaching onMessage. The chat looks frozen until
          // the user hard-refreshes.
          //
          // Flush whatever rows we did pull plus any buffered live so the
          // buffer returns to working state. If a real disconnect actually
          // happened, the next reconnect's beginCatchUp() wipes this state
          // cleanly anyway — partial delivery is strictly better than
          // permanent stick.
          if (myCycle === cycle) {
            for (const body of buffer.completeFetch(rows)) deliver(body);
          }
          return;
        }
        if (myCycle !== cycle) return; // superseded by a newer connect
        if (result.resync) {
          after = null;
          rows.length = 0;
          continue;
        }
        rows.push(...result.rows);
        const last = result.rows.at(-1);
        if (!result.has_more || !last) break;
        after = { created_at: last.created_at ?? '', id: last.id };
      }
      for (const body of buffer.completeFetch(rows)) deliver(body);
    };

    const unsubscribeUpdates = client.subscribe((payload: UpdatePayload) => {
      const body = payload.body;
      if (body.t === 'new-message' && body.instance_id === instanceId) {
        for (const ready of buffer.bufferLive(body)) deliver(ready);
      } else if (body.t === 'message-update' && body.instance_id === instanceId) {
        // In-place metadata patch (queued/consumed/cancelled indicators) —
        // never appends, so it bypasses the append-ordering buffer above.
        getMessageStore().patchMetadata(instanceId, body.id, body.message_metadata ?? null);
      } else if (body.t === 'instance-update' && body.id === instanceId) {
        if (statusTracker.accept(body)) {
          cb.current.onStatusUpdate?.(body.status);
          cb.current.onInstanceMetadata?.(body.instance_metadata);
        }
      }
    });

    const unsubscribeConnection = client.onConnectionChange((connected) => {
      setIsConnected(connected);
      cb.current.onConnectionStateChange?.(connected);
      if (connected) {
        cycle += 1;
        buffer.beginCatchUp();
        setError(null);
        runCatchUp().catch((err: unknown) => {
          const e = err instanceof Error ? err : new Error('catch-up failed');
          setError(e);
          cb.current.onError?.(e);
        });
      }
    });

    return () => {
      cycle += 1;
      unsubscribeUpdates();
      unsubscribeConnection();
    };
  }, [enabled, instanceId]);

  return { isConnected, error };
}

interface UseInstanceStreamOptions {
  enabled?: boolean;
  onInstanceCreated?: (instance: AgentInstanceResponse) => void;
  onInstanceUpdated?: (instance: Partial<AgentInstanceResponse> & { id: string }) => void;
  /**
   * Fires on every `new-message` across all instances. The dashboard uses this
   * to advance the row's `latest_message_at` from the message's `created_at` —
   * the WS `instance-update` frame body doesn't carry message metadata, so
   * without this the sidebar timestamp goes stale until the next REST refresh.
   */
  onNewMessage?: (msg: NewMessageBody) => void;
}

/**
 * Keeps the dashboard's instance list fresh over the shared WebSocket. New
 * sessions arrive as `instance-created`, field changes as `instance-update`;
 * a `fetch_instances_request` catch-up runs on every (re)connect (§2.6). The
 * mutable tracker drops out-of-order frames by `updated_at`.
 */
export function useInstanceStream({
  enabled = true,
  onInstanceCreated,
  onInstanceUpdated,
  onNewMessage,
}: UseInstanceStreamOptions) {
  const cb = useRef({ onInstanceCreated, onInstanceUpdated, onNewMessage });
  cb.current = { onInstanceCreated, onInstanceUpdated, onNewMessage };

  useEffect(() => {
    if (!enabled) return;

    const client = getWsClient();
    const buffer = new CatchUpBuffer<InstanceBody>(createMutableTracker());
    let cycle = 0;
    let watermark: string | null = null;

    const deliver = (body: InstanceBody) => {
      watermark = latestTimestamp(watermark, [body], 'updated_at');
      if (body.t === 'instance-created') {
        getBackendAPI(true)
          .getInstanceDetail(body.id, 1)
          .then((detail) =>
            cb.current.onInstanceCreated?.(detailToInstanceResponse(detail)),
          )
          .catch((err) => console.error('[ws] instance detail fetch failed:', err));
      } else {
        cb.current.onInstanceUpdated?.(bodyToInstancePatch(body));
      }
    };

    const runCatchUp = async () => {
      const myCycle = cycle;
      let rows: InstanceBody[];
      try {
        rows = await client.fetchInstances(watermark);
      } catch {
        // Same recovery as useMessageStream — a fetch_instances_request
        // timeout on a still-OPEN socket would otherwise leave the sidebar
        // buffer stuck and live instance-update / new-message frames
        // pinned in buffered[] until the next reconnect or page refresh.
        if (myCycle === cycle) {
          for (const body of buffer.completeFetch([])) deliver(body);
        }
        return;
      }
      if (myCycle !== cycle) return;
      for (const body of buffer.completeFetch(rows)) deliver(body);
    };

    const unsubscribeUpdates = client.subscribe((payload: UpdatePayload) => {
      const body = payload.body;
      if (body.t === 'instance-created' || body.t === 'instance-update') {
        for (const ready of buffer.bufferLive(body)) deliver(ready);
      } else if (body.t === 'new-message') {
        cb.current.onNewMessage?.(body);
      }
    });

    const unsubscribeConnection = client.onConnectionChange((connected) => {
      if (connected) {
        cycle += 1;
        buffer.beginCatchUp();
        void runCatchUp();
      }
    });

    return () => {
      cycle += 1;
      unsubscribeUpdates();
      unsubscribeConnection();
    };
  }, [enabled]);
}

interface UseMachineStreamOptions {
  enabled?: boolean;
  /**
   * Fires for each machine row — from a live `machine-update` frame and from the
   * reconnect `fetch_machines_request` catch-up. Bodies are canonical rows
   * (§2.4), so the consumer can replace whole local state per id.
   */
  onMachineUpdated?: (machine: MachineBody) => void;
}

/**
 * Keeps the machine list fresh over the shared WebSocket. Daemons broadcast a
 * `machine-update` on register (connect) and on every heartbeat; a
 * `fetch_machines_request` catch-up runs on every (re)connect (§2.6). The
 * mutable tracker drops out-of-order frames by `updated_at`.
 *
 * IMPORTANT: there is NO server event when a daemon goes *offline* — the row
 * simply stops receiving heartbeats and its `last_heartbeat_at` ages out. This
 * hook therefore makes connect/heartbeat realtime, but cannot signal a
 * disconnect; consumers must re-evaluate liveness on a timer (`isMachineOnline`
 * is a function of elapsed time) rather than waiting for a frame that never
 * comes.
 */
export function useMachineStream({
  enabled = true,
  onMachineUpdated,
}: UseMachineStreamOptions) {
  const cb = useRef({ onMachineUpdated });
  cb.current = { onMachineUpdated };

  useEffect(() => {
    if (!enabled) return;

    const client = getWsClient();
    const buffer = new CatchUpBuffer<MachineBody>(createMutableTracker());
    let cycle = 0;
    let watermark: string | null = null;

    const deliver = (body: MachineBody) => {
      watermark = latestTimestamp(watermark, [body], 'updated_at');
      cb.current.onMachineUpdated?.(body);
    };

    const runCatchUp = async () => {
      const myCycle = cycle;
      let rows: MachineBody[];
      try {
        rows = await client.fetchMachines(watermark);
      } catch {
        // Mirror the instance/message streams: a fetch timeout on a still-OPEN
        // socket would otherwise leave live `machine-update` frames pinned in
        // the buffer until the next reconnect. Flush the buffered live rows so
        // the list keeps updating.
        if (myCycle === cycle) {
          for (const body of buffer.completeFetch([])) deliver(body);
        }
        return;
      }
      if (myCycle !== cycle) return;
      for (const body of buffer.completeFetch(rows)) deliver(body);
    };

    const unsubscribeUpdates = client.subscribe((payload: UpdatePayload) => {
      const body = payload.body;
      if (body.t === 'machine-update') {
        for (const ready of buffer.bufferLive(body)) deliver(ready);
      }
    });

    const unsubscribeConnection = client.onConnectionChange((connected) => {
      if (connected) {
        cycle += 1;
        buffer.beginCatchUp();
        void runCatchUp();
      }
    });

    return () => {
      cycle += 1;
      unsubscribeUpdates();
      unsubscribeConnection();
    };
  }, [enabled]);
}
