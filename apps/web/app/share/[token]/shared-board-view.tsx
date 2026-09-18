'use client';

// A project's shared task board: read-only status columns, and a task sheet
// with the description and timeline. Comments are the single write a link
// can carry (§3.4) — the composer appears only when the link allows them and
// the visitor is signed in; an anonymous visitor of a comments-enabled link
// sees a sign-in prompt instead (§8.4).
//
// Not the dashboard's `TaskBoard`: that one is a drag-and-drop editor with a
// context menu of writes on every card. This is the same look with nothing to
// drag or edit — the cheaper way to be sure nothing editable leaks through.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, Loader2, LogIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import {
  LabelChips,
  PriorityIcon,
  ProjectIcon,
  STATUS_CONFIG,
  STATUS_ORDER,
  StatusHeading,
  TaskIdentifier,
  formatTaskDate,
  isPastDate,
} from '@/components/dashboard/task-ui';
import { ReactionRow, TaskTimeline } from '@/app/dashboard/tasks/[taskId]/task-timeline';
import { CommentComposer } from '@/app/dashboard/tasks/[taskId]/comment-composer';
import { principalFromResponse } from '@/lib/principals';
import type {
  PublicBoardResponse,
  PublicShareResponse,
  ShareBoardFilters,
  TaskResponse,
  TaskStatus,
  TaskTimelineResponse,
} from '@/lib/backend-api';
import {
  ShareNotFoundError,
  ShareRequestError,
  fetchPublicBoard,
  fetchPublicTaskTimeline,
  postPublicComment,
} from '@/lib/public-share-api';
import { cn } from '@/lib/utils';
import { ShareHeader } from './share-shell';
import { POLL_IDLE_MS, useSharePoll } from './use-share-poll';

const COLUMN_WIDTH = 280;

