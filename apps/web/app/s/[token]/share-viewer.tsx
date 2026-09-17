'use client';

// The public share page's client island (collaboration §8.4): the
// "Shared read-only via Vicoa" chrome with the sign-up CTA — this is the
// growth loop — over the kind-specific body. The server component already
// resolved the share once (for the OG tags and first paint); everything live
// below this line polls.

import Image from 'next/image';
import Link from 'next/link';
import { Suspense } from 'react';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { Button } from '@/components/ui/button';
import { principalFromResponse } from '@/lib/principals';
import type { PublicShareResponse } from '@/lib/backend-api';
import { SharedSessionView } from './shared-session-view';
import { SharedProjectSessionsView } from './shared-project-sessions-view';
import { SharedBoardView } from './shared-board-view';

export function ShareViewer({ token, share }: { token: string; share: PublicShareResponse }) {
  const owner = principalFromResponse(share.owner);
  const signedIn = share.viewer !== null;
  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background text-foreground">
      <header className="flex shrink-0 items-center gap-3 border-b border-border/60 bg-muted/30 px-4 py-2">
        <Link href="/" className="flex shrink-0 items-center" aria-label="Vicoa">
          <Image src="/images/vicoa-logo-text.webp" alt="Vicoa" width={0} height={0} sizes="100vw" className="h-6 w-auto" priority />
        </Link>
        <div className="flex min-w-0 flex-1 items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden sm:inline">Shared read-only via Vicoa</span>
          {owner && (
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <span className="hidden sm:inline">by</span>
              <PrincipalAvatar principal={owner} size="xs" />
              <span className="truncate">{owner.name ?? 'a Vicoa user'}</span>
            </span>
          )}
        </div>
        <Button asChild size="sm" variant={signedIn ? 'outline' : 'default'} className="h-7 text-xs">
          <Link href={signedIn ? '/dashboard' : '/sign-up'}>
            {signedIn ? 'Open Vicoa' : 'Run agents like this — free'}
          </Link>
        </Button>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        {share.kind === 'session' && share.session && (
          <SharedSessionView token={token} initialSession={share.session} />
        )}
        {share.kind === 'project_sessions' && share.project && (
          // useSearchParams needs a Suspense boundary for prerender.
          <Suspense fallback={null}>
            <SharedProjectSessionsView token={token} project={share.project} />
          </Suspense>
        )}
        {share.kind === 'project_board' && share.project && <SharedBoardView token={token} share={share} />}
      </main>
    </div>
  );
}
