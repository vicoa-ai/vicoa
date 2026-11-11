'use client';

// Task detail as a real route (collaboration §8.3), not a dialog: a markdown
// description, a properties rail, and a timeline that interleaves comments,
// generated activity and the agent sessions the task spawned.
//
// `task-dialog.tsx` stays — it is the fast create/edit path off the board. This
// is the deep-link surface: it is what "VIC-42" resolves to, what a comment
// cross-reference opens, and (in P4) what a shared board link lands on.
//
// The body is <TaskDetail> (task-detail.tsx), which a plugin page's peek panel
// renders too; this route only supplies the task id.

import { useParams } from 'next/navigation';

import { TaskDetail } from './task-detail';
import { TaskDetailSkeleton } from './task-detail-skeleton';

export default function TaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const taskId = params?.taskId;
  // No id yet: the page waited on the skeleton until there was one.
  if (!taskId) return <TaskDetailSkeleton />;
  return <TaskDetail taskId={taskId} variant="page" />;
}
