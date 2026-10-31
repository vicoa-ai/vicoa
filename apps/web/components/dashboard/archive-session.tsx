'use client';

/**
 * Archiving a session that works on a task.
 *
 * Archiving never moves the task on the server: it puts the session away,
 * which says nothing about whether the work is finished. When the task is
 * still under way (in progress or in review), the archive is a natural moment
 * to move it on, so we offer that: no change, or a status, preselected to
 * Done when this was the task's last open session. The choice is applied after
 * the archive succeeds, as an ordinary task update.
 *
 * The standing answer (Settings → Tasks) can turn the question off: `mark_done`
 * closes the task without asking, `leave` never touches it. Every surface that
 * archives one session goes through `useArchiveSession`, so they ask the same
 * question the same way.
 */

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { CircleMinus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { STATUS_CONFIG, StatusIcon } from '@/components/dashboard/task-ui';
import {
  ARCHIVE_TASK_CHOICES,
  archiveChoiceStatus,
  defaultArchiveChoice,
  loadArchiveTaskContext,
  standingTaskStatus,
  type ArchiveTaskChoice,
  type ArchiveTaskContext,
} from '@/lib/archive-task';
import { archiveTaskAction } from '@/lib/archive-task-pref';
import { getBackendAPI, refusalReason, type TaskResponse, type TaskStatus } from '@/lib/backend-api';
import { isImeComposing } from '@/lib/ime';
import { isDesktopLocal } from '@/lib/runtime-config';
import { toast } from '@/lib/toast';

export interface ArchiveTarget {
  id: string;
  task_id?: string | null;
}

interface PendingArchive {
  target: ArchiveTarget;
  /** Set when the dialog asks about the task; null for a plain confirmation. */
  ask: ArchiveTaskContext | null;
  /** The standing answer's change, applied after a plain confirmation. */
  standing: { task: TaskResponse; status: TaskStatus } | null;
}

/**
 * `archive(id)` does the archive, owns its own failure toast, and resolves to
 * whether it succeeded: the task is only changed for a session that really
 * was archived. `confirm` is for surfaces that always confirm an archive (the
 * session page); the others archive on one click and only open the dialog to
 * ask about a task.
 */
export function useArchiveSession(
  archive: (id: string) => Promise<boolean>,
  { confirm = false }: { confirm?: boolean } = {},
) {
  const [pending, setPending] = useState<PendingArchive | null>(null);
  const checking = useRef(false);

  const archiveThenMoveTask = useCallback(
    async (id: string, change: { task: TaskResponse; status: TaskStatus } | null) => {
      if (!(await archive(id)) || !change || change.status === change.task.status) return;
      try {
        await getBackendAPI(true).updateTask(change.task.id, { status: change.status });
      } catch (error) {
        console.error('Failed to update the task after archiving:', error);
        toast.error("Couldn't update the task", { description: refusalReason(error) });
      }
    },
    [archive],
  );

  const requestArchive = useCallback(
    async (target: ArchiveTarget) => {
      if (checking.current) return;
      // Read at click time: the answer may have changed since this rendered.
      const action = archiveTaskAction();
      let context: ArchiveTaskContext | null = null;
      if (target.task_id && action !== 'leave' && !isDesktopLocal()) {
        checking.current = true;
        try {
          context = await loadArchiveTaskContext(getBackendAPI(true), target.task_id, [target.id]);
        } catch (error) {
          // The archive does not touch the task, so not knowing about it costs
          // only the offer: archive without it.
          console.error('Failed to read the linked task before archiving:', error);
        } finally {
          checking.current = false;
        }
      }
      const ask = action === 'ask' ? context : null;
      const standingStatus = standingTaskStatus(action, context);
      const standing = context && standingStatus ? { task: context.task, status: standingStatus } : null;
      if (ask || confirm) {
        setPending({ target, ask, standing });
        return;
      }
      await archiveThenMoveTask(target.id, standing);
    },
    [confirm, archiveThenMoveTask],
  );

  const archiveDialog = pending ? (
    <ArchiveSessionDialog
      key={pending.target.id}
      context={pending.ask}
      confirm={confirm}
      onCancel={() => setPending(null)}
      onArchive={(choice) => {
        const { target, ask, standing } = pending;
        setPending(null);
        const status = ask && choice ? archiveChoiceStatus(choice) : null;
        void archiveThenMoveTask(target.id, ask ? (status ? { task: ask.task, status } : null) : standing);
      }}
    />
  ) : null;

  return { requestArchive, archiveDialog };
}

function ArchiveSessionDialog({
  context,
  confirm,
  onCancel,
  onArchive,
}: {
  context: ArchiveTaskContext | null;
  confirm: boolean;
  onCancel: () => void;
  onArchive: (choice?: ArchiveTaskChoice) => void;
}) {
  const [choice, setChoice] = useState<ArchiveTaskChoice>(
    context ? defaultArchiveChoice(context) : 'no_change',
  );
  const contentRef = useRef<HTMLDivElement>(null);

  // Land on the preselected choice (arrow keys move it) or, with nothing to
  // choose, on the Archive button, so Enter archives either way.
  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;
    const target =
      root.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]') ??
      root.querySelector<HTMLElement>('[data-autofocus]');
    target?.focus();
  }, []);

  const submit = () => onArchive(context ? choice : undefined);

  // Enter archives from anywhere in the dialog. Buttons and links keep their
  // own Enter; a radio does not (Radix swallows it), which is why this exists.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter' || isImeComposing(e)) return;
    const target = e.target as HTMLElement;
    if (target.closest('a')) return;
    if (target.closest('button') && target.getAttribute('role') !== 'radio') return;
    e.preventDefault();
    submit();
  };

  const task = context?.task ?? null;
  const others = context?.otherOpenSessions ?? 0;

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent ref={contentRef} className="font-mono" onKeyDown={onKeyDown}>
        <DialogHeader>
          <DialogTitle>Archive Session</DialogTitle>
          <DialogDescription>
            {confirm
              ? 'Are you sure you want to archive this session? No further messages can be sent after it is archived.'
              : 'Choose what happens to the task this session is working on.'}
          </DialogDescription>
        </DialogHeader>
        {task && (
          <div className="min-w-0 space-y-3">
            <div className="flex items-start gap-2 text-sm">
              <StatusIcon status={task.status} className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <div className="truncate font-medium">
                  {task.identifier ? `${task.identifier} ` : ''}
                  {task.title}
                </div>
                <div className="text-xs text-muted-foreground">
                  Task {STATUS_CONFIG[task.status].label}
                </div>
              </div>
            </div>
            <RadioGroup
              value={choice}
              onValueChange={(value) => setChoice(value as ArchiveTaskChoice)}
              aria-label="Task status after archiving"
              className="gap-1"
            >
              {ARCHIVE_TASK_CHOICES.map((value) => {
                const status = archiveChoiceStatus(value);
                return (
                  <label
                    key={value}
                    htmlFor={`archive-task-${value}`}
                    className="-mx-2 flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent/50"
                  >
                    <RadioGroupItem
                      id={`archive-task-${value}`}
                      value={value}
                      className="cursor-pointer border-muted-foreground/50"
                    />
                    {status ? (
                      <StatusIcon status={status} className="h-4 w-4 shrink-0" />
                    ) : (
                      <CircleMinus className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    )}
                    {status ? STATUS_CONFIG[status].label : 'No change'}
                  </label>
                );
              })}
            </RadioGroup>
            {others > 0 && (
              <p className="text-xs text-muted-foreground">
                {others === 1
                  ? '1 other session on this task is still open.'
                  : `${others} other sessions on this task are still open.`}
              </p>
            )}
          </div>
        )}
        {task && (
          <p className="text-xs text-muted-foreground">
            You can turn this question off in{' '}
            <Link
              href="/dashboard/settings?tab=tasks"
              onClick={onCancel}
              className="cursor-pointer underline underline-offset-2 hover:text-foreground"
            >
              Settings → Tasks
            </Link>
            .
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button data-autofocus onClick={submit}>
            Archive Session
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
