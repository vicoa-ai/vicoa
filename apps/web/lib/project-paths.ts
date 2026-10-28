/**
 * Pure path helpers behind the project-first new-session picker
 * (plans/todos/project-first-picker-and-sidebar.md §5a).
 *
 * The new-session `directory` is any folder inside a project — its root or a
 * subfolder — and never a worktree path. These helpers resolve such a folder
 * to the DB project it belongs to (longest linked-directory prefix on the
 * selected machine), split off the part below the root, and carry that part
 * into a worktree at spawn. Mirrored on mobile in `project_paths.dart`.
 */

import type { ProjectResponse } from '@/lib/backend-api';
import { toAbsolutePath } from '@/lib/utils';

/** Trailing slashes dropped (the root `/` kept), `~` expanded when the home
 * dir is known — the one form every comparison below is made in. */
export function canonicalPath(path: string, homeDir?: string | null): string {
  const expanded = toAbsolutePath(path.trim(), homeDir) ?? path.trim();
  if (expanded.length > 1) return expanded.replace(/\/+$/, '');
  return expanded;
}

/** Last path segment — the folder's own name. */
export function pathBasename(path: string): string {
  const parts = path.replace(/\/+$/, '').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/**
 * The part of `directory` below `root`: `''` when they are the same folder,
 * `apps/web` for `<root>/apps/web`, `null` when `directory` is not inside
 * `root` at all. Compared on a path boundary (`/a/b` is not inside `/a/bc`).
 */
export function relativeSubpath(
  directory: string,
  root: string,
  homeDir?: string | null,
): string | null {
  const dir = canonicalPath(directory, homeDir);
  const base = canonicalPath(root, homeDir);
  if (dir === base) return '';
  const prefix = base === '/' ? '/' : `${base}/`;
  if (!dir.startsWith(prefix)) return null;
  return dir.slice(prefix.length);
}

/** `base` + `subpath`, with no doubled or dangling slashes. */
export function joinSubpath(base: string, subpath: string): string {
  const trimmedBase = base.length > 1 ? base.replace(/\/+$/, '') : base;
  const trimmedSub = subpath.replace(/^\/+/, '');
  if (!trimmedSub) return trimmedBase;
  return trimmedBase === '/' ? `/${trimmedSub}` : `${trimmedBase}/${trimmedSub}`;
}

export interface ProjectDirectoryMatch {
  project: ProjectResponse;
  /** The project's linked folder on this machine, as stored. */
  root: string;
  /** `directory` below `root` (`''` when `directory` is the root itself). */
  subpath: string;
}

/**
 * Whether the backend files the caller's own sessions into `project`: their
 * own projects and their team's always, a project someone else shared with
 * them only once they follow it ("Add to sidebar"). Mirrors the session
 * matcher (`shared/database/project_matching.py`), so the picker never shows
 * a project the session would not land in.
 */
export function takesMySessions(project: ProjectResponse): boolean {
  return project.owner == null || project.is_team_member === true || project.followed === true;
}

/**
 * The project `directory` belongs to on `machineId`: the project whose linked
 * folder on that machine is the longest prefix of `directory`. `null` when no
 * project claims it — a freshly typed folder; the backend mints a project for
 * it on the first spawn.
 */
export function resolveProjectForDirectory(
  directory: string,
  machineId: string,
  projects: readonly ProjectResponse[],
  homeDir?: string | null,
): ProjectDirectoryMatch | null {
  if (!directory.trim() || !machineId) return null;
  let best: ProjectDirectoryMatch | null = null;
  for (const project of projects) {
    if (!takesMySessions(project)) continue;
    for (const link of project.directories) {
      if (link.machine_id !== machineId) continue;
      const subpath = relativeSubpath(directory, link.local_path, homeDir);
      if (subpath === null) continue;
      if (best === null || link.local_path.length > best.root.length) {
        best = { project, root: link.local_path, subpath };
      }
    }
  }
  return best;
}

/** The fields of a session `newProjectFolder` reads. */
export interface SessionFolderFields {
  machine_id?: string | null;
  project?: string | null;
  home_dir?: string | null;
  instance_metadata?: { repo_root?: string | null; [key: string]: unknown } | null;
}

/**
 * The folder a session's Project menu offers to make a project of its own
 * ("New project “scratch”"), or `null` to leave the entry out. It is the
 * folder the backend names a fresh project after: the repo root for a git
 * session, else its working folder. Null when the session has no machine
 * (someone else's, or registered before its daemon), the folder is the home
 * folder or `/` (the backend never mints those), a project is already linked
 * on that machine at the folder or inside it (then it is a choice already, or
 * the repo is split into subfolder projects), or a project carries the
 * session's git remote (its next session lands there by identity anyway).
 * Archived projects count: the backend re-matches them rather than duplicate.
 */
export function newProjectFolder(
  session: SessionFolderFields,
  projects: readonly ProjectResponse[],
): string | null {
  const machineId = session.machine_id;
  const folder = (session.instance_metadata?.repo_root || session.project)?.trim();
  if (!machineId || !folder) return null;
  const home = session.home_dir;
  const canonical = canonicalPath(folder, home);
  if (
    canonical === '~' ||
    canonical === '/' ||
    (home && canonical === canonicalPath(home)) ||
    !pathBasename(canonical)
  ) {
    return null;
  }
  const remote = session.instance_metadata?.git_remote_url;
  for (const project of projects) {
    if (!takesMySessions(project)) continue;
    if (typeof remote === 'string' && remote && project.git_remote_url === remote) return null;
    for (const link of project.directories) {
      if (link.machine_id !== machineId) continue;
      if (relativeSubpath(link.local_path, folder, home) !== null) return null;
    }
  }
  return folder;
}

/** The projects linked to a folder on `machineId` (the picker's list), each
 * with that folder: the user's drag order first (`position`, from the
 * sidebar), then newest activity, then name — the backend's own list order. */
export function projectsOnMachine(
  projects: readonly ProjectResponse[],
  machineId: string,
): { project: ProjectResponse; path: string }[] {
  const rows: { project: ProjectResponse; path: string }[] = [];
  for (const project of projects) {
    if (project.is_archived || !takesMySessions(project)) continue;
    const link = project.directories.find((d) => d.machine_id === machineId);
    if (link) rows.push({ project, path: link.local_path });
  }
  return rows.sort((a, b) => {
    const pa = a.project.position ?? null;
    const pb = b.project.position ?? null;
    if (pa !== null && pb !== null) return pa - pb;
    if (pa !== null) return -1;
    if (pb !== null) return 1;
    const at = a.project.last_activity_at ?? '';
    const bt = b.project.last_activity_at ?? '';
    if (at !== bt) return at > bt ? -1 : 1;
    return a.project.name.localeCompare(b.project.name);
  });
}

/**
 * Chip label for the picker: the project's name, with the subfolder when the
 * directory sits below the root (`vicoa · apps/web`); the folder's own name
 * when no project claims it yet.
 */
export function directoryChipLabel(
  directory: string,
  match: ProjectDirectoryMatch | null,
): string {
  if (!directory.trim()) return '';
  if (match === null) return pathBasename(directory);
  return match.subpath ? `${match.project.name} · ${match.subpath}` : match.project.name;
}
