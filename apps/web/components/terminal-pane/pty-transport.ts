// Terminal pane patterns adapted from Orca (https://github.com/stablyai/orca),
// MIT License, Copyright (c) 2026 Lovecast Inc.
//
// PtyTransport: the seam between the xterm React component and the local
// daemon's PTY RPC surface (desktop-app-v1 wire contract). The ws-client layer
// implements PtyRpc; this module owns ordering, base64 framing, and the
// spawn-race buffer.

import { base64ToBytes, utf8ToBase64 } from './base64';

/** Implemented by the ws-client layer (local daemon socket). */
export interface PtyRpc {
  callRpc(method: string, params: Record<string, unknown>): Promise<unknown>;
  /** Fire-and-forget send for order-sensitive, high-rate input
   *  (`pty-write`/`pty-resize`): sends in call order without awaiting the ack,
   *  so fast typing isn't serialized at one keystroke per relay round-trip. The
   *  daemon applies pty input in receive order, so pipelining stays ordered. */
  sendRpc(method: string, params: Record<string, unknown>): void;
  /** Push frames: `{"type":"pty-output","pty_id":str,"data":str(base64)}`. Returns unsubscribe. */
  onPtyOutput(cb: (ptyId: string, dataBase64: string) => void): () => void;
  /** Push frames: `{"type":"pty-exit","pty_id":str,"exit_code":int|null}`. Returns unsubscribe. */
  onPtyExit(cb: (ptyId: string, exitCode: number | null) => void): () => void;
}

export interface PtySpawnOptions {
  cwd: string;
  cols: number;
  rows: number;
  command?: string[];
}

export interface PtyTransport {
  /** `pty-spawn {cwd, cols, rows, command?}` -> pty_id. Callable again after exit (restart). */
  spawn(opts: PtySpawnOptions): Promise<string>;
  /** UTF-8 -> base64 -> `pty-write`. Fire and forget, but order-preserving. */
  write(data: string): void;
  /** `pty-resize {pty_id, cols, rows}`. Fire and forget, order-preserving. */
  resize(cols: number, rows: number): void;
  /** `pty-kill`, unsubscribes push handlers. Idempotent; never rejects. */
  kill(): Promise<void>;
  onData(cb: (data: Uint8Array) => void): () => void;
  onExit(cb: (exitCode: number | null) => void): () => void;
  readonly ptyId: string | null;
}

// Push frames can outrun the pty-spawn rpc-result on the socket, so frames
// seen while a spawn is in flight are buffered per pty_id and flushed once we
// learn our id. Frames for other panes' ptys land here too; the cap bounds it.
const MAX_EARLY_CHUNKS_PER_PTY = 512;

// Lease heartbeat: the daemon reaps a leased pty whose lease goes stale, which
// is how an orphaned remote shell (browser reloaded/crashed without sending
// pty-kill) gets cleaned up instead of leaking toward the 16-session cap. We
// opt in on spawn (`lease_secs`) and renew every HEARTBEAT_INTERVAL_MS.
//
// The lease TTL must comfortably EXCEED the worst-case interruption of the
// realtime path, or the reaper kills terminals we still want open:
//   - a backgrounded tab / asleep laptop throttles this setInterval to ~1/min
//     or slower (Chrome/Electron), far below the 15s cadence;
//   - a daemon↔server half-open takes up to the daemon's 70s recv-timeout to
//     notice, plus up to 30s reconnect backoff, before any renewal can land.
// The old 60s TTL was SHORTER than those windows, so an ordinary tab-switch or
// reconnect reaped the live shell (its running command included) and the pane
// froze. 300s clears them with margin; `installResumeListeners` below also
// renews the instant the tab is foregrounded, so a throttled interval is never
// the only thing between a live terminal and the reaper. Bounded orphan cleanup
// is preserved: a genuinely-dead browser's shell is still reaped within the TTL.
const HEARTBEAT_LEASE_SECONDS = 300;
const HEARTBEAT_INTERVAL_MS = 15_000;

export interface PtyTransportOptions {
  /** Lease-renewal period. 0 disables heartbeating (and lease opt-in) — used by
   *  tests so they don't leave a live timer. Defaults to HEARTBEAT_INTERVAL_MS. */
  heartbeatIntervalMs?: number;
}

