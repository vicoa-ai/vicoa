import { getRpcClient, RpcError } from '@/lib/ws-client';

export type RpcCode =
  | 'path_not_found'
  | 'permission_denied'
  | 'outside_project'
  | 'too_large'
  | 'not_a_repo'
  | 'no_handler'
  | 'not_a_directory'
  | 'not_a_file'
  | 'write_failed'
  | 'conflict'
  | 'target_disconnected'
  | 'timeout'
  | 'not_connected'
  | 'rpc_failed';

export interface FileEntry {
  name: string;
  type: 'dir' | 'file';
  size?: number;
}

export interface ListFilesResult {
  entries: FileEntry[];
}

export interface ReadFileResult {
  content: string;
  encoding: 'utf-8' | 'base64';
  is_binary: boolean;
  size: number;
  truncated: boolean;
  /** sha256 of the on-disk bytes; the base for edit conflict detection. `null`
   * for binary/truncated files (not editable), and absent from daemons that
   * predate editing — both leave the file read-only. */
  content_hash?: string | null;
}

/** `stat-file` — a cheap freshness probe (no contents) the editor polls for
 * open tabs to notice the file changed on disk under an active edit. */
export interface StatFileResult {
  size: number;
  mtime: number;
  content_hash: string | null;
}

/** `write-file` success. `content_hash` is the new base for the next save. */
export interface WriteFileResult {
  size: number;
  mtime: number;
  content_hash: string;
}

/** `write-file` refused because the on-disk hash no longer matches the base the
 * caller held — a concurrent write (e.g. the agent) would be clobbered. The
 * caller reloads or retries with `force`. */
export interface WriteConflict {
  conflict: true;
  content_hash: string | null;
}

export function isWriteConflict(
  r: WriteFileResult | WriteConflict,
): r is WriteConflict {
  return (r as WriteConflict).conflict === true;
}

export type GitStatusEntryStatus = 'M' | 'A' | 'D' | 'R' | 'C' | 'T' | 'U' | '??';

export interface GitStatusEntry {
  path: string;
  old_path?: string;
  status: GitStatusEntryStatus | string;
  additions: number;
  deletions: number;
  content_hash: string | null;
  /** A `160000` gitlink — the parent repo pins this path to one submodule
   * commit, so its plain diff is only ever "Subproject commit a..b". The panel
   * expands these by re-running `git-status`/`git-diff` with `cwd` set to the
   * submodule directory. Absent on daemons that predate the flag, which is
   * exactly what hides the toolbar toggle there. */
  is_submodule?: boolean;
}

export interface GitStatusResult {
  branch: string | null;
  ahead: number;
  behind: number;
  upstream?: string;
  detached_head?: boolean;
  staged: GitStatusEntry[];
  unstaged: GitStatusEntry[];
  untracked: GitStatusEntry[];
}

export type DiffLineKind = 'add' | 'remove' | 'context';

export interface DiffLine {
  type: DiffLineKind;
  content: string;
}

export interface DiffHunk {
  header: string;
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  lines: DiffLine[];
}

export interface GitDiffResult {
  path: string;
  hunks: DiffHunk[];
  is_binary: boolean;
  truncated: boolean;
  size?: number;
  old_size?: number;
  new_size?: number;
}

export async function rpcListFiles(
  machineId: string,
  cwd: string,
  path: string,
): Promise<ListFilesResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'list-files', { cwd, path });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as ListFilesResult;
}

/** Whole-project `@`-mention index. Folders (trailing `/`) first, then files. */
export interface ScanFilesResult {
  files: string[];
  file_count: number;
  hash: string;
  truncated: boolean;
  /** Unix seconds. Wall-clock, not the daemon's TTL clock. */
  scanned_at: number;
}

/** Reply when the caller's `known_hash` still matches — no payload resent. */
export interface ScanFilesUnchanged {
  unchanged: true;
  hash: string;
}

/**
 * Fetch the live project index for `@` mentions.
 *
 * Distinct from `rpcListFiles`, which lists ONE directory level for the Files
 * tab tree and filters through `git check-ignore`; this walks the whole
 * project through `pathspec` so it also works outside a git repo.
 *
 * Requires a daemon advertising the `file-index` capability — older ones fail
 * with `no_handler`, which `lib/file-mentions-store.ts` turns into a DB
 * fallback. Pass `knownHash` to get `{unchanged: true}` instead of the payload
 * when nothing on disk has moved.
 */
