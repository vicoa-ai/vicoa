'use client';

// One shared session: header (title, agent, status, config line) over the
// read-only transcript, polled with a watermark (`after=`) so a steady-state
// poll is a near-empty page. Used directly by a `session` link and by the
// project-sessions link once a session is picked.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, GitBranch, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
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

function statusLabel(session: PublicSessionSummary): { label: string; tone: string } {
  if (session.live_state === 'machine_offline') return { label: 'Offline', tone: 'bg-muted text-muted-foreground' };
  switch (session.status) {
    case 'STARTING':
    case 'ACTIVE':
      return { label: 'Working', tone: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-300' };
    case 'AWAITING_INPUT':
      return { label: 'Waiting for input', tone: 'bg-blue-500/15 text-blue-700 dark:text-blue-300' };
    case 'COMPLETED':
      return { label: 'Archived', tone: 'bg-muted text-muted-foreground' };
    case 'FAILED':
      return { label: 'Failed', tone: 'bg-red-500/15 text-red-700 dark:text-red-300' };
    case 'KILLED':
    case 'DISCONNECTED':
      return { label: 'Stopped', tone: 'bg-muted text-muted-foreground' };
    default:
      return { label: 'Idle', tone: 'bg-muted text-muted-foreground' };
  }
}

type LoadState = 'loading' | 'ready' | 'gone' | 'error';

export function SharedSessionView({
  token,
  initialSession,
  onBack,
}: {
  token: string;
  initialSession: PublicSessionSummary;
  /** Present when reached from a project-sessions list. */
  onBack?: () => void;
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
        setNotice(`Updates paused — too many requests. Retrying in ${err.retryAfterSeconds}s.`);
      } else {
        setNotice('Updates paused — connection problem. Retrying…');
      }
    }
  }, [state, messages, token, instanceId]);

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
  const status = statusLabel(session);
  const title = session.name || 'Untitled session';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-2">
        {onBack && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onBack} aria-label="Back to sessions">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        )}
        <SessionAgentIcon agentTypeName={session.agent_type_name} status={session.status} size={18} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-medium">{title}</h2>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${status.tone}`}>
              {status.label}
            </span>
          </div>
          <div className="flex items-center gap-1.5 truncate text-[11px] text-muted-foreground">
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
        </div>
      </div>

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
