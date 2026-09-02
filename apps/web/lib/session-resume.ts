/**
 * Relaunching a stopped session on the machine it came from.
 *
 * Resume rides the existing `spawn-session` RPC rather than a dedicated
 * endpoint: a resume *is* a spawn, just one that reuses the instance id and
 * carries the agent's prior conversation handle. Passing `resume` makes the
 * daemon skip minting a new id, and each wrapper reattaches to the existing
 * row instead of registering (which would 409).
 *
 * Resume is machine- and directory-bound for every agent — Claude's transcript
 * lives at ~/.claude/projects/<cwd-slug>/<instance_id>.jsonl, and codex's
 * thread/resume takes a cwd. So it only works against the original machine,
 * and only while that machine's daemon is online.
 */

import { getWsClient } from '@/lib/ws-client';
import { toSpawnMetadata, type SessionConfig } from '@/lib/agent-catalog';
import {
  LIVENESS_STARTUP_GRACE_MS,
  isClosedByDesign,
  isResumable,
  type LiveState,
} from '@/lib/session-liveness';

/** The agent's own conversation handle, recorded by the previous run. */
export interface AgentSessionHandles {
  /** codex `thread/resume` */
  codex_thread_id?: string | null;
  /** ACP `session/load` */
  acp_session_id?: string | null;
}

export interface ResumableInstance {
  id: string;
  status: string;
  machine_id?: string | null;
  project?: string | null;
  home_dir?: string | null;
  agent_type_name?: string | null;
  session_config?: Record<string, unknown> | null;
  instance_metadata?: (AgentSessionHandles & Record<string, unknown>) | null;
  live_state?: LiveState;
}

/**
 * Instances resumed in this tab, and when.
 *
 * A resumed session keeps a stale heartbeat until its relaunched agent beats
 * (~30s), during which liveness would keep the composer locked. Recorded here
 * rather than in the chat page because Resume is also triggered from the
 * sidebar — the chat page may not even be mounted at the time, and on arrival
 * it needs to know a resume just happened.
 *
 * Module-level and deliberately not persisted: it is a short-lived UI grace,
 * and a stale entry surviving a reload would unlock input on a dead session.
 */
const recentResumes = new Map<string, number>();

/** Record that this instance was just resumed. */
export function markResumed(instanceId: string, now: number = Date.now()): void {
  recentResumes.set(instanceId, now);
}

/** Whether a resume is recent enough that the agent may not have beaten yet. */
export function isWithinResumeGrace(
  instanceId: string | null | undefined,
  now: number = Date.now()
): boolean {
  if (!instanceId) return false;
  const at = recentResumes.get(instanceId);
  if (at === undefined) return false;
  if (now - at >= LIVENESS_STARTUP_GRACE_MS) {
    recentResumes.delete(instanceId);
    return false;
  }
  return true;
}

/** Test seam. */
export function clearResumeGrace(): void {
  recentResumes.clear();
}

/**
 * Deleting a session hard-deletes its messages, so there is nothing left to
 * resume into — the transcript the user would expect to continue is gone.
 */
const UNRESUMABLE_STATUSES = new Set(['DELETED']);

export type ResumeBlockedReason =
  | 'deleted'
  | 'no-machine'
  | 'no-directory'
  | 'machine-offline'
  | 'already-running';

/**
 * Why this session can't be resumed right now, or null if it can.
 *
 * Split from `canResumeSession` so the UI can explain a disabled button
 * instead of silently hiding it — "your computer is offline" is actionable,
 * a missing menu item is not.
 */
export function resumeBlockedReason(
  instance: ResumableInstance | null | undefined,
  liveState: LiveState
): ResumeBlockedReason | null {
  if (!instance) return 'no-machine';
  if (UNRESUMABLE_STATUSES.has(instance.status)) return 'deleted';
  // Legacy TUI-started sessions have no machine linkage, so there is no daemon
  // to address the relaunch to.
  if (!instance.machine_id) return 'no-machine';
  if (!instance.project) return 'no-directory';
  if (liveState === 'machine_offline') return 'machine-offline';
  // A session the user closed is resumable straight away. Its heartbeat can
  // linger for up to the online threshold while the agent shuts down, and
  // waiting that out made Resume appear a minute or two after archiving —
  // which reads as the button being broken.
  if (isClosedByDesign(instance.status)) return null;
  if (liveState === 'live' || liveState === 'reconnecting') return 'already-running';
  return null;
}

/** Whether Resume should be offered at all (menu visibility). */
export function canResumeSession(
  instance: ResumableInstance | null | undefined,
  liveState: LiveState
): boolean {
  if (!instance) return false;
  if (UNRESUMABLE_STATUSES.has(instance.status)) return false;
  if (!instance.machine_id || !instance.project) return false;
  // Closed on purpose: the user already knows it isn't running, so don't make
  // them wait for the heartbeat to age out before offering Resume.
  if (isClosedByDesign(instance.status)) return true;
  // Offer it while offline too, disabled with a reason — hiding it would make
  // the feature look absent rather than temporarily unavailable.
  return isResumable(liveState) || liveState === 'machine_offline';
}

/**
 * Compact label for the menu item's second line.
 *
 * A disabled menu item can't fire a click, so it can't explain itself on
 * demand — the reason has to be visible up front. The full sentence stays as
 * the hover title.
 */
