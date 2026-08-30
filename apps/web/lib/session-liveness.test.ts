import { describe, expect, it } from 'vitest';

import {
  LIVENESS_ONLINE_THRESHOLD_MS,
  LIVENESS_STALE_THRESHOLD_MS,
  LIVENESS_STARTUP_GRACE_MS,
  blocksSending,
  computeLiveState,
  liveStateHint,
  isHeartbeatFresh,
  isMachineOnline,
  isReachable,
  isResumable,
  resolveLiveState,
  type LiveState,
} from './session-liveness';

/**
 * Mirrors vicoa-backend/tests/test_session_liveness.py. The two derivations
 * must agree — a client that disagrees with the server about whether a session
 * is alive is worse than having no indicator at all.
 */

const NOW = new Date('2026-07-20T12:00:00Z').getTime();
const MACHINE = 'machine-1';

const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

const state = (
  overrides: {
    lastHeartbeatAt?: string | null;
    machineId?: string | null;
    machineLastHeartbeatAt?: string | null;
    status?: string | null;
    startedAt?: string | null;
  } = {}
): LiveState =>
  computeLiveState(
    {
      machineId: MACHINE,
      status: 'ACTIVE',
      // Default well past the startup grace so cases opt in to it explicitly.
      startedAt: ago(9999),
      ...overrides,
    },
    NOW
  );

describe('computeLiveState', () => {
  it('reports a fresh agent on a fresh machine as live', () => {
    expect(
      state({ lastHeartbeatAt: ago(10), machineLastHeartbeatAt: ago(10) })
    ).toBe('live');
  });

  it('does not mark an idle-but-healthy session as offline', () => {
    // The false-offline bug: headless sessions awaiting user input are idle by
    // definition, and must stay "live" while they're still heartbeating.
    expect(
      state({
        lastHeartbeatAt: ago(LIVENESS_ONLINE_THRESHOLD_MS / 1000 - 30),
        machineLastHeartbeatAt: ago(10),
      })
    ).toBe('live');
  });

  it('treats a briefly quiet agent as reconnecting rather than dead', () => {
    expect(
      state({
        lastHeartbeatAt: ago(LIVENESS_ONLINE_THRESHOLD_MS / 1000 + 30),
        machineLastHeartbeatAt: ago(10),
      })
    ).toBe('reconnecting');
  });

  it('reports a long-silent agent on a live machine as stopped', () => {
    expect(
      state({
        lastHeartbeatAt: ago(LIVENESS_STALE_THRESHOLD_MS / 1000 + 60),
        machineLastHeartbeatAt: ago(10),
      })
    ).toBe('agent_stopped');
  });

  it('reports an agent that never beat as stopped, not live', () => {
    // The zombie shape: status frozen at ACTIVE, nothing ever heartbeated.
    expect(
      state({
        lastHeartbeatAt: null,
        machineLastHeartbeatAt: ago(10),
        startedAt: ago(9999),
      })
    ).toBe('agent_stopped');
  });

  it('does not call a just-spawned session stopped', () => {
    // A session exists before its agent process does. Without the startup
    // grace it is born `agent_stopped` and the composer refuses input on a
    // brand-new session.
    expect(
      state({
        status: 'STARTING',
        lastHeartbeatAt: null,
        machineLastHeartbeatAt: ago(5),
        startedAt: ago(3),
      })
    ).toBe('live');
  });

  it('gives the startup grace to a spawned session before its first beat', () => {
    expect(
      state({
        status: 'ACTIVE',
        lastHeartbeatAt: null,
        machineLastHeartbeatAt: ago(5),
        startedAt: ago(LIVENESS_STARTUP_GRACE_MS / 1000 - 30),
      })
    ).toBe('live');
  });

  it('stops excusing a spawn that hung in STARTING', () => {
    // Stuck-in-STARTING is a documented zombie shape; the grace is bounded by
    // started_at precisely so the status alone can't excuse it forever.
    expect(
      state({
        status: 'STARTING',
        lastHeartbeatAt: null,
        machineLastHeartbeatAt: ago(5),
        startedAt: ago(LIVENESS_STARTUP_GRACE_MS / 1000 + 60),
      })
    ).toBe('agent_stopped');
  });

  it('does not re-apply the grace after a session has beaten once', () => {
    // started_at is recent but a heartbeat already landed and went stale —
    // the grace must not resurrect it.
    expect(
      state({
        status: 'ACTIVE',
        lastHeartbeatAt: ago(600),
        machineLastHeartbeatAt: ago(5),
        startedAt: ago(5),
      })
    ).toBe('agent_stopped');
  });

  it('says nothing about a session closed on purpose', () => {
    // Archived/closed sessions have no agent by design and keep their own
    // placeholder. Liveness must not speak for them.
    expect(
      state({
        status: 'COMPLETED',
        lastHeartbeatAt: null,
        machineId: null,
        startedAt: ago(9999),
      })
    ).toBe('unknown');
  });

  it('prefers the offline-machine explanation over blaming the agent', () => {
    expect(
      state({ lastHeartbeatAt: ago(600), machineLastHeartbeatAt: ago(600) })
    ).toBe('machine_offline');
  });

  it('leaves legacy rows without a machine as unknown', () => {
    // These are the bulk of the backlog; rendering them as errors would turn a
    // user's whole history red.
    expect(state({ lastHeartbeatAt: null, machineId: null })).toBe('unknown');
  });

  it('lets a fresh agent heartbeat win over missing machine linkage', () => {
    expect(state({ lastHeartbeatAt: ago(5), machineId: null })).toBe('live');
  });

  it('ignores an unparseable timestamp instead of treating it as fresh', () => {
    expect(
      state({ lastHeartbeatAt: 'not-a-date', machineLastHeartbeatAt: ago(10) })
    ).toBe('agent_stopped');
  });
});

