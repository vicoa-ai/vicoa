'use client';

// Board view for the human task tracker, styled after multica's board:
// 280px tinted status columns, Linear-style column headings, compact cards
// (priority icon, title, description preview, project chip, dates). Drag
// across columns writes {status}; reorder within a column writes {position}.

import {
  DndContext,
  DragOverlay,
  useDroppable,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { CalendarClock, CalendarDays, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  ProjectResponse,
  TaskResponse,
  TaskStatus,
  UpdateTaskRequest,
} from '@/lib/backend-api';
import {
  ChildProgressChip,
  LabelChips,
  ParentChip,
  PriorityIcon,
  ProjectChip,
  STATUS_CONFIG,
  STATUS_ORDER,
  StatusHeading,
  TaskActionsMenu,
  TaskContextMenu,
  formatTaskDate,
  isPastDate,
} from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';
import { TaskViewProperties } from './task-views';
import { columnDroppableId, useStatusColumnsDnd } from './use-status-dnd';

const BOARD_COL_WIDTH = 280;

export type ChildProgressMap = Map<string, { done: number; total: number }>;
export type TasksById = Map<string, TaskResponse>;

function TaskCard({
  task,
  projects,
  parent,
  childProgress,
  display,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
  dragOverlay = false,
}: {
  task: TaskResponse;
  projects: ProjectResponse[];
  parent?: TaskResponse;
  childProgress?: { done: number; total: number };
  display: TaskViewProperties;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
  dragOverlay?: boolean;
}) {
  const project = projects.find((p) => p.id === task.project_id);
  const start = formatTaskDate(task.start_date);
  const due = formatTaskDate(task.due_date);
  const isClosed = task.status === 'done' || task.status === 'cancelled';
  const showParent = display.parent && !!parent;
  const showProject = display.project && !!project && !project.is_inbox;
  const showLabels = display.labels && task.labels.length > 0;
  const showStart = display.startDate && !!start;
  const showDue = display.dueDate && !!due;
  const showProgress = display.childProgress && !!childProgress && childProgress.total > 0;
  const showChips = showParent || showProject || showLabels;
  const showMeta = showStart || showDue || showProgress;

  return (
    <div
      className={cn(
        'group/card rounded-lg border border-border/60 bg-card px-2.5 py-3 shadow-xs transition-colors',
        dragOverlay
          ? 'rotate-1 shadow-lg'
          : 'cursor-pointer hover:border-foreground/15 hover:bg-accent/30',
      )}
      onClick={dragOverlay ? undefined : () => onEdit(task)}
    >
      {/* Row 1: priority (left) + actions (right, on hover) */}
      <div className="flex items-center justify-between gap-2">
        {display.priority ? <PriorityIcon priority={task.priority} /> : <span />}
        {!dragOverlay && (
          <span
            onClick={(e) => e.stopPropagation()}
            className="-my-1 opacity-0 transition-opacity group-hover/card:opacity-100"
          >
            <TaskActionsMenu
              task={task}
              projects={projects}
              onEdit={onEdit}
              onPatch={onPatch}
              onDelete={onDelete}
              onStartSession={onStartSession}
              onCreateAutomation={onCreateAutomation}
            />
          </span>
        )}
      </div>

      {/* Row 2: title */}
      <p className={cn('mt-1 text-sm font-medium leading-snug line-clamp-2', isClosed && 'text-muted-foreground')}>
        {task.title}
      </p>

      {task.description && (
        <p className="mt-1 text-xs text-muted-foreground line-clamp-1">{task.description}</p>
      )}

      {showChips && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {showParent && <ParentChip parent={parent} />}
          {showProject && <ProjectChip project={project} />}
          {showLabels && <LabelChips labels={task.labels} />}
        </div>
      )}

      {showMeta && (
        <div className="mt-2 flex items-center justify-end gap-2">
          {showStart && (
            <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
              <CalendarClock className="size-3" />
              {start}
            </span>
          )}
          {showDue && (
            <span
              className={cn(
                'flex shrink-0 items-center gap-1 text-xs',
                !isClosed && isPastDate(task.due_date) ? 'text-red-500' : 'text-muted-foreground',
              )}
            >
              <CalendarDays className="size-3" />
              {due}
            </span>
          )}
          {showProgress && childProgress && (
            <ChildProgressChip done={childProgress.done} total={childProgress.total} />
          )}
        </div>
      )}
    </div>
  );
}

