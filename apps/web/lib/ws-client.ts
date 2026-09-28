/**
 * Shared user-scoped WebSocket client for vicoa-web (websocket-migration plan
 * §2.1-2.10). One connection per browser tab carries every realtime update for
 * the signed-in user; the React hooks in `use-ws-stream.ts` subscribe to it and
 * filter locally (§2.3 "get all, filter locally").
 *
 * Socket I/O and reconnect orchestration live here; the order-sensitive
 * merge/dedupe semantics are the pure functions in `ws-protocol.ts`.
 */

import type { Subscription } from '@supabase/supabase-js';
import { createClient } from '@/lib/auth/supabase-client';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { getBuiltinToken } from '@/lib/auth/builtin-client';
import { getCloudWsUrl, getDesktopConfig } from '@/lib/runtime-config';
import { ensureLocalMachineId, getLocalMachineId } from '@/lib/local-machine';
import { reconnectDelayMs } from '@/lib/ws-protocol';

// These bodies are written as `type` aliases, not `interface`s, so they satisfy
// the index-signature constraint of `EntityRow` (ws-protocol.ts) — interfaces
// are open to declaration merging and TS withholds the implicit index signature.

/** `update` body for a newly inserted `messages` row (append-only, §2.4). */
export type NewMessageBody = {
  t: 'new-message';
  id: string;
  instance_id: string;
  sender_type: string;
  sender_user_id: string | null;
  content: string;
  created_at: string | null;
  requires_user_input: boolean;
  message_metadata: Record<string, unknown> | null;
};

/**
 * `update` body for an existing `messages` row's metadata changing in place
 * (queued/consumed/cancelled indicators, and later sub-agent grouping).
 * Patches the row identified by `id` — never appends; that's `NewMessageBody`.
 */
export type MessageUpdateBody = {
  t: 'message-update';
  id: string;
  instance_id: string;
  message_metadata: Record<string, unknown> | null;
};

/** `update` body for an agent instance — the complete canonical row (§2.4). */
export type InstanceBody = {
  t: 'instance-created' | 'instance-update';
  id: string;
  user_agent_id: string;
  status: string;
  name: string | null;
  project: string | null;
  home_dir: string | null;
  started_at: string | null;
  ended_at: string | null;
  last_heartbeat_at: string | null;
  instance_metadata: Record<string, unknown> | null;
  has_git_changes: boolean;
  updated_at: string;
};

/** `update` body for a machine — the complete canonical row (§2.4). */
export type MachineBody = {
  t: 'machine-update';
  id: string;
  display_name: string | null;
  hostname: string | null;
  platform: string | null;
  home_dir: string | null;
  last_heartbeat_at: string | null;
  machine_metadata: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string;
};

export type UpdateBody = NewMessageBody | InstanceBody | MachineBody | MessageUpdateBody;

/** The `payload` of a server→client `update` frame (§2.4). */
export interface UpdatePayload {
  entity: string;
  entity_id: string;
  event_id: string;
  body: UpdateBody;
}

/** Cursor for `fetch_messages_request.after` — reconnect watermark or page cursor. */
export interface MessagesAfter {
  created_at: string;
  /** `null` = reconnect watermark (safety window); set = strict pagination cursor. */
  id: string | null;
}

export interface FetchMessagesResult {
  rows: NewMessageBody[];
  has_more: boolean;
  /** Set when the server could not serve the cursor — caller must re-fetch from scratch. */
  resync: boolean;
}

/** A failed `rpc-call` (§2.8). `code` is `no_handler` | `target_disconnected` | `timeout`. */
export class RpcError extends Error {
  readonly code: string;
  constructor(code: string) {
    super(`rpc call failed: ${code}`);
    this.name = 'RpcError';
    this.code = code;
  }
}

// Resolved per call, not once at module load: a self-hosting desktop build
// supplies its own endpoint through the preload, which is only readable once
// `window` exists (this module is also imported during SSR).
const wsUrl = (): string => getCloudWsUrl();

/**
 * How a WsClient authenticates its handshake (desktop-app v1 seam):
 * - `supabase` — the existing web path: read the Supabase session at connect
 *   time, send subprotocol `vicoa-supabase.<jwt>`, and mirror the auth
 *   lifecycle (token refresh / sign-out) into the socket.
 * - `local` — desktop path against the daemon's local server: send
 *   subprotocol `vicoa-local.<nonce>`; no Supabase involvement at all (must
 *   work with no Supabase session present).
 */
