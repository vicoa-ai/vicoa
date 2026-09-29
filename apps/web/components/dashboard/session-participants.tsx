'use client';

// Who is in a session (collaboration §8.2): the stack beside its title,
// the byline over a prompt, and the faces on its sidebar row. Faces appear
// only in a session more than one person has written in — one's own or
// someone else's — so a session one person writes in looks exactly as it
// always has. The one thing the title adds otherwise is "View only", on a
// session shared with someone who cannot send.

import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { PrincipalResponse, ProjectRole } from '@/lib/backend-api';
import { principalDisplayName, principalFromResponse } from '@/lib/principals';
import { roleLabel } from '@/lib/share-people';

const MAX_SHOWN = 4;

export function SessionParticipants({
  participants,
  owner,
  viewerRole,
  canPrompt,
}: {
  participants: PrincipalResponse[];
  /** Set only when the viewer does not own the session. */
  owner: PrincipalResponse | null | undefined;
  viewerRole: ProjectRole | null | undefined;
  canPrompt: boolean;
}) {
  const shared = !!owner;
  const people = participants.length > 1 ? participants : [];
  const viewOnly = shared && !canPrompt;
  if (people.length === 0 && !viewOnly) return null;

  const shown = people.slice(0, MAX_SHOWN);
  const hidden = people.length - shown.length;
  const names = people.map((p) => principalDisplayName(principalFromResponse(p))).join(', ');
  const ownerName = owner ? principalDisplayName(principalFromResponse(owner)) : null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex flex-shrink-0 cursor-default items-center gap-1.5">
          {shown.length > 0 && (
            <span className="flex items-center -space-x-1">
              {shown.map((person, index) => (
                <PrincipalAvatar
                  key={person.id ?? `p${index}`}
                  principal={principalFromResponse(person) ?? { type: 'user' }}
                  size="xs"
                  className="ring-1 ring-background"
                />
              ))}
              {hidden > 0 && (
                <span className="flex size-4 items-center justify-center rounded-full bg-muted text-[8px] text-muted-foreground ring-1 ring-background">
                  +{hidden}
                </span>
              )}
            </span>
          )}
          {viewOnly && <span className="text-xs text-muted-foreground">View only</span>}
        </span>
      </TooltipTrigger>
      <TooltipContent align="start">
        {shared && ownerName && (
          <p>
            Shared by {ownerName}
            {viewerRole ? ` (you: ${roleLabel(viewerRole)})` : ''}
          </p>
        )}
        {people.length > 0 && <p>In this session: {names}</p>}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Name and face over the first prompt of a run by one person (see
 * `transcriptBylines`). Right-aligned like the bubble it heads, with the
 * avatar on the outer edge so a column of prompts lines their faces up.
 */
export function MessageByline({ person }: { person: PrincipalResponse }) {
  const principal = principalFromResponse(person) ?? { type: 'user' as const };
  return (
    <span className="flex max-w-full items-center gap-1.5 px-1">
      <span className="truncate text-xs font-medium text-muted-foreground">
        {principalDisplayName(principal)}
      </span>
      <PrincipalAvatar principal={principal} size="sm" />
    </span>
  );
}

const ROW_MAX_SHOWN = 3;

/**
 * The people in a session, on its sidebar row (see `sessionRowPeople`): up to
 * three overlapping faces, then a count. Renders nothing for an empty list,
 * which is every session one person writes in.
 */
export function SessionRowAvatars({ people }: { people: PrincipalResponse[] }) {
  if (people.length === 0) return null;
  const shown = people.slice(0, ROW_MAX_SHOWN);
  const hidden = people.length - shown.length;
  const names = people.map((p) => principalDisplayName(principalFromResponse(p))).join(', ');
  return (
    <span className="flex shrink-0 items-center -space-x-1" title={names} aria-label={names}>
      {shown.map((person, index) => (
        <PrincipalAvatar
          key={person.id ?? `p${index}`}
          principal={principalFromResponse(person) ?? { type: 'user' }}
          size="xs"
          className="ring-1 ring-background"
        />
      ))}
      {hidden > 0 && (
        <span className="flex size-4 items-center justify-center rounded-full bg-muted text-[8px] text-muted-foreground ring-1 ring-background">
          +{hidden}
        </span>
      )}
    </span>
  );
}
