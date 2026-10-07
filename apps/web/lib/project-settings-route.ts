/**
 * Routing for the per-project Settings pane (`?tab=project&projectId=…`),
 * kept apart from the pane component so the app sidebar and the settings nav
 * can build links without pulling the pane (and its worktree editor) into
 * their bundles.
 */

export const PROJECT_SETTINGS_SECTIONS = [
  { id: 'general', label: 'General' },
  { id: 'sharing', label: 'Sharing' },
  { id: 'worktree', label: 'Git & Worktree' },
  { id: 'tasks', label: 'Tasks' },
] as const;

export type ProjectSettingsSection = (typeof PROJECT_SETTINGS_SECTIONS)[number]['id'];

/**
 * Resolve the `?section=` param to a known tab (general is the default). The
 * pane still falls back to General for a tab this project does not offer
 * (Sharing, for anyone who cannot administer it).
 */
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