function ReadOnlyTaskCard({ task, onOpen }: { task: TaskResponse; onOpen: (task: TaskResponse) => void }) {
  const due = formatTaskDate(task.due_date);
  const overdue = task.due_date ? isPastDate(task.due_date) && task.status !== 'done' : false;
  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      className="w-full cursor-pointer rounded-md border border-border/70 bg-background p-2.5 text-left shadow-sm transition-colors hover:border-border hover:bg-muted/40"
    >
      <div className="flex items-start gap-1.5">
        <PriorityIcon priority={task.priority} className="mt-0.5 size-3.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <TaskIdentifier task={task} />
            {task.assignee && (
              <PrincipalAvatar principal={principalFromResponse(task.assignee) ?? { type: 'user', name: null }} size="xs" className="ml-auto" />
            )}
          </div>
          <div className="text-sm leading-snug">{task.title}</div>
          {task.description && (
            <div className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{task.description}</div>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <LabelChips labels={task.labels} />
            {due && (
              <span
                className={cn(
                  'inline-flex items-center gap-1 text-[11px]',
                  overdue ? 'text-red-500' : 'text-muted-foreground',
                )}
              >
                <CalendarDays className="size-3" />
                {due}
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function TaskSheet({
  token,
  share,
  task,
  open,
  onOpenChange,
}: {
  token: string;
  share: PublicShareResponse;
  task: TaskResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [timeline, setTimeline] = useState<TaskTimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const viewer = useMemo(() => principalFromResponse(share.viewer), [share.viewer]);

  const load = useCallback(async () => {
    if (!task) return;
    try {
      setTimeline(await fetchPublicTaskTimeline(token, task.id));
      setError(null);
    } catch (err) {
      setError(err instanceof ShareNotFoundError ? 'This task is no longer shared.' : 'Could not load the discussion.');
    }
  }, [token, task]);

  useEffect(() => {
    setTimeline(null);
    setError(null);
    if (open && task) void load();
  }, [open, task, load]);
  useSharePoll(load, { intervalMs: POLL_IDLE_MS, enabled: open && task !== null });

  const postComment = useCallback(
    async (body: string, parentCommentId?: string) => {
      if (!task) return;
      try {
        setTimeline(await postPublicComment(token, task.id, { body, parent_comment_id: parentCommentId ?? null }));
        setError(null);
      } catch (err) {
        if (err instanceof ShareRequestError && err.status === 401) {
          setError('Sign in to comment.');
        } else if (err instanceof ShareNotFoundError) {
          setError('This link no longer accepts comments.');
        } else {
          setError(err instanceof Error ? err.message : 'Could not post the comment.');
        }
        throw err;
      }
    },
    [token, task],
  );

  const canComment = share.allow_comments && share.viewer !== null;
  const promptSignIn = share.comments_available && !share.viewer;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="custom-scrollbar max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {task && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {task.identifier && (
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] tracking-tight">{task.identifier}</span>
                )}
                <span>{STATUS_CONFIG[task.status].label}</span>
                {task.assignee && (
                  <span className="inline-flex items-center gap-1">
                    · <PrincipalAvatar principal={principalFromResponse(task.assignee) ?? { type: 'user', name: null }} size="xs" />
                    {task.assignee.name ?? 'Assigned'}
                  </span>
                )}
              </div>
              <DialogTitle className="text-base">{task.title}</DialogTitle>
              {task.description ? (
                <div className="text-sm leading-relaxed">
                  <MessageMarkdown>{task.description}</MessageMarkdown>
                </div>
              ) : (
                <DialogDescription>No description.</DialogDescription>
              )}
              {task.labels.length > 0 && (
                <div className="pt-1">
                  <LabelChips labels={task.labels} max={8} />
                </div>
              )}
            </DialogHeader>

            {timeline && timeline.reactions.length > 0 && (
              <ReactionRow reactions={timeline.reactions} viewer={viewer} />
            )}

            <div className="space-y-3 border-t pt-4">
              {timeline === null && !error ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" /> Loading discussion…
                </div>
              ) : timeline ? (
                <TaskTimeline
                  comments={timeline.comments}
                  activity={timeline.activity}
                  sessions={[]}
                  viewer={viewer}
                  onReply={canComment ? (parentId, body) => postComment(body, parentId) : undefined}
                />
              ) : null}
              {error && <p className="text-xs text-destructive">{error}</p>}
              {canComment && <CommentComposer onSubmit={(body) => postComment(body)} />}
              {promptSignIn && (
                <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-xs">
                  <span className="text-muted-foreground">Sign in to Vicoa to join the discussion.</span>
                  <Button asChild size="sm" variant="outline" className="h-7 gap-1.5 text-xs">
                    <a href={`/sign-in?redirect=${encodeURIComponent(typeof window !== 'undefined' ? window.location.pathname + window.location.search : `/share/${token}`)}`}>
                      <LogIn className="h-3 w-3" />
                      Sign in
                    </a>
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function SharedBoardView({
  token,
  share,
  openHref,
}: {
  token: string;
  share: PublicShareResponse;
  /** "Open in Vicoa" target for a signed-in viewer who owns the project. */
  openHref?: string | null;
}) {
  const [board, setBoard] = useState<PublicBoardResponse | null>(null);
  const [error, setError] = useState<'gone' | 'error' | null>(null);
  const [openTask, setOpenTask] = useState<TaskResponse | null>(null);

  const load = useCallback(async () => {
    try {
      setBoard(await fetchPublicBoard(token));
      setError(null);
    } catch (err) {
      setError(err instanceof ShareNotFoundError ? 'gone' : 'error');
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);
  useSharePoll(load, { intervalMs: POLL_IDLE_MS });

  // Keep the open sheet's task fresh across polls.
  useEffect(() => {
    if (!openTask || !board) return;
    const fresh = board.tasks.find((t) => t.id === openTask.id);
    if (fresh && fresh !== openTask) setOpenTask(fresh);
  }, [board, openTask]);

  const columns = useMemo(() => {
    const filters = (share.filters ?? null) as ShareBoardFilters | null;
    const statuses: TaskStatus[] = filters?.statuses?.length
      ? STATUS_ORDER.filter((s) => filters.statuses?.includes(s))
      : STATUS_ORDER;
    const byStatus = new Map<TaskStatus, TaskResponse[]>(statuses.map((s) => [s, []]));
    for (const task of board?.tasks ?? []) byStatus.get(task.status)?.push(task);
    return statuses.map((status) => ({ status, tasks: byStatus.get(status) ?? [] }));
  }, [board, share.filters]);

  const project = board?.project ?? share.project;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ShareHeader openHref={openHref}>
        <div className="flex min-w-0 items-center gap-2">
          {project && (
            <>
              <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
              <h1 className="min-w-0 truncate font-mono text-sm font-normal">{project.name}</h1>
            </>
          )}
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {board ? `${board.tasks.length} task${board.tasks.length === 1 ? '' : 's'}` : ''}
          </span>
        </div>
      </ShareHeader>

      {error === 'gone' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-muted-foreground">
          <p>This share is no longer available.</p>
          <p className="text-xs">The link may have been revoked or expired.</p>
        </div>
      ) : board === null ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : (
        <div className="custom-scrollbar min-h-0 flex-1 overflow-x-auto p-3">
          <div className="flex h-full gap-3">
            {columns.map(({ status, tasks }) => (
              <div
                key={status}
                style={{ width: COLUMN_WIDTH, minWidth: COLUMN_WIDTH }}
                className={cn('flex h-full flex-col rounded-lg', STATUS_CONFIG[status].columnBg)}
              >
                <div className="px-3 pt-2.5 pb-1.5">
                  <StatusHeading status={status} count={tasks.length} />
                </div>
                <div className="custom-scrollbar flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
                  {tasks.map((task) => (
                    <ReadOnlyTaskCard key={task.id} task={task} onOpen={setOpenTask} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          {error === 'error' && (
            <p className="py-2 text-center text-xs text-muted-foreground">Updates paused: connection problem.</p>
          )}
        </div>
      )}

      <TaskSheet
        token={token}
        share={share}
        task={openTask}
        open={openTask !== null}
        onOpenChange={(open) => {
          if (!open) setOpenTask(null);
        }}
      />
    </div>
  );
}
