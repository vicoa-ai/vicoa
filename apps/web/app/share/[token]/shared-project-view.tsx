'use client';

// A shared project: one link, one page, carrying whichever halves the link
// says (`share.scopes`). Tasks are the sidebar's Tasks row — the dashboard's
// own nav row, standing in for its page — and sessions are the list below it,
// in the dashboard's time buckets, newest first. Both are deep-linkable
// (`?view=tasks`, `?session=<id>`), and the page opens on something rather
// than on a "pick one" pane: the tasks when it carries them, else the newest
// session. The session list polls slowly: new sessions matter on the order of
// minutes, not seconds.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { SnakeLoader } from '@/components/dashboard/snake-loader';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { formatSidebarTime } from '@/components/dashboard/session-display';
import { parseUTCTimestamp } from '@/lib/message-grouping';
import type { PublicProjectSummary, PublicSessionSummary, PublicShareResponse } from '@/lib/backend-api';
import { ShareNotFoundError, fetchPublicSession, fetchPublicSessions } from '@/lib/public-share-api';
import { cn } from '@/lib/utils';
import { SHARE_ROW_SELECTED, ShareHeader, ShareShell, ShareSidebarSection, useShareChrome } from './share-shell';
import { SharedBoardView } from './shared-board-view';
import { SharedSessionView, isSessionLive } from './shared-session-view';
import { POLL_IDLE_MS, useSharePoll } from './use-share-poll';

const PAGE_SIZE = 50;

/** The dashboard sidebar's time buckets (Today / Yesterday / Last 7 days / …), on the same clock. */
function groupByTime(sessions: PublicSessionSummary[]): { label: string; items: PublicSessionSummary[] }[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const buckets: { label: string; from: number }[] = [
    { label: 'Today', from: startOfToday },
    { label: 'Yesterday', from: startOfToday - 86400000 },
    { label: 'Last 7 days', from: startOfToday - 6 * 86400000 },
    { label: 'Last 30 days', from: startOfToday - 29 * 86400000 },
    { label: 'Older', from: Number.NEGATIVE_INFINITY },
  ];
  const groups = buckets.map((b) => ({ label: b.label, items: [] as PublicSessionSummary[] }));
  for (const session of sessions) {
    const t = parseUTCTimestamp(session.latest_message_at || session.started_at).getTime();
    const index = buckets.findIndex((b) => t >= b.from);
    groups[index === -1 ? groups.length - 1 : index].items.push(session);
  }
  return groups.filter((g) => g.items.length > 0);
}

/** One sidebar row — the dashboard row's silhouette: agent mark, title, relative time. */
export function SharedSessionRow({
  session,
  selected,
  onClick,
}: {
  session: PublicSessionSummary;
  selected: boolean;
  onClick?: () => void;
}) {
  // Picking a row on a phone should also put the drawer away.
  const { closeSidebar } = useShareChrome();
  return (
    <button
      type="button"
      onClick={() => {
        onClick?.();
        closeSidebar();
      }}
      aria-current={selected ? 'page' : undefined}
      className={cn(
        'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted/60',
        selected && SHARE_ROW_SELECTED,
      )}
    >
      {isSessionLive(session) ? (
        <SnakeLoader size={13} />
      ) : (
        <SessionAgentIcon agentTypeName={session.agent_type_name} status={session.status} size={14} />
      )}
      <span className="min-w-0 flex-1 truncate">{session.name || 'Untitled session'}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {formatSidebarTime({ latest_message_at: session.latest_message_at, started_at: session.started_at })}
      </span>
    </button>
  );
}

/** The project's shared session list, polled slowly, plus the deep-linked
 * selection. `token` is null when the link does not carry sessions: nothing is
 * fetched, and the page is the board alone. */
function useSharedSessions(token: string | null) {
  const [sessions, setSessions] = useState<PublicSessionSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<'gone' | 'error' | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const page = await fetchPublicSessions(token, { limit: PAGE_SIZE });
      setSessions((prev) => {
        // Keep pages the reader already scrolled to; refresh the first one.
        if (!prev || prev.length <= page.items.length) return page.items;
        const seen = new Set(page.items.map((s) => s.id));
        return [...page.items, ...prev.filter((s) => !seen.has(s.id))];
      });
      setTotal(page.total);
      setError(null);
    } catch (err) {
      setError(err instanceof ShareNotFoundError ? 'gone' : 'error');
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);
  useSharePoll(load, { intervalMs: POLL_IDLE_MS, enabled: token !== null });

  const loadMore = useCallback(async () => {
    if (!token || !sessions || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await fetchPublicSessions(token, { limit: PAGE_SIZE, offset: sessions.length });
      setSessions((prev) => {
        const seen = new Set((prev ?? []).map((s) => s.id));
        return [...(prev ?? []), ...page.items.filter((s) => !seen.has(s.id))];
      });
      setTotal(page.total);
    } catch {
      // The button stays; the next click retries.
    } finally {
      setLoadingMore(false);
    }
  }, [sessions, loadingMore, token]);

  /** Fold a fresher summary (from the open session's own poll) into the list. */
  const patch = useCallback((summary: PublicSessionSummary) => {
    setSessions((prev) => prev?.map((s) => (s.id === summary.id ? summary : s)) ?? prev);
  }, []);

  return { sessions, total, loadingMore, error, loadMore, patch };
}

