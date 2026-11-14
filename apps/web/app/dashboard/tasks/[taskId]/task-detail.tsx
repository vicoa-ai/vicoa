'use client';

// The task detail body: a markdown description, its properties, and a timeline
// that interleaves comments, generated activity and the agent sessions the
// task spawned. Two hosts render it:
//
// - `variant="page"`: the task route (`page.tsx`), with its back link and the
//   property rail on the right.
// - `variant="panel"`: the peek panel a dashboard plugin page opens beside its
//   own content (`task-detail-panel.tsx`), one column, plus "Reply and hand
//   back" for working through tasks an agent handed over.
//
// Data, polling and writes are one hook (`use-task-detail.ts`) for both, and
// the dialogs (sub-task picker for Start session, comment delete) live here,
// so the two variants differ only in layout.

import { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';

import { projectRoleAtLeast, refusalReason, TaskCommentResponse, TaskResponse } from '@/lib/backend-api';
import { projectLabel } from '@/components/dashboard/task-ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { CommentComposer } from './comment-composer';
import { HandBackError } from './hand-back';
import { EditableDescription, EditableTitle } from './inline-fields';
import { ParentTaskLink, SubTasksSection } from './sub-tasks';
import { TaskDetailPanel } from './task-detail-panel';
import { TaskDetailSkeleton } from './task-detail-skeleton';
import { TaskPropertyRail } from './task-property-rail';
import { CreatedInSession, ReactionRow, TaskTimeline } from './task-timeline';
import {
  type TaskDetailModel,
  type TaskReferenceData,
  useTaskDetail,
  useTaskReferenceData,
} from './use-task-detail';
import { StartSessionDialog } from '../start-session-dialog';

export interface TaskDetailProps {
  taskId: string;
  variant: 'page' | 'panel';
  /** Panel only: called after "Reply and hand back" succeeded, so the host can move to the next item. */
  onHandedBack?: (task: TaskResponse) => void;
  /** Open a session from any session link ("Created in", "via", a session card's Open); the panel host may show it in the panel instead of navigating. Default: the link navigates to /dashboard/sessions/<id>. Modifier and middle clicks always open the link the browser's way. */
  onOpenSession?: (sessionId: string) => void;
  /** Fired whenever the task (re)loads, e.g. so a host can show its title. */
  onLoaded?: (task: TaskResponse) => void;
  /** Panel only: merged onto the column, e.g. to change its padding. */
  className?: string;
}

export function TaskDetail(props: TaskDetailProps): JSX.Element {
  const reference = useTaskReferenceData();
  // Keyed by task. The panel switches tasks in place (J/K), and a fresh body
  // per task is what makes that clean: no previous task on screen while the
  // next one loads (the skeleton shows instead), no draft, open dialog or
  // revealed property carried across, and a response still in flight for the
  // previous task lands on a component that is gone instead of on this one.
  return <TaskDetailBody key={props.taskId} {...props} reference={reference} />;
}

function TaskDetailBody({
  taskId,
  variant,
  onHandedBack,
  onOpenSession,
  onLoaded,
  className,
  reference,
}: TaskDetailProps & { reference: TaskReferenceData }) {
  const router = useRouter();
  const model = useTaskDetail(taskId, reference, onLoaded);
  const { task, allTasks, comments, isLoading, error, errorStatus } = model;

  // Properties the user asked for that have no value yet. A property shows
  // when it is set OR revealed — the rail stays short by default instead of
  // being a wall of "Unassigned / None / None".
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  // Set when "Start session" is fired on a task that has sub-tasks — opens the
  // picker so the user can choose which ride along (same flow as the board).
  const [sessionDialog, setSessionDialog] = useState<{
    task: TaskResponse;
    subtasks: TaskResponse[];
  } | null>(null);
  // The comment whose Delete was picked, while its confirmation is open.
  const [deletingComment, setDeletingComment] = useState<TaskCommentResponse | null>(null);

  // "Start session" seeds a new agent session from this task — the same path
  // as the board's context-menu action: with sub-tasks, open the picker first;
  // without, go straight to the New Session page.
  const startSession = useCallback(() => {
    if (!task) return;
    const children = allTasks.filter((t) => t.parent_task_id === task.id);
    if (children.length === 0) {
      router.push(`/dashboard/sessions/new?taskId=${task.id}`);
      return;
    }
    setSessionDialog({ task, subtasks: children });
  }, [router, task, allTasks]);

  // Picker confirmed: carry the chosen sub-task ids to the New Session page,
  // which seeds them into the prompt and advances their status with the parent.
  const confirmStartSession = useCallback(
    (selectedIds: string[]) => {
      if (!sessionDialog) return;
      const params = new URLSearchParams({ taskId: sessionDialog.task.id });
      if (selectedIds.length > 0) params.set('subtasks', selectedIds.join(','));
      setSessionDialog(null);
      router.push(`/dashboard/sessions/new?${params.toString()}`);
    },
    [router, sessionDialog],
  );

  // A hand back that resolves after the host has already moved on (it remounts
  // this body for the next task) must not move it along a second time.
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);
  const onHandedBackRef = useRef(onHandedBack);
  onHandedBackRef.current = onHandedBack;
  const { replyAndHandBack } = model;
  const handBack = useCallback(
    async (body: string) => {
      try {
        const updated = await replyAndHandBack(body);
        if (aliveRef.current) onHandedBackRef.current?.(updated);
      } catch (err) {
        const posted = err instanceof HandBackError && err.replyPosted;
        toast.error("Couldn't hand back", {
          // Once the reply is up, the retry only moves the status, so say so
          // rather than leave the kept draft looking unsent.
          description: posted
            ? 'Your reply was posted. Try again to move the task to In Review.'
            : refusalReason(err instanceof HandBackError ? err.reason : err),
        });
        // Rejecting keeps the draft in the composer.
        throw err;
      }
    },
    [replyAndHandBack],
  );

  if (isLoading) return <TaskDetailSkeleton variant={variant} className={className} />;

  if (error || !task) {
    if (variant === 'panel') {
      return (
        <div className={cn('px-4 py-4', className)}>
          <p className="text-sm text-muted-foreground">
            {errorStatus === 404 || !error ? 'Task not found' : "Couldn't load this task"}
          </p>
        </div>
      );
    }
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-6 py-8">
        <p className="text-sm text-muted-foreground">{error ?? 'Task not found'}</p>
        <button
          type="button"
          onClick={() => router.push('/dashboard/tasks')}
          className="cursor-pointer text-sm underline underline-offset-4"
        >
          Back to tasks
        </button>
      </div>
    );
  }

  const requestDeleteComment = (commentId: string) =>
    setDeletingComment(comments.find((c) => c.id === commentId) ?? null);

  const dialogs = (
    <>
      <StartSessionDialog
        open={!!sessionDialog}
        parentTask={sessionDialog?.task ?? null}
        subtasks={sessionDialog?.subtasks ?? []}
        onClose={() => setSessionDialog(null)}
        onConfirm={confirmStartSession}
      />

      <ConfirmDialog
        open={deletingComment !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingComment(null);
        }}
        title="Delete comment"
        description="Are you sure you want to delete this comment? This action cannot be undone."
        preview={
          deletingComment?.body && (
            <div className="line-clamp-3 whitespace-pre-wrap [overflow-wrap:anywhere]">
              {deletingComment.body}
            </div>
          )
        }
        onConfirm={() => {
          if (deletingComment) void model.deleteComment(deletingComment.id);
        }}
      />
    </>
  );

  if (variant === 'panel') {
    return (
      <TaskDetailPanel
        task={task}
        model={model}
        className={className}
        onStartSession={startSession}
        onOpenSession={onOpenSession}
        onRequestDeleteComment={requestDeleteComment}
        onHandBack={handBack}
      >
        {dialogs}
      </TaskDetailPanel>
    );
  }

  return (
    <TaskDetailPage
      task={task}
      model={model}
      revealed={revealed}
      onReveal={(key) => setRevealed((prev) => new Set(prev).add(key))}
      onStartSession={startSession}
      onOpenSession={onOpenSession}
      onRequestDeleteComment={requestDeleteComment}
    >
      {dialogs}
    </TaskDetailPage>
  );
}

