/**
 * Derived session liveness — the TypeScript mirror of the backend's
 * `shared/database/liveness.py`. Keep the two in sync; the thresholds and the
 * branch ordering are load-bearing and are asserted by tests on both sides.
 *
 * Why derive client-side at all when the API already returns `live_state`?
 * Because liveness is a function of *elapsed time*, not of events. A value
 * computed server-side is already stale by the time it renders, and it never
 * changes again until the next fetch — so a session that dies while the user
 * is looking at it would keep claiming to be alive. The server value is the
 * authoritative snapshot at fetch time; this recomputes it on a timer from the
 * raw heartbeats, which arrive over the websocket as they change.
 */

export type LiveState =
  | 'live'
  | 'reconnecting'
  | 'agent_stopped'
  | 'machine_offline'
  | 'unknown';

/** Agents and daemons heartbeat every 30s, so allow ~3 missed beats. */
export const LIVENESS_ONLINE_THRESHOLD_MS = 90_000;
/** Past this, a quiet agent is treated as gone rather than reconnecting. */
export const LIVENESS_STALE_THRESHOLD_MS = 300_000;
/**
 * A freshly spawned session hasn't heartbeated yet — the daemon still has to
 * launch the process, register the instance, and reach the first beat. Until
 * this much time has passed after `started_at`, silence means "starting", not
 * "dead". Without it a session is born `agent_stopped` and the composer would
 * refuse input on a brand-new session.
 */
export const LIVENESS_STARTUP_GRACE_MS = 120_000;

/**
 * Statuses where the session is closed by design — archived, deleted, or ended.
 *
 * Liveness says nothing about these: they have no agent on purpose, and the UI
 * already explains itself from `status` (an archived session keeps its own
 * placeholder). Liveness exists for the opposite case — a session that still
 * claims to be usable while its agent is gone.
 */
export const CLOSED_BY_DESIGN_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DISCONNECTED',
  'DELETED',
]);

/** Whether `status` means the session is closed on purpose. */
export function isClosedByDesign(status: string | null | undefined): boolean {
  return !!status && CLOSED_BY_DESIGN_STATUSES.has(status);
}

function ageMs(timestamp: string | null | undefined, now: number): number | null {
  if (!timestamp) return null;
  const parsed = new Date(timestamp).getTime();
  if (Number.isNaN(parsed)) return null;
  return now - parsed;
}

/** Whether a heartbeat is recent enough to count as alive. */
export function isHeartbeatFresh(
  timestamp: string | null | undefined,
  now: number = Date.now()
): boolean {
  const age = ageMs(timestamp, now);
  return age !== null && age < LIVENESS_ONLINE_THRESHOLD_MS;
}

/** Whether a host daemon has beaten recently enough to accept work. */
export function isMachineOnline(
  machine: { last_heartbeat_at?: string | null } | null | undefined,
  now: number = Date.now()
): boolean {
  return isHeartbeatFresh(machine?.last_heartbeat_at, now);
}

