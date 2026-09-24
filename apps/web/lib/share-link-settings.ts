// The pure half of the share dialog's settings: what a link's mutable settings
// are, how a link seeds the form, and how the two are compared.
//
// It lives out here because the dialog's live settings save on the *difference*
// between the form and the link — no Save button — so "these two say the same
// thing" is load-bearing: a comparison that reports a phantom difference would
// have the panel saving in a loop. That deserves a test, and a test deserves a
// module it can import without mounting React.

import type {
  ShareAudience,
  ShareBoardFilters,
  ShareLinkResponse,
  ShareProjectFilters,
  ShareScope,
  ShareSessionsFilters,
  TaskStatus,
} from '@/lib/backend-api';

/** The two halves of a project, in the order they are always listed. */
export const SCOPE_ORDER: ShareScope[] = ['tasks', 'sessions'];

/**
 * "Keep the deadline this link already has". `expires_at` is a date and the
 * picker speaks in "in N days", so an existing expiry cannot be shown as one of
 * those options without guessing which one minted it — it is offered as itself
 * instead, and saving simply omits the field.
 */
export const KEEP_EXPIRY = 'keep';

/**
 * What "include archived sessions" sends: the statuses a link shows by default
 * are everything but archived, so asking for archived means naming them all.
 * DELETED is never shareable and is not in the list.
 */
const EVERY_SESSION_STATUS: ShareSessionsFilters['statuses'] = [
  'STARTING',
  'ACTIVE',
  'AWAITING_INPUT',
  'REVIEWED',
  'PAUSED',
  'STALE',
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DISCONNECTED',
];

/** The filter half of the form: the fields the dialog holds as separate state. */
export interface ShareFilterFields {
  statuses: TaskStatus[];
  labelIds: string[];
  includeArchived: boolean;
  /** `YYYY-MM-DD`, as the date pills speak it. */
  dateFrom: string;
  dateTo: string;
}

/** What a link (or nothing, for a fresh one) seeds those fields to. */
export function filterFieldsFromLink(link: ShareLinkResponse | null): ShareFilterFields {
  const tasks = link?.filters?.tasks;
  const sessions = link?.filters?.sessions;
  return {
    statuses: tasks?.statuses ?? [],
    labelIds: tasks?.label_ids ?? [],
    includeArchived: Boolean(sessions?.statuses?.length),
    dateFrom: sessions?.date_from?.slice(0, 10) ?? '',
    dateTo: sessions?.date_to?.slice(0, 10) ?? '',
  };
}

/**
 * The filters the form describes; `null` = no narrowing. Each half is dropped
 * unless the link carries that scope, which is also what the server does with
 * the value it is sent.
 */
export function buildShareFilters(
  form: ShareFilterFields & { scopes: ShareScope[] },
): ShareProjectFilters | null {
  const filters: ShareProjectFilters = {};
  if (form.scopes.includes('tasks')) {
    const tasks: ShareBoardFilters = {};
    if (form.statuses.length) tasks.statuses = form.statuses;
    if (form.labelIds.length) tasks.label_ids = form.labelIds;
    if (Object.keys(tasks).length) filters.tasks = tasks;
  }
  if (form.scopes.includes('sessions')) {
    const sessions: ShareSessionsFilters = {};
    if (form.includeArchived) sessions.statuses = EVERY_SESSION_STATUS;
    if (form.dateFrom) sessions.date_from = `${form.dateFrom}T00:00:00Z`;
    if (form.dateTo) sessions.date_to = `${form.dateTo}T23:59:59Z`;
    if (Object.keys(sessions).length) filters.sessions = sessions;
  }
  return Object.keys(filters).length ? filters : null;
}

/** A link's mutable settings, apart from its deadline (see `formDiffersFromLink`). */
export interface ShareSettings {
  audience: ShareAudience;
  allow_comments: boolean;
  show_owner: boolean;
  show_branch: boolean;
  scopes: ShareScope[];
  filters: ShareProjectFilters | null;
}

/**
 * Those settings as one comparable string.
 *
 * Order- and format-independent on purpose: two filter lists that mean the same
 * thing must never read as a change. Dates compare by day, because the form only
 * ever speaks in whole days while the stored value is a timestamp.
 */
export function settingsKey(s: ShareSettings): string {
  const tasks = s.filters?.tasks;
  const sessions = s.filters?.sessions;
  return [
    s.audience,
    s.allow_comments ? 'comments' : '',
    s.show_owner ? 'owner' : '',
    s.show_branch ? 'branch' : '',
    SCOPE_ORDER.filter((scope) => s.scopes.includes(scope)).join(','),
    (tasks?.statuses ?? []).slice().sort().join(','),
    (tasks?.label_ids ?? []).slice().sort().join(','),
    sessions?.statuses?.length ? 'archived' : '',
    sessions?.date_from?.slice(0, 10) ?? '',
    sessions?.date_to?.slice(0, 10) ?? '',
  ].join('|');
}

/** The same string for what a link currently says. */
export function linkSettingsKey(link: ShareLinkResponse): string {
  return settingsKey({
    audience: link.audience,
    allow_comments: link.allow_comments,
    show_owner: link.show_owner,
    show_branch: link.show_branch,
    scopes: link.scopes,
    filters: link.filters,
  });
}

/**
 * Does this form say something the link does not?
 *
 * The deadline is compared apart from the rest because the form speaks in
 * durations and the link stores a date: `KEEP_EXPIRY` means "leave it alone",
 * and so does "never" on a link that never expires. Any other choice restates
 * the deadline from now, which is a change even when the date looks similar.
 */
export function formDiffersFromLink(
  link: ShareLinkResponse,
  form: ShareSettings,
  expiry: string,
): boolean {
  if (settingsKey(form) !== linkSettingsKey(link)) return true;
  return expiry !== KEEP_EXPIRY && !(expiry === 'never' && link.expires_at === null);
}
