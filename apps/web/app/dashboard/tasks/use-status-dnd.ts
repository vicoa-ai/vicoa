'use client';

// Shared drag-and-drop logic for the tasks surface, used by BOTH the board
// (horizontal status columns) and the list (vertical status sections). Cards
// live in per-status columns; dragging across columns writes {status},
// reordering within a column writes {position} as the midpoint of the new
// neighbours (double precision keeps subdividing safely). Kept in one place so
// the two views can never drift apart.
//
// It also owns the closed-column cap (task-views CLOSED_COLUMN_LIMIT): Done
// and Cancelled render their newest cards until expanded, and the drop logic
// accounts for the cards the cap hides.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { TaskResponse, TaskStatus, UpdateTaskRequest } from '@/lib/backend-api';
import { STATUS_ORDER, makeKanbanCollision } from '@/components/dashboard/task-ui';
import { CLOSED_COLUMN_LIMIT, capColumnIds, isClosedStatus } from './task-views';

export type ColumnMap = Record<TaskStatus, string[]>;

/** Droppable id for a status container (column body / list section). */
export function columnDroppableId(status: TaskStatus): string {
  return `column:${status}`;
}

// Column droppable ids — fed to the kanban collision detection so a pointer
// over an empty container resolves to that container, not a card in a neighbour.
const COLUMN_IDS = new Set(STATUS_ORDER.map((status) => columnDroppableId(status)));

function buildColumns(tasks: TaskResponse[]): ColumnMap {
  const columns = Object.fromEntries(
    STATUS_ORDER.map((status) => [status, [] as string[]]),
  ) as ColumnMap;
  for (const task of tasks) {
    columns[task.status]?.push(task.id);
  }
  return columns;
}

/**
 * Owns the live column state + the four dnd-kit handlers. Returns everything a
 * view needs to wire a `<DndContext>`: the current column→ids map (which
 * re-parents cards live while dragging), the task being dragged (for the drag
 * overlay), the sensors, the collision detection, and the handlers.
 */
