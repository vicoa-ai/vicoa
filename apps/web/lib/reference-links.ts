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
  `^/dashboard/(?:(tasks)/(${UUID})|(sessions)/(${UUID})|(automation)\\?automation=(${UUID}))$`,
  'i',
);
const KIND_OF_SEGMENT: Record<string, ReferenceKind> = {
  tasks: 'task',
  sessions: 'session',
  automation: 'automation',
};

/** What a {@link referenceHref} page points at, or null for any other href. */
export function parseReferenceHref(href: string): { kind: ReferenceKind; id: string } | null {
  const m = APP_LINK.exec(href);
  if (!m) return null;
  const segment = (m[1] ?? m[3] ?? m[5]).toLowerCase();
  const id = (m[2] ?? m[4] ?? m[6]).toLowerCase();
  return { kind: KIND_OF_SEGMENT[segment], id };
}

/**
 * Is `href` exactly one of {@link referenceHref}'s pages? Such a link stays in
 * the app (client-side navigation) instead of opening a browser tab, and in
 * message markdown it must not be mistaken for an absolute file path. Matched
 * exactly, so `/dashboard/anything-else` keeps whatever meaning it had.
 */
export function isReferenceHref(href: string): boolean {
  return APP_LINK.test(href);
}

/** A reference as markdown: `[<label>](<page>)`, the label escaped so a `]`
 *  in it can't end the link text early. */
export function referenceLinkMarkdown(kind: ReferenceKind, id: string, label: string): string {
  return `[${label.replace(/[\\[\]]/g, '\\$&')}](${referenceHref(kind, id)})`;
}

/** A pick as markdown source, for a field that holds markdown as plain text
 *  (the task dialog's textarea): `[#VIC-42](/dashboard/tasks/…)`. */
export function referenceMarkdown(item: Pick<ReferenceCandidate, 'kind' | 'id' | 'token'>): string {
  return referenceLinkMarkdown(item.kind, item.id, `#${item.token}`);
}
