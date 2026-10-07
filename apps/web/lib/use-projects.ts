'use client';

/**
 * The caller's projects — one SWR read shared by the sidebar, the session
 * header, Settings (nav + pane), the new-session folder chip and Automations.
 *
 * Each of those used to fetch the list into its own state, so every mount
 * started empty: on desktop, opening Settings swaps the sidebar out, and coming
 * back drew every project icon as the default glyph until the refetch landed,
 * then swapped in the image. A shared cache gives a remount the last list on
 * its first render while SWR revalidates behind it.
 *
 * Archived projects are included (the sidebar and Settings need them); callers
 * that list only live projects filter `is_archived` themselves. Projects live
 * on the cloud backend, so the logged-out desktop (local daemon only) has
 * nothing to ask; the key goes null there and SWR never fetches.
 */

import useSWR, { mutate as globalMutate, type KeyedMutator } from 'swr';

import { getBackendAPI, type ProjectResponse } from '@/lib/backend-api';
import { isDesktopLocal } from '@/lib/runtime-config';

export const PROJECTS_KEY = 'projects';

export function useProjects(): {
  /** undefined until the first load (or when the load failed with no cache). */
  projects: ProjectResponse[] | undefined;
  error: unknown;
  /** A fetch is on the wire (the first load or a revalidation). */
  isValidating: boolean;
  mutate: KeyedMutator<ProjectResponse[]>;
} {
  const { data, error, isValidating, mutate } = useSWR<ProjectResponse[]>(
    isDesktopLocal() ? null : PROJECTS_KEY,
    () => getBackendAPI(true).listProjects(true),
    { shouldRetryOnError: false },
  );
  return { projects: data, error, isValidating, mutate };
}

/** Refetch the shared list (after a mutation made outside the hook). */
export function refreshProjects(): void {
  void globalMutate(PROJECTS_KEY);
}

/** Write a project row the server just returned into the shared list, so
 *  every reader shows it now, then revalidate. */
export function replaceCachedProject(next: ProjectResponse): void {
  void globalMutate<ProjectResponse[]>(
    PROJECTS_KEY,
    (list) => list?.map((p) => (p.id === next.id ? next : p)),
  );
}
