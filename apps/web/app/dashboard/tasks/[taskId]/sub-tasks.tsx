'use client';

// The task page's tree context: a "Sub-task of …" link under the title when the
// task has a parent, and a Sub-tasks section listing its children. Both read
// from the page's flat task list (children are `parent_task_id` matches), so
// there is no extra endpoint and a child added here shows up on the board too.

import { useState } from 'react';
import Link from 'next/link';
import { CalendarDays, ChevronDown, Loader2, Plus } from 'lucide-react';

import { TaskResponse, TaskStatus } from '@/lib/backend-api';
import {
  ChildProgressChip,
  LabelChips,
  PickerItem,
  PickerPopover,
  PriorityIcon,
  ProgressRing,
  STATUS_CONFIG,
  STATUS_ORDER,
  StatusIcon,
  TaskIdentifier,
  formatTaskDate,
  isPastDate,
} from '@/components/dashboard/task-ui';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import {
  type Principal,
  principalDisplayName,
  principalForAvatar,
  principalFromResponse,
} from '@/lib/principals';
import { cn } from '@/lib/utils';

type Progress = { done: number; total: number };

/** done/total over a set of siblings; "done" alone counts, as on the board. */
export function subTaskProgress(children: TaskResponse[]): Progress {
  return {
    done: children.filter((c) => c.status === 'done').length,
    total: children.length,
  };
}

function isClosed(task: TaskResponse): boolean {
  return task.status === 'done' || task.status === 'cancelled';
}

function taskHref(taskId: string): string {
  return `/dashboard/tasks/${taskId}`;
}

/**
 * "Sub-task of ◯ VIC-41 Parent title 2/5". `parent` is null when the parent is
 * not in the caller's task list; the denormalized `parent_title` still names it.
 */
export function ParentTaskLink({
  task,
  parent,
  siblings,
}: {
  task: TaskResponse;
  parent: TaskResponse | null;
  /** The parent's children, this task included. */
  siblings: TaskResponse[];
}) {
  if (!task.parent_task_id) return null;
  const title = parent?.title ?? task.parent_title;
  if (!title) return null;
  const progress = subTaskProgress(siblings);
  return (
    <Link
      href={taskHref(task.parent_task_id)}
      className="group/parent inline-flex max-w-full cursor-pointer items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <span className="shrink-0 font-medium">Sub-task of</span>
      {parent && <StatusIcon status={parent.status} className="h-3.5 w-3.5" />}
      {parent && <TaskIdentifier task={parent} />}
      <span className="truncate group-hover/parent:text-foreground">{title}</span>
      {progress.total > 0 && (
        <span className="ml-1">
          <ChildProgressChip done={progress.done} total={progress.total} />
        </span>
      )}
    </Link>
  );
}