export function useStatusColumnsDnd(
  tasks: TaskResponse[],
  onPatch: (taskId: string, patch: UpdateTaskRequest) => void,
  // When false, a non-manual ordering (priority/date/…) is active: a drop
  // persists only a status change, never a `position` write — reordering
  // within a column would be silently overridden by the sort, so we don't
  // write an invisible position. Cross-status drag still works.
  manualOrder = true,
) {
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);
  // Local column state so cards re-parent live while dragging; re-derived from
  // props whenever the task list changes outside a drag.
  const [columns, setColumns] = useState<ColumnMap>(() => buildColumns(tasks));
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const draggingRef = useRef(false);
  // Closed columns the user expanded past the cap. Lives for the mount, not
  // the saved view: the capped default is the point, so a reload restores it.
  const [expanded, setExpanded] = useState<ReadonlySet<TaskStatus>>(() => new Set());

  useEffect(() => {
    if (!draggingRef.current) {
      setColumns(buildColumns(tasks));
    }
  }, [tasks]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );
  const collisionDetection = useMemo(() => makeKanbanCollision(COLUMN_IDS), []);

  const limitFor = useCallback(
    (status: TaskStatus) =>
      isClosedStatus(status) && !expanded.has(status) ? CLOSED_COLUMN_LIMIT : Infinity,
    [expanded],
  );
  // A column whose order the drop can't choose: every column under a sorted
  // view, and a closed one under Manual too (newest first, see compareTasks).
  // A drop there writes the status only.
  const isSortedColumn = useCallback(
    (status: TaskStatus) => !manualOrder || isClosedStatus(status),
    [manualOrder],
  );

  const findColumn = useCallback(
    (id: string): TaskStatus | null => {
      if (id.startsWith('column:')) {
        return id.slice('column:'.length) as TaskStatus;
      }
      for (const status of STATUS_ORDER) {
        if (columns[status].includes(id)) return status;
      }
      return null;
    },
    [columns],
  );

  const onDragStart = useCallback((event: DragStartEvent) => {
    draggingRef.current = true;
    setActiveTaskId(String(event.active.id));
  }, []);

  const onDragOver = useCallback(
    (event: DragOverEvent) => {
      const { active, over } = event;
      if (!over) return;
      const activeId = String(active.id);
      const overId = String(over.id);
      const from = findColumn(activeId);
      const to = findColumn(overId);
      if (!from || !to || from === to) return;

      // Re-parent the card into the hovered column at the hovered index. A
      // closed column under Manual puts a just-closed task on top, so preview
      // it there. Over the column body rather than a card, land after the last
      // card shown, not after the cards a capped column is hiding.
      setColumns((prev) => {
        const fromIds = prev[from].filter((id) => id !== activeId);
        const toIds = [...prev[to]];
        const overIndex = toIds.indexOf(overId);
        const insertAt =
          manualOrder && isClosedStatus(to)
            ? 0
            : overIndex >= 0
              ? overIndex
              : Math.min(toIds.length, limitFor(to));
        toIds.splice(insertAt, 0, activeId);
        return { ...prev, [from]: fromIds, [to]: toIds };
      });
    },
    [findColumn, limitFor, manualOrder],
  );

  const onDragEnd = useCallback(
    (event: DragEndEvent) => {
      draggingRef.current = false;
      setActiveTaskId(null);
      const { active, over } = event;
      const activeId = String(active.id);
      const task = tasksById.get(activeId);
      if (!task || !over) {
        setColumns(buildColumns(tasks));
        return;
      }

      const overId = String(over.id);
      const column = findColumn(activeId) ?? findColumn(overId);
      if (!column) {
        setColumns(buildColumns(tasks));
        return;
      }

      // Sorted column (any column under a non-manual ordering, a closed one
      // under Manual): persist a status change (cross-column drop) only; never
      // a position. The live cross-column re-parent from onDragOver stays
      // until the optimistic patch flows back and the sort re-derives order. A
      // same-column reorder is discarded — dnd-kit's transforms reset the card
      // to its sorted slot on drop.
      if (isSortedColumn(column)) {
        if (task.status !== column) onPatch(activeId, { status: column });
        return;
      }

      // Final in-column order after the drop (dnd-kit already applied the
      // cross-column move in onDragOver; same-column reorder lands here).
      setColumns((prev) => {
        const ids = [...prev[column]];
        const fromIndex = ids.indexOf(activeId);
        const overIndex = ids.indexOf(overId);
        if (fromIndex >= 0 && overIndex >= 0 && fromIndex !== overIndex) {
          ids.splice(fromIndex, 1);
          ids.splice(overIndex, 0, activeId);
        }
        const next = { ...prev, [column]: ids };

        // Position = midpoint of the new neighbours.
        const index = ids.indexOf(activeId);
        const prevTask = index > 0 ? tasksById.get(ids[index - 1]) : undefined;
        const nextTask =
          index < ids.length - 1 ? tasksById.get(ids[index + 1]) : undefined;
        let position: number;
        if (prevTask && nextTask) {
          position = (prevTask.position + nextTask.position) / 2;
        } else if (prevTask) {
          position = prevTask.position + 1;
        } else if (nextTask) {
          position = nextTask.position - 1;
        } else {
          position = task.position;
        }

        const patch: UpdateTaskRequest = { position };
        if (task.status !== column) patch.status = column;
        if (patch.status || position !== task.position) {
          onPatch(activeId, patch);
        }
        return next;
      });
    },
    [findColumn, onPatch, tasks, tasksById, isSortedColumn],
  );

  const onDragCancel = useCallback(() => {
    draggingRef.current = false;
    setActiveTaskId(null);
    setColumns(buildColumns(tasks));
  }, [tasks]);

  const activeTask = activeTaskId ? tasksById.get(activeTaskId) ?? null : null;

  // What each column renders. `columns` stays complete, so drop neighbours and
  // header counts see every card, hidden or not.
  const visibleColumns = useMemo(
    () =>
      Object.fromEntries(
        STATUS_ORDER.map((status) => [
          status,
          capColumnIds(columns[status], limitFor(status), activeTaskId),
        ]),
      ) as ColumnMap,
    [columns, limitFor, activeTaskId],
  );

  const toggleExpanded = useCallback(
    (status: TaskStatus) =>
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(status)) next.delete(status);
        else next.add(status);
        return next;
      }),
    [],
  );

  return {
    columns,
    visibleColumns,
    expanded,
    toggleExpanded,
    tasksById,
    activeTask,
    sensors,
    collisionDetection,
    dndHandlers: { onDragStart, onDragOver, onDragEnd, onDragCancel },
  };
}
