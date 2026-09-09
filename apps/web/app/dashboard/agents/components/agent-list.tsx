'use client';

/**
 * The Agents page's left column.
 *
 * At full width it is a table with a header: one line per agent, every fact in
 * its own column, so the list scans down a column instead of being re-read row
 * by row. That earns its keep here in a way it would not in the automation list,
 * because an agent has several independent attributes (config, usage, recency)
 * rather than one headline fact like a schedule.
 *
 * With the detail panel open there is no room for columns, so the same rows
 * collapse to name + config and the header disappears. Never two lines per
 * agent: a stacked row makes a list of five agents look like ten.
 */

import { useMemo, useState } from 'react';
import { MoreHorizontal, Search, Trash2 } from 'lucide-react';

import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { agentPickerLabel, type AgentCatalog } from '@/lib/agent-catalog';
import type { AgentProfile } from '@/lib/backend-api';
import { humanizeDuration } from '@/lib/machine-display';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { cn } from '@/lib/utils';

// One template for the header and every row, so the columns actually line up.
// Text columns are fr-based and floored at 0 so `truncate` works inside them;
// the numeric ones are fixed, which is what makes them scannable.
const COLUMNS =
  'grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1.2fr)_4.5rem_5.5rem_1.75rem] items-center gap-3';

/** "Claude Code · Opus 5", falling back to raw ids the catalog hasn't heard of. */
function configLabel(profile: AgentProfile, catalog: AgentCatalog): string {
  const agent = catalog.agents.find((a) => a.id === profile.agent);
  const label = agentPickerLabel(profile.agent, agent?.label ?? profile.agent);
  const modelId = (profile.config as { model?: string }).model;
  const model = agent?.models?.find((m) => m.id === modelId);
  return [label, model?.label ?? modelId].filter(Boolean).join(' · ');
}

/** "2h ago" since the agent last did anything, or null when it never has. */
function lastUsedLabel(profile: AgentProfile, now: number): string | null {
  if (!profile.last_active_at) return null;
  const active = new Date(profile.last_active_at).getTime();
  return Number.isNaN(active) ? null : `${humanizeDuration(now - active)} ago`;
}

/** An em dash, not a blank: an empty cell reads as a rendering bug in a table. */
function Empty() {
  return <span className="text-muted-foreground/50">—</span>;
}

export function AgentList({
  profiles,
  catalog,
  selectedId,
  onSelect,
  onDelete,
  wide,
}: {
  profiles: AgentProfile[];
  catalog: AgentCatalog;
  selectedId: string | null;
  onSelect: (profile: AgentProfile) => void;
  onDelete: (profile: AgentProfile) => void;
  /** Detail panel closed — the list has the full width to spend on columns. */
  wide: boolean;
}) {
  const [query, setQuery] = useState('');
  // One clock read per render rather than per row, so every "2h ago" in the
  // list is measured from the same instant.
  const now = Date.now();

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return profiles;
    return profiles.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.description ?? '').toLowerCase().includes(q),
    );
  }, [profiles, query]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-2">
        <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-2.5">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={query}
            placeholder="Search agents"
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
          />
        </div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto">
        {/* Sticky so the columns stay labelled once the list outgrows the
            viewport — the whole point of having a header. */}
        {wide && visible.length > 0 && (
          <div
            className={cn(
              COLUMNS,
              'sticky top-0 z-10 border-b border-border bg-background px-3 py-1.5',
              'text-[11px] font-medium text-muted-foreground',
            )}
          >
            <div>Agent</div>
            <div>Description</div>
            <div>Configuration</div>
            <div className="text-right">Sessions</div>
            <div className="text-right">Last used</div>
            <div />
          </div>
        )}

        {visible.length === 0 ? (
          <div className="px-4 py-10 text-center text-xs text-muted-foreground">
            No matches.
          </div>
        ) : (
          <ul>
            {visible.map((profile) => {
              const config = configLabel(profile, catalog);
              const description = profile.description?.trim();
              const lastUsed = lastUsedLabel(profile, now);
              const hasInstructions = Boolean(profile.system_prompt?.trim());
              return (
                <li
                  key={profile.id}
                  onClick={() => onSelect(profile)}
                  className={cn(
                    'group cursor-pointer border-b border-border/50 px-3 py-2',
                    wide ? COLUMNS : 'flex items-center gap-2.5',
                    selectedId === profile.id
                      ? 'bg-foreground/[0.07]'
                      : 'hover:bg-foreground/[0.04]',
                  )}
                >
                  {/* Agent */}
                  <div className="flex min-w-0 items-center gap-2.5">
                    <PrincipalAvatar principal={agentPrincipal(profile)} size="md" />
                    <span className="min-w-0 truncate text-sm">{profile.name}</span>
                  </div>

                  {wide ? (
                    <>
                      {/* Description */}
                      <div className="min-w-0 truncate text-xs text-muted-foreground">
                        {description || <Empty />}
                      </div>

                      {/* Configuration — the instructions marker belongs here:
                          it is part of how the agent is set up, and a whole
                          column for one boolean is not worth the width. */}
                      <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                        <AgentTypeIcon
                          agentTypeName={profile.agent}
                          size={11}
                          whiteForOpenAI
                        />
                        <span className="min-w-0 truncate">{config}</span>
                        {hasInstructions && (
                          <span
                            title="Has custom instructions"
                            className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] leading-none"
                          >
                            Instructions
                          </span>
                        )}
                      </div>

                      {/* Sessions */}
                      <div className="text-right text-xs tabular-nums text-muted-foreground">
                        {profile.session_count ? profile.session_count : <Empty />}
                      </div>

                      {/* Last used */}
                      <div className="truncate text-right text-xs text-muted-foreground">
                        {lastUsed ?? <Empty />}
                      </div>
                    </>
                  ) : (
                    // Narrow: only the config survives, and it still shares the
                    // one line — the panel beside it holds everything else.
                    <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 text-xs text-muted-foreground">
                      <AgentTypeIcon
                        agentTypeName={profile.agent}
                        size={11}
                        whiteForOpenAI
                      />
                      <span className="min-w-0 truncate">{config}</span>
                    </div>
                  )}

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        onClick={(e) => e.stopPropagation()}
                        className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground opacity-0 hover:bg-foreground/[0.06] hover:text-foreground group-hover:opacity-100 data-[state=open]:opacity-100 dark:hover:bg-foreground/10"
                        title="Actions"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="end"
                      className="rounded-xl"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <DropdownMenuItem onClick={() => onDelete(profile)}>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