/** The row's status icon as a picker; a plain icon when the row is read-only. */
function RowStatusPicker({
  status,
  onSelect,
}: {
  status: TaskStatus;
  onSelect?: (status: TaskStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!onSelect) return <StatusIcon status={status} className="h-[15px] w-[15px]" />;
  return (
    <PickerPopover
      open={open}
      onOpenChange={setOpen}
      trigger={
        <button
          type="button"
          aria-label={`Status: ${STATUS_CONFIG[status].label}`}
          className="flex shrink-0 cursor-pointer items-center rounded-sm"
        >
          <StatusIcon status={status} className="h-[15px] w-[15px]" />
        </button>
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

function SubTaskRow({
  task,
  childProgress,
  viewer,
  onStatusChange,
}: {
  task: TaskResponse;
  /** The sub-task's own children — it can be a parent too. */
  childProgress?: Progress;
  viewer: Principal | null;
  onStatusChange?: (status: TaskStatus) => void;
}) {
  const closed = isClosed(task);
  const due = formatTaskDate(task.due_date);
  const assignee = principalFromResponse(task.assignee);

  // The link wraps only the identifier/title area: the status picker is a
  // sibling, so picking a status never navigates.
  return (
    <div className="group/row flex h-9 items-center gap-2.5 px-3 transition-colors hover:bg-accent/50">
      <PriorityIcon priority={task.priority} />
      <RowStatusPicker status={task.status} onSelect={onStatusChange} />
      <Link
        href={taskHref(task.id)}
        className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5"
      >
        <TaskIdentifier task={task} />
        <span
          className={cn(
            'min-w-0 truncate text-sm',
            closed && 'text-muted-foreground line-through',
          )}
        >
          {task.title}
        </span>
        <span className="hidden md:inline-flex">
          <LabelChips labels={task.labels} max={2} />
        </span>
        {childProgress && childProgress.total > 0 && (
          <ChildProgressChip done={childProgress.done} total={childProgress.total} />
        )}
      </Link>
      {due && (
        <span
          className={cn(
            'flex shrink-0 items-center gap-1 text-xs tabular-nums',
            !closed && isPastDate(task.due_date) ? 'text-red-500' : 'text-muted-foreground',
          )}
        >
          <CalendarDays className="size-3" />
          {due}
        </span>
      )}
      {assignee ? (
        <span title={principalDisplayName(assignee, viewer)} className="shrink-0">
          <PrincipalAvatar principal={principalForAvatar(assignee, viewer)} size="xs" />
        </span>
      ) : (
        <span
          aria-hidden
          className="size-4 shrink-0 rounded-full border border-dashed border-muted-foreground/30"
        />
      )}
    </div>
  );
}

/** Title input at the foot of the list; Enter adds and stays open for the next one. */
function AddSubTaskInput({
  onAdd,
  onClose,
}: {
  onAdd: (title: string) => Promise<void>;
  onClose: () => void;
}) {
  const [title, setTitle] = useState('');
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex h-9 items-center gap-2.5 px-3">
      {adding ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      )}
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={() => {
          if (!title.trim() && !adding) onClose();
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
            return;
          }
          if (e.key !== 'Enter' || !title.trim() || adding) return;
          e.preventDefault();
          setAdding(true);
          onAdd(title.trim())
            .then(() => setTitle(''))
            .catch((err) => console.error('Failed to add sub-task:', err))
            .finally(() => setAdding(false));
        }}
        placeholder="Sub-task title"
        className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
      />
    </div>
  );
}

export function SubTasksSection({
  subTasks,
  progressById,
  viewer,
  canAdd,
  canEditTask,
  onAdd,
  onStatusChange,
}: {
  subTasks: TaskResponse[];
  /** task id -> its own children's progress, for sub-tasks that are parents. */
  progressById: Map<string, Progress>;
  viewer: Principal | null;
  /** Whether the viewer may add children under this task. */
  canAdd: boolean;
  /** Whether the viewer may edit a given sub-task (it can sit in another project). */
  canEditTask: (task: TaskResponse) => boolean;
  onAdd: (title: string) => Promise<void>;
  onStatusChange: (task: TaskResponse, status: TaskStatus) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [adding, setAdding] = useState(false);

  if (subTasks.length === 0 && !adding) {
    if (!canAdd) return null;
    return (
      <button
        type="button"
        onClick={() => setAdding(true)}
        className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <Plus className="h-3.5 w-3.5" />
        Add sub-tasks
      </button>
    );
  }

  const progress = subTaskProgress(subTasks);
  const startAdding = () => {
    setCollapsed(false);
    setAdding(true);
  };

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          className="flex cursor-pointer items-center gap-1.5 text-sm font-medium transition-colors hover:text-foreground/80"
        >
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground transition-transform',
              collapsed && '-rotate-90',
            )}
          />
          Sub-tasks
        </button>
        {progress.total > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-muted/60 px-2 py-0.5">
            <ProgressRing done={progress.done} total={progress.total} size={11} />
            <span className="text-[11px] font-medium tabular-nums text-muted-foreground">
              {progress.done}/{progress.total}
            </span>
          </span>
        )}
        {canAdd && (
          <button
            type="button"
            onClick={startAdding}
            aria-label="Add sub-task"
            title="Add sub-task"
            className="ml-auto inline-flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>

      {!collapsed && (
        <div className="divide-y divide-border/60 overflow-hidden rounded-lg border bg-card/30">
          {subTasks.map((child) => (
            <SubTaskRow
              key={child.id}
              task={child}
              childProgress={progressById.get(child.id)}
              viewer={viewer}
              onStatusChange={
                canEditTask(child) ? (status) => onStatusChange(child, status) : undefined
              }
            />
          ))}
          {adding && canAdd && (
            <AddSubTaskInput onAdd={onAdd} onClose={() => setAdding(false)} />
          )}
        </div>
      )}
    </div>
  );
}
