import { loadPersistedSelection } from '@/lib/agent-catalog';
import type { ProjectResponse } from '@/lib/backend-api';

/** Where a task's `@` file search runs: one of its project's linked folders. */
export interface ProjectMentionTarget {
  path: string;
  machineId: string | null;
}

/**
 * The linked folder `@` searches for a task in `project`. A project can be
 * linked on several machines, so prefer the one whose machine you last started
 * a session on; otherwise take the first. No link → undefined, since there'd be
 * no index to search.
 *
 * The machine goes along with the path: mentions try the live daemon index
 * first. On a task that usually misses (you write it while the laptop is
 * asleep) and falls back to the CLI-synced DB copy, which is exactly what that
 * fallback exists for.
 */
export function projectMentionTarget(
  project: Pick<ProjectResponse, 'directories'> | null | undefined,
): ProjectMentionTarget | undefined {
  const links = project?.directories ?? [];
  if (links.length === 0) return undefined;
  const lastMachineId = loadPersistedSelection().lastMachineId;
  const link = links.find((d) => d.machine_id === lastMachineId) ?? links[0];
  return { path: link.local_path, machineId: link.machine_id ?? null };
}
