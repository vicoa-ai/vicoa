'use client';

// A project's shared sessions: the list, grouped by day, newest first. Picking
// one opens the transcript in place (deep-linkable via `?session=`), with a
// back button to the list. The list itself polls slowly — new sessions matter
// on the order of minutes, not seconds.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ChevronRight, GitBranch, Loader2, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { formatSidebarTime } from '@/components/dashboard/session-display';
import { formatDateGroup, parseUTCTimestamp } from '@/lib/message-grouping';
import type { PublicProjectSummary, PublicSessionSummary } from '@/lib/backend-api';
import {
  ShareNotFoundError,
  fetchPublicSession,
  fetchPublicSessions,
} from '@/lib/public-share-api';
import { SharedSessionView } from './shared-session-view';
import { POLL_IDLE_MS, useSharePoll } from './use-share-poll';

const PAGE_SIZE = 50;

function groupByDay(sessions: PublicSessionSummary[]): { label: string; items: PublicSessionSummary[] }[] {
  const groups: { label: string; items: PublicSessionSummary[] }[] = [];
  for (const session of sessions) {
    const label = formatDateGroup(parseUTCTimestamp(session.started_at));
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(session);
    else groups.push({ label, items: [session] });
  }
  return groups;
}

export function SharedProjectSessionsView({
  token,
  project,
}: {
  token: string;
  project: PublicProjectSummary;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get('session');

  const [sessions, setSessions] = useState<PublicSessionSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<'gone' | 'error' | null>(null);
  // The session behind `?session=` when it is not (or not yet) in the list.
  const [selected, setSelected] = useState<PublicSessionSummary | null>(null);

  const load = useCallback(async () => {
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
  useSharePoll(load, { intervalMs: POLL_IDLE_MS, enabled: selectedId === null });

  const loadMore = useCallback(async () => {
    if (!sessions || loadingMore) return;
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

  // Resolve a deep-linked session that the list does not hold.
  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    const fromList = sessions?.find((s) => s.id === selectedId) ?? null;
    if (fromList) {
      setSelected(fromList);
      return;
    }
    let cancelled = false;
    fetchPublicSession(token, selectedId)
      .then((s) => {
        if (!cancelled) setSelected(s);
      })
      .catch(() => {
        if (!cancelled) setSelected(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, sessions, token]);

  const select = useCallback(
    (id: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set('session', id);
      else params.delete('session');
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  const groups = useMemo(() => groupByDay(sessions ?? []), [sessions]);

  if (selectedId && selected) {
    return <SharedSessionView token={token} initialSession={selected} onBack={() => select(null)} />;
  }

  return (
    <div className="custom-scrollbar flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-2">
        <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
        <h2 className="truncate text-sm font-medium">{project.name}</h2>
        <span className="text-[11px] text-muted-foreground">
          {total} session{total === 1 ? '' : 's'}
        </span>
      </div>

      {error === 'gone' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-muted-foreground">
          <p>This share is no longer available.</p>
          <p className="text-xs">The link may have been revoked or expired.</p>
        </div>
      ) : sessions === null ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
          No sessions to show yet.
        </div>
      ) : (
        <div className="mx-auto w-full max-w-3xl px-4 py-3">
          {groups.map((group) => (
            <div key={group.label} className="mb-4">
              <div className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </div>
              <ul className="grid gap-0.5">
                {group.items.map((session) => (
                  <li key={session.id}>
                    <button
                      type="button"
                      onClick={() => select(session.id)}
                      className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted"
                    >
                      <SessionAgentIcon agentTypeName={session.agent_type_name} status={session.status} size={16} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm">{session.name || 'Untitled session'}</div>
                        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                          <span>{session.agent_profile?.name ?? session.agent_type_name}</span>
                          {session.worktree_name && (
                            <span className="inline-flex items-center gap-0.5">
                              <GitBranch className="h-3 w-3" />
                              {session.worktree_name}
                            </span>
                          )}
                          <span className="inline-flex items-center gap-0.5">
                            <MessageSquare className="h-3 w-3" />
                            {session.message_count}
                          </span>
                        </div>
                      </div>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {formatSidebarTime({ latest_message_at: session.latest_message_at, started_at: session.started_at })}
                      </span>
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {sessions.length < total && (
            <div className="flex justify-center py-2">
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => void loadMore()} disabled={loadingMore}>
                {loadingMore ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
                Show more
              </Button>
            </div>
          )}
          {error === 'error' && (
            <p className="py-2 text-center text-xs text-muted-foreground">Updates paused — connection problem.</p>
          )}
        </div>
      )}
    </div>
  );
}
