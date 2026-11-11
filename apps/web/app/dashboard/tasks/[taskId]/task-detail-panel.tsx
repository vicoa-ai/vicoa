'use client';

// <TaskDetail variant="panel">: the task in a narrow column beside a plugin
// page's own content (a ~360–700px peek panel). Everything the task page has
// that you need to answer a task, nothing that needs the page's width:
//
// - a header of identifier + project with the two ways out (Start session,
//   Open task), the title, and the key properties as one wrapping row of pills
//   (status, priority, due date when set, labels) instead of the page's rail;
// - the description and its reactions, sub-tasks only when there are some;
// - the timeline, then the composer, whose second button is "Reply and hand
//   back": post the reply and move the task to In Review in one step, so the
//   host can go on to the next task.
//
// A plain block that grows with its content: scrolling is the host's, so
// there is no height or overflow here.

import Link from 'next/link';
import { ArrowUpRight, Play } from 'lucide-react';

import { projectRoleAtLeast, TaskResponse } from '@/lib/backend-api';
import { labelsForProject } from '@/lib/project-vocabulary';
import {
  DatePickerPill,
  LabelPickerPill,
  PriorityPickerPill,
  projectLabel,
  StatusPickerPill,
  toDateOnly,
  dateOnlyToLocalDate,
} from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';
import { CommentComposer } from './comment-composer';
import { EditableDescription, EditableTitle } from './inline-fields';
import { ParentTaskLink, SubTasksSection } from './sub-tasks';
import { CreatedInSession, ReactionRow, TaskTimeline } from './task-timeline';
import type { TaskDetailModel } from './use-task-detail';

const HEADER_ACTION =
  'inline-flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground';

export function TaskDetailPanel({
  task,
  model,
  className,
  onStartSession,
  onOpenSession,
  onRequestDeleteComment,
  onHandBack,
  children,
}: {
  task: TaskResponse;
  model: TaskDetailModel;
  className?: string;
  onStartSession: () => void;
  /** From the host; without it session links are plain links. */
  onOpenSession?: (sessionId: string) => void;
  /** Opens the delete confirmation (held by <TaskDetail>). */
  onRequestDeleteComment: (commentId: string) => void;
  /** "Reply and hand back"; rejects (after its toast) to keep the draft. */
  onHandBack: (body: string) => Promise<void>;
  /** The dialogs, mounted inside the column like the page mounts them. */
  children?: React.ReactNode;
}) {
  const {
    projects,
    labels,
    comments,
    activity,
    sessions,
    sessionRefs,
    taskReactions,
    viewer,
    canEdit,
    canComment,
    isOwner,
    roleOf,
    subTasks,
    parentTask,
    siblingTasks,
    mentionTarget,
    progressById,
    patchTask,
    createLabelAndAttach,
    postComment,
    editComment,
    toggleReaction,
    addSubTask,
    setSubTaskStatus,
  } = model;
  const project = projects.find((p) => p.id === task.project_id);

  return (
    <div className={cn('space-y-5 px-4 py-4', className)}>
      <div className="space-y-2.5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {task.identifier && (
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] tracking-tight">
              {task.identifier}
            </span>
          )}
          <span className="min-w-0 truncate">{projectLabel(project)}</span>
          <div className="-my-1 ml-auto flex shrink-0 items-center gap-0.5">
            {/* Owner only, as on the page's rail: a session runs on your own
                machine and links back to the task. */}
            {isOwner && (
              <button type="button" onClick={onStartSession} className={HEADER_ACTION}>
                <Play className="size-3" />
                Start session
              </button>
            )}
            <Link href={`/dashboard/tasks/${task.id}`} className={HEADER_ACTION}>
              <ArrowUpRight className="size-3.5" />
              Open task
            </Link>
          </div>
        </div>

        <EditableTitle
          size="compact"
          value={task.title}
          onSave={(title) => void patchTask({ title })}
          readOnly={!canEdit}
        />
        <ParentTaskLink task={task} parent={parentTask} siblings={siblingTasks} />
        <CreatedInSession
          sessionRef={sessionRefs.find((ref) => ref.id === task.created_in_instance_id)}
          onOpenSession={onOpenSession}
        />

        {/* The rail's key properties as the create dialog's wrapping pill row.
            Below editor they are inert labels, as the rail's are. */}
        <fieldset
          disabled={!canEdit}
          className={cn(
            'flex flex-wrap items-center gap-1.5',
            !canEdit && '[&_button]:cursor-default',
          )}
        >
          <StatusPickerPill
            status={task.status}
            onSelect={(status) => void patchTask({ status })}
          />
          <PriorityPickerPill
            priority={task.priority}
            onSelect={(priority) => void patchTask({ priority })}
          />
          {task.due_date && (
            <DatePickerPill
              label="Due date"
              value={toDateOnly(new Date(task.due_date))}
              onChange={(value) =>
                void patchTask({
                  due_date: value ? dateOnlyToLocalDate(value)?.toISOString() ?? null : null,
                })
              }
            />
          )}
          {(canEdit || task.labels.length > 0) && (
            <LabelPickerPill
              labels={labelsForProject(labels, project, task.labels)}
              selectedIds={task.labels.map((l) => l.id)}
              onToggle={(labelId) => {
                const current = task.labels.map((l) => l.id);
                void patchTask({
                  label_ids: current.includes(labelId)
                    ? current.filter((id) => id !== labelId)
                    : [...current, labelId],
                });
              }}
              onCreate={(name) => void createLabelAndAttach(name)}
            />
          )}
        </fieldset>

        <EditableDescription
          key={task.id}
          value={task.description}
          onSave={(description) => void patchTask({ description })}
          readOnly={!canEdit}
          mentionTarget={mentionTarget}
          taskId={task.id}
        />
        <ReactionRow
          reactions={taskReactions}
          viewer={viewer}
          onToggle={
            canComment ? (emoji) => void toggleReaction('task', task.id, emoji) : undefined
          }
        />
      </div>

      {/* Only when there are some: in a column this narrow an empty "Add
          sub-tasks" row is one more thing between the task and its thread. */}
      {subTasks.length > 0 && (
        <SubTasksSection
          key={task.id}
          compact
          subTasks={subTasks}
          progressById={progressById}
          viewer={viewer}
          canAdd={canEdit}
          canEditTask={(t) => projectRoleAtLeast(roleOf(t), 'editor')}
          onAdd={addSubTask}
          onStatusChange={(t, status) => void setSubTaskStatus(t, status)}
        />
      )}

      <div className="space-y-3 border-t pt-4">
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
            canComment ? (parentCommentId, body) => postComment(body, parentCommentId) : undefined
          }
          onEditComment={canComment ? editComment : undefined}
          onDeleteComment={canComment ? onRequestDeleteComment : undefined}
        />
        {canComment ? (
          <CommentComposer
            onSubmit={(body) => postComment(body)}
            // Handing back moves the task's status, an editor's write.
            secondaryAction={
              canEdit ? { label: 'Reply and hand back', onSubmit: onHandBack } : undefined
            }
          />
        ) : (
          <p className="text-xs text-muted-foreground">
            You can view this task. Commenting needs commenter access to its project.
          </p>
        )}
      </div>

      {children}
    </div>
  );
}
