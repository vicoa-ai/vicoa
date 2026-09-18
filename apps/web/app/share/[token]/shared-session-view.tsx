'use client';

// One shared session: the main pane — header (title, agent, config line) over
// the read-only transcript, polled with a watermark (`after=`) so a
// steady-state poll is a near-empty page. Used by a `session` link and by the
// project-sessions link for the picked session.
//
// No status pill: "Waiting for input" is the owner's to-do, not the viewer's,
// and it reads as an invitation on a page where nobody can type. The one
// state a spectator cares about — "is this still moving?" — is a small live
// dot while the agent is actually working, plus the transcript's own
// thinking indicator.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { GitBranch, Loader2 } from 'lucide-react';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { SessionTranscript } from '@/components/dashboard/session-transcript';
import { AttachmentUrlProvider } from '@/components/chat-attachments';
import type { PublicMessage, PublicSessionSummary } from '@/lib/backend-api';
import {
  ShareNotFoundError,
  ShareRateLimitedError,
  fetchPublicMessages,
  fetchPublicSession,
  publicAttachmentUrl,
} from '@/lib/public-share-api';
import { isClosedByDesign } from '@/lib/session-liveness';
import { ShareHeader } from './share-shell';
import { POLL_ACTIVE_MS, POLL_IDLE_MS, useDocumentVisible, useSharePoll } from './use-share-poll';

const PAGE_SIZE = 100;

/** The display subset of `session_config`, as one "agent · model · effort · mode" line. */
export function describeSessionConfig(config: Record<string, unknown> | null): string | null {
  if (!config) return null;
  const parts: string[] = [];
  const str = (key: string) => (typeof config[key] === 'string' && config[key] ? String(config[key]) : null);
  const model = str('model');
  const effort = str('thinking_effort') ?? str('reasoning_effort');
  const mode = str('permission_mode') ?? str('opencode_mode');
  if (model) parts.push(model);
  if (effort) parts.push(`${effort} effort`);
  if (mode) parts.push(mode);
  return parts.length ? parts.join(' · ') : null;
}

type LoadState = 'loading' | 'ready' | 'gone' | 'error';

/** Whether the agent is working right now — the only status a viewer is shown. */
export function isSessionLive(session: PublicSessionSummary): boolean {
  if (session.live_state === 'machine_offline') return false;
  return session.status === 'ACTIVE' || session.status === 'STARTING';
}

export function SharedSessionView({
  token,
  initialSession,
  openHref,
  onSessionChange,
}: {
  token: string;
  initialSession: PublicSessionSummary;
  /** "Open in Vicoa" target for a signed-in viewer who can see this session (the owner). */
  openHref?: string | null;
  /** Each polled summary, so the sidebar row can follow the title and live state. */
  onSessionChange?: (session: PublicSessionSummary) => void;
}) {
  const instanceId = initialSession.id;
  const [session, setSession] = useState<PublicSessionSummary>(initialSession);
  const [messages, setMessages] = useState<PublicMessage[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [state, setState] = useState<LoadState>('loading');
  const [notice, setNotice] = useState<string | null>(null);
  const visible = useDocumentVisible();

  // First paint: the newest page.
  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setMessages([]);
    fetchPublicMessages(token, instanceId, { limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        setMessages(page.messages);
        setHasOlder(page.has_more);
        setState('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setState(err instanceof ShareNotFoundError ? 'gone' : 'error');
      });
    return () => {
      cancelled = true;
    };
  }, [token, instanceId]);

  const tick = useCallback(async () => {
    if (state !== 'ready') return;
    try {
      const tail = messages[messages.length - 1]?.id;
      const [page, summary] = await Promise.all([
        fetchPublicMessages(token, instanceId, tail ? { after: tail, limit: PAGE_SIZE } : { limit: PAGE_SIZE }),
        fetchPublicSession(token, instanceId),
      ]);
      setSession(summary);
      onSessionChange?.(summary);
      setNotice(null);
      if (page.messages.length === 0) return;
      setMessages((prev) => {
        if (!tail) return page.messages;
        const seen = new Set(prev.map((m) => m.id));
        const fresh = page.messages.filter((m) => !seen.has(m.id));
        return fresh.length ? [...prev, ...fresh] : prev;
      });
    } catch (err) {
      if (err instanceof ShareNotFoundError) {
        // Revoked / expired mid-view (a live share is a window, §10.3).
        setState('gone');
      } else if (err instanceof ShareRateLimitedError) {
        setNotice(`Updates paused: too many requests. Retrying in ${err.retryAfterSeconds}s.`);
      } else {
        setNotice('Updates paused: connection problem. Retrying…');
      }
    }
  }, [state, messages, token, instanceId, onSessionChange]);

  const active = !isClosedByDesign(session.status);
  useSharePoll(tick, {
    intervalMs: visible && active ? POLL_ACTIVE_MS : POLL_IDLE_MS,
    enabled: state === 'ready',
  });

  const loadOlder = useCallback(async () => {
    const head = messages[0]?.id;
    if (!head || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await fetchPublicMessages(token, instanceId, { before: head, limit: PAGE_SIZE });
      setMessages((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        return [...page.messages.filter((m) => !seen.has(m.id)), ...prev];
      });
      setHasOlder(page.has_more);
    } catch {
      // Leave `hasOlder` as is; the next reach-top retries.
    } finally {
      setLoadingOlder(false);
    }
  }, [messages, loadingOlder, token, instanceId]);

  const resolveAttachment = useCallback((id: string) => publicAttachmentUrl(token, id), [token]);
  const configLine = useMemo(() => describeSessionConfig(session.session_config), [session.session_config]);
  const live = isSessionLive(session);
  const title = session.name || 'Untitled session';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ShareHeader openHref={openHref}>
        <div className="flex min-w-0 items-center gap-2">
          <SessionAgentIcon agentTypeName={session.agent_type_name} status={session.status} size={16} />
          <h1 className="min-w-0 truncate font-mono text-sm font-normal" title={title}>
            {title}
          </h1>
          {live && (
            <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground" title="The agent is working">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-success" />
              </span>
              Live
            </span>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-1.5 truncate text-[11px] text-muted-foreground">
          <span>{session.agent_profile?.name ?? session.agent_type_name}</span>
          {configLine && (
            <>
              <span>·</span>
              <span className="truncate">{configLine}</span>
            </>
          )}
          {session.worktree_name && (
            <>
              <span>·</span>
              <span className="inline-flex items-center gap-1">
                <GitBranch className="h-3 w-3" />
                {session.worktree_name}
              </span>
            </>
          )}
        </div>
      </ShareHeader>

      {notice && (
        <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1 text-center text-[11px] text-amber-700 dark:text-amber-300">
          {notice}
        </div>
      )}

      {state === 'loading' ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : state === 'gone' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-muted-foreground">
          <p>This share is no longer available.</p>
          <p className="text-xs">The link may have been revoked or expired.</p>
        </div>
      ) : state === 'error' ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
          Could not load this session. Try again in a moment.
        </div>
      ) : (
        <AttachmentUrlProvider resolve={resolveAttachment}>
          <SessionTranscript
            messages={messages}
            agentTypeName={session.agent_type_name}
            thinking={session.status === 'ACTIVE' || session.status === 'STARTING'}
            startAt={active ? 'bottom' : 'top'}
            hasOlder={hasOlder}
            loadingOlder={loadingOlder}
            onLoadOlder={() => void loadOlder()}
            empty="Nothing has been said in this session yet."
          />
        </AttachmentUrlProvider>
      )}
    </div>
  );
}
