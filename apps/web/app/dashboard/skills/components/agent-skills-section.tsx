'use client';

import { Folder, Puzzle, SearchX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ListSkillsResult, SkillSummary } from '../lib/skills-rpc';
import { groupSkillsByFolder, skillMatchesQuery } from '../lib/skills-view';
import { SkillCard } from './skill-card';

interface AgentSkillsSectionProps {
  state: ListSkillsResult | undefined;
  loading: boolean;
  /** Active search query; filters the grid by name + description. */
  query: string;
  onSelect: (skill: SkillSummary) => void;
  /** Opens the "New Skill" chooser from the empty state. */
  onAdd: () => void;
}

/** The active agent's installed skills as a two-column card grid, grouped by
 *  folder (co-located nested skills render together), filtered by `query`. */
export function AgentSkillsSection({
  state,
  loading,
  query,
  onSelect,
  onAdd,
}: AgentSkillsSectionProps) {
  const all = state?.skills ?? [];
  const skills = all.filter((s) => skillMatchesQuery(s, query));
  const groups = groupSkillsByFolder(skills);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-x-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-muted/40" />
        ))}
      </div>
    );
  }

  if (state && !state.supported) {
    return (
      <p className="rounded-lg border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
        Skills for this agent are provided by the agent itself and aren&apos;t managed here.
      </p>
    );
  }

  // Installed skills exist but none match the query.
  if (all.length > 0 && skills.length === 0) {
    return (
      <div className="mx-auto mt-14 flex max-w-sm flex-col items-center text-center">
        <SearchX className="h-9 w-9 text-muted-foreground/40" />
        <p className="mt-3 text-sm text-muted-foreground">
          No skills match &ldquo;{query.trim()}&rdquo;.
        </p>
      </div>
    );
  }

  if (skills.length === 0) {
    return (
      <div className="mx-auto mt-14 flex max-w-sm flex-col items-center text-center">
        <Puzzle className="h-9 w-9 text-muted-foreground/40" />
        <p className="mt-3 text-sm font-medium">No skills installed yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Install one from a git repository, or have an agent author one for you.
        </p>
        <Button size="sm" className="mt-4 gap-1.5" onClick={onAdd}>
          New skill
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <div key={group.folder ?? '__root__'}>
          {group.folder && (
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Folder className="h-3.5 w-3.5" />
              <span className="font-mono">{group.folder}</span>
            </div>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-x-6">
            {group.skills.map((skill) => (
              <SkillCard key={skill.name} skill={skill} onSelect={onSelect} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