/** The task route's layout: back link, the main column, the property rail. */
function TaskDetailPage({
  task,
  model,
  revealed,
  onReveal,
  onStartSession,
  onOpenSession,
  onRequestDeleteComment,
  children,
}: {
  task: TaskResponse;
  model: TaskDetailModel;
  revealed: Set<string>;
  onReveal: (key: string) => void;
  onStartSession: () => void;
  onOpenSession?: (sessionId: string) => void;
  onRequestDeleteComment: (commentId: string) => void;
  /** The dialogs. */
  children: React.ReactNode;
}) {
  const router = useRouter();
  const {
    projects,
    comments,
    activity,
    sessions,
    sessionRefs,
    taskReactions,
    viewer,
    canEdit,
    canComment,
    roleOf,
    subTasks,
    parentTask,
    siblingTasks,
    mentionTarget,
    progressById,
    patchTask,
    postComment,
    editComment,
    toggleReaction,
    addSubTask,
    setSubTaskStatus,
  } = model;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <button
        type="button"
        onClick={() => router.push('/dashboard/tasks')}
        className="mb-4 flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        Tasks
      </button>

      <div className="flex gap-10">
        <div className="min-w-0 flex-1 space-y-6">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {/* The identifier is absent for a task that predates the backfill
                  or whose project has no key — render nothing rather than a
                  placeholder that looks like a real reference. */}
              {task.identifier && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] tracking-tight">
                  {task.identifier}
                </span>
              )}
              <span>{projectLabel(projects.find((p) => p.id === task.project_id))}</span>
            </div>
            <EditableTitle
              value={task.title}
              onSave={(title) => void patchTask({ title })}
              readOnly={!canEdit}
            />
            <ParentTaskLink task={task} parent={parentTask} siblings={siblingTasks} />
            <CreatedInSession
              sessionRef={sessionRefs.find((ref) => ref.id === task.created_in_instance_id)}
              onOpenSession={onOpenSession}
            />
            <EditableDescription
              // One editor per task: its undo history and in-flight edit
              // belong to the task they were made on.
              key={task.id}
              value={task.description}
              onSave={(description) => void patchTask({ description })}
              readOnly={!canEdit}
              mentionTarget={mentionTarget}
              taskId={task.id}
            />
            {/* The task itself is reactable, like an issue's opening post. */}
            <ReactionRow
              reactions={taskReactions}
              viewer={viewer}
              onToggle={
                canComment ? (emoji) => void toggleReaction('task', task.id, emoji) : undefined
              }
            />
          </div>

          <SubTasksSection
            key={task.id}
            subTasks={subTasks}
            progressById={progressById}
            viewer={viewer}
            canAdd={canEdit}
            canEditTask={(t) => projectRoleAtLeast(roleOf(t), 'editor')}
            onAdd={addSubTask}
            onStatusChange={(t, status) => void setSubTaskStatus(t, status)}
          />

          <div className="space-y-3 border-t pt-6">
            <TaskTimeline
              comments={comments}
              activity={activity}
              sessions={sessions}
              sessionRefs={sessionRefs}
              viewer={viewer}
              onOpenSession={onOpenSession}
              onToggleCommentReaction={
                canComment
                  ? (commentId, emoji) => void toggleReaction('comment', commentId, emoji)
                  : undefined
              }
              onReply={
                canComment
                  ? (parentCommentId, body) => postComment(body, parentCommentId)
                  : undefined
              }
              onEditComment={canComment ? editComment : undefined}
              onDeleteComment={canComment ? onRequestDeleteComment : undefined}
            />
            {/* The bottom composer always starts a new thread; replying is
                the affordance inside a thread. */}
            {canComment ? (
              <CommentComposer onSubmit={(body) => postComment(body)} />
            ) : (
              <p className="text-xs text-muted-foreground">
                You can view this task. Commenting needs commenter access to its project.
              </p>
            )}
          </div>
        </div>

        <TaskPropertyRail
          task={task}
          model={model}
          revealed={revealed}
          onReveal={onReveal}
          onStartSession={onStartSession}
          onOpenSession={onOpenSession}
        />
      </div>

      {children}
    </div>
  );
}
