'use client';

import { Plus } from 'lucide-react';

/** What a "+" starts a session in: a folder (optionally with one of its
    worktrees preselected), or a project with no session yet, whose folder the
    new-session page picks per machine. */
export type NewSessionTarget =
  | { directory: string; worktreePath?: string; worktreeBranch?: string }
  | { projectId: string };

/** Where a project or worktree header's "+" goes. Shared with the header rows
    themselves: an empty project or worktree row navigates here on click, since
    it has nothing to collapse. */
export function newSessionHref(target: NewSessionTarget): string {
  if ('projectId' in target) {
    return `/dashboard/sessions/new?${new URLSearchParams({ projectId: target.projectId })}`;
  }
  const params = new URLSearchParams({ directory: target.directory });
  if (target.worktreePath) params.set('worktreePath', target.worktreePath);
  if (target.worktreeBranch) params.set('worktreeBranch', target.worktreeBranch);
  return `/dashboard/sessions/new?${params.toString()}`;
}

/** Hover-revealed "+" on a project or worktree header: starts a session in that
    group's project folder. On a worktree header, `worktreePath` + `worktreeBranch`
    ride along so the new-session page opens on the project's root with that
    worktree preselected — the folder chip is always the project, never the
    worktree, so a removed worktree can't leave a dangling "project" behind.

    Reveal is driven by the parent header's `group/label` hover, so it must be
    rendered inside such a group. */
export function NewSessionButton({
  href,
  label,
  onNavigate,
}: {
  /** From `newSessionHref`. */
  href: string;
  label: string;
  onNavigate: (href: string) => void;
}) {
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