export function createRpcPtyTransport(
  rpc: PtyRpc,
  options: PtyTransportOptions = {},
): PtyTransport {
  const heartbeatIntervalMs = options.heartbeatIntervalMs ?? HEARTBEAT_INTERVAL_MS;
  const leaseEnabled = heartbeatIntervalMs > 0;
  // Set from the pty-spawn result: true only when the daemon advertised that it
  // applies pty input in receive order (`ordered_input`). Gates fire-and-forget
  // pipelining, so a daemon predating the ordered path keeps the safe awaited
  // path (one write in flight) and can't reorder keystrokes. Known before any
  // write runs — writes queue behind spawn on the send chain.
  let orderedInput = false;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  // Removes the visibility/focus/online listeners installed while heartbeating;
  // null when none are installed (SSR/tests, or between spawns).
  let resumeCleanup: (() => void) | null = null;
  let ptyId: string | null = null;
  let spawnInFlight = false;
  let exited = false;
  let closed = false;
  /** Orders pty-write / pty-resize / pty-kill so wire order matches call order.
   *  Writes/resizes are fire-and-forget (sent, not awaited), so the chain only
   *  sequences the sends — it never blocks a keystroke on the prior one's ack.
   *  kill still awaits, and runs last, so the daemon sees pending input first. */
  let sendChain: Promise<void> = Promise.resolve();

  const dataListeners = new Set<(data: Uint8Array) => void>();
  const exitListeners = new Set<(exitCode: number | null) => void>();

  let rpcUnsubs: Array<() => void> | null = null;
  let earlyOutput: Map<string, string[]> | null = null;
  let earlyExits: Map<string, number | null> | null = null;

  const emitData = (dataBase64: string): void => {
    let bytes: Uint8Array;
    try {
      bytes = base64ToBytes(dataBase64);
    } catch {
      return; // corrupt frame; drop rather than kill the pane
    }
    for (const cb of dataListeners) cb(bytes);
  };

  const emitExit = (exitCode: number | null): void => {
    exited = true;
    stopHeartbeat();
    for (const cb of exitListeners) cb(exitCode);
  };

  const stopHeartbeat = (): void => {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    removeResumeListeners();
  };

  // Renew the lease once, now. Shared by the interval and the resume listeners.
  const sendHeartbeat = (): void => {
    const id = ptyId;
    if (id === null || exited || closed) return;
    void Promise.resolve(
      rpc.callRpc('pty-heartbeat', {
        pty_ids: [id],
        lease_secs: HEARTBEAT_LEASE_SECONDS,
      }),
    )
      .then((result) => {
        // The daemon echoes `renewed` — the leased ids it still holds. If ours
        // is absent the pty is gone: reaped as a stale lease, or the shell
        // exited while our output socket was down so we missed its `pty-exit`
        // frame. Either way, surface an exit so the pane shows Restart instead
        // of freezing silently. Only a well-formed `renewed` array is
        // authoritative — a daemon too old to know pty-heartbeat answers an
        // error with no `renewed`, and its ptys simply aren't leased (legacy
        // path), so silence there means alive. Re-check the guards: a
        // respawn/kill/exit may have landed while this reply was in flight.
        if (closed || exited || ptyId !== id) return;
        const renewed = (result as { renewed?: unknown } | null)?.renewed;
        if (Array.isArray(renewed) && !renewed.includes(id)) {
          emitExit(null);
        }
      })
      .catch(() => undefined); // transient disconnect: the pty may still live
  };

  // A backgrounded tab throttles the renewal interval well below the lease TTL,
  // so renew the instant the tab/window is foregrounded again (mirrors the
  // socket resume hooks in ws-client). DOM-guarded so the transport still runs
  // headless in SSR / node tests, where there is nothing to resume from.
  const installResumeListeners = (): void => {
    if (resumeCleanup !== null) return;
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    const onResume = (): void => {
      // visibilitychange fires on hide too; only renew when actually visible.
      if (document.visibilityState === 'hidden') return;
      sendHeartbeat();
    };
    document.addEventListener('visibilitychange', onResume);
    window.addEventListener('focus', onResume);
    window.addEventListener('online', onResume);
    resumeCleanup = () => {
      document.removeEventListener('visibilitychange', onResume);
      window.removeEventListener('focus', onResume);
      window.removeEventListener('online', onResume);
    };
  };

  const removeResumeListeners = (): void => {
    if (resumeCleanup !== null) {
      resumeCleanup();
      resumeCleanup = null;
    }
  };

  const startHeartbeat = (): void => {
    if (!leaseEnabled) return;
    stopHeartbeat();
    heartbeatTimer = setInterval(sendHeartbeat, heartbeatIntervalMs);
    installResumeListeners();
  };

  const handleOutput = (id: string, dataBase64: string): void => {
    if (id === ptyId) {
      emitData(dataBase64);
    } else if (spawnInFlight && earlyOutput) {
      const chunks = earlyOutput.get(id) ?? [];
      if (chunks.length < MAX_EARLY_CHUNKS_PER_PTY) {
        chunks.push(dataBase64);
        earlyOutput.set(id, chunks);
      }
    }
  };

  const handleExit = (id: string, exitCode: number | null): void => {
    if (id === ptyId) {
      emitExit(exitCode);
    } else if (spawnInFlight && earlyExits) {
      earlyExits.set(id, exitCode);
    }
  };

  /** Append a task to the ordered send chain. The chain never rejects; each
   *  task's failure is swallowed (fire-and-forget semantics). */
  const enqueue = (task: () => unknown): Promise<void> => {
    const next = sendChain.then(task).then(
      () => undefined,
      () => undefined,
    );
    sendChain = next;
    return next;
  };

  const spawn = async (opts: PtySpawnOptions): Promise<string> => {
    if (closed) throw new Error('PtyTransport is closed');
    if (spawnInFlight) throw new Error('pty spawn already in progress');
    if (ptyId !== null && !exited) throw new Error('pty already running');

    if (!rpcUnsubs) {
      rpcUnsubs = [rpc.onPtyOutput(handleOutput), rpc.onPtyExit(handleExit)];
    }
    spawnInFlight = true;
    exited = false;
    ptyId = null;
    earlyOutput = new Map();
    earlyExits = new Map();

    const params: Record<string, unknown> = {
      cwd: opts.cwd,
      cols: opts.cols,
      rows: opts.rows,
    };
    if (opts.command !== undefined) params.command = opts.command;
    // Opt into lease-reaping only when we'll actually heartbeat, so a leased
    // pty is never left unrenewed (which would get it reaped mid-use).
    if (leaseEnabled) params.lease_secs = HEARTBEAT_LEASE_SECONDS;

    const spawnPromise = (async () => {
      const result = (await rpc.callRpc('pty-spawn', params)) as
        | { pty_id?: unknown; ordered_input?: unknown }
        | null
        | undefined;
      const id = result && typeof result.pty_id === 'string' ? result.pty_id : null;
      if (!id) throw new Error('pty-spawn returned no pty_id');
      // Only pipeline input if this daemon guarantees ordered pty input.
      orderedInput = result?.ordered_input === true;
      // Set the id and flush the race buffer synchronously, before any queued
      // write task (gated on this same promise) or live push frame runs.
      ptyId = id;
      const chunks = earlyOutput?.get(id);
      const hadEarlyExit = earlyExits?.has(id) ?? false;
      const earlyExitCode = hadEarlyExit ? (earlyExits?.get(id) ?? null) : null;
      spawnInFlight = false;
      earlyOutput = null;
      earlyExits = null;
      if (chunks) for (const chunk of chunks) emitData(chunk);
      if (hadEarlyExit) emitExit(earlyExitCode);
      // Renew the lease from here on; skip if the shell already exited on spawn.
      if (!exited) startHeartbeat();
      return id;
    })();

    // Writes/resizes issued before spawn resolves stay queued behind it.
    sendChain = sendChain
      .then(() => spawnPromise)
      .then(
        () => undefined,
        () => undefined,
      );

    try {
      return await spawnPromise;
    } catch (err) {
      spawnInFlight = false;
      earlyOutput = null;
      earlyExits = null;
      throw err;
    }
  };

  const write = (data: string): void => {
    if (closed || exited || data.length === 0) return;
    const b64 = utf8ToBase64(data); // encode now so order == call order
    void enqueue(() => {
      if (ptyId === null || exited) return;
      // Fire-and-forget when the daemon guarantees ordered input: don't await
      // the round-trip ack, so the next keystroke isn't gated on this one's
      // relay round-trip. Order holds via the send chain (this runs after prior
      // writes) + the daemon's ordered pty-input worker. Otherwise fall back to
      // the awaited path (one write in flight), safe against an older daemon's
      // parallel RPC pool.
      if (orderedInput) {
        rpc.sendRpc('pty-write', { pty_id: ptyId, data: b64 });
        return;
      }
      return rpc.callRpc('pty-write', { pty_id: ptyId, data: b64 });
    });
  };

  const resize = (cols: number, rows: number): void => {
    if (closed || exited) return;
    if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols <= 0 || rows <= 0) return;
    void enqueue(() => {
      if (ptyId === null || exited) return;
      if (orderedInput) {
        rpc.sendRpc('pty-resize', { pty_id: ptyId, cols, rows });
        return;
      }
      return rpc.callRpc('pty-resize', { pty_id: ptyId, cols, rows });
    });
  };

  const kill = async (): Promise<void> => {
    if (closed) return;
    closed = true;
    stopHeartbeat();
    const unsubs = rpcUnsubs;
    rpcUnsubs = null;
    if (unsubs) {
      for (const unsub of unsubs) {
        try {
          unsub();
        } catch {
          /* ignore */
        }
      }
    }
    // Read ptyId INSIDE the queued task, not now: the send chain runs it after
    // any in-flight pty-spawn resolves, so a kill issued while spawn is still
    // in flight (e.g. React StrictMode's mount → unmount → mount in dev) still
    // reaps the pty instead of orphaning it on the daemon. Also queues behind
    // pending writes so the daemon sees them before the kill.
    await enqueue(() => {
      const id = ptyId;
      return id !== null && !exited
        ? rpc.callRpc('pty-kill', { pty_id: id })
        : Promise.resolve();
    });
  };

  return {
    spawn,
    write,
    resize,
    kill,
    onData(cb) {
      dataListeners.add(cb);
      return () => dataListeners.delete(cb);
    },
    onExit(cb) {
      exitListeners.add(cb);
      return () => exitListeners.delete(cb);
    },
    get ptyId() {
      return ptyId;
    },
  };
}
