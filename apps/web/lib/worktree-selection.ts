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

/**
 * Whether the daemon honours `worktree.name` on spawn and serves the
 * `git-worktree-check-name` RPC. Gated separately from `worktree`: an old
 * daemon drops the unknown `name` silently and spawns a random slug, so
 * offering the field against one would hand the user a different name than
 * they typed.
 */
export function machineSupportsWorktreeName(
  machine: MetadataShape | null | undefined,
): boolean {
  const caps = readCapabilities(machine);
  return Array.isArray(caps) && caps.some((c) => String(c) === 'worktree-name');
}

/**
 * Instant client-side verdict on a typed worktree name — the common
 * `git check-ref-format --branch` rules, so obvious mistakes are flagged as
 * the user types without a daemon round trip. Returns a short reason, or
 * null when the name passes. The daemon (`git-worktree-check-name`) stays the
 * authority: it runs git's real check and knows what's taken.
 */
export function validateWorktreeName(name: string): string | null {
  const n = name.trim();
  if (!n) return null; // blank = random name, always fine
  if (/\s/.test(n)) return 'No spaces';
  if (/[~^:?*[\\\u0000-\u001f\u007f]/.test(n)) return 'No ~ ^ : ? * [ or \\';
  if (n.startsWith('-')) return "Can't start with -";
  if (n.includes('..') || n.includes('@{') || n === '@') return 'No .. or @{';
  if (n.endsWith('.')) return "Can't end with .";
  // `feat/login` is a fine branch (nested middle dir); each segment must
  // still be non-empty, not dot-led, and not end in `.lock`.
  const parts = n.split('/');
  if (parts.some((part) => !part || part.startsWith('.') || part.endsWith('.lock'))) {
    return 'Bad path segment (empty, leading . or .lock)';
  }
  return null;
}

export interface WorktreeSpawn {
  directory: string;
  /** The spawn-session `worktree` param, or undefined for a plain spawn. */
  worktree: { new: true; name?: string } | undefined;
}

/**
 * Map a worktree selection onto spawn-session args. `new` keeps the base
 * directory (the daemon forks off its HEAD, on `newWorktreeName` when the user
 * picked one, else a random slug); `existing` spawns directly in the selected
 * worktree path; `none` is a plain spawn. A stale `existing` selection with no
 * path falls back to the base directory.
 */
export function resolveWorktreeSpawn({
  mode,
  baseDirectory,
  selectedWorktreePath,
  newWorktreeName,
}: {
  mode: WorktreeMode;
  baseDirectory: string;
  selectedWorktreePath?: string | null;
  newWorktreeName?: string | null;
}): WorktreeSpawn {
  switch (mode) {
    case 'new': {
      const name = newWorktreeName?.trim();
      return {
        directory: baseDirectory,
        worktree: name ? { new: true, name } : { new: true },
      };
    }
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