export async function rpcScanFiles(
  machineId: string,
  cwd: string,
  knownHash?: string,
): Promise<ScanFilesResult | ScanFilesUnchanged> {
  const params: Record<string, unknown> = { cwd };
  if (knownHash) params.known_hash = knownHash;
  const result = await getRpcClient(machineId).callRpc(machineId, 'scan-files', params);
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as ScanFilesResult | ScanFilesUnchanged;
}

/** One slash command or skill from the live daemon index. */
export interface ScanCommandItem {
  name: string;
  description: string;
  kind: 'command' | 'skill';
  /** Composer text to insert on selection when it differs from /name. */
  insert?: string;
}

/** Live slash command/skill index for a machine + agent. */
export interface ScanCommandsResult {
  commands: ScanCommandItem[];
  command_count: number;
  hash: string;
  /** Unix seconds, wall-clock. */
  scanned_at: number;
}

/** Reply when the caller's `known_hash` still matches — no payload resent. */
export interface ScanCommandsUnchanged {
  unchanged: true;
  hash: string;
}

/**
 * Fetch the live slash command/skill set for `agentType` on a machine.
 *
 * Counterpart to `rpcScanFiles` for the `/` menu: reads the machine's current
 * ~/.claude, ~/.codex and ~/.agents dirs instead of the copy the CLI synced
 * into the DB at session start. `cwd` scopes project-local sources and may be
 * omitted (globals are still scanned).
 *
 * Requires a daemon advertising the `command-index` capability — older ones
 * fail with `no_handler`, which `lib/slash-commands-store.ts` turns into a DB
 * fallback.
 */
export async function rpcScanCommands(
  machineId: string,
  agentType: string,
  cwd?: string | null,
  knownHash?: string,
): Promise<ScanCommandsResult | ScanCommandsUnchanged> {
  const params: Record<string, unknown> = { agent_type: agentType };
  if (cwd) params.cwd = cwd;
  if (knownHash) params.known_hash = knownHash;
  const result = await getRpcClient(machineId).callRpc(machineId, 'scan-commands', params);
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as ScanCommandsResult | ScanCommandsUnchanged;
}

export async function rpcReadFile(
  machineId: string,
  cwd: string,
  path: string,
): Promise<ReadFileResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'read-file', { cwd, path });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as ReadFileResult;
}

/** Poll an open file's on-disk signature without transferring its contents. */
export async function rpcStatFile(
  machineId: string,
  cwd: string,
  path: string,
): Promise<StatFileResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'stat-file', { cwd, path });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as StatFileResult;
}

/**
 * Write `content` (UTF-8) back to `path`, atomically on the daemon side.
 *
 * `baseHash` is the hash the caller held when it opened the file; the daemon
 * rejects the write with a {@link WriteConflict} (rather than throwing) if the
 * file changed underneath — pass `force` to overwrite anyway. Hard failures
 * (permission, offline, …) still throw {@link RpcError}.
 */
export async function rpcWriteFile(
  machineId: string,
  cwd: string,
  path: string,
  content: string,
  baseHash: string | null,
  force = false,
): Promise<WriteFileResult | WriteConflict> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'write-file', {
    cwd,
    path,
    content,
    base_hash: baseHash,
    force,
  });
  if (result.error === 'conflict') {
    return { conflict: true, content_hash: (result.content_hash as string | null) ?? null };
  }
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as WriteFileResult;
}

/**
 * `git-show-file` — the baseline ("original") side of the editable diff view.
 * Returns a `read-file`-shaped payload for `path` at git `ref` (default HEAD;
 * `''` reads the index/staged blob). A path absent at the ref (a new/untracked
 * file) comes back as `{ not_in_ref: true }` so the client shows an empty
 * original. Requires a daemon advertising the `git-base` capability — older
 * ones fail `no_handler`, and the diff view falls back to the read-only inline
 * diff.
 */
export interface GitShowFileResult {
  content?: string;
  encoding?: 'utf-8' | 'base64';
  is_binary?: boolean;
  size?: number;
  truncated?: boolean;
  content_hash?: string | null;
  /** The path doesn't exist at the ref — treat the original as empty. */
  not_in_ref?: boolean;
}

export async function rpcGitShowFile(
  machineId: string,
  cwd: string,
  path: string,
  ref = 'HEAD',
): Promise<GitShowFileResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-show-file', {
    cwd,
    path,
    ref,
  });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as GitShowFileResult;
}

export async function rpcGitStatus(
  machineId: string,
  cwd: string,
): Promise<GitStatusResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-status', { cwd });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as GitStatusResult;
}