export function ProjectShare({
  token,
  share,
  project,
}: {
  token: string;
  share: PublicShareResponse;
  project: PublicProjectSummary;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sharesTasks = share.scopes.includes('tasks');
  const sharesSessions = share.scopes.includes('sessions');
  const requestedId = sharesSessions ? searchParams.get('session') : null;
  // Tasks is the default view when the link carries them: it is the project's
  // overview, and the sessions are one click away in the same sidebar.
  const viewingTasks = sharesTasks && (!sharesSessions || searchParams.get('view') === 'tasks' || !requestedId);
  const { sessions, total, loadingMore, error, loadMore, patch } = useSharedSessions(
    sharesSessions ? token : null,
  );

  // Newest by default: a project link should open on something, not on a
  // "pick one" pane. Chosen once, when the list first arrives — a newer
  // session landing on a later poll must not yank the reader off the one they
  // are in. The URL is only rewritten when the visitor picks.
  const [defaultId, setDefaultId] = useState<string | null>(null);
  useEffect(() => {
    if (defaultId === null && sessions && sessions.length > 0) setDefaultId(sessions[0].id);
  }, [defaultId, sessions]);
  const selectedId = viewingTasks ? null : (requestedId ?? defaultId);

  // The session behind `?session=` when it is not (or not yet) in the list.
  const [resolved, setResolved] = useState<PublicSessionSummary | null>(null);
  useEffect(() => {
    if (!selectedId) {
      setResolved(null);
      return;
    }
    if (sessions?.some((s) => s.id === selectedId)) return;
    let cancelled = false;
    fetchPublicSession(token, selectedId)
      .then((s) => {
        if (!cancelled) setResolved(s);
      })
      .catch(() => {
        if (!cancelled) setResolved(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, sessions, token]);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    return sessions?.find((s) => s.id === selectedId) ?? (resolved?.id === selectedId ? resolved : null);
  }, [selectedId, sessions, resolved]);

  const select = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete('view');
      params.set('session', id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  const selectTasks = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('session');
    params.set('view', 'tasks');
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [router, pathname, searchParams]);

  const groups = useMemo(() => groupByTime(sessions ?? []), [sessions]);
  const isOwner = share.viewer_is_owner;

  const sidebar = !sharesSessions ? null : (
    <ShareSidebarSection
      label={
        <>
          <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
          <span className="truncate">{project.name}</span>
          <span className="ml-auto shrink-0">{total || ''}</span>
        </>
      }
    >
      {error === 'gone' ? (
        <p className="px-2 py-1 text-[11px] text-muted-foreground">This share is no longer available.</p>
      ) : sessions === null ? (
        <div className="flex items-center gap-2 px-2 py-1 text-[11px] text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading…
        </div>
      ) : sessions.length === 0 ? (
        <p className="px-2 py-1 text-[11px] text-muted-foreground">No sessions to show yet.</p>
      ) : (
        <>
          {groups.map((group) => (
            <div key={group.label} className="mb-2">
              <div className="px-2 pb-0.5 pt-1 text-[10px] text-muted-foreground/70">{group.label}</div>
              <ul className="grid gap-px">
                {group.items.map((session) => (
                  <li key={session.id}>
                    <SharedSessionRow session={session} selected={session.id === selectedId} onClick={() => select(session.id)} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {sessions.length < total && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full text-[11px] text-muted-foreground"
              onClick={() => void loadMore()}
              disabled={loadingMore}
            >
              {loadingMore ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
              Show more
            </Button>
          )}
          {error === 'error' && (
            <p className="px-2 py-1 text-[11px] text-muted-foreground">Updates paused: connection problem.</p>
          )}
        </>
      )}
    </ShareSidebarSection>
  );

  const tasksNav = sharesTasks ? { active: viewingTasks, onSelect: selectTasks } : undefined;
  const openBoardHref = isOwner ? '/dashboard/tasks' : null;

  return (
    <ShareShell token={token} share={share} sidebar={sidebar} tasksNav={tasksNav}>
      {viewingTasks ? (
        <SharedBoardView token={token} share={share} openHref={openBoardHref} />
      ) : selected ? (
        <SharedSessionView
          key={selected.id}
          token={token}
          initialSession={selected}
          openHref={isOwner ? `/dashboard/agents/${selected.id}` : null}
          onSessionChange={patch}
        />
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          <ShareHeader>
            <div className="flex min-w-0 items-center gap-2">
              <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
              <h1 className="min-w-0 truncate font-mono text-sm font-normal">{project.name}</h1>
            </div>
          </ShareHeader>
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
            {error === 'gone' ? (
              <div className="space-y-1">
                <p>This share is no longer available.</p>
                <p className="text-xs">The link may have been revoked or expired.</p>
              </div>
            ) : sessions === null ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : sessions.length === 0 ? (
              'No sessions to show yet.'
            ) : (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
          </div>
        </div>
      )}
    </ShareShell>
  );
}