export function resumeBlockedShortLabel(reason: ResumeBlockedReason): string {
  switch (reason) {
    case 'deleted':
      return 'Session deleted';
    case 'no-machine':
      return 'No computer linked';
    case 'no-directory':
      return 'No folder recorded';
    case 'machine-offline':
      return 'Computer offline';
    case 'already-running':
      return 'Already running';
  }
}

export function resumeBlockedMessage(reason: ResumeBlockedReason): string {
  switch (reason) {
    case 'deleted':
      return 'This session was deleted, so there is nothing to resume.';
    case 'no-machine':
      return 'This session is not linked to a computer, so it cannot be resumed.';
    case 'no-directory':
      return 'This session has no recorded folder, so it cannot be resumed.';
    case 'machine-offline':
      return 'Your computer is offline. Bring it back online to resume.';
    case 'already-running':
      return 'This session is already running.';
  }
}

/** Expand a stored tilde path against the session's recorded home directory. */
export function expandProjectPath(
  project: string,
  homeDir?: string | null
): string {
  if (!project.startsWith('~')) return project;
  if (!homeDir) return project;
  return homeDir.replace(/\/$/, '') + project.slice(1);
}

/**
 * The agent slug the daemon expects.
 *
 * `session_config.agent` is the catalog id recorded at spawn and is what the
 * daemon validates against, so it is authoritative. `agent_type_name` is the
 * UserAgent row's name — user-editable and free-form — so deriving the slug
 * from it alone silently fell back to "claude" for every agent whose display
 * name didn't happen to contain a known keyword. That launched the Claude
 * wrapper for ACP sessions, which died with "Headless Claude encountered a
 * fatal error".
 */
export function resumeAgentSlug(instance: ResumableInstance): string {
  const configured = instance.session_config?.agent;
  if (typeof configured === 'string' && configured.trim()) {
    return configured.trim().toLowerCase();
  }
  const name = (instance.agent_type_name || '').toLowerCase();
  if (name.includes('codex')) return 'codex';
  if (name.includes('opencode')) return 'opencode';
  if (name.includes('cursor')) return 'cursor';
  if (name.includes('gemini')) return 'gemini';
  if (name.includes('copilot')) return 'copilot';
  if (name.includes('kimi')) return 'kimi';
  if (name.includes('hermes')) return 'hermes';
  return 'claude';
}

/**
 * The agent's prior conversation handle, if the previous run recorded one.
 *
 * Absent is normal, not an error: the session may predate handle capture, or
 * the agent may not support reloading. The relaunch still happens — it just
 * comes back without memory of the conversation.
 */
export function agentSessionHandle(
  instance: ResumableInstance
): string | undefined {
  const meta = instance.instance_metadata;
  if (!meta) return undefined;
  return meta.codex_thread_id ?? meta.acp_session_id ?? undefined;
}

/**
 * Rebuild the daemon spawn `metadata` from the session's stored config so a
 * resume relaunches with the SAME model, thinking effort, and permission mode
 * it had.
 *
 * Resume used to send no `metadata` at all, so the daemon saw nothing to
 * restore and fell back to its own defaults (permission mode `default`, no
 * model/effort flags) — an `auto`-mode session came back running as `default`.
 * `session_config` is the source of truth persisted on the row; run it through
 * the same `toSpawnMetadata` the new-session spawn uses so the two paths agree.
 * Returns `{}` when the row recorded no config (legacy rows) — the caller then
 * omits `metadata` and the daemon keeps its own fallback.
 */
export function resumeSpawnMetadata(
  instance: ResumableInstance
): Record<string, unknown> {
  const cfg = instance.session_config ?? {};
  const str = (v: unknown): string | undefined =>
    typeof v === 'string' && v.trim() ? v : undefined;
  const config: SessionConfig = {
    agent: resumeAgentSlug(instance),
    model: str(cfg.model),
    thinking_effort: str(cfg.thinking_effort),
    reasoning_effort: str(cfg.reasoning_effort),
    permission_mode: str(cfg.permission_mode),
    opencode_mode: str(cfg.opencode_mode),
  };
  return toSpawnMetadata(config);
}

export interface ResumeResult {
  agentInstanceId?: string;
}

/**
 * Relaunch the session on its original machine.
 *
 * Throws on RPC failure so the caller can surface it; a silent failure here
 * would leave the user staring at a session that never comes back.
 */
export async function resumeSession(
  instance: ResumableInstance
): Promise<ResumeResult> {
  if (!instance.machine_id || !instance.project) {
    throw new Error('Session cannot be resumed: missing machine or folder');
  }

  const handle = agentSessionHandle(instance);
  // Carry the stored model / effort / permission mode through the resume so the
  // relaunched session isn't silently reset to the daemon's defaults.
  const metadata = resumeSpawnMetadata(instance);
  const result = await getWsClient().callRpc(instance.machine_id, 'spawn-session', {
    directory: expandProjectPath(instance.project, instance.home_dir),
    agent: resumeAgentSlug(instance),
    resume: {
      agent_instance_id: instance.id,
      agent_session_id: handle,
    },
    ...(Object.keys(metadata).length > 0 ? { metadata } : {}),
  });

  if (result.error) {
    throw new Error(String(result.error));
  }

  markResumed(instance.id);
  return { agentInstanceId: instance.id };
}
