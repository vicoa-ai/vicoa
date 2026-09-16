'use client';

/**
 * An agent's run history: every session it has started, newest first.
 *
 * The sibling of the automation panel's Run history, and deliberately the same
 * card — the two answer the same question ("what has this thing actually
 * done?") and should not look like different features. The difference is where
 * the rows come from: an automation records its own `automation_runs`, while an
 * agent's history is `agent_instances.agent_profile_id`, stamped at spawn. That
 * makes it provenance rather than a live join, so editing the agent never
 * rewrites what already ran.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Loader2 } from 'lucide-react';

import { getAgentStatusColors } from '@/lib/agent-status-colors';
import type { AgentInstanceResponse, getBackendAPI } from '@/lib/backend-api';
import { cn } from '@/lib/utils';
import { FieldGroup } from '../../automation/components/field-row';

type Api = ReturnType<typeof getBackendAPI>;

function sessionLabel(session: AgentInstanceResponse): string {
  return session.name?.trim() || session.project?.split('/').filter(Boolean).pop() || 'Session';
}

export function RunHistorySection({ api, agentId }: { api: Api; agentId: string }) {
  const [sessions, setSessions] = useState<AgentInstanceResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listAgentProfileSessions(agentId)
      .then((rows) => !cancelled && setSessions(rows))
      .catch(() => !cancelled && setSessions([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [api, agentId]);

  return (
    <FieldGroup title="Run history">
      {loading ? (
        <div className="flex h-16 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="px-3.5 py-4 text-center text-xs text-muted-foreground">
          No sessions yet. Pick this agent when you start one and it will show up here.
        </div>
      ) : (
        sessions.map((session) => {
          const colors = getAgentStatusColors(session.status);
          return (
            <Link
              key={session.id}
              href={`/dashboard/agents/${session.id}`}
              className="flex items-center gap-2.5 px-3.5 py-2 transition-colors hover:bg-foreground/[0.04]"
            >
              <span
                aria-label={session.status}
                className={cn('size-2 shrink-0 rounded-full', colors.dot)}
              />
              <span className="min-w-0 flex-1 truncate text-sm" title={sessionLabel(session)}>
                {sessionLabel(session)}
              </span>
              <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
                {new Date(session.started_at).toLocaleString()}
              </span>
              <ArrowUpRight className="size-4 shrink-0 text-muted-foreground" />
            </Link>
          );
        })
      )}
    </FieldGroup>
  );
}