function SortableTaskCard(props: {
  task: TaskResponse;
  projects: ProjectResponse[];
  parent?: TaskResponse;
  childProgress?: { done: number; total: number };
  display: TaskViewProperties;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.task.id });

  return (
    <TaskContextMenu
      task={props.task}
      projects={props.projects}
      onEdit={props.onEdit}
      onPatch={props.onPatch}
      onDelete={props.onDelete}
      onStartSession={props.onStartSession}
      onCreateAutomation={props.onCreateAutomation}
    >
      <div
        ref={setNodeRef}
        style={{ transform: CSS.Transform.toString(transform), transition }}
        className={cn(isDragging && 'opacity-30')}
        {...attributes}
        {...listeners}
      >
        <TaskCard {...props} />
      </div>
    </TaskContextMenu>
  );
}

function BoardColumn({
  status,
  taskIds,
  tasksById,
  projects,
  parentById,
  childProgressMap,
  display,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
  onCreate,
}: {
  status: TaskStatus;
  taskIds: string[];
  tasksById: Map<string, TaskResponse>;
  projects: ProjectResponse[];
  parentById?: TasksById;
  childProgressMap?: ChildProgressMap;
  display: TaskViewProperties;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
  onCreate?: (status: TaskStatus) => void;
}) {
  // The column body is droppable so cards can be dropped on empty columns.
  const { setNodeRef, isOver } = useDroppable({ id: columnDroppableId(status) });

  return (
    <div
      style={{ width: BOARD_COL_WIDTH }}
      className={cn('flex shrink-0 flex-col rounded-xl p-2', STATUS_CONFIG[status].columnBg)}
    >
      <div className="mb-2 flex items-center justify-between px-1.5">
        <StatusHeading status={status} count={taskIds.length} />
        {onCreate && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 rounded-full p-0 text-muted-foreground"
            title="Add task"
            onClick={() => onCreate(status)}
          >
            <Plus className="size-3.5" />
          </Button>
        )}
      </div>
      <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
        <div
          ref={setNodeRef}
          className={cn(
            'flex min-h-[200px] flex-1 flex-col gap-2 rounded-lg p-1 transition-colors',
            isOver && 'bg-accent/60',
          )}
        >
          {taskIds.length === 0 && !isOver && (
            <p className="py-8 text-center text-xs text-muted-foreground">No tasks</p>
          )}
          {taskIds.map((taskId) => {
            const task = tasksById.get(taskId);
            if (!task) return null;
            return (
              <SortableTaskCard
                key={taskId}
                task={task}
                projects={projects}
                parent={task.parent_task_id ? parentById?.get(task.parent_task_id) : undefined}
                childProgress={childProgressMap?.get(taskId)}
                display={display}
                onEdit={onEdit}
                onPatch={onPatch}
                onDelete={onDelete}
                onStartSession={onStartSession}
                onCreateAutomation={onCreateAutomation}
              />
            );
          })}
        </div>
      </SortableContext>
    </div>
  );
}

export function TaskBoard({
  tasks,
  projects,
  parentById,
  childProgressMap,
  display,
  manualOrder = true,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
  onCreate,
}: {
  /** Visible tasks, already filtered + ordered by the active view. */
  tasks: TaskResponse[];
  projects: ProjectResponse[];
  /** All tasks by id, for resolving a card's parent chip. */
  parentById?: TasksById;
  childProgressMap?: ChildProgressMap;
  display: TaskViewProperties;
  /** False when a non-manual ordering is active (disables position writes). */
  manualOrder?: boolean;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession?: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
  onCreate?: (status: TaskStatus) => void;
}) {
  const { columns, tasksById, activeTask, sensors, collisionDetection, dndHandlers } =
    useStatusColumnsDnd(tasks, onPatch, manualOrder);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisionDetection}
      {...dndHandlers}
    >
      <div className="flex h-full gap-3">
        {STATUS_ORDER.map((status) => (
          <BoardColumn
            key={status}
            status={status}
            taskIds={columns[status]}
            tasksById={tasksById}
            projects={projects}
            parentById={parentById}
            childProgressMap={childProgressMap}
            display={display}
            onEdit={onEdit}
            onPatch={onPatch}
            onDelete={onDelete}
            onStartSession={onStartSession}
            onCreateAutomation={onCreateAutomation}
            onCreate={onCreate}
          />
        ))}
      </div>
      <DragOverlay dropAnimation={null}>
        {activeTask ? (
          <div style={{ width: BOARD_COL_WIDTH - 24 }} className="cursor-grabbing opacity-90">
            <TaskCard
              task={activeTask}
              projects={projects}
              display={display}
              onEdit={onEdit}
              onPatch={onPatch}
              onDelete={onDelete}
              dragOverlay
            />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
