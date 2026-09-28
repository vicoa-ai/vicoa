'use client';

// Who a project is shared with, as a small avatar stack beside the Tasks
// header's Share button (collaboration §8.4, P5). Renders nothing until the
// project has at least one grant, so a solo board looks exactly as before.
// A click opens the share dialog on its People tab.
//
// Only a project admin (on both scopes) can list grants, and the Share button
// it sits beside is admin-only too; for anyone else the list 403s and this
// stays empty.

import { useEffect, useState } from 'react';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type BackendAPI from '@/lib/backend-api';
import type { ProjectPerson } from '@/lib/backend-api';
import { principalFromResponse } from '@/lib/principals';
import { personLines } from '@/lib/share-people';
import { cn } from '@/lib/utils';

const SHOWN = 3;

export function ProjectPeopleStack({
  api,
  projectId,
  version,
  onOpen,
  className,
}: {
  api: BackendAPI | null;
  projectId: string;
  /** Bump to refetch (after the dialog changed a grant). */
  version: number;
  onOpen: () => void;
  className?: string;
}) {
  const [people, setPeople] = useState<ProjectPerson[]>([]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .listProjectPeople(projectId)
      .then((rows) => {
        if (!cancelled) setPeople(rows.filter((p) => !p.is_owner));
      })
      .catch(() => {
        if (!cancelled) setPeople([]);
      });
    return () => {
      cancelled = true;
    };
  }, [api, projectId, version]);

  if (people.length === 0) return null;
  const extra = people.length - SHOWN;
  const names = people.map((p) => personLines(p).primary).join(', ');

  return (
    <button
      type="button"
      onClick={onOpen}
      title={`Shared with ${names}`}
      aria-label={`Shared with ${people.length} ${people.length === 1 ? 'person or team' : 'people and teams'}`}
      className={cn(
        'flex cursor-pointer items-center rounded-full outline-none focus-visible:ring-1 focus-visible:ring-ring',
        className,
      )}
    >
      <span className="flex -space-x-1.5">
        {people.slice(0, SHOWN).map((person) => (
          <PrincipalAvatar
            key={person.id ?? personLines(person).primary}
            principal={principalFromResponse(person.principal) ?? { type: 'user' }}
            size="sm"
            className="size-5 ring-2 ring-background"
            title={personLines(person).primary}
          />
        ))}
      </span>
      {extra > 0 && <span className="ml-1 text-[11px] text-muted-foreground">+{extra}</span>}
    </button>
  );
}
