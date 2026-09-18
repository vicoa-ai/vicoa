'use client';

import { Plus } from 'lucide-react';

/** Hover-revealed "+" on a project or worktree header: starts a session in that
    group's project folder. On a worktree header, `worktreePath` + `worktreeBranch`
    ride along so the new-session page opens on the project's root with that
    worktree preselected — the folder chip is always the project, never the
    worktree, so a removed worktree can't leave a dangling "project" behind.

    Reveal is driven by the parent header's `group/label` hover, so it must be
    rendered inside such a group. */
export function NewSessionButton({
  directory,
  label,
  worktreePath,
  worktreeBranch,
  onNavigate,
}: {
  /** The project's folder (the repo's main checkout), never a worktree. */
  directory: string;
  label: string;
  worktreePath?: string;
  worktreeBranch?: string;
  onNavigate: (href: string) => void;
}) {
  const params = new URLSearchParams({ directory });
  if (worktreePath) params.set('worktreePath', worktreePath);
  if (worktreeBranch) params.set('worktreeBranch', worktreeBranch);
  const href = `/dashboard/agents/new-session?${params.toString()}`;
  return (
    <button
      type="button"
      onClick={() => onNavigate(href)}
      title={`New session in ${label}`}
      aria-label={`New session in ${label}`}
      className="shrink-0 rounded p-0.5 text-muted-foreground/50 opacity-0 transition-opacity hover:text-muted-foreground focus-visible:opacity-100 group-hover/label:opacity-100"
    >
      <Plus className="h-3 w-3" />
    </button>
  );
}
