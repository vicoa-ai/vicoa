'use client';

import { Archive, Check, CirclePlay, Copy, Mail, MoreVertical, Pencil, Pin, PinOff, Trash2, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

/** The set of session actions, independent of how they're rendered. Both the
    three-dot dropdown (below) and the sidebar's right-click context menu build
    from this so they can't drift apart. */
export interface SessionActionsConfig {
  onRename?: () => void;
  onCopyId?: () => void;
  copied?: boolean;
  onMarkDone?: () => void;
  showMarkDone?: boolean;
  onUnread?: () => void;
  showUnread?: boolean;
  onDelete?: () => void;
  onResume?: () => void;
  showResume?: boolean;
  /** Set when Resume is visible but not possible right now (e.g. the computer
   *  is offline). Rendered disabled with the reason rather than hidden — a
   *  missing item reads as "unsupported", a disabled one as "not right now". */
  resumeDisabledReason?: string | null;
  /** Short reason shown under "Resume" when it can't run (e.g. "Computer offline"). */
  resumeBlockedLabel?: string | null;
  onPin?: () => void;
  isPinned?: boolean;
  extraActions?: Array<{ label: string; onClick: () => void }>;
}

/** One rendered action: an icon, a label (optionally with a small sublabel),
    a select handler, and an optional disabled state + tooltip. */
export interface SessionActionDescriptor {
  key: string;
  icon?: LucideIcon;
  iconClassName?: string;
  label: string;
  sublabel?: string | null;
  onSelect: () => void;
  disabled?: boolean;
  title?: string;
}

/** Resolve the config into an ordered action list. Order is the canonical one
    shared by every menu: extras, Resume, Pin, Rename, Copy ID, Unread, Archive,
    Delete. Items whose handler/flag is absent are omitted. */
export function buildSessionActions({
  onRename,
  onCopyId,
  copied = false,
  onMarkDone,
  showMarkDone = false,
  onUnread,
  showUnread = false,
  onDelete,
  onResume,
  showResume = false,
  resumeDisabledReason = null,
  resumeBlockedLabel = null,
  onPin,
  isPinned = false,
  extraActions = [],
}: SessionActionsConfig): SessionActionDescriptor[] {
  const actions: SessionActionDescriptor[] = [];

  for (const action of extraActions) {
    actions.push({ key: `extra:${action.label}`, label: action.label, onSelect: action.onClick });
  }
  if (showResume && onResume) {
    actions.push({
      key: 'resume',
      icon: CirclePlay,
      label: 'Resume',
      sublabel: resumeBlockedLabel,
      onSelect: onResume,
      disabled: !!resumeDisabledReason,
      title: resumeDisabledReason ?? undefined,
    });
  }
  if (onPin) {
    actions.push({
      key: 'pin',
      icon: isPinned ? PinOff : Pin,
      label: isPinned ? 'Unpin' : 'Pin',
      onSelect: onPin,
    });
  }
  if (onRename) {
    actions.push({ key: 'rename', icon: Pencil, label: 'Rename', onSelect: onRename });
  }
  if (onCopyId) {
    actions.push({
      key: 'copy-id',
      icon: copied ? Check : Copy,
      iconClassName: copied ? 'text-success' : undefined,
      label: copied ? 'Copied ID' : 'Copy ID',
      onSelect: onCopyId,
    });
  }
  if (showUnread && onUnread) {
    actions.push({ key: 'unread', icon: Mail, label: 'Unread', onSelect: onUnread });
  }
  if (showMarkDone && onMarkDone) {
    actions.push({ key: 'archive', icon: Archive, label: 'Archive', onSelect: onMarkDone });
  }
  if (onDelete) {
    actions.push({ key: 'delete', icon: Trash2, label: 'Delete', onSelect: onDelete });
  }
  return actions;
}

/** The inner content of a menu item (icon + label + optional sublabel), shared
    across DropdownMenuItem and ContextMenuItem — both already provide `gap-2`
    and icon sizing, so no per-item margin is needed. */
export function SessionActionItemContent({ action }: { action: SessionActionDescriptor }) {
  const Icon = action.icon;
  return (
    <>
      {Icon ? <Icon className={cn('h-3 w-3', action.iconClassName)} /> : null}
      {action.sublabel ? (
        <span className="flex flex-col items-start leading-tight">
          <span>{action.label}</span>
          {/* A disabled item can't fire a click, so it can't explain itself on
              demand — surface the reason inline instead. */}
          <span className="text-[10px] text-muted-foreground">{action.sublabel}</span>
        </span>
      ) : (
        action.label
      )}
    </>
  );
}

type SessionActionsMenuProps = SessionActionsConfig & {
  className?: string;
  iconClassName?: string;
  contentClassName?: string;
};

export function SessionActionsMenu({
  className,
  iconClassName,
  contentClassName,
  ...config
}: SessionActionsMenuProps) {
  const actions = buildSessionActions(config);
  if (actions.length === 0) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={className ?? 'h-6 w-6 p-0'}
        >
          <MoreVertical className={iconClassName ?? 'h-3 w-3'} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className={contentClassName ?? 'font-mono'}>
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.key}
            onClick={action.onSelect}
            disabled={action.disabled}
            title={action.title}
            className="text-xs"
          >
            <SessionActionItemContent action={action} />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
