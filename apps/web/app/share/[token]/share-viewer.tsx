'use client';

// The public share page's client island (collaboration §8.4): picks the
// kind-specific composition — each one is the share shell (sidebar + main
// pane) around its body. The server component already resolved the share
// once (for the OG tags and first paint); everything live below this line
// polls.

import { Suspense, useCallback, useState } from 'react';
import { KanbanSquare } from 'lucide-react';
import { ProjectIcon, STATUS_CONFIG } from '@/components/dashboard/task-ui';
import type { PublicSessionSummary, PublicShareResponse, ShareBoardFilters } from '@/lib/backend-api';
import { cn } from '@/lib/utils';
import { SHARE_ROW_SELECTED, ShareShell, ShareSidebarSection } from './share-shell';
import { SharedSessionView } from './shared-session-view';
import { ProjectSessionsShare, SharedSessionRow } from './shared-project-sessions-view';
import { SharedBoardView } from './shared-board-view';

function isOwnerViewing(share: PublicShareResponse): boolean {
  return share.viewer_is_owner;
}

/** A single shared session: the sidebar holds just that one row, selected. */
function SessionShare({ token, share, initial }: { token: string; share: PublicShareResponse; initial: PublicSessionSummary }) {
  // The main pane polls the summary; mirror it so the row follows the title
  // and live state instead of freezing at first paint.
  const [session, setSession] = useState(initial);
  const onSessionChange = useCallback((next: PublicSessionSummary) => setSession(next), []);
  return (
    <ShareShell
      share={share}
      sidebar={
        <ShareSidebarSection label="Workspace">
          <SharedSessionRow session={session} selected />
        </ShareSidebarSection>
      }
    >
      <SharedSessionView
        token={token}
        initialSession={initial}
        openHref={isOwnerViewing(share) ? `/dashboard/agents/${initial.id}` : null}
        onSessionChange={onSessionChange}
      />
    </ShareShell>
  );
}

/** A project's task board: the sidebar shows the project and the one nav row. */
function BoardShare({ token, share }: { token: string; share: PublicShareResponse }) {
  const project = share.project;
  const filters = (share.filters ?? null) as ShareBoardFilters | null;
  const statuses = filters?.statuses ?? [];
  const labelCount = filters?.label_ids?.length ?? 0;
  return (
    <ShareShell
      share={share}
      sidebar={
        project && (
          <ShareSidebarSection
            label={
              <>
                <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
                <span className="truncate">{project.name}</span>
              </>
            }
          >
            <div
              aria-current="page"
              className={cn('flex items-center gap-2 rounded-md px-2 py-1.5 text-xs', SHARE_ROW_SELECTED)}
            >
              <KanbanSquare className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Task board</span>
            </div>
            {(statuses.length > 0 || labelCount > 0) && (
              <div className="px-2 pt-1.5 text-[11px] text-muted-foreground">
                Showing{' '}
                {statuses.length > 0 ? statuses.map((s) => STATUS_CONFIG[s].label).join(', ') : 'every status'}
                {labelCount > 0 ? ` · ${labelCount} label${labelCount === 1 ? '' : 's'}` : ''}
              </div>
            )}
          </ShareSidebarSection>
        )
      }
    >
      <SharedBoardView token={token} share={share} openHref={isOwnerViewing(share) ? '/dashboard/tasks' : null} />
    </ShareShell>
  );
}

export function ShareViewer({ token, share }: { token: string; share: PublicShareResponse }) {
  if (share.kind === 'session' && share.session) {
    return <SessionShare token={token} share={share} initial={share.session} />;
  }
  if (share.kind === 'project_sessions' && share.project) {
    return (
      // useSearchParams needs a Suspense boundary for prerender.
      <Suspense fallback={null}>
        <ProjectSessionsShare token={token} share={share} project={share.project} />
      </Suspense>
    );
  }
  if (share.kind === 'project_board' && share.project) {
    return <BoardShare token={token} share={share} />;
  }
  return null;
}
