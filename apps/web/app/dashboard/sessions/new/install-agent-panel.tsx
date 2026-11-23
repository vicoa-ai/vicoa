'use client';

import { RefreshCw } from 'lucide-react';
import { AgentInstallChoices } from '@/components/dashboard/agent-install';
import type { InstallOs } from '@/lib/desktop-agent-install';
import { cn } from '@/lib/utils';

/**
 * Under the new-session hero: how to get an agent onto the selected machine.
 *
 * Shown when the machine has none at all, or when the user asks to install the
 * agent they picked. The composer stays as it is below, so a prompt can be
 * written meanwhile; picking a row here also makes it the session's agent.
 */
export function InstallAgentPanel({
  title,
  description,
  agents,
  os,
  selectedId,
  onSelect,
  onRefresh,
  refreshing,
}: {
  title: string;
  description: string;
  /** Agents not installed on the machine, in picker order. */
  agents: { id: string; label: string }[];
  os: InstallOs;
  /** The open row; null (nothing open) until the user picks one. */
  selectedId: string | null;
  onSelect: (agentId: string | null) => void;
  /** Re-check the machine; null when its daemon can't (too old, offline). */
  onRefresh: (() => void) | null;
  refreshing: boolean;
}) {
  return (
    <div className="w-full max-w-xl space-y-3 text-left">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-foreground">{title}</p>
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      </div>
      <AgentInstallChoices agents={agents} os={os} selectedId={selectedId} onSelect={onSelect} />
    </div>
  );
}