export async function rpcGitDiff(
  machineId: string,
  cwd: string,
  path: string,
  staged: boolean,
  ignoreWhitespace: boolean,
): Promise<GitDiffResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-diff', {
    cwd,
    path,
    staged,
    ignore_whitespace: ignoreWhitespace,
  });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as GitDiffResult;
}

// ── Staging + commit (git-stage / git-unstage / git-commit) ───────────────────
// All three need a daemon advertising the `git-write` capability — older ones
// fail `no_handler`, which the UI surfaces as "update the daemon".

/** `git-stage`/`git-unstage` result: `ok`, or the daemon's own git error text
 * (e.g. an index lock held by a running agent) for the UI to show verbatim. */
export type GitWriteOutcome = { ok: true } | { ok: false; message: string };

async function callGitWrite(
  machineId: string,
  method: 'git-stage' | 'git-unstage',
  cwd: string,
  paths: string[],
): Promise<GitWriteOutcome> {
  const result = await getRpcClient(machineId).callRpc(machineId, method, { cwd, paths });
  if (result.error === 'stage_failed' || result.error === 'unstage_failed') {
    return { ok: false, message: (result.message as string | undefined) || String(result.error) };
  }
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return { ok: true };
}

export function rpcGitStage(
  machineId: string,
  cwd: string,
  paths: string[],
): Promise<GitWriteOutcome> {
  return callGitWrite(machineId, 'git-stage', cwd, paths);
}

export function rpcGitUnstage(
  machineId: string,
  cwd: string,
  paths: string[],
): Promise<GitWriteOutcome> {
  return callGitWrite(machineId, 'git-unstage', cwd, paths);
}

/**
 * `git-commit` — commit whatever is staged. A git-level failure (nothing
 * staged, missing user identity, a hook rejecting) comes back as
 * `{ok: false}` with git's own message rather than throwing, so the commit box
 * can show something actionable. Transport-level failures still throw.
 */
export async function rpcGitCommit(
  machineId: string,
  cwd: string,
  message: string,
): Promise<GitWriteOutcome & { commit_id?: string }> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-commit', {
    cwd,
    message,
  });
  if (result.error === 'commit_failed') {
    return { ok: false, message: (result.message as string | undefined) || 'commit failed' };
  }
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return { ok: true, commit_id: result.commit_id as string | undefined };
}

/** One git worktree of a repo (`git-worktree-list`). `managed` means the daemon
 * created it under `~/vicoa/workspaces/` — only those are removable. */
export interface WorktreeInfo {
  path: string;
  branch: string;
  head: string;
  managed: boolean;
}

export async function rpcGitWorktreeList(
  machineId: string,
  cwd: string,
): Promise<WorktreeInfo[]> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-worktree-list', { cwd });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return (result.worktrees as WorktreeInfo[]) ?? [];
}

export async function rpcGitWorktreeRemove(
  machineId: string,
  cwd: string,
  worktreePath: string,
  force: boolean,
): Promise<void> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-worktree-remove', {
    cwd,
    worktree_path: worktreePath,
    force,
  });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
}

// ── Commit history (git-log / git-commit-files / git-commit-diff) ─────────────

export interface CommitRef {
  name: string;
  kind: 'head' | 'branch' | 'remote' | 'tag';
}

export interface CommitEntry {
  id: string;
  short_id: string;
  parent_ids: string[];
  subject: string;
  body: string;
  author_name: string;
  author_email: string;
  timestamp: number;
  refs: CommitRef[];
}

export interface RefRevision {
  name: string;
  revision: string;
}

export interface GitLogResult {
  commits: CommitEntry[];
  has_more: boolean;
  current_ref?: RefRevision;
  upstream_ref?: RefRevision;
}

export interface CommitFileEntry {
  path: string;
  old_path?: string;
  status: GitStatusEntryStatus | string;
  additions: number;
  deletions: number;
}

export interface CommitFilesResult {
  files: CommitFileEntry[];
  stats: { files: number; insertions: number; deletions: number };
}

export async function rpcGitLog(
  machineId: string,
  cwd: string,
  limit: number,
): Promise<GitLogResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-log', { cwd, limit });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as GitLogResult;
}

export async function rpcGitCommitFiles(
  machineId: string,
  cwd: string,
  commitId: string,
): Promise<CommitFilesResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-commit-files', {
    cwd,
    commit_id: commitId,
  });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as CommitFilesResult;
}

export async function rpcGitCommitDiff(
  machineId: string,
  cwd: string,
  commitId: string,
  path: string,
): Promise<GitDiffResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'git-commit-diff', {
    cwd,
    commit_id: commitId,
    path,
  });
  if (typeof result.error === 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as GitDiffResult;
}
