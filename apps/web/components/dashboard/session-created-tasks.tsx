'use client';

// The tasks a session created (`vicoa task create` run inside it), as a chip in
// the session header next to the other provenance chips. The reverse of the
// task page's "Created in <session>" line.
//
// Lists only tasks the viewer can see: the server filters
// `GET /tasks?created_in_instance_id=` through the same task lens as the board.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ListTodo } from 'lucide-react';

import { StatusIcon, TaskIdentifier } from '@/components/dashboard/task-ui';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { NO_DRAG } from '@/lib/app-region';
import type { TaskResponse } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';

// The agent creates tasks mid-run, so the list follows the transcript; a burst
// of messages costs one refetch, not one each.
const REFETCH_DEBOUNCE_MS = 1500;

export function SessionCreatedTasks({
  instanceId,
  messageCount,
}: {
  instanceId: string;
  /** Changes as the transcript grows; each settled change refetches. */
  messageCount: number;
}) {
  const { api } = useAgentDashboard();
  const [tasks, setTasks] = useState<TaskResponse[]>([]);

  useEffect(() => {
    setTasks([]);
  }, [instanceId]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    const load = () => {
      api
        .listTasks({ createdInInstanceId: instanceId })
        .then((rows) => {
          if (!cancelled) setTasks(rows);
        })
        // Provenance is a nicety: a failed fetch keeps the last list.
        .catch(() => {});
    };
    const timer = window.setTimeout(load, REFETCH_DEBOUNCE_MS);
    window.addEventListener('focus', load);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener('focus', load);
    };
  }, [api, instanceId, messageCount]);

  if (tasks.length === 0) return null;
  return (
    <>
      <span className="text-muted-foreground flex-shrink-0">·</span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            style={NO_DRAG}
            className="flex flex-shrink-0 cursor-pointer items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ListTodo className="h-3.5 w-3.5" />
            <span>
              {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
            </span>
          </button>
        </DropdownMenuTrigger>
        {/* Portaled, but it opens over the header's bottom edge: in the
            desktop app that strip is a window-drag region, which would
            swallow clicks on the menu's top rows. */}
        <DropdownMenuContent align="start" className="w-80" style={NO_DRAG}>
          <DropdownMenuLabel className="text-[0.8rem] font-normal text-muted-foreground">
            Created in this session
          </DropdownMenuLabel>
          {tasks.map((task) => (
            <DropdownMenuItem key={task.id} asChild className="cursor-pointer">
              <Link href={`/dashboard/tasks/${task.id}`} className="flex min-w-0 items-center gap-2">
                <StatusIcon status={task.status} className="h-3.5 w-3.5" />
                <TaskIdentifier task={task} />
                <span className="truncate">{task.title}</span>
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}
