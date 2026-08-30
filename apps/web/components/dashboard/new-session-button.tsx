'use client';

import { Plus } from 'lucide-react';

/** Hover-revealed "+" on a project or worktree header: starts a session in that
    group's directory. On a worktree header, `worktreeBranch` rides along so the
    new-session page opens with that worktree preselected rather than the repo.

    Reveal is driven by the parent header's `group/label` hover, so it must be
    rendered inside such a group. */
export function NewSessionButton({
  directory,
  label,
  worktreeBranch,
  onNavigate,
}: {
  directory: string;
  label: string;
  worktreeBranch?: string;
  onNavigate: (href: string) => void;
}) {
  const href = worktreeBranch
    ? `/dashboard/agents/new-session?directory=${encodeURIComponent(directory)}&worktreeBranch=${encodeURIComponent(worktreeBranch)}`
    : `/dashboard/agents/new-session?directory=${encodeURIComponent(directory)}`;
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
