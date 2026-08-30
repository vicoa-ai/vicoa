import { describe, test, expect, vi } from 'vitest';
import { createRpcPtyTransport, type PtyRpc } from './pty-transport';

// Most tests exercise ordering/lifecycle, not leasing — construct with
// heartbeating off so they neither send `lease_secs` nor leave a live timer.
const noHeartbeat = { heartbeatIntervalMs: 0 } as const;

type Call = { method: string; params: Record<string, unknown> };

/** Fake PtyRpc that records calls and lets tests drive push frames.
 *  `orderedInput: false` simulates a daemon that predates the ordered-input
 *  path — its pty-spawn omits the `ordered_input` flag, so the transport keeps
 *  the awaited (non-pipelined) write path. */
function fakeRpc(opts?: {
  spawnDelay?: boolean;
  orderedInput?: boolean;
  // Simulate a daemon that no longer holds the pty: pty-heartbeat replies with
  // an empty `renewed`, the signal the transport uses to recover a reaped pane.
  reapOnHeartbeat?: boolean;
}) {
  const calls: Call[] = []; // every request in order (awaited callRpc + fire-and-forget sendRpc)
  const sent: Call[] = []; // fire-and-forget sends only (pty-write / pty-resize)
  let outputCb: ((ptyId: string, dataBase64: string) => void) | null = null;
  let exitCb: ((ptyId: string, exitCode: number | null) => void) | null = null;
  let resolveSpawn: (() => void) | null = null;

  const rpc: PtyRpc = {
    async callRpc(method, params) {
      calls.push({ method, params });
      if (method === 'pty-spawn') {
        if (opts?.spawnDelay) {
          await new Promise<void>((resolve) => {
            resolveSpawn = resolve;
          });
        }
        return opts?.orderedInput === false
          ? { pty_id: 'pty-1' } // old daemon: no ordered_input flag
          : { pty_id: 'pty-1', ordered_input: true };
      }
      if (method === 'pty-heartbeat') {
        // Real daemons echo the ids they still hold; an empty list means ours
        // was reaped/gone. Absent `renewed` (the default) models a legacy
        // daemon and must be treated as alive.
        return opts?.reapOnHeartbeat ? { renewed: [] } : { renewed: ['pty-1'] };
      }
      return {};
    },
    sendRpc(method, params) {
      calls.push({ method, params });
      sent.push({ method, params });
    },
    onPtyOutput(cb) {
      outputCb = cb;
      return () => {
        outputCb = null;
      };
    },
    onPtyExit(cb) {
      exitCb = cb;
      return () => {
        exitCb = null;
      };
    },
  };
  return {
    rpc,
    calls,
    sent,
    pushOutput: (id: string, b64: string) => outputCb?.(id, b64),
    pushExit: (id: string, code: number | null) => exitCb?.(id, code),
    releaseSpawn: () => resolveSpawn?.(),
    isSubscribed: () => outputCb !== null,
  };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('createRpcPtyTransport', () => {
  test('spawn sends the wire params and exposes ptyId', async () => {
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    const id = await t.spawn({ cwd: '/repo', cols: 120, rows: 32 });
    expect(id).toBe('pty-1');
    expect(t.ptyId).toBe('pty-1');
    expect(f.calls[0]).toEqual({
      method: 'pty-spawn',
      params: { cwd: '/repo', cols: 120, rows: 32 },
    });
  });

  test('writes issued before spawn resolves flush after it, in order', async () => {
    const f = fakeRpc({ spawnDelay: true });
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    const spawned = t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    t.write('a');
    t.write('b');
    await flush();
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn']);
    f.releaseSpawn();
    await spawned;
    await flush();
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn', 'pty-write', 'pty-write']);
    // 'a' then 'b', utf-8 -> base64, addressed to our pty.
    expect(f.calls[1].params).toEqual({ pty_id: 'pty-1', data: 'YQ==' });
    expect(f.calls[2].params).toEqual({ pty_id: 'pty-1', data: 'Yg==' });
  });

  test('input is fire-and-forget (write/resize sent, not awaited); spawn/kill stay awaited', async () => {
    // The whole point of the latency fix: keystrokes ride sendRpc, so the next
    // one isn't gated on the prior one's relay round-trip. spawn/kill still use
    // the awaited request/response RPC.
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    t.write('a');
    t.write('b');
    t.resize(100, 40);
    await flush();
    expect(f.sent.map((c) => c.method)).toEqual(['pty-write', 'pty-write', 'pty-resize']);
    // 'a' then 'b' preserved on the fire-and-forget path.
    expect(f.sent[0].params).toEqual({ pty_id: 'pty-1', data: 'YQ==' });
    expect(f.sent[1].params).toEqual({ pty_id: 'pty-1', data: 'Yg==' });
    await t.kill();
    // spawn and kill never take the fire-and-forget path.
    expect(f.sent.some((c) => c.method === 'pty-spawn' || c.method === 'pty-kill')).toBe(false);
  });

  test('old daemon (no ordered_input): input falls back to the awaited path', async () => {
    // Safety gate: against a daemon that predates the ordered pty-input worker,
    // pipelining could reorder keystrokes across its parallel RPC pool. Without
    // the spawn flag, writes/resizes stay on the awaited (one-in-flight) path.
    const f = fakeRpc({ orderedInput: false });
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    t.write('a');
    t.resize(100, 40);
    await flush();
    expect(f.sent).toEqual([]); // nothing rode the fire-and-forget path
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn', 'pty-write', 'pty-resize']);
  });

  test('output racing ahead of the spawn result is buffered then delivered', async () => {
    const f = fakeRpc({ spawnDelay: true });
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    const chunks: string[] = [];
    t.onData((bytes) => chunks.push(new TextDecoder().decode(bytes)));
    const spawned = t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    await flush();
    f.pushOutput('pty-1', Buffer.from('early', 'utf-8').toString('base64'));
    f.pushOutput('someone-elses-pty', Buffer.from('noise', 'utf-8').toString('base64'));
    f.releaseSpawn();
    await spawned;
    f.pushOutput('pty-1', Buffer.from(' late', 'utf-8').toString('base64'));
    expect(chunks).toEqual(['early', ' late']);
  });

  test('exit marks the transport dead: listeners fire, writes drop', async () => {
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    const exits: Array<number | null> = [];
    t.onExit((code) => exits.push(code));
    f.pushExit('pty-1', 137);
    expect(exits).toEqual([137]);
    t.write('into the void');
    t.resize(100, 40);
    await flush();
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn']);
  });

  test('kill sends pty-kill after pending writes, unsubscribes, and is idempotent', async () => {
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    t.write('bye');
    await t.kill();
    await t.kill();
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn', 'pty-write', 'pty-kill']);
    expect(f.isSubscribed()).toBe(false);
    await expect(t.spawn({ cwd: '/repo', cols: 80, rows: 24 })).rejects.toThrow(/closed/);
  });

  test('kill during an in-flight spawn still reaps the pty once it resolves', async () => {
    // React StrictMode (dev) mounts → unmounts → mounts: the unmount kills
    // while the first spawn's rpc is still in flight, so the id isn't known
    // yet. The kill must ride the send chain and reap the pty after spawn
    // resolves — otherwise it leaks on the daemon.
    const f = fakeRpc({ spawnDelay: true });
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    const spawnPromise = t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    const killPromise = t.kill(); // before the id is known
    f.releaseSpawn(); // pty-spawn now returns { pty_id: 'pty-1' }
    await spawnPromise.catch(() => undefined);
    await killPromise;
    expect(f.calls.map((c) => c.method)).toEqual(['pty-spawn', 'pty-kill']);
  });

  test('spawn is callable again after exit (restart path)', async () => {
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, noHeartbeat);
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    f.pushExit('pty-1', 0);
    await expect(t.spawn({ cwd: '/repo', cols: 80, rows: 24 })).resolves.toBe('pty-1');
    expect(f.calls.filter((c) => c.method === 'pty-spawn')).toHaveLength(2);
  });
});

