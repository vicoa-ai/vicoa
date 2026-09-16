'use client';

import { ChevronRight, MoreHorizontal, Trash2, type LucideIcon } from 'lucide-react';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { NewSessionButton } from '@/components/dashboard/new-session-button';
import { PrHoverCard } from '@/components/dashboard/pr-hover-card';
import { prPresentation, type PrInfo } from '@/components/dashboard/pr-status';

interface WorktreeAction {
  key: string;
  icon: LucideIcon;
  label: string;
  onSelect: () => void;
}

export interface WorktreeSubGroupHeaderProps {
  label: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Target of this group's "+", or null to hide it. */
  newSessionDirectory: string | null;
  /** Preselect this worktree on the new-session page; absent for main. */
  worktreeBranch?: string;
  /** Git no longer has a checkout at this folder: the row reads as deleted.
      Its actions are unchanged — "Delete" still archives the sessions that
      were started in it, and the (already gone) folder counts as removed. */
  missing?: boolean;
  onNavigate: (href: string) => void;
  /** When set, the row is removable: it gets both a right-click menu and a
      hover three-dot menu wired to this *same* action. Omitted for the main
      checkout and unmanaged worktrees, which render as a plain header. */
  onRequestDelete?: () => void;
  /** This branch's pull request, when it has one. Recolors the branch icon and
      adds the hover card; absent (no PR, no `gh`, no GitHub) renders the plain
      grey branch icon this row has always shown. */
  pr?: PrInfo | null;
}

/**
 * One row header under a split project group — the main folder or a worktree:
 * a collapse toggle, a "+" to start a session there, and (for removable
 * worktrees) a delete action surfaced two ways from a single definition:
 * right-click and a hover-revealed three-dot menu. Keeping the two menus off
 * one `actions` list is what keeps them from drifting apart.
 */
export function WorktreeSubGroupHeader({
  label,
  collapsed,
  onToggleCollapsed,
  newSessionDirectory,
  worktreeBranch,
  missing = false,
  onNavigate,
  onRequestDelete,
  pr,
}: WorktreeSubGroupHeaderProps) {
  const actions: WorktreeAction[] = onRequestDelete
    ? [{ key: 'delete', icon: Trash2, label: 'Delete', onSelect: onRequestDelete }]
    : [];

  const { icon: BranchIcon, className: branchIconClassName } = prPresentation(pr);
  // One size for every state, PR or not. PR data lands a beat after the sidebar
  // first paints, so a size that depended on it would jog every branch row in
  // the list a second after load; only the glyph and colour may change.
  const branchIcon = <BranchIcon className={cn('h-3 w-3 shrink-0', branchIconClassName)} />;

  const header = (
    // `select-none` stops a right-click from starting a text selection on the
    // label instead of opening the context menu.
    <div className="group/label flex w-full select-none items-center gap-1 py-0.5 pl-3 pr-2">
      <button
        type="button"
        onClick={onToggleCollapsed}
        aria-expanded={!collapsed}
        className="flex min-w-0 flex-1 items-center gap-1 text-left"
      >
        <PrHoverCard pr={pr} branch={worktreeBranch ?? label}>
          {/* A span, not a button: the trigger sits inside the collapse button,
              and hover cards open on hover anyway. Its panel is portaled out, so
              its own buttons never nest inside this one. */}
          <span className="flex shrink-0 items-center">{branchIcon}</span>
        </PrHoverCard>
        <span
          className={cn(
            'truncate text-[11px] font-light text-muted-foreground/60',
            missing && 'line-through text-muted-foreground/40',
          )}
        >
          {label}
        </span>
        {missing && (
          <span
            title="This worktree's folder no longer exists"
            className="shrink-0 rounded border border-border/60 px-1 text-[9px] leading-4 text-muted-foreground/50"
          >
            deleted
          </span>
        )}
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/label:text-muted-foreground',
            !collapsed && 'rotate-90',
          )}
        />
      </button>
      {actions.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              title="Worktree actions"
              aria-label="Worktree actions"
              className="shrink-0 rounded p-0.5 text-muted-foreground/50 opacity-0 transition-opacity hover:text-muted-foreground focus-visible:opacity-100 group-hover/label:opacity-100"
            >
              <MoreHorizontal className="h-3 w-3" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-32 font-mono text-xs">
            {actions.map(({ key, icon: Icon, label: actionLabel, onSelect }) => (
              <DropdownMenuItem key={key} className="text-xs" onSelect={onSelect}>
                <Icon className="h-3 w-3" />
                {actionLabel}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {newSessionDirectory && (
        <NewSessionButton
          directory={newSessionDirectory}
          label={label}
          worktreeBranch={worktreeBranch}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );

  if (actions.length === 0) return header;

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{header}</ContextMenuTrigger>
      <ContextMenuContent className="text-xs">
        {actions.map(({ key, icon: Icon, label: actionLabel, onSelect }) => (
          <ContextMenuItem key={key} className="text-xs" onSelect={onSelect}>
            <Icon className="h-3 w-3" />
            {actionLabel}
          </ContextMenuItem>
        ))}
      </ContextMenuContent>
    </ContextMenu>
  );
}
