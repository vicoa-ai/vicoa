/**
 * WS-RPC wrappers for the Skills tab. Skills live on the selected machine's
 * disk, so — like automation's "Run now" — these ride the daemon RPC path
 * (`getRpcClient(machineId).callRpc`), not the REST `BackendAPI`. The daemon
 * handlers are `vicoa.rpc.skills_ops` (list-skills / install-skill /
 * uninstall-skill).
 */

import { getRpcClient, RpcError } from '@/lib/ws-client';
import type { MachineSummary } from '@/lib/backend-api';

/** An agent id from the catalog (claude / codex / opencode / …). */
export type SkillAgentType = string;

/** Capability a daemon advertises once it can manage skills (machine_daemon
 *  `_capabilities`). Absent on older daemons — gate on it to avoid the 3s
 *  `no_handler` grace penalty, same pattern as `machineSupportsAgentScan`. */
export const SKILL_MANAGE_CAPABILITY = 'skill-manage';

export function machineSupportsSkills(
  machine:
    | (Pick<MachineSummary, 'metadata'> & { machine_metadata?: Record<string, unknown> | null })
    | null
    | undefined,
): boolean {
  if (!machine) return false;
  const metadata = machine.metadata ?? machine.machine_metadata;
  if (!metadata || typeof metadata !== 'object') return false;
  const caps = (metadata as Record<string, unknown>).capabilities;
  return Array.isArray(caps) && caps.some((c) => String(c) === SKILL_MANAGE_CAPABILITY);
}

/** Agents whose on-disk skills the daemon can manage. Others render a note. */
export const SKILL_SUPPORTED_AGENTS: readonly string[] = ['claude', 'codex', 'opencode'];

export interface SkillSummary {
  name: string;
  description: string;
  /** Absolute on-disk skill directory. */
  path: string;
  /** 'user' (the agent's own dir) or 'shared' (~/.agents/skills). */
  scope: string;
  /** Install source URL when vicoa installed it; null for hand-installed. */
  source: string | null;
  installed_at: string | null;
}

export interface SkillFileRef {
  path: string;
  size: number;
}

/** Full detail for one skill — the SKILL.md body + its supporting files. */
export interface SkillDetail extends SkillSummary {
  content: string;
  truncated: boolean;
  files: SkillFileRef[];
}

export interface ListSkillsResult {
  skills: SkillSummary[];
  /** False for agents with no managed local skill source. */
  supported: boolean;
}

export interface InstallSkillParams {
  git_url: string;
  subdir?: string;
  overwrite?: boolean;
}

/** A daemon-returned `{error: code}` (invalid_url, skill_exists, …). Distinct
 *  from `RpcError`, which is a transport failure (machine offline / timeout). */
export class SkillOpError extends Error {
  readonly code: string;
  readonly detail?: string;
  constructor(code: string, detail?: string) {
    super(code);
    this.name = 'SkillOpError';
    this.code = code;
    this.detail = detail;
  }
}

const SKILL_ERROR_MESSAGES: Record<string, string> = {
  invalid_url: 'Enter a valid git repository URL (https:// or git@…).',
  invalid_subdir: 'That subdirectory path is not allowed.',
  clone_failed: 'Could not clone the repository. Check the URL and that it is public.',
  git_not_available: 'git is not installed on this machine.',
  install_timeout: 'Cloning took too long — try a smaller repo or a subdirectory.',
  skill_md_not_found: 'No SKILL.md found at the repo root or the given subdirectory.',
  invalid_skill_name: 'The skill has an invalid name.',
  file_too_large: 'A file in the repo exceeds the size limit.',
  too_many_files: 'The repo has too many files to install as a skill.',
  skill_too_large: 'The skill is too large to install.',
  skill_exists: 'A skill with that name is already installed.',
  not_found: 'That skill is no longer installed.',
  unsupported_agent: 'This agent does not support installable skills.',
};

/** A human-readable message for any error thrown by the wrappers below. */
export function describeSkillError(err: unknown): string {
  if (err instanceof SkillOpError) {
    return SKILL_ERROR_MESSAGES[err.code] ?? err.code;
  }
  if (err instanceof RpcError) {
    if (err.code === 'no_handler') {
      return 'This machine’s Vicoa CLI is too old to manage skills — update it.';
    }
    if (err.code === 'not_connected' || err.code === 'target_disconnected') {
      return 'Machine is offline — reconnect it to manage skills.';
    }
    if (err.code === 'timeout') return 'The machine did not respond in time.';
    return err.code;
  }
  return err instanceof Error ? err.message : 'Something went wrong.';
}

/** True when the error means the machine is unreachable (offline/timeout).
 *  `no_handler` is excluded — that's a too-old daemon, not an offline one. */
export function isMachineUnreachable(err: unknown): boolean {
  return (
    err instanceof RpcError &&
    (err.code === 'not_connected' ||
      err.code === 'target_disconnected' ||
      err.code === 'timeout')
  );
}

/** True when the machine is reachable but its daemon lacks the skill RPCs. */
export function isDaemonTooOld(err: unknown): boolean {
  return err instanceof RpcError && err.code === 'no_handler';
}

export async function listSkills(
  machineId: string,
  agentType: SkillAgentType,
): Promise<ListSkillsResult> {
  const res = await getRpcClient(machineId).callRpc(machineId, 'list-skills', {
    agent_type: agentType,
  });
  return {
    skills: Array.isArray(res.skills) ? (res.skills as SkillSummary[]) : [],
    supported: res.supported !== false,
  };
}

export async function getSkill(
  machineId: string,
  agentType: SkillAgentType,
  name: string,
): Promise<SkillDetail> {
  const res = await getRpcClient(machineId).callRpc(machineId, 'get-skill', {
    agent_type: agentType,
    name,
  });
  if (res.error) throw new SkillOpError(String(res.error));
  return res as unknown as SkillDetail;
}

export async function installSkill(
  machineId: string,
  agentType: SkillAgentType,
  params: InstallSkillParams,
): Promise<SkillSummary> {
  const res = await getRpcClient(machineId).callRpc(machineId, 'install-skill', {
    agent_type: agentType,
    git_url: params.git_url,
    ...(params.subdir ? { subdir: params.subdir } : {}),
    ...(params.overwrite ? { overwrite: true } : {}),
  });
  if (res.error) {
    throw new SkillOpError(String(res.error), res.detail ? String(res.detail) : undefined);
  }
  return res as unknown as SkillSummary;
}

export async function uninstallSkill(
  machineId: string,
  agentType: SkillAgentType,
  name: string,
): Promise<void> {
  const res = await getRpcClient(machineId).callRpc(machineId, 'uninstall-skill', {
    agent_type: agentType,
    name,
  });
  if (res.error) throw new SkillOpError(String(res.error));
}
