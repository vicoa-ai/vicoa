/** Pure view helpers for the Skills tab: folder grouping + label formatting. */

import type { SkillSummary } from './skills-rpc';

/** Nested skills key on ':' (e.g. `web:forms`). The parent folder groups
 *  siblings; a top-level skill (no ':') has no folder. */
export function parentFolder(name: string): string | null {
  const i = name.lastIndexOf(':');
  return i === -1 ? null : name.slice(0, i);
}

/** The leaf title shown on a card (last ':' segment). */
export function skillTitle(name: string): string {
  const i = name.lastIndexOf(':');
  return i === -1 ? name : name.slice(i + 1);
}

export interface SkillGroup {
  /** null = ungrouped top-level skills; otherwise the shared parent folder. */
  folder: string | null;
  skills: SkillSummary[];
}

/**
 * Group skills by their parent folder so co-located skills render together.
 * Ungrouped (top-level) skills come first, then folders alphabetically; within
 * each group skills are sorted by name.
 */
export function groupSkillsByFolder(skills: SkillSummary[]): SkillGroup[] {
  const byFolder = new Map<string | null, SkillSummary[]>();
  for (const skill of skills) {
    const folder = parentFolder(skill.name);
    const bucket = byFolder.get(folder);
    if (bucket) bucket.push(skill);
    else byFolder.set(folder, [skill]);
  }
  const folders = [...byFolder.keys()].filter((f): f is string => f !== null).sort();
  const ordered: (string | null)[] = byFolder.has(null) ? [null, ...folders] : folders;
  return ordered.map((folder) => ({
    folder,
    skills: (byFolder.get(folder) ?? []).sort((a, b) => a.name.localeCompare(b.name)),
  }));
}

const SCOPE_LABELS: Record<string, string> = {
  user: 'User',
  shared: 'Shared',
  project: 'Project',
};

export function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

/** Case-insensitive filter over a skill's name (incl. folder) + description.
 *  An empty/whitespace query matches everything. */
export function skillMatchesQuery(skill: SkillSummary, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    skill.name.toLowerCase().includes(q) || skill.description.toLowerCase().includes(q)
  );
}