type WsAuth = { kind: 'supabase' } | { kind: 'local'; token: string };

/** The hello frame a client announces on connect. Defaults to user-scoped
 *  (the shared realtime socket); a per-machine terminal client announces
 *  `terminal-scoped` + its `machineId` to join that machine's pty-output room. */
type WsHello = { scope: string; machineId?: string };

interface WsClientOptions {
  url: string;
  auth: WsAuth;
  hello?: WsHello;
}

// No frame (not even a server ping every 30s) for this long means a dead
// socket the browser has not surfaced yet — force a reconnect.
const LIVENESS_TIMEOUT_MS = 70_000;

// When the user comes back from a background tab / sleep / network blip, we
// can't trust the liveness timer above: Chrome throttles setTimeout in
// background tabs (1 wake/min, sometimes much less under intensive
// throttling), so the 70 s timer may not have fired on schedule even after
// the socket actually died. If no frame has arrived for this long when a
// resume event fires, treat the socket as a zombie and close it to trigger
// a fresh reconnect.
//
// Threshold must stay comfortably above the server's 30 s ping cadence,
// otherwise a focus event landing between two healthy pings would tear
// down the live socket. 60 s == 2 missed pings is a strong "definitely
// dead" signal without false positives from normal foreground use.
const RESUME_STALE_THRESHOLD_MS = 60_000;

// Per-request wall-clock timeouts. The liveness timer above only fires when no
// frames at all are arriving; server pings keep it from helping when a single
// in-flight request gets stuck server-side. Server's own RPC timeout is 30s
// (shared/websocket/rpc.py), so the client waits a touch longer; fetch_* has
// no server-side timeout so the DB statement_timeout has to bite first.
const RPC_REQUEST_TIMEOUT_MS = 35_000;
const FETCH_REQUEST_TIMEOUT_MS = 15_000;

// Grace before tearing down the socket once the last subscriber leaves, so a
// React strict-mode remount or a fast route change does not flap the socket.
const IDLE_CLOSE_GRACE_MS = 1_000;

