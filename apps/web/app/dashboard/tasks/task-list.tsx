'use client';

// List view for the human task tracker: collapsible status sections rendered
// top-to-bottom, Linear-style compact rows. Every status is shown (even when
// empty) so a task can be dragged into any of them. Drag across sections
// writes {status}; reorder within a section writes {position} — the same
// midpoint scheme the board uses, shared via use-status-dnd.

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
import { ChevronRight, Plus } from 'lucide-react';
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
  STATUS_ORDER,
  StatusHeading,
  TaskActionsMenu,
  TaskContextMenu,
  formatTaskDate,
  isPastDate,
} from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';
import type { ChildProgressMap, TasksById } from './task-board';
import { TaskViewProperties } from './task-views';
import { columnDroppableId, useStatusColumnsDnd } from './use-status-dnd';

type RowProps = {
  task: TaskResponse;
  projects: ProjectResponse[];
  parent?: TaskResponse;
  childProgress?: { done: number; total: number };
  display: TaskViewProperties;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
};

function TaskRow({
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
}: RowProps & { dragOverlay?: boolean }) {
  const project = projects.find((p) => p.id === task.project_id);
  const start = formatTaskDate(task.start_date);
  const due = formatTaskDate(task.due_date);
  const isClosed = task.status === 'done' || task.status === 'cancelled';

  return (
    <div
      className={cn(
        'group/row flex h-9 items-center gap-2 rounded-md px-3 text-sm transition-colors',
        dragOverlay ? 'bg-card shadow-lg' : 'cursor-pointer hover:bg-accent/50',
      )}
      onClick={dragOverlay ? undefined : () => onEdit(task)}
    >
      {display.priority && <PriorityIcon priority={task.priority} />}
      <span className={cn('min-w-0 flex-1 truncate', isClosed && 'text-muted-foreground line-through')}>
        {task.title}
      </span>
      {display.parent && parent && (
        <span className="hidden sm:inline-flex">
          <ParentChip parent={parent} />
        </span>
      )}
      {display.childProgress && childProgress && childProgress.total > 0 && (
        <ChildProgressChip done={childProgress.done} total={childProgress.total} />
      )}
      {display.labels && (
        <span className="hidden md:inline-flex">
          <LabelChips labels={task.labels} />
        </span>
      )}
      {display.project && (
        <span className="hidden sm:inline-flex">
          <ProjectChip project={project} />
        </span>
      )}
      {display.startDate && start && (
        <span className="hidden shrink-0 text-xs text-muted-foreground md:inline">{start}</span>
      )}
      {display.dueDate && due && (
        <span
          className={cn(
            'shrink-0 text-xs',
            !isClosed && isPastDate(task.due_date) ? 'text-red-500' : 'text-muted-foreground',
          )}
        >
          {due}
        </span>
      )}
      {!dragOverlay && (
        <span
          onClick={(e) => e.stopPropagation()}
          className="opacity-0 transition-opacity group-hover/row:opacity-100"
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
  );
}

function SortableTaskRow(props: RowProps) {
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
        <TaskRow {...props} />
      </div>
    </TaskContextMenu>
  );
}

function ListSection({
  status,
  taskIds,
  tasksById,
  projects,
  parentById,
  childProgressMap,
  display,
  collapsed,
  onToggle,
  onCreate,
  onEdit,
  onPatch,
  onDelete,
  onStartSession,
  onCreateAutomation,
}: {
  status: TaskStatus;
  taskIds: string[];
  tasksById: TasksById;
  projects: ProjectResponse[];
  parentById?: TasksById;
  childProgressMap?: ChildProgressMap;
  display: TaskViewProperties;
  collapsed: boolean;
  onToggle: (status: TaskStatus) => void;
  onCreate?: (status: TaskStatus) => void;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
}) {
  // The whole section is droppable so a card dropped anywhere in it — including
  // on a collapsed header — lands in this status (appended to the end).
  const { setNodeRef, isOver } = useDroppable({ id: columnDroppableId(status) });

  return (
    <div ref={setNodeRef} className={cn('rounded-lg transition-colors', isOver && 'bg-accent/40')}>
      {/* Sticky section header (multica StatusAccordionItem) */}
      <div className="group/header sticky top-0 z-10 flex h-10 items-center rounded-lg bg-muted transition-colors hover:bg-accent">
        <button
          type="button"
          onClick={() => onToggle(status)}
          className="flex h-full flex-1 cursor-pointer items-center gap-2 px-3 text-left outline-none"
        >
          <ChevronRight
            className={cn(
              'size-3.5 shrink-0 text-muted-foreground transition-transform',
              !collapsed && 'rotate-90',
            )}
          />
          <StatusHeading status={status} count={taskIds.length} />
        </button>
        {onCreate && (
          <div className="pr-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 rounded-full p-0 text-muted-foreground opacity-0 transition-opacity group-hover/header:opacity-100"
              title="Add task with this status"
              onClick={() => onCreate(status)}
            >
              <Plus className="size-3.5" />
            </Button>
          </div>
        )}
      </div>

      {!collapsed && (
        <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
          <div className="min-h-[2.25rem] py-0.5">
            {taskIds.length === 0 ? (
              <p className="px-3 py-1.5 text-xs text-muted-foreground/60">No tasks</p>
            ) : (
              taskIds.map((taskId) => {
                const task = tasksById.get(taskId);
                if (!task) return null;
                return (
                  <SortableTaskRow
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
              })
            )}
          </div>
        </SortableContext>
      )}
    </div>
  );
}

export function TaskList({
  tasks,
  projects,
  parentById,
  childProgressMap,
  display,
  manualOrder = true,
  collapsed,
  onToggle,
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
  /** All tasks by id, for resolving a row's parent chip. */
  parentById?: TasksById;
  childProgressMap?: ChildProgressMap;
  display: TaskViewProperties;
  /** False when a non-manual ordering is active (disables position writes). */
  manualOrder?: boolean;
  /** Statuses collapsed in this view. */
  collapsed: Set<TaskStatus>;
  onToggle: (status: TaskStatus) => void;
  onEdit: (task: TaskResponse) => void;
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void;
  onDelete: (task: TaskResponse) => void;
  onStartSession: (task: TaskResponse) => void;
  onCreateAutomation?: (task: TaskResponse) => void;
  onCreate?: (status: TaskStatus) => void;
}) {
  const { columns, tasksById, activeTask, sensors, collisionDetection, dndHandlers } =
    useStatusColumnsDnd(tasks, onPatch, manualOrder);

  return (
    <DndContext sensors={sensors} collisionDetection={collisionDetection} {...dndHandlers}>
      <div className="space-y-1">
        {STATUS_ORDER.map((status) => (
          <ListSection
            key={status}
            status={status}
            taskIds={columns[status]}
            tasksById={tasksById}
            projects={projects}
            parentById={parentById}
            childProgressMap={childProgressMap}
            display={display}
            collapsed={collapsed.has(status)}
            onToggle={onToggle}
            onCreate={onCreate}
            onEdit={onEdit}
            onPatch={onPatch}
            onDelete={onDelete}
            onStartSession={onStartSession}
            onCreateAutomation={onCreateAutomation}
          />
        ))}
      </div>
      <DragOverlay dropAnimation={null}>
        {activeTask ? (
          <div className="cursor-grabbing opacity-95">
            <TaskRow
              task={activeTask}
              projects={projects}
              parent={
                activeTask.parent_task_id ? parentById?.get(activeTask.parent_task_id) : undefined
              }
              display={display}
              onEdit={onEdit}
              onPatch={onPatch}
              onDelete={onDelete}
              onStartSession={onStartSession}
              dragOverlay
            />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
