import type { ReferenceCandidate, ReferenceKind } from '@/lib/backend-api';

// A `#` reference kept in stored markdown (a task description) is a link, not
// a bare `#VIC-42`: the chat composer can carry the referenced id beside the
// text until it sends, but a description is only its text. So the token is the
// link's text and the page is its destination, `[#VIC-42](/dashboard/tasks/…)`.
// The id survives a renamed task or a re-keyed project, sessions and
// automations (whose tokens are title slugs) work the same way, and an agent
// reading the raw markdown sees both the token and the id.

/** The page a reference opens: where cmd+K takes the same item. */
export function referenceHref(kind: ReferenceKind, id: string): string {
  switch (kind) {
    case 'task':
      return `/dashboard/tasks/${id}`;
    case 'session':
      return `/dashboard/sessions/${id}`;
    case 'automation':
      return `/dashboard/automation?automation=${id}`;
  }
}

const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const APP_LINK = new RegExp(
  `^/dashboard/(?:tasks/${UUID}|sessions/${UUID}|automation\\?automation=${UUID})$`,
  'i',
);

/**
 * Is `href` exactly one of {@link referenceHref}'s pages? Such a link stays in
 * the app (client-side navigation) instead of opening a browser tab, and in
 * message markdown it must not be mistaken for an absolute file path. Matched
 * exactly, so `/dashboard/anything-else` keeps whatever meaning it had.
 */
export function isReferenceHref(href: string): boolean {
  return APP_LINK.test(href);
}

/** A pick as markdown source, for a field that holds markdown as plain text
 *  (the task dialog's textarea): `[#VIC-42](/dashboard/tasks/…)`. */
export function referenceMarkdown(item: Pick<ReferenceCandidate, 'kind' | 'id' | 'token'>): string {
  const label = `#${item.token}`.replace(/[\\[\]]/g, '\\$&');
  return `[${label}](${referenceHref(item.kind, item.id)})`;
}
