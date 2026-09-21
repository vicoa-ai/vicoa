/**
 * Routing for the per-project Settings pane (`?tab=project&projectId=…`),
 * kept apart from the pane component so the app sidebar and the settings nav
 * can build links without pulling the pane (and its worktree editor) into
 * their bundles.
 */

export const PROJECT_SETTINGS_SECTIONS = [
  { id: 'general', label: 'General' },
  { id: 'worktree', label: 'Git & Worktree' },
  { id: 'tasks', label: 'Tasks' },
] as const;

export type ProjectSettingsSection = (typeof PROJECT_SETTINGS_SECTIONS)[number]['id'];

/** Resolve the `?section=` param to a known tab (general is the default). */
export function projectSettingsSection(param: string | null): ProjectSettingsSection {
  return PROJECT_SETTINGS_SECTIONS.some((section) => section.id === param)
    ? (param as ProjectSettingsSection)
    : 'general';
}

/** Href of a project's settings pane, with an optional tab. */
export function projectSettingsHref(projectId: string, section?: ProjectSettingsSection): string {
  const params = new URLSearchParams({ tab: 'project', projectId });
  if (section && section !== 'general') params.set('section', section);
  return `/dashboard/settings?${params.toString()}`;
}

/**
 * Window event the pane fires after any project mutation (rename, icon,
 * folders, archive, delete) so the settings navs — which keep their own copy
 * of the project list — refetch without a route change or window blur.
 */
export const PROJECTS_CHANGED_EVENT = 'vicoa:projects-changed';

export function notifyProjectsChanged(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(PROJECTS_CHANGED_EVENT));
}