describe('resolveLiveState', () => {
  it('derives fully when the machine is known', () => {
    expect(
      resolveLiveState(
        { last_heartbeat_at: ago(600), machine_id: MACHINE },
        { last_heartbeat_at: ago(600) },
        NOW
      )
    ).toBe('machine_offline');
  });

  it('proves liveness from the session heartbeat without the machine', () => {
    expect(
      resolveLiveState(
        { last_heartbeat_at: ago(5), machine_id: MACHINE },
        undefined,
        NOW
      )
    ).toBe('live');
  });

  it("falls back to the server's verdict when the machine is unknown", () => {
    expect(
      resolveLiveState(
        {
          last_heartbeat_at: ago(600),
          machine_id: MACHINE,
          live_state: 'machine_offline',
        },
        undefined,
        NOW
      )
    ).toBe('machine_offline');
  });

  it('stays silent when neither a heartbeat nor a server verdict exists', () => {
    // A backend predating `live_state` must not make every session look dead
    // during a deploy skew.
    expect(
      resolveLiveState(
        { last_heartbeat_at: null, machine_id: MACHINE },
        undefined,
        NOW
      )
    ).toBe('unknown');
  });

  it('handles a missing instance', () => {
    expect(resolveLiveState(null, undefined, NOW)).toBe('unknown');
  });

  // resolveLiveState is what the composer and both sidebars call, usually
  // WITHOUT a machine. These three are the cases it must settle on its own.

  it('reports a live-looking session whose agent is gone as stopped', () => {
    // The case the placeholder exists for: status still claims ACTIVE, but
    // nothing has heartbeated and the host is up to be asked.
    expect(
      resolveLiveState(
        {
          status: 'ACTIVE',
          last_heartbeat_at: ago(600),
          machine_id: MACHINE,
          started_at: ago(9999),
        },
        { last_heartbeat_at: ago(5) },
        NOW
      )
    ).toBe('agent_stopped');
  });

  it('does not block a session that is still starting', () => {
    expect(
      resolveLiveState(
        {
          status: 'STARTING',
          last_heartbeat_at: null,
          machine_id: MACHINE,
          started_at: ago(3),
        },
        undefined,
        NOW
      )
    ).toBe('live');
  });

  it('stops excusing a hung spawn once the grace expires', () => {
    expect(
      resolveLiveState(
        {
          status: 'STARTING',
          last_heartbeat_at: null,
          machine_id: MACHINE,
          started_at: ago(LIVENESS_STARTUP_GRACE_MS / 1000 + 60),
        },
        { last_heartbeat_at: ago(5) },
        NOW
      )
    ).toBe('agent_stopped');
  });
});

describe('helpers', () => {
  it('isHeartbeatFresh is false for null and unparseable input', () => {
    expect(isHeartbeatFresh(null, NOW)).toBe(false);
    expect(isHeartbeatFresh(undefined, NOW)).toBe(false);
    expect(isHeartbeatFresh('nonsense', NOW)).toBe(false);
  });

  it('isMachineOnline respects the shared threshold', () => {
    expect(isMachineOnline({ last_heartbeat_at: ago(10) }, NOW)).toBe(true);
    expect(
      isMachineOnline(
        { last_heartbeat_at: ago(LIVENESS_ONLINE_THRESHOLD_MS / 1000 + 1) },
        NOW
      )
    ).toBe(false);
    expect(isMachineOnline(null, NOW)).toBe(false);
  });

  it.each([
    ['live', true],
    ['reconnecting', true],
    ['agent_stopped', false],
    ['machine_offline', false],
    ['unknown', false],
  ] as const)('isReachable(%s) === %s', (value, expected) => {
    expect(isReachable(value)).toBe(expected);
  });

  it.each([
    ['agent_stopped', true],
    ['machine_offline', true],
    ['live', false],
    ['reconnecting', false],
    // Legacy rows and old-backend deploy skew land here. Blocking on no
    // evidence would break working sessions.
    ['unknown', false],
  ] as const)('blocksSending(%s) === %s', (value, expected) => {
    expect(blocksSending(value)).toBe(expected);
  });

  it('gives an actionable hint exactly when sending is blocked', () => {
    // The composer uses the hint as its placeholder, so every blocked state
    // must have copy and no unblocked state may show any.
    const states: LiveState[] = [
      'live',
      'reconnecting',
      'agent_stopped',
      'machine_offline',
      'unknown',
    ];
    for (const s of states) {
      expect(liveStateHint(s) !== null).toBe(blocksSending(s));
    }
  });

  it('does not promise delivery in the blocked-state copy', () => {
    // Sending is refused in these states, so "we'll deliver it later" would be
    // a lie. The copy must tell the user what to do instead.
    expect(liveStateHint('agent_stopped')).toBe(
      "This session's agent isn't running. Resume it to send messages."
    );
    expect(liveStateHint('machine_offline')).toBe(
      'Your computer is offline. Bring it back online to send messages.'
    );
    for (const s of ['agent_stopped', 'machine_offline'] as const) {
      expect(liveStateHint(s)).not.toMatch(/will be delivered|we'll deliver/i);
    }
  });

  it('only offers resume for a stopped agent on a reachable machine', () => {
    // An offline machine has no daemon to relaunch into, so Resume would fail.
    expect(isResumable('agent_stopped')).toBe(true);
    expect(isResumable('machine_offline')).toBe(false);
    expect(isResumable('live')).toBe(false);
    expect(isResumable('unknown')).toBe(false);
  });
});
