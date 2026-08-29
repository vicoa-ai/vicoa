'use client';

import { Layers2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SkillSummary } from '../lib/skills-rpc';
import { skillTitle } from '../lib/skills-view';

interface SkillCardProps {
  skill: SkillSummary;
  onSelect: (skill: SkillSummary) => void;
}

/** A borderless skill row: a large neutral icon spanning the title + one-line
 *  description. Click opens the detail view. */
export function SkillCard({ skill, onSelect }: SkillCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(skill)}
      className={cn(
        'flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-left',
        'transition-colors hover:bg-accent',
      )}
    >
      <Layers2 className="size-5 shrink-0 text-muted-foreground" strokeWidth={1.5} />
      <div className="min-w-0 flex-1">
        <span className="block truncate text-[17px] leading-tight text-foreground">
          {skillTitle(skill.name)}
        </span>
        {skill.description && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{skill.description}</p>
        )}
      </div>
    </button>
  );
}
