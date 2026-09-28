'use client';

// A session someone shared with you, read-only (collaboration §8.4, P5).
//
// The signed-in twin of the public `/share/<token>` session view: the same
// header shape and the same `<SessionTranscript>`, polled with a watermark
// (`after_message_id`) because a grantee has no socket until P6. It reads
// through the ordinary authenticated endpoints, which already enforce the
// grant and hand a non-owner a redacted row: no machine id, no paths, only
// the display part of the config, and message authors by name, never email.
//
// It is deliberately not the full session page. That page drives a daemon
// (terminal, files, git, resume) that only the owner can reach, and it has a
// composer; the capability-degraded version of it is P6. So there is no
// composer here and nothing that aims an RPC anywhere (§10.2).
//
// An owner who lands here (a stale link, their own row) is sent to the real
// session page instead.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Eye, GitBranch, Loader2 } from 'lucide-react';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { SessionTranscript } from '@/components/dashboard/session-transcript';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import type { AgentInstanceDetail, MessageResponse } from '@/lib/backend-api';
import { principalFromResponse } from '@/lib/principals';
import { roleLabel } from '@/lib/share-people';
import { describeSessionConfig } from '@/lib/session-config-line';
import { isClosedByDesign } from '@/lib/session-liveness';
import { POLL_ACTIVE_MS, POLL_IDLE_MS, useDocumentVisible, useSharePoll } from '@/lib/use-share-poll';

const PAGE_SIZE = 100;

type LoadState = 'loading' | 'ready' | 'gone' | 'error';

function isLive(session: AgentInstanceDetail): boolean {
  if (session.live_state === 'machine_offline') return false;
  return session.status === 'ACTIVE' || session.status === 'STARTING';
}

export default function SharedSessionPage() {
  const params = useParams<{ instanceId: string }>();
  const instanceId = params?.instanceId ?? '';
  const router = useRouter();
  const { api } = useAgentDashboard();
  const visible = useDocumentVisible();

  const [session, setSession] = useState<AgentInstanceDetail | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [state, setState] = useState<LoadState>('loading');
  const [notice, setNotice] = useState<string | null>(null);

  // First paint: the session and its newest page in one call.
  useEffect(() => {
    if (!api || !instanceId) return;
    let cancelled = false;
    setState('loading');
    setMessages([]);
    api
      .getInstanceDetail(instanceId, PAGE_SIZE)
      .then((detail) => {
        if (cancelled) return;
        if (detail.is_owner) {
          router.replace(`/dashboard/sessions/${instanceId}`);
          return;
        }
        setSession(detail);
        setMessages(detail.messages);
        setHasOlder(detail.messages.length >= PAGE_SIZE);
        setState('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        const status = (err as { status?: number }).status;
        setState(status === 404 ? 'gone' : 'error');
      });
    return () => {
      cancelled = true;
    };
  }, [api, instanceId, router]);

  const tick = useCallback(async () => {
    if (!api || state !== 'ready') return;
    try {
      const tail = messages[messages.length - 1]?.id;
      const [fresh, detail] = await Promise.all([
        api.getInstanceMessagesPaginated(instanceId, PAGE_SIZE, undefined, tail) as Promise<
          MessageResponse[]
        >,
        // The summary only: one message keeps the payload small.
        api.getInstanceDetail(instanceId, 1),
      ]);
      setSession(detail);
      setNotice(null);
      if (fresh.length === 0) return;
      setMessages((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        const added = fresh.filter((m) => !seen.has(m.id));
        return added.length ? [...prev, ...added] : prev;
      });
    } catch (err) {
      if ((err as { status?: number }).status === 404) {
        // Access was revoked (or the session deleted) while you watched.
        setState('gone');
      } else {
        setNotice('Updates paused: connection problem. Retrying…');
      }
    }
  }, [api, state, messages, instanceId]);

  const active = session ? !isClosedByDesign(session.status) : false;
  useSharePoll(tick, {
    intervalMs: visible && active ? POLL_ACTIVE_MS : POLL_IDLE_MS,
    enabled: state === 'ready',
  });

  const loadOlder = useCallback(async () => {
    const head = messages[0]?.id;
    if (!api || !head || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const older = (await api.getInstanceMessagesPaginated(
        instanceId,
        PAGE_SIZE,
        head,
      )) as MessageResponse[];
      setMessages((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        return [...older.filter((m) => !seen.has(m.id)), ...prev];
      });
      setHasOlder(older.length >= PAGE_SIZE);
    } catch {
      // Leave `hasOlder` as is; the next reach-top retries.
    } finally {
      setLoadingOlder(false);
    }
  }, [api, messages, loadingOlder, instanceId]);

  const configLine = useMemo(
    () => describeSessionConfig(session?.session_config ?? null),
    [session?.session_config],
  );
  const owner = principalFromResponse(session?.owner);
  const title = session?.name || 'Untitled session';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-3 border-b border-border/60 px-4 py-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            {session && (
              <SessionAgentIcon agentTypeName={session.agent_type_name} status={session.status} size={16} />
            )}
            <h1 className="min-w-0 truncate font-mono text-sm font-normal" title={title}>
              {session ? title : ' '}
            </h1>
            {session && isLive(session) && (
              <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground" title="The agent is working">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
                  <span className="relative inline-flex size-2 rounded-full bg-success" />
                </span>
                Live
              </span>
            )}
          </div>
          {session && (
            <div className="flex min-w-0 items-center gap-1.5 truncate text-[11px] text-muted-foreground">
              <span>{session.agent_type_name}</span>
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
          )}
        </div>
        {session && (
          <div className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
            {owner && (
              <span className="inline-flex items-center gap-1.5" title="Owner">
                <PrincipalAvatar principal={owner} size="xs" />
                <span className="max-w-[10rem] truncate">{owner.name?.trim() || 'Vicoa user'}</span>
              </span>
            )}
            <span
              className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-px"
              title="You can read this session. Sending messages from here arrives in a later update."
            >
              <Eye className="h-3 w-3" />
              {session.viewer_role ? `${roleLabel(session.viewer_role)}, read-only` : 'Read-only'}
            </span>
          </div>
        )}
      </div>

      {notice && (
        <div className="shrink-0 border-b border-warning/30 bg-warning/10 px-4 py-1 text-center text-[11px] text-foreground/80">
          {notice}
        </div>
      )}

      {state === 'loading' ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : state === 'gone' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-muted-foreground">
          <p>This session is no longer shared with you.</p>
          <p className="text-xs">Its owner may have removed your access, or deleted it.</p>
        </div>
      ) : state === 'error' ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
          Could not load this session. Try again in a moment.
        </div>
      ) : (
        session && (
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
        )
      )}
    </div>
  );
}