/** Epoch ms of a machine's last heartbeat, or 0 when missing/unparseable. */
function heartbeatEpoch(
  machine: { last_heartbeat_at?: string | null } | null | undefined
): number {
  if (!machine?.last_heartbeat_at) return 0;
  const parsed = new Date(machine.last_heartbeat_at).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * Order machines for selection: online hosts first, then most-recently-seen
 * first within each group (by `last_heartbeat_at`). Pure and non-mutating, so
 * the first element is the natural default — the freshest online machine when
 * any is online, otherwise the most recently seen offline one.
 */
export function sortMachinesOnlineFirst<
  T extends { last_heartbeat_at?: string | null },
>(machines: T[], now: number = Date.now()): T[] {
  return [...machines].sort((a, b) => {
    const aOnline = isMachineOnline(a, now);
    const bOnline = isMachineOnline(b, now);
    if (aOnline !== bOnline) return aOnline ? -1 : 1;
    return heartbeatEpoch(b) - heartbeatEpoch(a);
  });
}

export interface LiveStateInputs {
  /** `agent_instances.last_heartbeat_at` */
  lastHeartbeatAt?: string | null;
  /** `agent_instances.machine_id` — null for legacy TUI-registered rows. */
  machineId?: string | null;
  /** The owning machine's `last_heartbeat_at`, if we have the machine. */
  machineLastHeartbeatAt?: string | null;
  /** `agent_instances.status` — a terminal value is the agent's own verdict. */
  status?: string | null;
  /** `agent_instances.started_at` — bounds the startup grace. */
  startedAt?: string | null;
}

/**
 * Whether the session is still coming up and simply hasn't beaten yet.
 *
 * Bounded by `startedAt` rather than by the `STARTING` status, because a spawn
 * that hung leaves the row stuck in `STARTING` forever. Past the grace window,
 * silence is death no matter what the status claims.
 */
function isStartingUp(
  status: string | null | undefined,
  lastHeartbeatAt: string | null | undefined,
  startedAt: string | null | undefined,
  now: number
): boolean {
  // Once a session has beaten even once, later silence is real.
  if (lastHeartbeatAt) return false;
  const age = ageMs(startedAt, now);
  if (age === null) return status === 'STARTING';
  return age < LIVENESS_STARTUP_GRACE_MS;
}

/**
 * Derive a session's live state.
 *
 * Ordering matters, and mirrors the backend:
 *  1. A fresh agent heartbeat is direct proof of life and wins outright —
 *     including for rows with no machine linkage, whose liveness would
 *     otherwise be discarded.
 *  2. Otherwise an unreachable host explains the silence and is the more
 *     actionable message, so it is checked before we blame the agent.
 */
export function computeLiveState(
  {
    lastHeartbeatAt,
    machineId,
    machineLastHeartbeatAt,
    status,
    startedAt,
  }: LiveStateInputs,
  now: number = Date.now()
): LiveState {
  const age = ageMs(lastHeartbeatAt, now);

  // 1. Still coming up: silence is expected, not damning.
  if (isStartingUp(status, lastHeartbeatAt, startedAt, now)) return 'live';

  // 2. A fresh beat is direct proof of life.
  if (age !== null && age < LIVENESS_ONLINE_THRESHOLD_MS) return 'live';

  // 3. An unreachable host explains the silence, and also means resume can't
  //    work — so it outranks blaming the agent.
  if (machineId && !isHeartbeatFresh(machineLastHeartbeatAt, now)) {
    return 'machine_offline';
  }

  if (!machineId) {
    // Legacy row, still non-terminal: silence is unexplained, not damning.
    // Keeps the pre-machine_id backlog from rendering as errors.
    return 'unknown';
  }

  if (age !== null && age < LIVENESS_STALE_THRESHOLD_MS) return 'reconnecting';
  return 'agent_stopped';
}

export interface LivenessInstanceFields {
  last_heartbeat_at?: string | null;
  machine_id?: string | null;
  status?: string | null;
  started_at?: string | null;
  /** Server-derived snapshot, used only when the caller lacks the machine. */
  live_state?: LiveState;
}

/**
 * Live state for a session, tolerating a caller that doesn't have the machine.
 *
 * Pure, so list views can call it inside a render loop with a single shared
 * clock rather than needing a hook (and therefore a component) per row.
 *
 * When `machine` is omitted we can still prove liveness from the session's own
 * heartbeat; failing that we defer to the server's snapshot instead of
 * inventing "machine offline" out of data we simply don't have.
 */
export function resolveLiveState(
  instance: LivenessInstanceFields | null | undefined,
  machine: { last_heartbeat_at?: string | null } | null | undefined,
  now: number = Date.now()
): LiveState {
  if (!instance) return 'unknown';

  const inputs: LiveStateInputs = {
    lastHeartbeatAt: instance.last_heartbeat_at,
    machineId: instance.machine_id,
    status: instance.status,
    startedAt: instance.started_at,
  };

  if (machine) {
    return computeLiveState(
      { ...inputs, machineLastHeartbeatAt: machine.last_heartbeat_at },
      now
    );
  }

  // Without the machine we can still settle the two cases that don't need it:
  // a session still starting, and one that's actively beating. Anything else
  // needs the host to explain the silence.
  if (
    isStartingUp(instance.status, instance.last_heartbeat_at, instance.started_at, now)
  ) {
    return 'live';
  }
  if (isHeartbeatFresh(instance.last_heartbeat_at, now)) return 'live';
  if (!instance.machine_id) return 'unknown';

  // Host unknown to this view: defer to the server's snapshot rather than
  // inventing a verdict. Falls back to `unknown` on a backend that predates
  // `live_state`, so a deploy skew stays silent instead of accusing every
  // session of being dead.
  return instance.live_state ?? 'unknown';
}

/** Whether a message sent right now has a live agent to receive it. */
export function isReachable(state: LiveState): boolean {
  return state === 'live' || state === 'reconnecting';
}

/** Whether the session can be relaunched — needs a reachable host to run on. */
export function isResumable(state: LiveState): boolean {
  return state === 'agent_stopped';
}

/** Short, user-facing explanation. Null when there is nothing worth saying. */
export function liveStateLabel(state: LiveState): string | null {
  switch (state) {
    case 'agent_stopped':
      return 'Session stopped';
    case 'machine_offline':
      return 'Computer offline';
    case 'reconnecting':
      return 'Reconnecting…';
    default:
      return null;
  }
}

/**
 * Why the user can't reach this session, and what to do about it. Deliberately
 * distinguishes the two remedies: a cold laptop needs turning on, whereas a
 * stopped agent on a live machine can be resumed in place.
 *
 * Phrased as an instruction, not a promise. Sending is blocked in these states
 * (see `blocksSending`), so telling the user we'll "deliver it later" would be
 * a lie — there is nothing to deliver until they act.
 */
export function liveStateHint(state: LiveState): string | null {
  switch (state) {
    case 'agent_stopped':
      return "This session's agent isn't running. Resume it to send messages.";
    case 'machine_offline':
      return 'Your computer is offline. Bring it back online to send messages.';
    default:
      return null;
  }
}

/**
 * Whether the composer should refuse input, the same way an archived session
 * does. Note `unknown` deliberately does NOT block: it covers legacy rows and
 * old-backend deploy skew, where refusing to send would break working sessions
 * on no evidence.
 */
export function blocksSending(state: LiveState): boolean {
  return state === 'agent_stopped' || state === 'machine_offline';
}
