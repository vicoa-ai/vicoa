'use client';

// Design system for the human task tracker, modeled on multica's issue UI
// (~/playground/multica): Linear-style SVG status icons (dashed ring + pie
// fill), 4-bar priority icons, pill-button property pickers, and the shared
// status/priority vocabulary. Used by the tasks page (list + board), the
// task dialog, and the new-session task picker.

import { useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  CalendarDays,
  CalendarOff,
  Check,
  CornerDownRight,
  CornerUpRight,
  Folder,
  Inbox,
  MoreHorizontal,
  Pencil,
  Play,
  Repeat,
  Tag,
  Trash2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Input } from '@/components/ui/input';
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  ProjectResponse,
  TaskLabelResponse,
  TaskPriority,
  TaskResponse,
  TaskStatus,
  UpdateTaskRequest,
} from '@/lib/backend-api';
import { projectAvatarColor, projectIconSrc, projectInitial } from '@/lib/project-icons';
import { cn } from '@/lib/utils';
import { pointerWithin, closestCenter, type CollisionDetection } from '@dnd-kit/core';

// ---------------------------------------------------------------------------
// Status / priority vocabulary (multica STATUS_CONFIG / PRIORITY_CONFIG,
// colors mapped onto vicoa's palette — no warning/success/info tokens here)
// ---------------------------------------------------------------------------

export const STATUS_ORDER: TaskStatus[] = [
  'backlog',
  'todo',
  'in_progress',
  'in_review',
  'done',
  'blocked',
  'cancelled',
];

export const STATUS_CONFIG: Record<
  TaskStatus,
  { label: string; iconColor: string; hoverBg: string; columnBg: string }
> = {
  backlog: {
    label: 'Backlog',
    iconColor: 'text-muted-foreground',
    hoverBg: 'hover:bg-accent',
    columnBg: 'bg-muted/40',
  },
  todo: {
    label: 'Todo',
    iconColor: 'text-muted-foreground',
    hoverBg: 'hover:bg-accent',
    columnBg: 'bg-muted/40',
  },
  in_progress: {
    label: 'In Progress',
    iconColor: 'text-yellow-500',
    hoverBg: 'hover:bg-yellow-500/10',
    columnBg: 'bg-yellow-500/5',
  },
  in_review: {
    label: 'In Review',
    iconColor: 'text-green-500',
    hoverBg: 'hover:bg-green-500/10',
    columnBg: 'bg-green-500/5',
  },
  done: {
    label: 'Done',
    iconColor: 'text-blue-500',
    hoverBg: 'hover:bg-blue-500/10',
    columnBg: 'bg-blue-500/5',
  },
  blocked: {
    label: 'Blocked',
    iconColor: 'text-red-500',
    hoverBg: 'hover:bg-red-500/10',
    columnBg: 'bg-red-500/5',
  },
  cancelled: {
    label: 'Cancelled',
    iconColor: 'text-muted-foreground',
    hoverBg: 'hover:bg-accent',
    columnBg: 'bg-muted/40',
  },
};

export const PRIORITY_ORDER: TaskPriority[] = ['urgent', 'high', 'medium', 'low', 'none'];

export const PRIORITY_CONFIG: Record<
  TaskPriority,
  { label: string; bars: number; color: string; badgeBg: string; badgeText: string }
> = {
  urgent: { label: 'Urgent', bars: 4, color: 'text-red-500', badgeBg: 'bg-red-500/10', badgeText: 'text-red-500' },
  high: { label: 'High', bars: 3, color: 'text-yellow-500', badgeBg: 'bg-yellow-500/10', badgeText: 'text-yellow-600 dark:text-yellow-500' },
  medium: { label: 'Medium', bars: 2, color: 'text-yellow-500', badgeBg: 'bg-yellow-500/10', badgeText: 'text-yellow-600 dark:text-yellow-500' },
  low: { label: 'Low', bars: 1, color: 'text-blue-500', badgeBg: 'bg-blue-500/10', badgeText: 'text-blue-500' },
  none: { label: 'No priority', bars: 0, color: 'text-muted-foreground', badgeBg: 'bg-muted', badgeText: 'text-muted-foreground' },
};

/** The Inbox project is shown by its own name everywhere — calling it "Inbox"
 *  in the filter but "No project" on a task read as two different buckets. */
