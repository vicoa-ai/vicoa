/**
 * Moving a project between owners (collaboration §3.3): into a team, or out
 * of one into your own space. Pure helpers behind `MoveProjectDialog`, kept
 * apart so they can be tested without a DOM.
 */

import type { BackendApiError, ProjectResponse, TeamRole, TeamSummary } from './backend-api';

/** Same shape the backend enforces on `projects.key` (§3.5). */
export const PROJECT_KEY_PATTERN = /^[A-Z][A-Z0-9]{1,7}$/;

export function normalizeProjectKey(input: string): string {
  return input.trim().toUpperCase();
}

export function isValidProjectKey(input: string): boolean {
  return PROJECT_KEY_PATTERN.test(normalizeProjectKey(input));
}

/** Where a project can go: `teamId` null is the caller's own space. */
export interface MoveDestination {
  teamId: string | null;
  name: string;
  team: TeamSummary | null;
}

export const PERSONAL_DESTINATION_NAME = 'Personal';

/**
 * Destinations for a project the caller owns: every team they are on except
 * the one that already owns it, and their own space when it is a team's.
 * (Owning a team's project means owning the team, so taking it out is theirs
 * to do.) Any member may bring their own project into a team.
 */
export function moveDestinations(
  project: Pick<ProjectResponse, 'team_id'>,
  teams: TeamSummary[],
): MoveDestination[] {
  const out: MoveDestination[] = [];
  if (project.team_id) {
    out.push({ teamId: null, name: PERSONAL_DESTINATION_NAME, team: null });
  }
  for (const team of [...teams].sort((a, b) => a.name.localeCompare(b.name))) {
    if (team.id !== project.team_id) out.push({ teamId: team.id, name: team.name, team });
  }
  return out;
}

/** The key clash a move answered with (409 `project_key_taken`), or null. */
export function projectKeyConflict(err: unknown): { suggestedKey: string | null } | null {
  if (!(err instanceof Error)) return null;
  const { status, code, suggestedKey } = err as Partial<BackendApiError>;
  if (status !== 409 || code !== 'project_key_taken') return null;
  return { suggestedKey: suggestedKey ?? null };
}

/**
 * What changes, in the order people care about: who can see it, who runs it,
 * and what happens to labels.
 */
export function moveConsequences(
  destination: MoveDestination,
  current: { teamName: string | null },
  viewerRoleInDestination: TeamRole | null,
): string[] {
  if (destination.teamId === null) {
    return [
      `It becomes your personal project. People on ${current.teamName ?? 'the team'} lose access unless you share it with them.`,
      'Its labels move to your own set.',
    ];
  }
  const lines = [
    `Everyone on ${destination.name} can see its tasks and sessions, including past ones. Members can edit tasks and prompt its sessions.`,
  ];
  if (current.teamName) {
    lines.push(`People on ${current.teamName} lose access unless it is shared with them.`);
  }
  lines.push(
    viewerRoleInDestination === 'owner'
      ? `You own ${destination.name}, so you keep full control of it.`
      : viewerRoleInDestination === 'admin'
        ? `You'll manage it as a team admin; only the team's owner can move it out again.`
        : `You'll have editor access as a member; the team's owner and admins manage it, and only the owner can move it out again.`,
  );
  lines.push(`Its labels join the team's set.`);
  return lines;
}
