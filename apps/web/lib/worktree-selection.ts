/**
 * New-session worktree selection logic for the web dashboard. Mirrors the
 * mobile `worktree_selection.dart`. Pure functions — unit-tested in
 * `worktree-selection.test.ts`.
 *
 * See the daemon side in vicoa-backend `rpc/worktree_*.py` and the plan
 * `plans/todos/vicoa-app-worktree.md`.
 */

/** How a new session relates to a git worktree. */
export type WorktreeMode = 'none' | 'new' | 'existing';

type MetadataShape = {
  metadata?: Record<string, unknown> | null;
  machine_metadata?: Record<string, unknown> | null;
};

function readCapabilities(machine: MetadataShape | null | undefined): unknown {
  if (!machine) return undefined;
  const meta = machine.metadata ?? machine.machine_metadata;
  if (!meta || typeof meta !== 'object') return undefined;
  return (meta as Record<string, unknown>).capabilities;
}

/**
 * Whether the machine's daemon advertises git-worktree support via
 * `metadata.capabilities`. Unlike agent availability, a MISSING capability
 * reads as UNsupported (an old daemon silently ignores the spawn-session
 * `worktree` param), so the UI hides the option unless it's explicitly there.
 */
export function machineSupportsWorktree(
  machine: MetadataShape | null | undefined,
): boolean {
  const caps = readCapabilities(machine);
  return Array.isArray(caps) && caps.some((c) => String(c) === 'worktree');
}

export interface WorktreeSpawn {
  directory: string;
  /** The spawn-session `worktree` param, or undefined for a plain spawn. */
  worktree: { new: true } | undefined;
}

/**
 * Map a worktree selection onto spawn-session args. `new` keeps the base
 * directory (the daemon forks off its HEAD); `existing` spawns directly in the
 * selected worktree path; `none` is a plain spawn. A stale `existing` selection
 * with no path falls back to the base directory.
 */
export function resolveWorktreeSpawn({
  mode,
  baseDirectory,
  selectedWorktreePath,
}: {
  mode: WorktreeMode;
  baseDirectory: string;
  selectedWorktreePath?: string | null;
}): WorktreeSpawn {
  switch (mode) {
    case 'new':
      return { directory: baseDirectory, worktree: { new: true } };
    case 'existing':
      return { directory: selectedWorktreePath || baseDirectory, worktree: undefined };
    case 'none':
    default:
      return { directory: baseDirectory, worktree: undefined };
  }
}

/**
 * Whether `path` looks like a vicoa-managed worktree (under
 * `~/vicoa/workspaces/`). A heuristic for "should we offer removal" — the
 * daemon re-validates on remove.
 */
export function isManagedWorktreePath(path: string): boolean {
  return path.includes('/vicoa/workspaces/');
}