type UpdateListener = (payload: UpdatePayload) => void;
type ConnectionListener = (connected: boolean) => void;
/** `data` is the base64-encoded output chunk exactly as it arrived on the wire. */
type PtyOutputListener = (ptyId: string, data: string) => void;
type PtyExitListener = (ptyId: string, exitCode: number | null) => void;
type ConnectedWaiter = {
  resolve: () => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

interface PendingFetch {
  resolve: (frame: Record<string, unknown>) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

class WsClient {
  private readonly url: string;
  private readonly auth: WsAuth;
  private readonly hello: WsHello;
  private socket: WebSocket | null = null;
  private connected = false;
  private destroyed = false;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private livenessTimer: ReturnType<typeof setTimeout> | null = null;
  private idleCloseTimer: ReturnType<typeof setTimeout> | null = null;
  private retainCount = 0;
  private requestSeq = 0;
  /**
   * Last foreground state reported via `sendPresence`, or null if never set
   * (plain web, or the desktop reporter isn't mounted). Re-asserted after every
   * reconnect, since each new server-side connection starts backgrounded.
   */
  private lastPresence: boolean | null = null;
  /** Wall-clock at the last received frame. Powers the resume-staleness check. */
  private lastFrameAt = 0;
  private resumeHooksInstalled = false;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private authSubscription: Subscription | null = null;
  private authHooksInstalled = false;
  private readonly pendingFetches = new Map<string, PendingFetch>();
  private readonly connectedWaiters = new Set<ConnectedWaiter>();
  private readonly updateListeners = new Set<UpdateListener>();
  private readonly connectionListeners = new Set<ConnectionListener>();
  private readonly ptyOutputListeners = new Set<PtyOutputListener>();
  private readonly ptyExitListeners = new Set<PtyExitListener>();

  constructor(options: WsClientOptions) {
    this.url = options.url;
    this.auth = options.auth;
    this.hello = options.hello ?? { scope: 'user-scoped' };
    this.installResumeHooks();
    this.startHeartbeatCheck();
    // Local auth carries a static nonce — there is no Supabase session to
    // mirror (and none may exist at all in logged-out desktop mode).
    if (this.auth.kind === 'supabase') this.installAuthHook();
  }

  /** True once the hello/server_info handshake has completed. */
  isConnected(): boolean {
    return this.connected;
  }

  /**
   * Subscribe to live `update` payloads. The first subscriber opens the socket;
   * the connection stays up until the last subscriber leaves. Returns an
   * unsubscribe function.
   */
  subscribe(listener: UpdateListener): () => void {
    this.updateListeners.add(listener);
    this.retain();
    return () => {
      this.updateListeners.delete(listener);
      this.release();
    };
  }

  /** Observe connect/disconnect transitions (fires with the current state). */
  onConnectionChange(listener: ConnectionListener): () => void {
    this.connectionListeners.add(listener);
    listener(this.connected);
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  /**
   * Subscribe to `pty-output` push frames (desktop terminal pane). Like
   * `subscribe`, holding a listener retains the connection so output keeps
   * flowing while a terminal is open. Returns an unsubscribe function.
   */
  onPtyOutput(listener: PtyOutputListener): () => void {
    this.ptyOutputListeners.add(listener);
    this.retain();
    return () => {
      this.ptyOutputListeners.delete(listener);
      this.release();
    };
  }

  /** Subscribe to `pty-exit` push frames. Returns an unsubscribe function. */
  onPtyExit(listener: PtyExitListener): () => void {
    this.ptyExitListeners.add(listener);
    this.retain();
    return () => {
      this.ptyExitListeners.delete(listener);
      this.release();
    };
  }

  /** Catch-up fetch for one session's messages (§2.6). */
  async fetchMessages(
    instanceId: string,
    after: MessagesAfter | null,
  ): Promise<FetchMessagesResult> {
    const frame = await this.sendFetch('fetch_messages_request', {
      instance_id: instanceId,
      after,
    });
    if (frame.type === 'resync_required') {
      return { rows: [], has_more: false, resync: true };
    }
    return {
      rows: (frame.rows as NewMessageBody[]) ?? [],
      has_more: Boolean(frame.has_more),
      resync: false,
    };
  }

  /** Catch-up fetch for the user's agent instances (§2.6). */
  async fetchInstances(updatedAfter: string | null): Promise<InstanceBody[]> {
    const frame = await this.sendFetch('fetch_instances_request', {
      updated_after: updatedAfter,
    });
    return (frame.rows as InstanceBody[]) ?? [];
  }

  /** Catch-up fetch for the user's machines (§2.6). */
  async fetchMachines(updatedAfter: string | null): Promise<MachineBody[]> {
    const frame = await this.sendFetch('fetch_machines_request', {
      updated_after: updatedAfter,
    });
    return (frame.rows as MachineBody[]) ?? [];
  }

  /**
   * Resolve when the next `update` for `(entity, entityId)` arrives, or after
   * `timeoutMs`. Used after `spawn-session` to await the daemon-spawned
   * agent's self-registration without polling REST — the user-scoped socket
   * is already receiving the `instance-created` broadcast for the dashboard.
   *
   * Returns true on the event, false on timeout.
   *
   * CALLER POLICY: do not wrap this in per-flow REST polling. If you find
   * yourself wanting a REST fallback, the correct fix is to unify catch-up
   * rows into the same dispatch path as live frames (so `fetch_*_response`
   * rows feed `dispatchUpdate` and a reconnect catch-up resolves this
   * promise automatically). The Flutter spawn widgets keep a contained
   * REST fallback as a known exception until that unification lands; the
   * web client does not need one and should stay that way.
   */
  waitForEntity(
    entity: string,
    entityId: string,
    { timeoutMs = 15000 }: { timeoutMs?: number } = {},
  ): Promise<boolean> {
    return new Promise((resolve) => {
      let unsubscribe: () => void = () => {};
      const timer = setTimeout(() => {
        unsubscribe();
        resolve(false);
      }, timeoutMs);
      unsubscribe = this.subscribe((payload) => {
        if (payload.entity === entity && payload.entity_id === entityId) {
          clearTimeout(timer);
          unsubscribe();
          resolve(true);
        }
      });
    });
  }

  /**
   * Invoke an RPC method on a daemon over the shared connection (§2.8) — e.g.
   * `spawn-session`. Resolves with the daemon's result, or rejects with an
   * `RpcError` carrying the wire error code.
   */
  async callRpc(
    machineId: string,
    method: string,
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const transientRetain = this.retainCount === 0;
    if (transientRetain) this.retain();
    try {
      await this.waitUntilConnected();
      const frame = await this.sendFetch(
        'rpc-call',
        { machine_id: machineId, method, params },
        RPC_REQUEST_TIMEOUT_MS,
      );
      if (frame.type === 'rpc-error') {
        throw new RpcError(String(frame.code ?? 'rpc_failed'));
      }
      return (frame.result as Record<string, unknown>) ?? {};
    } catch (err) {
      if (err instanceof RpcError) throw err;
      if (err instanceof Error && err.message === 'rpc-call timed out') {
        throw new RpcError('timeout');
      }
      throw new RpcError('not_connected');
    } finally {
      if (transientRetain) this.release();
    }
  }

  /**
   * Fire-and-forget RPC: send the `rpc-call` frame and return immediately,
   * WITHOUT awaiting the daemon's `rpc-result`. For high-rate, order-sensitive
   * input (`pty-write`/`pty-resize`) where awaiting a full relay round-trip per
   * call would serialize typing at one keystroke per RTT.
   *
   * Ordering is preserved by the socket — frames are sent in call order — and
   * the daemon applies pty input in receive order (a single ordered worker), so
   * pipelining can't reorder keystrokes. Best-effort: if the socket isn't OPEN
   * the frame is dropped, which is correct for a terminal (it's lossy across a
   * reconnect, which re-spawns a fresh shell anyway). Unlike `callRpc` this
   * registers no pending request; the daemon still answers (so the relay's
   * pending map doesn't grow), and that `rpc-result` is simply ignored.
   */
  sendRpc(machineId: string, method: string, params: Record<string, unknown>): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const requestId = `r${(this.requestSeq += 1)}`;
    socket.send(
      JSON.stringify({
        type: 'rpc-call',
        request_id: requestId,
        machine_id: machineId,
        method,
        params,
      }),
    );
  }

  /**
   * Report the app window's foreground/blur state to the server (desktop app
   * only). The server keeps the most recent value per connection and suppresses
   * the FCM phone push while it is `true`, so the phone stays quiet while the
   * user is looking at the desktop app. Fire-and-forget: dropped if the socket
   * isn't OPEN, but the value is remembered and re-asserted on the next connect.
   */
  sendPresence(foreground: boolean): void {
    this.lastPresence = foreground;
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: 'presence', foreground }));
  }

  /**
   * Retain the connection WITHOUT subscribing to updates. Used by the desktop
   * foreground reporter so `presence` frames keep the socket alive (and thus
   * phone-push suppression working) even when no other subscriber is mounted.
   * Returns an idempotent release function.
   */
  retainConnection(): () => void {
    this.retain();
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.release();
    };
  }

  private retain(): void {
    this.retainCount += 1;
    if (this.idleCloseTimer) {
      clearTimeout(this.idleCloseTimer);
      this.idleCloseTimer = null;
    }
    if (this.retainCount === 1) this.connect();
  }

  private release(): void {
    this.retainCount = Math.max(0, this.retainCount - 1);
    if (this.retainCount === 0 && !this.idleCloseTimer) {
      this.idleCloseTimer = setTimeout(() => {
        this.idleCloseTimer = null;
        if (this.retainCount === 0) this.teardown();
      }, IDLE_CLOSE_GRACE_MS);
    }
  }

  private async connect(): Promise<void> {
    if (typeof window === 'undefined') return;
    if (this.socket || this.retainCount === 0) return;

    let authProtocol: string;
    if (this.auth.kind === 'local') {
      // Desktop local socket: static nonce, no session read, no refresh.
      authProtocol = `vicoa-local.${this.auth.token}`;
    } else {
      const token = await this.readSupabaseToken();
      // Retainer may have left, or another connect() already ran, while awaiting.
      if (this.socket || this.retainCount === 0 || this.destroyed) return;
      if (!token) {
        this.scheduleReconnect();
        return;
      }
      authProtocol = `vicoa-supabase.${token}`;
    }

    const socket = new WebSocket(this.url, ['vicoa-ws', authProtocol]);
    this.socket = socket;

    socket.onopen = () => {
      const helloFrame: Record<string, unknown> = { type: 'hello', scope: this.hello.scope };
      if (this.hello.machineId) helloFrame.machine_id = this.hello.machineId;
      socket.send(JSON.stringify(helloFrame));
      this.resetLivenessTimer();
    };
    socket.onmessage = (event) => {
      this.resetLivenessTimer();
      this.handleFrame(event.data);
    };
    socket.onclose = () => this.handleSocketDown(socket);
    socket.onerror = () => this.handleSocketDown(socket);
  }

  /** Read the user's access token for the handshake (cloud auth only). */
  private async readSupabaseToken(): Promise<string | null> {
    // The built-in provider has no refresh flow — the cookie either holds an
    // unexpired token or the user has to sign in again — so none of the
    // Supabase expiry dance below applies.
    if (isBuiltinAuth()) {
      return getBuiltinToken();
    }
    try {
      const supabase = createClient();
      const { data: sessionData } = await supabase.auth.getSession();
      let session = sessionData.session;
      // Proactive expiry guard. supabase-js's auto-refresh is driven by an
      // in-process setTimeout that Chrome throttles in background tabs, so by
      // the time a reconnect fires (focus event, heartbeat-detected stale
      // socket, network blip) the cached access_token can already be expired.
      // The handshake then hits a 401 and the browser surfaces it only as
      // "WebSocket connection ... failed" at the `new WebSocket(...)` line.
      // Force a refresh anytime we're inside a 30 s margin of expiry.
      if (session) {
        const expiresAt = session.expires_at ?? 0;
        const nowSec = Math.floor(Date.now() / 1000);
        if (expiresAt - nowSec < 30) {
          try {
            const { data: refreshData } = await supabase.auth.refreshSession();
            if (refreshData.session) {
              session = refreshData.session;
            }
          } catch {
            // Best-effort; the upcoming handshake will fail and trigger a
            // normal reconnect cycle which retries the refresh.
          }
        }
      }
      return session?.access_token ?? null;
    } catch (err) {
      console.error('[ws] failed to read Supabase session:', err);
      return null;
    }
  }

  private handleFrame(raw: unknown): void {
    let frame: Record<string, unknown>;
    try {
      frame = JSON.parse(String(raw));
    } catch {
      console.error('[ws] dropped unparseable frame');
      return;
    }

    switch (frame.type) {
      case 'ping':
        this.socket?.send(JSON.stringify({ type: 'pong' }));
        return;
      case 'server_info':
        this.reconnectAttempt = 0;
        this.setConnected(true);
        return;
      case 'update':
        this.dispatchUpdate(frame.payload as UpdatePayload);
        return;
      case 'ephemeral':
        return;
      case 'pty-output': {
        // Local-only push frame: {pty_id, data(base64)} (desktop-app v1 wire
        // contract). Delivered as-is; the terminal transport decodes.
        const ptyId = typeof frame.pty_id === 'string' ? frame.pty_id : null;
        const data = typeof frame.data === 'string' ? frame.data : null;
        if (ptyId === null || data === null) return;
        for (const listener of this.ptyOutputListeners) {
          try {
            listener(ptyId, data);
          } catch (err) {
            console.error('[ws] pty-output listener threw:', err);
          }
        }
        return;
      }
      case 'pty-exit': {
        // Local-only push frame: {pty_id, exit_code(int|null)}.
        const ptyId = typeof frame.pty_id === 'string' ? frame.pty_id : null;
        if (ptyId === null) return;
        const exitCode = typeof frame.exit_code === 'number' ? frame.exit_code : null;
        for (const listener of this.ptyExitListeners) {
          try {
            listener(ptyId, exitCode);
          } catch (err) {
            console.error('[ws] pty-exit listener threw:', err);
          }
        }
        return;
      }
      case 'fetch_messages_response':
      case 'fetch_instances_response':
      case 'fetch_machines_response':
      case 'resync_required':
      case 'rpc-result':
      case 'rpc-error': {
        const pending = this.pendingFetches.get(String(frame.request_id));
        if (pending) {
          clearTimeout(pending.timer);
          this.pendingFetches.delete(String(frame.request_id));
          pending.resolve(frame);
        }
        return;
      }
      default:
        return;
    }
  }

  private dispatchUpdate(payload: UpdatePayload | undefined): void {
    if (!payload || !payload.body) return;
    for (const listener of this.updateListeners) {
      try {
        listener(payload);
      } catch (err) {
        console.error('[ws] update listener threw:', err);
      }
    }
  }

  private sendFetch(
    type: string,
    fields: Record<string, unknown>,
    timeoutMs: number = FETCH_REQUEST_TIMEOUT_MS,
  ): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        reject(new Error('websocket not connected'));
        return;
      }
      const requestId = `r${(this.requestSeq += 1)}`;
      const timer = setTimeout(() => {
        const entry = this.pendingFetches.get(requestId);
        if (!entry) return;
        this.pendingFetches.delete(requestId);
        entry.reject(new Error(`${type} timed out`));
      }, timeoutMs);
      this.pendingFetches.set(requestId, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ type, request_id: requestId, ...fields }));
    });
  }

  private setConnected(value: boolean): void {
    if (this.connected === value) return;
    this.connected = value;
    if (value) {
      this.resolveConnectedWaiters();
      // Re-assert foreground state: the fresh server-side connection defaults to
      // backgrounded, so without this a reconnect while focused would wrongly
      // let a phone push through.
      if (this.lastPresence !== null && this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(
          JSON.stringify({ type: 'presence', foreground: this.lastPresence }),
        );
      }
    }
    for (const listener of this.connectionListeners) {
      try {
        listener(value);
      } catch (err) {
        console.error('[ws] connection listener threw:', err);
      }
    }
  }

  private waitUntilConnected(timeoutMs = 10_000): Promise<void> {
    if (this.connected) return Promise.resolve();
    if (!this.socket && this.retainCount > 0) void this.connect();
    return new Promise((resolve, reject) => {
      const waiter: ConnectedWaiter = {
        resolve,
        reject,
        timer: setTimeout(() => {
          this.connectedWaiters.delete(waiter);
          reject(new Error('websocket connection timed out'));
        }, timeoutMs),
      };
      this.connectedWaiters.add(waiter);
    });
  }

  private resolveConnectedWaiters(): void {
    for (const waiter of this.connectedWaiters) {
      clearTimeout(waiter.timer);
      waiter.resolve();
    }
    this.connectedWaiters.clear();
  }

  private rejectConnectedWaiters(err: Error): void {
    for (const waiter of this.connectedWaiters) {
      clearTimeout(waiter.timer);
      waiter.reject(err);
    }
    this.connectedWaiters.clear();
  }

  private handleSocketDown(socket: WebSocket): void {
    if (socket !== this.socket) return;
    this.socket = null;
    this.setConnected(false);
    this.rejectPendingFetches();
    this.rejectConnectedWaiters(new Error('websocket disconnected'));
    this.clearLivenessTimer();
    if (!this.destroyed && this.retainCount > 0) this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = reconnectDelayMs(this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, delay);
  }

  private resetLivenessTimer(): void {
    this.lastFrameAt = Date.now();
    this.clearLivenessTimer();
    this.livenessTimer = setTimeout(() => {
      // Stale socket the browser has not closed — drop it to trigger reconnect.
      this.socket?.close();
    }, LIVENESS_TIMEOUT_MS);
  }

  private clearLivenessTimer(): void {
    if (this.livenessTimer) {
      clearTimeout(this.livenessTimer);
      this.livenessTimer = null;
    }
  }

  /**
   * Subscribes to visibilitychange / focus / online so the next time the user
   * comes back we can shake the socket awake. Background tabs throttle our
   * 70 s liveness timer to the point it may never fire on schedule — without
   * this, a socket that died during sleep/NAT-timeout/network handoff stays
   * "connected" in our view, but no frames arrive until a page refresh.
   */
  private installResumeHooks(): void {
    if (this.resumeHooksInstalled) return;
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    this.resumeHooksInstalled = true;
    document.addEventListener('visibilitychange', this.handleVisibilityChange);
    window.addEventListener('focus', this.handleResume);
    window.addEventListener('online', this.handleResume);
  }

  private handleVisibilityChange = (): void => {
    if (document.visibilityState === 'visible') {
      this.handleResume();
    }
  };

  /**
   * Called from focus / online / visibility-to-visible. If we have no socket
   * (or one is scheduled but throttled), expedite the reconnect — skip the
   * backoff because a user-triggered resume is a strong signal we want
   * realtime data now. If we have a socket but it has gone quiet past
   * RESUME_STALE_THRESHOLD_MS, it's a zombie; close it so handleSocketDown
   * runs the normal reconnect path.
   */
  private handleResume = (): void => {
    if (this.destroyed || this.retainCount === 0) return;
    if (!this.socket) {
      this.reconnectAttempt = 0;
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      void this.connect();
      return;
    }
    this.recoverIfStale('resume');
  };

  /**
   * Shared zombie check used by both the focus/visibility/online hooks above
   * and the periodic heartbeat below. Only an OPEN socket is a candidate:
   *   - CONNECTING hasn't had a chance to receive its first frame yet, and
   *     lastFrameAt is still 0 from class init — closing here would put us
   *     in a reconnect loop where every wake aborts the handshake.
   *   - CLOSING/CLOSED is already in handleSocketDown's reconnect path.
   */
  private recoverIfStale(_source: 'resume' | 'heartbeat'): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    const sinceLastFrame = Date.now() - this.lastFrameAt;
    if (sinceLastFrame > RESUME_STALE_THRESHOLD_MS) {
      this.reconnectAttempt = 0;
      try {
        this.socket.close();
      } catch {
        // Best-effort; handleSocketDown will run on the next event-loop tick.
      }
    }
  }

  /**
   * Mirror the Supabase JWT lifecycle into the WS connection — matches what
   * vicoa-app's VicoaWsClient does in `_handleAuthChange`. Without this, the
   * socket connects once with the current access token and then drifts: the
   * server doesn't re-validate JWTs mid-session, so the connection itself
   * keeps working, but any reconnect (heartbeat, sleep/wake, network blip)
   * reads back whatever getSession() returns, which can be a now-stale token
   * if Supabase's refresh and our reconnect race. The handshake gets a 401,
   * we back off, retry with the same stale read, and the page looks
   * permanently disconnected until the user hard-refreshes.
   *
   * Reacting to TOKEN_REFRESHED / SIGNED_IN by force-closing means the next
   * reconnect always reads the freshly-stored JWT. SIGNED_OUT tears down the
   * socket since there's no authenticated user to scope to.
   */
  private installAuthHook(): void {
    if (this.authHooksInstalled) return;
    if (typeof window === 'undefined') return;
    // Nothing to subscribe to under the built-in provider: its tokens are not
    // refreshed in the background, so there is no event to react to.
    if (isBuiltinAuth()) return;
    this.authHooksInstalled = true;
    try {
      const supabase = createClient();
      const { data } = supabase.auth.onAuthStateChange((event) => {
        if (event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') {
          if (this.destroyed || this.retainCount === 0) return;
          // Only act on a connected socket — a pending connect() will read
          // the same fresh token from the next getSession(), so re-firing
          // here would just thrash the in-flight handshake.
          if (!this.socket || !this.connected) return;
          this.reconnectAttempt = 0;
          try {
            this.socket.close();
          } catch {
            // Best-effort; handleSocketDown runs on the next event-loop tick.
          }
        } else if (event === 'SIGNED_OUT') {
          if (this.socket) {
            try {
              this.socket.close();
            } catch {
              // Best-effort.
            }
          }
        }
      });
      this.authSubscription = data.subscription;
    } catch (err) {
      console.error('[ws] failed to subscribe to Supabase auth state:', err);
    }
  }

  /**
   * Backstop for the setTimeout-based liveness timer above. Chrome's
   * intensive throttling stretches setTimeout to 1+ min in idle foreground
   * tabs after 5 min of no input, so a half-open TCP — server stopped
   * sending, OS hasn't noticed — can stay "connected" indefinitely with no
   * frames arriving. setInterval is throttled too, but it still fires
   * periodically, and combined with the staleness check we catch silent
   * deaths within ~30-90 s of the last real frame even when the user never
   * switches tabs.
   */
  private startHeartbeatCheck(): void {
    if (typeof window === 'undefined') return;
    if (this.heartbeatInterval) return;
    this.heartbeatInterval = setInterval(() => {
      if (this.destroyed || this.retainCount === 0) return;
      this.recoverIfStale('heartbeat');
    }, 30_000);
  }

  private rejectPendingFetches(): void {
    for (const pending of this.pendingFetches.values()) {
      clearTimeout(pending.timer);
      pending.reject(new Error('websocket disconnected'));
    }
    this.pendingFetches.clear();
  }

  private teardown(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearLivenessTimer();
    this.reconnectAttempt = 0;
    this.rejectPendingFetches();
    this.rejectConnectedWaiters(new Error('websocket closed'));
    const socket = this.socket;
    this.socket = null;
    this.setConnected(false);
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
  }
}

