'use client';

import type React from 'react';
import {
  Archive,
  Check,
  ChevronRight,
  CirclePlay,
  Copy,
  Folder,
  Mail,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Share,
  Trash2,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from '@/components/ui/context-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

/** One entry of an action's submenu (e.g. a project under "Project ▸"). */
export interface SessionActionChoice {
  key: string;
  label: string;
  /** Leading icon, already rendered (a project's own icon, say). */
  leading?: React.ReactNode;
  /** The current value: drawn with a check. */
  checked?: boolean;
  /** Draw a separator above this entry. */
  separatorBefore?: boolean;
  onSelect: () => void;
}

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
  /** Open the share dialog (a read-only link; collaboration P4). Omitted where
   *  the caller cannot mint one — e.g. logged-out desktop, non-owners. */
  onShare?: () => void;
  /** Where the session can be filed, for the "Project ▸" submenu: the
   *  projects plus No project, the current one checked. Omitted where the
   *  caller cannot move it (someone else's session, no projects API). */
  projectChoices?: SessionActionChoice[];
  extraActions?: Array<{ label: string; onClick: () => void }>;
}

/** One rendered action: an icon, a label (optionally with a small sublabel),
    a select handler, and an optional disabled state + tooltip. With
    `submenu`, the action opens those choices instead of firing `onSelect`. */
export interface SessionActionDescriptor {
  key: string;
  icon?: LucideIcon;
  iconClassName?: string;
  label: string;
  sublabel?: string | null;
  onSelect: () => void;
  disabled?: boolean;
  title?: string;
  submenu?: SessionActionChoice[];
}

/** Resolve the config into an ordered action list. Order is the canonical one
    shared by every menu: extras, Resume, Pin, Share, Rename, Project, Copy ID,
    Unread, Archive, Delete. Items whose handler/flag is absent are omitted. */
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
  onShare,
  projectChoices,
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
  if (onShare) {
    actions.push({ key: 'share', icon: Share, label: 'Share', onSelect: onShare });
  }
  if (onRename) {
    actions.push({ key: 'rename', icon: Pencil, label: 'Rename', onSelect: onRename });
  }
  if (projectChoices && projectChoices.length > 0) {
    actions.push({
      key: 'project',
      icon: Folder,
      label: 'Project',
      onSelect: () => {},
      submenu: projectChoices,
    });
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

// A project list can be long; the submenu scrolls rather than run off screen.
const SUBMENU_CONTENT_CLASS = 'font-mono max-w-64 max-h-72 overflow-y-auto custom-scrollbar';

// The dropdown's sub-trigger primitive is styled apart from its items (no icon
// gap, accent highlight, arrow cursor); match the items so it reads as one.
const DROPDOWN_SUB_TRIGGER_CLASS =
  "gap-2 text-xs cursor-pointer focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 data-[state=open]:bg-foreground/[0.06] dark:data-[state=open]:bg-foreground/10 focus:text-foreground data-[state=open]:text-foreground [&_svg:not([class*='text-'])]:text-muted-foreground [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4";

function SessionActionChoiceContent({ choice }: { choice: SessionActionChoice }) {
  return (
    <>
      {choice.leading}
      <span className="truncate">{choice.label}</span>
      {choice.checked ? <Check className="ml-auto h-3 w-3" /> : null}
    </>
  );
}

/** The actions as right-click menu items — the context-menu twin of the
    dropdown below, submenus included. */
export function SessionActionContextMenuItems({ actions }: { actions: SessionActionDescriptor[] }) {
  return (
    <>
      {actions.map((action) =>
        action.submenu ? (
          <ContextMenuSub key={action.key}>
            <ContextMenuSubTrigger className="text-xs">
              <SessionActionItemContent action={action} />
              {/* Unlike the dropdown's, this trigger draws no chevron itself. */}
              <ChevronRight className="ml-auto h-3 w-3" />
            </ContextMenuSubTrigger>
            <ContextMenuSubContent className={SUBMENU_CONTENT_CLASS}>
              {action.submenu.map((choice) => [
                choice.separatorBefore ? <ContextMenuSeparator key={`${choice.key}:sep`} /> : null,
                <ContextMenuItem key={choice.key} className="text-xs" onSelect={choice.onSelect}>
                  <SessionActionChoiceContent choice={choice} />
                </ContextMenuItem>,
              ])}
            </ContextMenuSubContent>
          </ContextMenuSub>
        ) : (
          <ContextMenuItem
            key={action.key}
            className="text-xs"
            disabled={action.disabled}
            title={action.title}
            onSelect={action.onSelect}
          >
            <SessionActionItemContent action={action} />
          </ContextMenuItem>
        ),
      )}
    </>
  );
}

type SessionActionsMenuProps = SessionActionsConfig & {
  className?: string;
  iconClassName?: string;
  contentClassName?: string;
  /** Extra items rendered below the standard actions. They draw their own
      separator (one that may render nothing must not leave a stray line).
      Dropdown-only: the sidebar's context-menu variant builds from
      `buildSessionActions` and can't host DropdownMenu children. Used by the
      session header for the "Open in ▸" submenu. */
  trailingItems?: React.ReactNode;
};

export function SessionActionsMenu({
  className,
  iconClassName,
  contentClassName,
  trailingItems,
  ...config
}: SessionActionsMenuProps) {
  const actions = buildSessionActions(config);
  if (actions.length === 0 && !trailingItems) {
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
          <MoreHorizontal className={iconClassName ?? 'h-3 w-3'} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className={contentClassName ?? 'font-mono'}>
        {actions.map((action) =>
          action.submenu ? (
            <DropdownMenuSub key={action.key}>
              <DropdownMenuSubTrigger className={DROPDOWN_SUB_TRIGGER_CLASS}>
                <SessionActionItemContent action={action} />
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className={SUBMENU_CONTENT_CLASS}>
                {action.submenu.map((choice) => [
                  choice.separatorBefore ? <DropdownMenuSeparator key={`${choice.key}:sep`} /> : null,
                  <DropdownMenuItem key={choice.key} className="text-xs" onClick={choice.onSelect}>
                    <SessionActionChoiceContent choice={choice} />
                  </DropdownMenuItem>,
                ])}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          ) : (
            <DropdownMenuItem
              key={action.key}
              onClick={action.onSelect}
              disabled={action.disabled}
              title={action.title}
              className="text-xs"
            >
              <SessionActionItemContent action={action} />
            </DropdownMenuItem>
          ),
        )}
        {trailingItems}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
