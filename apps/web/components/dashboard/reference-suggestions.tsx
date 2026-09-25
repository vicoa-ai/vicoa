'use client';

import { CalendarClock, MessageCircle } from 'lucide-react';
import type { ReferenceCandidate, ReferenceKind, TaskStatus } from '@/lib/backend-api';
import { ProjectIcon, StatusIcon } from '@/components/dashboard/task-ui';
import { StartEllipsisText } from '@/components/ui/start-ellipsis-text';

const GROUP_LABEL: Record<ReferenceKind, string> = {
  session: 'Sessions',
  task: 'Tasks',
  automation: 'Automations',
};

function KindIcon({ item }: { item: ReferenceCandidate }) {
  if (item.kind === 'task') {
    return (
      <StatusIcon
        status={(item.status ?? 'backlog') as TaskStatus}
        className="h-3.5 w-3.5 shrink-0"
      />
    );
  }
  if (item.kind === 'automation') {
    return <CalendarClock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  }
  return <MessageCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
}

/**
 * The row's trailing slot: where this thing lives.
 *
 * A resolved project shows its icon and name, clipped at the end like any
 * name. The fallback — a session or automation in a folder no project is set
 * up for — is a raw path, where the tail carries the meaning, so it
 * ellipsizes from the front instead.
 */
function RowMeta({ item }: { item: ReferenceCandidate }) {
  if (!item.meta) return null;
  if (item.project) {
    return (
      <span className="flex min-w-0 max-w-[45%] items-center gap-1.5 text-xs text-muted-foreground">
        <ProjectIcon
          // `ProjectIcon` treats a missing `updated_at` as "no cache-buster";
          // the DTO spells that as null.
          project={{ ...item.project, updated_at: item.project.updated_at ?? undefined }}
          className="size-3"
        />
        <span className="truncate">{item.meta}</span>
      </span>
    );
  }
  return (
    <span className="min-w-0 max-w-[45%] text-xs text-muted-foreground">
      <StartEllipsisText value={item.meta} />
    </span>
  );
}

/**
 * Rows for the composer's `#` panel.
 *
 * One flat keyboard list with a heading wherever `kind` changes — the server
 * already returns the items kind-ordered, so the arrow keys only ever walk a
 * single array and the caller keeps one `selectedIndex`.
 */
export function ReferenceSuggestions({
  items,
  selectedIndex,
  isLoading,
  onSelect,
  onHover,
  listRef,
}: {
  items: ReferenceCandidate[];
  selectedIndex: number;
  isLoading: boolean;
  onSelect: (item: ReferenceCandidate) => void;
  onHover: (index: number) => void;
  listRef?: React.RefObject<HTMLDivElement | null>;
}) {
  if (items.length === 0) {
    return (
      <div ref={listRef} className="px-4 py-3 text-xs text-muted-foreground">
        {isLoading ? 'Searching…' : 'No sessions, tasks or automations match'}
      </div>
    );
  }

  return (
    <div ref={listRef}>
      {items.map((item, index) => {
        const isSelected = index === selectedIndex;
        const startsGroup = index === 0 || items[index - 1].kind !== item.kind;
        return (
          <div key={`${item.kind}:${item.id}`}>
            {startsGroup && (
              <div className="px-4 pb-1 pt-2 text-[0.8rem] font-normal text-muted-foreground">
                {GROUP_LABEL[item.kind]}
              </div>
            )}
            <button
              type="button"
              onClick={() => onSelect(item)}
              onMouseEnter={() => onHover(index)}
              className={`flex w-full cursor-pointer items-center gap-2.5 px-4 py-2 text-left transition-colors duration-150 ${
                isSelected ? 'bg-primary/10' : 'hover:bg-accent/40'
              }`}
            >
              <KindIcon item={item} />
              <span className="min-w-0 flex-1 truncate text-sm">{item.label}</span>
              <RowMeta item={item} />
              {/* With the "#", because the key IS the token this row types. */}
              {item.identifier && (
                <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                  #{item.identifier}
                </span>
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