let sharedClient: WsClient | null = null;
let localRpcClient: WsClient | null = null;
// One dedicated terminal-scoped cloud connection per remote machine. Keeping
// pty traffic off the shared user-scoped socket means a chatty terminal's
// backpressure sheds only its own connection, never the app's realtime stream.
const terminalRpcClients = new Map<string, WsClient>();

/**
 * The process-wide shared WebSocket client (one connection per browser tab).
 * Carries the user-scoped update stream:
 * - plain web / desktop-cloud → the cloud WS (`WS_URL`) with Supabase auth,
 *   exactly as before;
 * - desktop-local → the daemon's local socket with the `vicoa-local.<nonce>`
 *   subprotocol (there is no Supabase session in logged-out desktop mode).
 */
export function getWsClient(): WsClient {
  if (!sharedClient) {
    const desktop = getDesktopConfig();
    sharedClient =
      desktop && desktop.mode === 'local'
        ? new WsClient({
            url: desktop.wsUrl,
            auth: { kind: 'local', token: desktop.token },
          })
        : new WsClient({ url: wsUrl(), auth: { kind: 'supabase' } });
  }
  return sharedClient;
}

/**
 * The client that RPC (files/git/spawn) and pty traffic for `machineId` should
 * use.
 * - plain web → `getWsClient()` (RPC rides the cloud socket, as today);
 * - desktop-local → `getWsClient()` too, since the main client already IS the
 *   local socket (all traffic local);
 * - desktop-cloud → route by machine. RPC/pty for THIS machine goes straight to
 *   the daemon's local socket (no relay hop); anything for ANOTHER machine must
 *   ride the cloud relay — the local daemon only serves itself, so sending a
 *   foreign machine's calls there would just fail. The relay dispatches by the
 *   `machine_id` in each frame.
 *
 * `machineId` omitted, or this machine's id not yet known (daemon still
 * booting / cloud registration not finished), falls back to the cloud relay:
 * it reaches every machine including this one, so it is always the safe
 * default — just one extra hop until the id cache warms.
 */