describe('lease heartbeat', () => {
  const beats = (calls: Call[]) => calls.filter((c) => c.method === 'pty-heartbeat');

  test('spawn opts into a lease and then renews it on the interval', async () => {
    vi.useFakeTimers();
    try {
      const f = fakeRpc();
      const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 1000 });
      await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
      // The spawn itself carries the lease opt-in, and nothing renews yet.
      expect(f.calls[0]).toMatchObject({
        method: 'pty-spawn',
        params: { cwd: '/repo', lease_secs: 300 },
      });
      expect(beats(f.calls)).toHaveLength(0);
      await vi.advanceTimersByTimeAsync(2000);
      expect(beats(f.calls)).toHaveLength(2);
      expect(beats(f.calls)[0].params).toEqual({ pty_ids: ['pty-1'], lease_secs: 300 });
      await t.kill();
    } finally {
      vi.useRealTimers();
    }
  });

  test('kill stops the heartbeat', async () => {
    vi.useFakeTimers();
    try {
      const f = fakeRpc();
      const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 1000 });
      await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
      await vi.advanceTimersByTimeAsync(1000);
      await t.kill();
      const before = beats(f.calls).length;
      await vi.advanceTimersByTimeAsync(5000);
      expect(beats(f.calls).length).toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  test('exit stops the heartbeat (an exited pty is never renewed)', async () => {
    vi.useFakeTimers();
    try {
      const f = fakeRpc();
      const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 1000 });
      await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
      f.pushExit('pty-1', 0);
      await vi.advanceTimersByTimeAsync(5000);
      expect(beats(f.calls)).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });

  test('a heartbeat reply missing our pty surfaces an exit (reaped-pane recovery)', async () => {
    vi.useFakeTimers();
    try {
      const f = fakeRpc({ reapOnHeartbeat: true });
      const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 1000 });
      await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
      const exits: Array<number | null> = [];
      t.onExit((code) => exits.push(code));
      // The daemon's reply omits our id → it has reaped/lost the pty. The
      // transport must stop looking alive rather than freeze silently.
      await vi.advanceTimersByTimeAsync(1000);
      expect(exits).toEqual([null]);
      // Now dead: input drops and the heartbeat stops renewing.
      const beatsAtExit = beats(f.calls).length;
      t.write('into the void');
      await vi.advanceTimersByTimeAsync(5000);
      expect(f.sent).toEqual([]);
      expect(beats(f.calls).length).toBe(beatsAtExit);
    } finally {
      vi.useRealTimers();
    }
  });

  test('a heartbeat reply still holding our pty does not surface an exit', async () => {
    vi.useFakeTimers();
    try {
      const f = fakeRpc(); // default: renewed echoes ['pty-1']
      const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 1000 });
      await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
      const exits: Array<number | null> = [];
      t.onExit((code) => exits.push(code));
      await vi.advanceTimersByTimeAsync(3000);
      expect(beats(f.calls).length).toBeGreaterThan(0);
      expect(exits).toEqual([]);
      await t.kill();
    } finally {
      vi.useRealTimers();
    }
  });

  test('heartbeatIntervalMs: 0 disables leasing entirely', async () => {
    const f = fakeRpc();
    const t = createRpcPtyTransport(f.rpc, { heartbeatIntervalMs: 0 });
    await t.spawn({ cwd: '/repo', cols: 80, rows: 24 });
    expect(f.calls[0].params).not.toHaveProperty('lease_secs');
    await t.kill();
  });
});
