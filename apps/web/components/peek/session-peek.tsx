'use client';

/**
 * A session in the peek panel: what it is, how it went, and its newest agent
 * message (for a finished run, usually its report), with a box to continue it.
 *
 * Continuing goes through `continueSession`: a running agent gets the message,
 * a stopped one is resumed on its machine with the message as its next prompt.
 * The full transcript is one click away ("Open session").
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ExternalLink, Loader2, MessageCircle, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import type { AgentInstanceDetail, MachineSummary, MessageResponse } from '@/lib/backend-api';
import { humanizeDuration } from '@/lib/machine-display';
import { isImeComposing } from '@/lib/ime';
import { liveStateLabel, resolveLiveState } from '@/lib/session-liveness';
import { continueSession, ContinueSessionError } from '@/lib/session-continue';
import { toast } from '@/lib/toast';

const POLL_MS = 15_000;

const isUser = (m: MessageResponse) => /^(user|human)$/i.test(m.sender_type);

function folderName(path: string | null | undefined): string | null {
  if (!path) return null;
  const parts = path.split('/').filter(Boolean);
  return parts[parts.length - 1] ?? null;
}

export function SessionPeek({
  sessionId,
  onLoaded,
}: {
  sessionId: string;
  onLoaded?: (detail: AgentInstanceDetail) => void;
}) {
  const router = useRouter();
  const { api } = useAgentDashboard();
  const [detail, setDetail] = useState<AgentInstanceDetail | null>(null);
  const [machine, setMachine] = useState<MachineSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const current = useRef(sessionId);
  current.current = sessionId;
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  const load = useCallback(async () => {
    if (!api) return;
    const id = sessionId;
    try {
      const d = await api.getInstanceDetail(id, 20);
      if (current.current !== id) return;
      setDetail(d);
      setError(null);
      onLoadedRef.current?.(d);
      if (d.machine_id) {
        const list = await api.listMachines().catch(() => [] as MachineSummary[]);
        if (current.current === id) setMachine(list.find((m) => m.machine_id === d.machine_id) ?? null);
      }
    } catch (e) {
      if (current.current === id) setError(e instanceof Error ? e.message : 'Failed to load session');
    }
  }, [api, sessionId]);

  // A different session: start clean, then load and keep it fresh.
  useEffect(() => {
    setDetail(null);
    setMachine(null);
    setError(null);
    setDraft('');
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const send = async () => {
    const text = draft.trim();
    if (!api || !text || sending) return;
    setSending(true);
    try {
      const outcome = await continueSession(api, sessionId, text);
      setDraft('');
      toast.success(outcome === 'resumed' ? 'Session resumed with your message' : 'Message sent');
      void load();
    } catch (e) {
      toast.error("Couldn't send the message", {
        description: e instanceof ContinueSessionError ? e.message : undefined,
      });
    } finally {
      setSending(false);
    }
  };

  if (error) return <p className="px-4 py-6 text-sm text-muted-foreground">{error}</p>;
  if (!detail) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
      </div>
    );
  }

  const live = resolveLiveState(detail, machine);
  const offline = live === 'machine_offline';
  const lastAgent = [...(detail.messages ?? [])].reverse().find((m) => !isUser(m)) ?? null;
  const started = Date.parse(detail.started_at);
  const ended = detail.ended_at ? Date.parse(detail.ended_at) : null;
  const lastAt = lastAgent ? Date.parse(lastAgent.created_at) : null;
  const span = (ended ?? lastAt ?? Date.now()) - started;
  const meta = [
    detail.agent_type_name,
    folderName(detail.project),
    liveStateLabel(live) ?? detail.status.toLowerCase().replace(/_/g, ' '),
    `started ${humanizeDuration(Date.now() - started)} ago`,
    Number.isFinite(span) && span > 0 ? `ran ${humanizeDuration(span)}` : null,
  ].filter(Boolean);

  return (
    <div className="flex min-h-full flex-col">
      <div className="space-y-1.5 px-5 pt-4 pb-3">
        <div className="flex items-start gap-2">
          <MessageCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <h2 className="min-w-0 text-[15px] font-medium leading-snug [overflow-wrap:anywhere]">
            {detail.name || 'Untitled session'}
          </h2>
        </div>
        <p className="text-xs text-muted-foreground">{meta.join(' · ')}</p>
        {detail.automation ? (
          <p className="text-xs text-muted-foreground">From automation: {detail.automation.title}</p>
        ) : null}
      </div>

      <div className="flex-1 border-t border-border/60 px-5 py-4">
        <div className="mb-2 text-[0.8rem] text-muted-foreground">
          {lastAgent ? `Latest from the agent, ${humanizeDuration(Date.now() - Date.parse(lastAgent.created_at))} ago` : 'No agent messages yet'}
        </div>
        {lastAgent ? (
          <div className="text-sm [overflow-wrap:anywhere]">
            <MessageMarkdown>{lastAgent.content}</MessageMarkdown>
          </div>
        ) : null}
      </div>

      <div className="sticky bottom-0 space-y-2 border-t border-border/60 bg-background px-5 py-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (isImeComposing(e)) return;
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void send();
            }
          }}
          disabled={offline || sending}
          rows={3}
          placeholder={offline ? "Its machine is offline, so it can't be continued now" : 'Continue this session…'}
          className="custom-scrollbar w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 text-xs text-muted-foreground"
            onClick={() => router.push(`/dashboard/sessions/${encodeURIComponent(sessionId)}`)}
          >
            <ExternalLink className="size-3.5" />
            Open session
          </Button>
          <Button size="sm" className="h-8 gap-1.5" onClick={() => void send()} disabled={!draft.trim() || offline || sending}>
            <Send className="size-3.5" />
            {sending ? 'Sending…' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  );
}
