'use client';

// The public share page's client island (collaboration §8.4): picks the
// kind-specific composition — each one is the share shell (sidebar + main
// pane) around its body. The server component already resolved the share
// once (for the OG tags and first paint); everything live below this line
// polls.

import { Suspense, useCallback, useState } from 'react';
import type { PublicSessionSummary, PublicShareResponse } from '@/lib/backend-api';
import { ShareShell, ShareSidebarSection } from './share-shell';
import { SharedSessionView } from './shared-session-view';
import { ProjectShare, SharedSessionRow } from './shared-project-view';

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
      token={token}
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
        openHref={isOwnerViewing(share) ? `/dashboard/sessions/${initial.id}` : null}
        onSessionChange={onSessionChange}
      />
    </ShareShell>
  );
}

export function ShareViewer({ token, share }: { token: string; share: PublicShareResponse }) {
  if (share.kind === 'session' && share.session) {
    return <SessionShare token={token} share={share} initial={share.session} />;
  }
  if (share.kind === 'project' && share.project) {
    return (
      // useSearchParams needs a Suspense boundary for prerender.
      <Suspense fallback={null}>
        <ProjectShare token={token} share={share} project={share.project} />
      </Suspense>
    );
  }
  return null;
}
