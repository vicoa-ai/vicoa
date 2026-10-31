'use client';

/**
 * Archiving a session that works on a task.
 *
 * Archive is the COMPLETED status, which the server maps to the task's `done`.
 * That is right when the session finished the work and wrong when the user is
 * only putting the session away, so before archiving a session linked to a
 * task we ask what should happen to the task: no change, or a status.
 *
 * The server decides whether there is anything to ask (`archive-preview`: the
 * archive would close the task, or would but for another open session) and
 * which choice to preselect; the user's standing answer (Settings → Tasks) can
 * turn the question off. Every surface that archives one session goes through
 * `useArchiveSession`, so they ask the same question the same way.
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
import { ARCHIVE_TASK_CHOICES, archiveChoiceStatus, defaultArchiveChoice } from '@/lib/archive-task';
import { archiveTaskAction } from '@/lib/archive-task-pref';
import {
  getBackendAPI,
  refusalReason,
  type ArchivePreview,
  type ArchiveTaskChoice,
  type BackendApiError,
} from '@/lib/backend-api';
import { isImeComposing } from '@/lib/ime';
import { isDesktopLocal } from '@/lib/runtime-config';
import { toast } from '@/lib/toast';

export interface ArchiveTarget {
  id: string;
  task_id?: string | null;
}

interface PendingArchive {
  target: ArchiveTarget;
  /** Set when there is a task to ask about; null for a plain confirmation. */
  preview: ArchivePreview | null;
}

/**
 * `archive(id, taskStatus)` does the archive and owns its own failure toast.
 * `confirm` is for surfaces that always confirm an archive (the session page);
 * the others archive on one click and only open the dialog to ask about a task.
 */
export function useArchiveSession(
  archive: (id: string, taskStatus?: ArchiveTaskChoice) => Promise<void>,
  { confirm = false }: { confirm?: boolean } = {},
) {
  const [pending, setPending] = useState<PendingArchive | null>(null);
  const checking = useRef(false);

  const requestArchive = useCallback(
    async (target: ArchiveTarget) => {
      if (checking.current) return;
      let preview: ArchivePreview | null = null;
      // Read at click time: the answer may have changed since this rendered.
      if (target.task_id && archiveTaskAction() === 'ask' && !isDesktopLocal()) {
        checking.current = true;
        try {
          const result = await getBackendAPI(true).getArchivePreview(target.id);
          if (result.ask && result.task) preview = result;
        } catch (error) {
          // A backend that predates the preview has no route for it (404): there
          // is nothing to ask with, so archive as before. A session that really
          // is gone 404s again on the archive itself, which reports it.
          if ((error as Partial<BackendApiError>).status !== 404) {
            console.error('Failed to check the linked task before archiving:', error);
            toast.error("Couldn't archive session", { description: refusalReason(error) });
            return;
          }
        } finally {
          checking.current = false;
        }
      }
      if (preview || confirm) {
        setPending({ target, preview });
        return;
      }
      await archive(target.id);
    },
    [confirm, archive],
  );

  const archiveDialog = pending ? (
    <ArchiveSessionDialog
      key={pending.target.id}
      preview={pending.preview}
      confirm={confirm}
      onCancel={() => setPending(null)}
      onArchive={(choice) => {
        setPending(null);
        void archive(pending.target.id, choice);
      }}
    />
  ) : null;

  return { requestArchive, archiveDialog };
}

function ArchiveSessionDialog({
  preview,
  confirm,
  onCancel,
  onArchive,
}: {
  preview: ArchivePreview | null;
  confirm: boolean;
  onCancel: () => void;
  onArchive: (choice?: ArchiveTaskChoice) => void;
}) {
  const [choice, setChoice] = useState<ArchiveTaskChoice>(
    preview ? defaultArchiveChoice(preview) : 'no_change',
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

  const submit = () => onArchive(preview ? choice : undefined);

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

  const task = preview?.task ?? null;
  const others = preview?.other_open_sessions ?? 0;

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
                  {task.key ? `${task.key} ` : ''}
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