export function projectLabel(project: ProjectResponse | undefined | null): string {
  return project?.name ?? 'Inbox';
}

export function formatTaskDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Parse a calendar day ("yyyy-mm-dd") as local midnight, not UTC midnight.
 *  `new Date('2026-07-24')` is UTC, which renders as the 23rd anywhere west of
 *  Greenwich — the day the user picked has to survive the round trip. */
export function dateOnlyToLocalDate(value: string): Date | undefined {
  const parts = value.split('-').map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return undefined;
  const [year, month, day] = parts;
  return new Date(year, month - 1, day);
}

/** Inverse of {@link dateOnlyToLocalDate}: a local Date → "yyyy-mm-dd". */
export function toDateOnly(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Short label for a calendar day, e.g. "Jul 24". */
export function formatDateOnly(value: string): string | null {
  const date = dateOnlyToLocalDate(value);
  if (!date) return null;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function isPastDate(iso: string | null): boolean {
  if (!iso) return false;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return date.getTime() < today.getTime();
}

// ---------------------------------------------------------------------------
// StatusIcon — multica's progress-circle glyphs (viewBox 0 0 14 14)
// ---------------------------------------------------------------------------

const CX = 7;
const CY = 7;
const OUTER_R = 6;
const FILL_R = 3.5;

/** Build a pie-wedge SVG path from 12 o'clock, clockwise */
function piePath(cx: number, cy: number, r: number, progress: number): string {
  const angle = 2 * Math.PI * progress;
  const endX = cx + r * Math.sin(angle);
  const endY = cy - r * Math.cos(angle);
  const largeArc = progress > 0.5 ? 1 : 0;
  return `M${cx},${cy} L${cx},${cy - r} A${r},${r} 0 ${largeArc},1 ${endX},${endY} Z`;
}

function ProgressCircle({
  progress,
  children,
}: {
  progress: number;
  children?: React.ReactNode;
}) {
  return (
    <>
      <circle
        cx={CX}
        cy={CY}
        r={OUTER_R}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeDasharray="3.14 0"
        strokeDashoffset={-0.7}
      />
      {progress === 1 ? (
        <circle cx={CX} cy={CY} r={OUTER_R} fill="currentColor" />
      ) : progress > 0 ? (
        <path d={piePath(CX, CY, FILL_R, progress)} fill="currentColor" />
      ) : null}
      {children}
    </>
  );
}

/** 16 small dots arranged in a ring */
function BacklogIcon() {
  const count = 16;
  const dotR = 0.55;
  return (
    <g>
      {Array.from({ length: count }, (_, i) => {
        const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
        return (
          <circle
            key={i}
            cx={CX + OUTER_R * Math.cos(angle)}
            cy={CY + OUTER_R * Math.sin(angle)}
            r={dotR}
            fill="currentColor"
          />
        );
      })}
    </g>
  );
}

const STATUS_RENDERERS: Record<TaskStatus, () => React.ReactNode> = {
  backlog: () => <BacklogIcon />,
  todo: () => <ProgressCircle progress={0} />,
  in_progress: () => <ProgressCircle progress={0.5} />,
  in_review: () => <ProgressCircle progress={0.75} />,
  done: () => (
    <ProgressCircle progress={1}>
      <path
        d="M10.951 4.24896C11.283 4.58091 11.283 5.11909 10.951 5.45104L5.95104 10.451C5.61909 10.783 5.0809 10.783 4.74896 10.451L2.74896 8.45104C2.41701 8.11909 2.41701 7.5809 2.74896 7.24896C3.0809 6.91701 3.61909 6.91701 3.95104 7.24896L5.35 8.64792L9.74896 4.24896C10.0809 3.91701 10.6191 3.91701 10.951 4.24896Z"
        fill="white"
        stroke="none"
      />
    </ProgressCircle>
  ),
  blocked: () => (
    <ProgressCircle progress={0}>
      <line
        x1={CX + FILL_R * Math.cos(Math.PI * 0.75)}
        y1={CY - FILL_R * Math.sin(Math.PI * 0.75)}
        x2={CX + FILL_R * Math.cos(-Math.PI * 0.25)}
        y2={CY - FILL_R * Math.sin(-Math.PI * 0.25)}
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </ProgressCircle>
  ),
  cancelled: () => (
    <ProgressCircle progress={0}>
      <path
        d="M5 5 L9 9 M9 5 L5 9"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </ProgressCircle>
  ),
};

export function StatusIcon({
  status,
  className = 'h-4 w-4',
  inheritColor = false,
}: {
  status: TaskStatus;
  className?: string;
  inheritColor?: boolean;
}) {
  const cfg = STATUS_CONFIG[status];
  const Renderer = STATUS_RENDERERS[status];
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      className={cn(className, inheritColor ? '' : cfg.iconColor, 'shrink-0')}
    >
      <Renderer />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// PriorityIcon — multica's 4-bar glyph
// ---------------------------------------------------------------------------

export function PriorityIcon({
  priority,
  className = '',
  inheritColor = false,
}: {
  priority: TaskPriority;
  className?: string;
  inheritColor?: boolean;
}) {
  const cfg = PRIORITY_CONFIG[priority];

  // "none" — a simple horizontal dash
  if (cfg.bars === 0) {
    return (
      <svg
        viewBox="0 0 16 16"
        className={cn('h-3.5 w-3.5 shrink-0', inheritColor ? '' : 'text-muted-foreground', className)}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      >
        <line x1="3" y1="8" x2="13" y2="8" />
      </svg>
    );
  }

  const isUrgent = priority === 'urgent';

  return (
    <svg
      viewBox="0 0 16 16"
      className={cn('h-3.5 w-3.5 shrink-0', inheritColor ? '' : cfg.color, className)}
      fill="currentColor"
      style={isUrgent ? { animation: 'task-priority-pulse 2s ease-in-out infinite' } : undefined}
    >
      {[0, 1, 2, 3].map((i) => (
        <rect
          key={i}
          x={1 + i * 4}
          width="3"
          rx="0.5"
          y={12 - (i + 1) * 3}
          height={(i + 1) * 3}
          opacity={i < cfg.bars ? 1 : 0.2}
        />
      ))}
      {isUrgent && (
        <style>{`@keyframes task-priority-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}`}</style>
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// ProjectIcon — the project's emoji, else a line icon (multica project-icon)
// ---------------------------------------------------------------------------

/**
 * A project with no emoji falls back to a stroked lucide glyph rather than a
 * default emoji: 📁/📥 read as a *chosen* icon and sat oddly next to the line
 * icons on the neighbouring pills (status, priority, dates).
 */
/**
 * A project's icon, rendering the full fallback chain (identity-unification
 * §5d): uploaded/seeded image → emoji `icon` → a generated initial-square
 * (paseo-style hashed color + first letter) → Inbox/Folder glyph when there's no
 * name to seed one. `className` sizes the box (default `size-3.5`); the image and
 * square fill it, so a larger box just needs a bigger `size-*`.
 */
export function ProjectIcon({
  project,
  className,
}: {
  project?: {
    id?: string;
    name?: string | null;
    icon?: string | null;
    icon_image_uri?: string | null;
    updated_at?: string;
    is_inbox?: boolean;
  } | null;
  className?: string;
}) {
  const box = cn('size-3.5 shrink-0', className);

  const src = project && project.id ? projectIconSrc({
    id: project.id,
    icon_image_uri: project.icon_image_uri,
    updated_at: project.updated_at,
  }) : null;
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element -- authed proxy stream, not a static asset
    return (
      <img
        src={src}
        alt=""
        aria-hidden="true"
        className={cn('rounded-[0.28em] object-cover', box)}
      />
    );
  }

  if (project?.icon) {
    return (
      <span
        aria-hidden="true"
        className={cn('inline-flex items-center justify-center text-xs leading-none', box)}
      >
        {project.icon}
      </span>
    );
  }

  // A real (non-Inbox) project with a name and no icon gets a generated square.
  if (project && !project.is_inbox && project.name) {
    return (
      <span
        aria-hidden="true"
        style={{ backgroundColor: projectAvatarColor(project.id ?? project.name) }}
        className={cn(
          'inline-flex items-center justify-center rounded-[0.28em] text-[10px] font-medium leading-none text-white',
          box,
        )}
      >
        {projectInitial(project.name)}
      </span>
    );
  }

  const Icon = project?.is_inbox ? Inbox : Folder;
  return <Icon aria-hidden="true" className={cn('text-muted-foreground', box)} />;
}

// ---------------------------------------------------------------------------
// PillButton — outlined property-pill trigger (multica common/pill-button)
// ---------------------------------------------------------------------------

export function PillButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
        'hover:bg-accent/60 transition-colors cursor-pointer',
        'data-[state=open]:bg-accent data-[state=open]:text-accent-foreground',
        'disabled:cursor-not-allowed disabled:hover:bg-transparent',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// PropertyPicker — generic popover list shell + PickerItem rows
// ---------------------------------------------------------------------------

export function PickerItem({
  selected,
  onClick,
  hoverClassName,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  hoverClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors cursor-pointer',
        hoverClassName ?? 'hover:bg-accent',
      )}
    >
      {children}
      {selected && <Check className="ml-auto h-3.5 w-3.5 shrink-0" />}
    </button>
  );
}

function PickerPopover({
  open,
  onOpenChange,
  trigger,
  width = 'w-44',
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  trigger: React.ReactNode;
  width?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="start" className={cn(width, 'p-1')}>
        {children}
      </PopoverContent>
    </Popover>
  );
}

export function StatusPickerPill({
  status,
  onSelect,
}: {
  status: TaskStatus;
  onSelect: (status: TaskStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <PickerPopover
      open={open}
      onOpenChange={setOpen}
      trigger={
        <PillButton>
          <StatusIcon status={status} className="h-3.5 w-3.5" />
          <span className="truncate">{STATUS_CONFIG[status].label}</span>
        </PillButton>
      }
    >
      {STATUS_ORDER.map((s) => (
        <PickerItem
          key={s}
          selected={s === status}
          hoverClassName={STATUS_CONFIG[s].hoverBg}
          onClick={() => {
            onSelect(s);
            setOpen(false);
          }}
        >
          <StatusIcon status={s} className="h-3.5 w-3.5" />
          <span>{STATUS_CONFIG[s].label}</span>
        </PickerItem>
      ))}
    </PickerPopover>
  );
}

export function PriorityPickerPill({
  priority,
  onSelect,
}: {
  priority: TaskPriority;
  onSelect: (priority: TaskPriority) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <PickerPopover
      open={open}
      onOpenChange={setOpen}
      trigger={
        <PillButton>
          <PriorityIcon priority={priority} />
          <span className="truncate">{PRIORITY_CONFIG[priority].label}</span>
        </PillButton>
      }
    >
      {PRIORITY_ORDER.map((p) => {
        const c = PRIORITY_CONFIG[p];
        return (
          <PickerItem
            key={p}
            selected={p === priority}
            onClick={() => {
              onSelect(p);
              setOpen(false);
            }}
          >
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium',
                c.badgeBg,
                c.badgeText,
              )}
            >
              <PriorityIcon priority={p} className="h-3 w-3" inheritColor />
              {c.label}
            </span>
          </PickerItem>
        );
      })}
    </PickerPopover>
  );
}

export function ProjectPickerPill({
  projects,
  projectId,
  onSelect,
}: {
  projects: ProjectResponse[];
  projectId: string | null;
  onSelect: (projectId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = projects.find((p) => p.id === projectId) ?? null;
  return (
    <PickerPopover
      open={open}
      onOpenChange={setOpen}
      width="w-52"
      trigger={
        <PillButton>
          <ProjectIcon project={current} />
          <span className="max-w-32 truncate">{projectLabel(current)}</span>
        </PillButton>
      }
    >
      {projects.map((project) => (
        <PickerItem
          key={project.id}
          selected={project.id === projectId}
          onClick={() => {
            onSelect(project.id);
            setOpen(false);
          }}
        >
          <ProjectIcon project={project} />
          <span className="truncate">{projectLabel(project)}</span>
        </PickerItem>
      ))}
    </PickerPopover>
  );
}

/**
 * All descendants of `rootId` in the flat task list (children, grandchildren, …).
 * Used to exclude a task's own subtree from the parent picker so the client
 * can't offer a parent that would create a cycle (the backend rejects it too,
 * via `_validate_parent` — this is just UX).
 */
export function collectDescendantIds(
  tasks: TaskResponse[],
  rootId: string,
): Set<string> {
  const childrenOf = new Map<string, string[]>();
  for (const t of tasks) {
    if (!t.parent_task_id) continue;
    const list = childrenOf.get(t.parent_task_id) ?? [];
    list.push(t.id);
    childrenOf.set(t.parent_task_id, list);
  }
  const out = new Set<string>();
  const stack = [...(childrenOf.get(rootId) ?? [])];
  while (stack.length) {
    const id = stack.pop()!;
    if (out.has(id)) continue;
    out.add(id);
    for (const child of childrenOf.get(id) ?? []) stack.push(child);
  }
  return out;
}

/**
 * Parent-task picker pill (sibling of ProjectPickerPill). Lists the user's
 * tasks in a filterable popover so any task can be made a sub-task of another.
 * `currentTaskId` and its descendants are excluded to keep the tree acyclic;
 * in create mode (`currentTaskId` null) nothing is excluded.
 */
export function ParentPickerPill({
  tasks,
  currentTaskId,
  parentId,
  onSelect,
}: {
  tasks: TaskResponse[];
  currentTaskId: string | null;
  parentId: string | null;
  onSelect: (parentId: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const current = tasks.find((t) => t.id === parentId) ?? null;

  const excluded = useMemo(() => {
    if (!currentTaskId) return new Set<string>();
    const set = collectDescendantIds(tasks, currentTaskId);
    set.add(currentTaskId);
    return set;
  }, [tasks, currentTaskId]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tasks
      .filter((t) => !excluded.has(t.id))
      .filter((t) => (q ? t.title.toLowerCase().includes(q) : true))
      .slice(0, 50);
  }, [tasks, excluded, query]);

  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setQuery('');
      }}
    >
      <PopoverTrigger asChild>
        <PillButton className={current ? '' : 'text-muted-foreground'}>
          <CornerUpRight className="h-3 w-3 shrink-0" />
          <span className="max-w-40 truncate">{current ? current.title : 'No parent'}</span>
        </PillButton>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-1">
        <div className="p-1">
          <Input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks…"
            className="h-7 text-xs"
          />
        </div>
        <div className="custom-scrollbar max-h-64 overflow-y-auto">
          <PickerItem
            selected={parentId === null}
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
          >
            <X className="h-3.5 w-3.5 text-muted-foreground" />
            <span>No parent</span>
          </PickerItem>
          {results.map((t) => (
            <PickerItem
              key={t.id}
              selected={t.id === parentId}
              onClick={() => {
                onSelect(t.id);
                setOpen(false);
              }}
            >
              <StatusIcon status={t.status} className="h-3.5 w-3.5" />
              <span className="truncate">{t.title}</span>
            </PickerItem>
          ))}
          {results.length === 0 && (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">No matching tasks</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** Date pill: popover hosting a native date input + Clear. */
export function DatePickerPill({
  label,
  value,
  icon = 'due',
  onChange,
}: {
  label: string;
  /** yyyy-mm-dd or '' */
  value: string;
  icon?: 'start' | 'due';
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const Icon = icon === 'start' ? CalendarClock : CalendarDays;
  const display = value ? formatDateOnly(value) : null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <PillButton className={display ? '' : 'text-muted-foreground'}>
          <Icon className="h-3 w-3 shrink-0" />
          <span>{display ?? label}</span>
        </PillButton>
      </PopoverTrigger>
      {/* The calendar itself is the popover body — opening the pill lands
          straight on a month grid (multica's DateOnlyPicker), rather than on a
          native date input that needs a second click to reveal one. */}
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          mode="single"
          autoFocus
          selected={value ? dateOnlyToLocalDate(value) : undefined}
          defaultMonth={value ? dateOnlyToLocalDate(value) : undefined}
          onSelect={(date) => {
            onChange(date ? toDateOnly(date) : '');
            setOpen(false);
          }}
        />
        {value && (
          <div className="border-t p-2">
            <button
              type="button"
              onClick={() => {
                onChange('');
                setOpen(false);
              }}
              className="flex w-full cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <CalendarOff className="h-3 w-3" />
              Clear {label.toLowerCase()}
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

// ---------------------------------------------------------------------------
// Task actions menu (…) — status / priority / project submenus + actions
// ---------------------------------------------------------------------------

export function TaskActionsMenu({
  task,
  projects,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
  className,
}: {
  task: TaskResponse;
  projects: ProjectResponse[];
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  /** Open the automation create form seeded from this task (title + description). */
  onCreateAutomation?: (task: TaskResponse) => void;
  className?: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn('h-6 w-6 p-0 rounded-full text-muted-foreground', className)}
          title="Task actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44 text-xs">
        {onStartSession && (
          <>
            <DropdownMenuItem onSelect={() => onStartSession(task)}>
              <Play className="h-3.5 w-3.5 mr-2" />
              Start session
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onSelect={() => onEdit(task)}>
          <Pencil className="h-3.5 w-3.5 mr-2" />
          Edit
        </DropdownMenuItem>
        {onCreateAutomation && (
          <DropdownMenuItem onSelect={() => onCreateAutomation(task)}>
            <Repeat className="h-3.5 w-3.5 mr-2" />
            Schedule
          </DropdownMenuItem>
        )}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <StatusIcon status={task.status} className="h-3.5 w-3.5 mr-2" />
            Status
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="text-xs">
            {STATUS_ORDER.map((status) => (
              <DropdownMenuItem key={status} onSelect={() => onPatch(task.id, { status })}>
                <StatusIcon status={status} className="h-3.5 w-3.5 mr-2" />
                {STATUS_CONFIG[status].label}
                {status === task.status && <Check className="ml-auto h-3 w-3" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <PriorityIcon priority={task.priority} className="mr-2" />
            Priority
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="text-xs">
            {PRIORITY_ORDER.map((priority) => (
              <DropdownMenuItem
                key={priority}
                onSelect={() => onPatch(task.id, { priority })}
              >
                <PriorityIcon priority={priority} className="mr-2" />
                {PRIORITY_CONFIG[priority].label}
                {priority === task.priority && <Check className="ml-auto h-3 w-3" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <ProjectIcon
              project={projects.find((p) => p.id === task.project_id)}
              className="mr-2"
            />
            Move to project
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="text-xs">
            {projects.map((project) => (
              <DropdownMenuItem
                key={project.id}
                onSelect={() => onPatch(task.id, { project_id: project.id })}
              >
                <ProjectIcon project={project} className="mr-2" />
                {projectLabel(project)}
                {project.id === task.project_id && <Check className="ml-auto h-3 w-3" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-red-600 dark:text-red-400 focus:text-red-600 dark:focus:text-red-400"
          onSelect={() => onDelete(task)}
        >
          <Trash2 className="h-3.5 w-3.5 mr-2" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// Labels (multica label-chip + inline-create palette)
// ---------------------------------------------------------------------------

/**
 * Map a label's #rrggbb color to a readable text color (BT.601 luminance).
 * The backend pins colors to #rrggbb — LabelChip inline-styles them, so that
 * format must never loosen (injection vector otherwise).
 */
function contrastTextColor(hex: string): string {
  const h = hex.replace('#', '');
  if (h.length !== 6) return '#111827';
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance > 0.55 ? '#111827' : '#f9fafb';
}

export function LabelChip({ label }: { label: TaskLabelResponse }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-4"
      style={{ backgroundColor: label.color, color: contrastTextColor(label.color) }}
      title={label.name}
    >
      <span className="max-w-[8rem] truncate">{label.name}</span>
    </span>
  );
}

/** Up to `max` chips + a "+n" overflow hint (multica list-row treatment). */
export function LabelChips({
  labels,
  max = 3,
}: {
  labels: TaskLabelResponse[];
  max?: number;
}) {
  if (labels.length === 0) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 overflow-hidden">
      {labels.slice(0, max).map((label) => (
        <LabelChip key={label.id} label={label} />
      ))}
      {labels.length > max && (
        <span className="text-[11px] text-muted-foreground">+{labels.length - max}</span>
      )}
    </span>
  );
}

/**
 * Colors cycled by hash(name) for inline label creation, so the same name
 * always gets the same color (multica INLINE_COLORS).
 */
export const INLINE_LABEL_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6',
  '#3b82f6', '#6366f1', '#a855f7', '#ec4899', '#64748b',
] as const;

export function inlineLabelColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  return INLINE_LABEL_COLORS[Math.abs(hash) % INLINE_LABEL_COLORS.length];
}

/** Multi-select label pill: toggle rows + inline create-from-query. */
export function LabelPickerPill({
  labels,
  selectedIds,
  onToggle,
  onCreate,
}: {
  labels: TaskLabelResponse[];
  selectedIds: string[];
  onToggle: (labelId: string) => void;
  /** Create a label named after the query; caller persists + selects it. */
  onCreate?: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const selected = labels.filter((label) => selectedIds.includes(label.id));
  const visible = labels.filter((label) =>
    label.name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const canCreate =
    !!onCreate &&
    !!query.trim() &&
    !labels.some((label) => label.name.toLowerCase() === query.trim().toLowerCase());

  return (
    <Popover open={open} onOpenChange={(v) => { setOpen(v); if (!v) setQuery(''); }}>
      <PopoverTrigger asChild>
        {/* Leading icon like every neighbouring pill (status, priority,
            project, dates) — without one this pill read as stray text. */}
        <PillButton className={selected.length > 0 ? '' : 'text-muted-foreground'}>
          <Tag className="h-3 w-3 shrink-0" />
          {selected.length > 0 ? (
            <span className="flex items-center gap-1">
              {selected.slice(0, 2).map((label) => (
                <span
                  key={label.id}
                  className="size-2 rounded-full"
                  style={{ backgroundColor: label.color }}
                />
              ))}
              <span className="max-w-28 truncate">
                {selected.map((label) => label.name).join(', ')}
              </span>
            </span>
          ) : (
            <span>Labels</span>
          )}
        </PillButton>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-52 p-0">
        <div className="border-b px-2 py-1.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter or create…"
            className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-56 overflow-y-auto p-1">
          {visible.map((label) => (
            <PickerItem
              key={label.id}
              selected={selectedIds.includes(label.id)}
              onClick={() => onToggle(label.id)}
            >
              <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: label.color }} />
              <span className="truncate">{label.name}</span>
            </PickerItem>
          ))}
          {canCreate && (
            <button
              type="button"
              onClick={() => {
                onCreate?.(query.trim());
                setQuery('');
              }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-accent cursor-pointer"
            >
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: inlineLabelColor(query.trim()) }}
              />
              Create “{query.trim()}”
            </button>
          )}
          {visible.length === 0 && !canCreate && (
            <p className="px-2 py-2 text-center text-xs text-muted-foreground">No labels</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ---------------------------------------------------------------------------
// ProgressRing — sub-task progress (multica progress-ring)
// ---------------------------------------------------------------------------

export function ProgressRing({
  done,
  total,
  size = 12,
}: {
  done: number;
  total: number;
  size?: number;
}) {
  const stroke = 1.5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = total > 0 ? Math.min(done / total, 1) : 0;
  const offset = circumference * (1 - ratio);
  const isComplete = total > 0 && done >= total;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={isComplete ? 'text-blue-500' : 'text-primary'}
      aria-hidden="true"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

/** "done/total" chip shown on parent rows/cards. */
export function ChildProgressChip({ done, total }: { done: number; total: number }) {
  if (total === 0) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-muted/60 px-1.5 py-0.5">
      <ProgressRing done={done} total={total} size={14} />
      <span className="text-[11px] font-medium tabular-nums text-muted-foreground">
        {done}/{total}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Kanban collision (multica drag-utils.makeKanbanCollision): prefer the card
// under the pointer, else the hovered column, else nearest center — this is
// what makes drops into EMPTY columns land (closestCorners picks a far card
// in a neighbouring column instead of the hovered empty column).
// ---------------------------------------------------------------------------

export function makeKanbanCollision(columnIds: Set<string>): CollisionDetection {
  return (args) => {
    const pointer = pointerWithin(args);
    if (pointer.length > 0) {
      const items = pointer.filter((c) => !columnIds.has(String(c.id)));
      if (items.length > 0) return items;
      return pointer;
    }
    return closestCenter(args);
  };
}

// ---------------------------------------------------------------------------
// Right-click context menu — same actions as TaskActionsMenu
// ---------------------------------------------------------------------------

export function TaskContextMenu({
  task,
  projects,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
  children,
}: {
  task: TaskResponse;
  projects: ProjectResponse[];
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  /** Open the automation create form seeded from this task (title + description). */
  onCreateAutomation?: (task: TaskResponse) => void;
  children: React.ReactNode;
}) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-44 text-xs">
        {onStartSession && (
          <>
            <ContextMenuItem onSelect={() => onStartSession(task)}>
              <Play className="h-3.5 w-3.5 mr-2" />
              Start session
            </ContextMenuItem>
            <ContextMenuSeparator />
          </>
        )}
        <ContextMenuItem onSelect={() => onEdit(task)}>
          <Pencil className="h-3.5 w-3.5 mr-2" />
          Edit
        </ContextMenuItem>
        {onCreateAutomation && (
          <ContextMenuItem onSelect={() => onCreateAutomation(task)}>
            <Repeat className="h-3.5 w-3.5 mr-2" />
            Schedule
          </ContextMenuItem>
        )}
        <ContextMenuSub>
          <ContextMenuSubTrigger>
            <StatusIcon status={task.status} className="h-3.5 w-3.5 mr-2" />
            Status
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="text-xs">
            {STATUS_ORDER.map((status) => (
              <ContextMenuItem key={status} onSelect={() => onPatch(task.id, { status })}>
                <StatusIcon status={status} className="h-3.5 w-3.5 mr-2" />
                {STATUS_CONFIG[status].label}
                {status === task.status && <Check className="ml-auto h-3 w-3" />}
              </ContextMenuItem>
            ))}
          </ContextMenuSubContent>
        </ContextMenuSub>
        <ContextMenuSub>
          <ContextMenuSubTrigger>
            <PriorityIcon priority={task.priority} className="mr-2" />
            Priority
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="text-xs">
            {PRIORITY_ORDER.map((priority) => (
              <ContextMenuItem
                key={priority}
                onSelect={() => onPatch(task.id, { priority })}
              >
                <PriorityIcon priority={priority} className="mr-2" />
                {PRIORITY_CONFIG[priority].label}
                {priority === task.priority && <Check className="ml-auto h-3 w-3" />}
              </ContextMenuItem>
            ))}
          </ContextMenuSubContent>
        </ContextMenuSub>
        <ContextMenuSub>
          <ContextMenuSubTrigger>
            <ProjectIcon
              project={projects.find((p) => p.id === task.project_id)}
              className="mr-2"
            />
            Move to project
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="text-xs">
            {projects.map((project) => (
              <ContextMenuItem
                key={project.id}
                onSelect={() => onPatch(task.id, { project_id: project.id })}
              >
                <ProjectIcon project={project} className="mr-2" />
                {projectLabel(project)}
                {project.id === task.project_id && <Check className="ml-auto h-3 w-3" />}
              </ContextMenuItem>
            ))}
          </ContextMenuSubContent>
        </ContextMenuSub>
        <ContextMenuSeparator />
        <ContextMenuItem
          className="text-red-600 dark:text-red-400 focus:text-red-600 dark:focus:text-red-400"
          onSelect={() => onDelete(task)}
        >
          <Trash2 className="h-3.5 w-3.5 mr-2" />
          Delete
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------

/** Section/column heading: status icon + label + muted count. */
export function StatusHeading({ status, count }: { status: TaskStatus; count: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
        <StatusIcon status={status} className="h-3 w-3" />
        {STATUS_CONFIG[status].label}
      </span>
      <span className="text-xs text-muted-foreground">{count}</span>
    </div>
  );
}

/** Project chip (rounded, muted) used on cards and rows. */
export function ProjectChip({ project }: { project: ProjectResponse | undefined }) {
  if (!project || project.is_inbox) return null;
  return (
    <span className="inline-flex max-w-[160px] items-center gap-1 rounded-full bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
      <ProjectIcon project={project} />
      <span className="truncate">{project.name}</span>
    </span>
  );
}

/**
 * "Sub-task of …" chip for list rows / board cards, so a sub-task visibly
 * reads as one. Renders nothing when the task has no parent (or the parent
 * isn't in the map, e.g. filtered out).
 */
export function ParentChip({ parent }: { parent: TaskResponse | undefined }) {
  if (!parent) return null;
  return (
    <span
      className="inline-flex max-w-[160px] items-center gap-1 rounded-full bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground"
      title={`Sub-task of ${parent.title}`}
    >
      <CornerDownRight className="h-3 w-3 shrink-0" />
      <span className="truncate">{parent.title}</span>
    </span>
  );
}

/** Debounce-free ESC/typing guard used by the dialog title input. */
export function useAutoFocus<T extends HTMLElement>(enabled: boolean) {
  const [node, setNode] = useState<T | null>(null);
  useEffect(() => {
    if (enabled && node) {
      const frame = requestAnimationFrame(() => node.focus());
      return () => cancelAnimationFrame(frame);
    }
  }, [enabled, node]);
  return setNode;
}