export function getRpcClient(machineId?: string): WsClient {
  const desktop = getDesktopConfig();
  if (!desktop || desktop.mode === 'local') return getWsClient();

  const localId = getLocalMachineId();
  if (!machineId || !localId || machineId !== localId) {
    // Another machine, unknown target, or we don't yet know who we are — the
    // cloud relay handles all of these. Warm the id cache so the next call to
    // this machine can take the direct local path.
    if (!localId) void ensureLocalMachineId();
    return getWsClient();
  }

  // This machine → the daemon's local socket directly.
  if (!localRpcClient) {
    localRpcClient = new WsClient({
      url: desktop.wsUrl,
      auth: { kind: 'local', token: desktop.token },
    });
  }
  return localRpcClient;
}

/**
 * The client a TERMINAL for `machineId` should use. Terminals stream
 * high-volume output, so unlike `getRpcClient` (request/response, fine on the
 * shared socket) a remote machine gets its OWN terminal-scoped connection,
 * subscribed to that machine's `pty-output` room:
 * - desktop-local → `getWsClient()` (the one local socket carries everything);
 * - desktop-cloud, THIS machine → the daemon's local 127.0.0.1 socket, exactly
 *   as today — the local terminal never touches the relay;
 * - desktop-cloud ANOTHER machine, OR plain web (where every machine is remote)
 *   → a dedicated per-machine terminal-scoped cloud connection. It MUST be this
 *   connection, not the user-scoped socket: the relay fans `pty-output` only to
 *   the `…:terminals` room, so the shared socket would spawn but see no output.
 */
export function getTerminalRpcClient(machineId?: string): WsClient {
  const desktop = getDesktopConfig();
  // Desktop-local: the single local socket already serves this machine's ptys.
  if (desktop?.mode === 'local') return getWsClient();

  // Desktop-cloud, THIS machine → the direct 127.0.0.1 socket (unchanged).
  if (desktop) {
    const localId = getLocalMachineId();
    if (machineId && localId && machineId === localId) return getRpcClient(machineId);
    if (!localId) void ensureLocalMachineId();
  }

  if (!machineId) return getWsClient(); // unknown target — best effort
  let client = terminalRpcClients.get(machineId);
  if (!client) {
    client = new WsClient({
      url: wsUrl(),
      auth: { kind: 'supabase' },
      hello: { scope: 'terminal-scoped', machineId },
    });
    terminalRpcClients.set(machineId, client);
  }
  return client;
}

export type { WsClient };
