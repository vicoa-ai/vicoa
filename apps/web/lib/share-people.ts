/**
 * The pure half of the share dialog's People tab (collaboration §8.4, P5):
 * the role vocabulary, how a row is labelled, and what an invite reports.
 * Kept out of the component so the wording rules — never an email where the
 * backend did not send one, never an em dash — are testable.
 */

import type {
  GrantRole,
  GrantScope,
  ProjectPerson,
  ProjectGrantCreated,
  SessionShare,
} from './backend-api';

export interface RoleOption<T extends string> {
  value: T;
  label: string;
  description: string;
}

/** The grantable ladder (§2), weakest first. Owner is a column, never offered. */
export const GRANT_ROLE_OPTIONS: RoleOption<GrantRole>[] = [
  { value: 'viewer', label: 'Viewer', description: 'Reads the board and sessions' },
  { value: 'commenter', label: 'Commenter', description: 'Also comments and reacts on tasks' },
  { value: 'editor', label: 'Editor', description: 'Also creates and edits tasks' },
  { value: 'admin', label: 'Admin', description: 'Also manages who has access' },
];

/**
 * One session's own shares speak the older two-level vocabulary; named with
 * the project ladder's words so one dialog does not teach two sets of terms.
 */
export const SESSION_ACCESS_OPTIONS: RoleOption<'READ' | 'WRITE'>[] = [
  { value: 'READ', label: 'Viewer', description: 'Reads the transcript' },
  { value: 'WRITE', label: 'Editor', description: 'Can also send messages' },
];

export const SCOPE_LABELS: Record<GrantScope, string> = {
  tasks: 'Tasks',
  sessions: 'Sessions',
  automations: 'Automations',
};

/**
 * Every scope, in the order they are always listed. A share link names the
 * same parts of a project with the same words, so it reads this list too.
 */
export const SCOPE_ORDER: GrantScope[] = ['tasks', 'sessions', 'automations'];

export function roleLabel(role: string): string {
  if (role === 'owner') return 'Owner';
  return (
    GRANT_ROLE_OPTIONS.find((o) => o.value === role)?.label ??
    SESSION_ACCESS_OPTIONS.find((o) => o.value === role)?.label ??
    role
  );
}

/**
 * The scopes as a phrase, in canonical order: "Tasks", "Tasks and sessions",
 * "Tasks, sessions and automations". Empty for no scopes.
 */
export function scopeSummary(scopes: readonly GrantScope[]): string {
  const words = SCOPE_ORDER.filter((s) => scopes.includes(s)).map((s, i) =>
    i === 0 ? SCOPE_LABELS[s] : SCOPE_LABELS[s].toLowerCase(),
  );
  if (words.length <= 1) return words[0] ?? '';
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

/**
 * Toggle one scope, refusing to leave none: a grant with no scope would be a
 * row that confers nothing, and the backend rejects it anyway. Returns the
 * input unchanged when the toggle would empty it.
 */
export function toggleScope(scopes: GrantScope[], scope: GrantScope): GrantScope[] {
  const next = scopes.includes(scope)
    ? scopes.filter((s) => s !== scope)
    : [...scopes, scope];
  if (next.length === 0) return scopes;
  return SCOPE_ORDER.filter((s) => next.includes(s));
}

export type GrantAction = 'invite' | 'change' | 'remove';

/**
 * What to say when a grant write is refused over `automations`, or null for
 * any other failure. Automations joined the scopes after grants existed, so an
 * admin whose own grant predates it administers tasks and sessions but not
 * automations: the server answers 403 when they hand that scope out, or change
 * or remove a grant that carries it. `scopes` are the ones the write touched
 * (the grant's current scopes plus any it asked for). Its generic "Requires
 * admin access" would read as though they could not manage people at all.
 */
export function automationsDeniedMessage(
  err: unknown,
  scopes: readonly GrantScope[],
  action: GrantAction,
): string | null {
  if (!(err instanceof Error)) return null;
  if ((err as { status?: unknown }).status !== 403) return null;
  if (!scopes.includes('automations')) return null;
  const lead = "Your access doesn't include this project's automations, so you can't";
  if (action === 'invite') return `${lead} share them. Untick Automations and try again.`;
  return `${lead} ${action} access that covers them.`;
}

/** Loose on purpose: the server is the judge, this only catches "forgot the @". */
export function looksLikeEmail(text: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text.trim());
}

export interface PersonLines {
  primary: string;
  secondary: string | null;
}

/**
 * The two lines of a People row. A name when there is one, else the address
 * the backend sent (only an admin ever receives it), else a neutral label.
 * A team reads "Team · n members" underneath.
 */
export function personLines(person: ProjectPerson): PersonLines {
  const name = person.principal.name?.trim() || null;
  if (person.principal.type === 'team') {
    const n = person.member_count ?? 0;
    return {
      primary: name ?? 'Team',
      secondary: `Team · ${n} ${n === 1 ? 'member' : 'members'}`,
    };
  }
  if (person.pending) {
    return {
      primary: person.email ?? 'Pending invite',
      secondary: 'Pending, joins when they sign up',
    };
  }
  return {
    primary: name ?? person.email ?? 'Vicoa user',
    secondary: name ? person.email : null,
  };
}

export function sessionShareLines(share: SessionShare): PersonLines {
  const name = share.display_name?.trim() || null;
  if (share.principal_type === 'team') {
    const n = share.member_count ?? 0;
    return {
      primary: name ?? 'Team',
      secondary: `Team · ${n} ${n === 1 ? 'member' : 'members'}`,
    };
  }
  if (share.invited) {
    return {
      primary: share.email ?? 'Pending invite',
      secondary: 'Pending, joins when they sign up',
    };
  }
  return { primary: name ?? share.email ?? 'Vicoa user', secondary: name ? share.email : null };
}

/**
 * What to say after an invite. Honest about mail: a self-hosted server with
 * no mail transport still creates the grant, so the inviter has to tell the
 * person themselves.
 */
export function inviteOutcome(created: ProjectGrantCreated): string {
  const who = created.principal.name?.trim() || created.email || 'them';
  if (created.principal.type === 'team') return `Shared with ${who}.`;
  if (created.email_sent) return `Invite sent to ${created.email ?? who}.`;
  return `Added ${who}. This server can't send email, so let them know it's under Shared with me once they sign in.`;
}

/** People on a project who can reach its sessions, owner excluded. */
export function sessionReach(people: ProjectPerson[]): ProjectPerson[] {
  return people.filter((p) => !p.is_owner && p.scopes.includes('sessions'));
}

/**
 * How many people a set of grants reaches: one per person, a team's members
 * for a team. Approximate by design (someone in two teams counts twice); it
 * is a sense of scale for the session dialog, not an audit.
 */
export function reachCount(people: ProjectPerson[]): number {
  return people.reduce(
    (n, p) => n + (p.principal.type === 'team' ? (p.member_count ?? 0) : 1),
    0,
  );
}
