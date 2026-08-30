'use client';

// Agent filter tabs for the Skills tab: one tab per supported agent detected on
// the machine, each with its brand logo, label, and installed-skill count. The
// active tab drives which agent's skills the grid below shows.

import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { cn } from '@/lib/utils';
import type { SkillAgentType } from '../lib/skills-rpc';

interface SkillAgentTabsProps {
  agents: { type: SkillAgentType; label: string }[];
  active: SkillAgentType | null;
  /** Installed-skill count per agent; undefined while that agent is loading. */
  counts: Record<string, number | undefined>;
  onSelect: (type: SkillAgentType) => void;
}

export function SkillAgentTabs({ agents, active, counts, onSelect }: SkillAgentTabsProps) {
  return (
    <div className="px-4 pb-1 pt-2">
      {/* Same column as the skills grid below, so the tab row lines up with the
          leftmost skill card. */}
      <div className="custom-scrollbar mx-auto flex max-w-3xl items-center gap-1 overflow-x-auto">
        {agents.map((agent) => {
        const isActive = agent.type === active;
        const count = counts[agent.type];
        return (
          <button
            key={agent.type}
            type="button"
            onClick={() => onSelect(agent.type)}
            className={cn(
              'flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-md px-2.5 text-xs transition-colors',
              isActive
                ? 'bg-accent text-foreground'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
            )}
          >
            <AgentTypeIcon agentTypeName={agent.type} size={15} whiteForOpenAI />
            <span className="whitespace-nowrap">{agent.label}</span>
            {typeof count === 'number' && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[10px] tabular-nums',
                  isActive ? 'bg-background/70' : 'bg-muted',
                  'text-muted-foreground',
                )}
              >
                {count}
              </span>
            )}
          </button>
          );
        })}
      </div>
    </div>
  );
}
