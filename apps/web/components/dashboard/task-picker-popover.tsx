"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, CircleSlash, Loader2 } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  ProjectResponse,
  TaskResponse,
  getBackendAPI,
} from "@/lib/backend-api";
import {
  PriorityIcon,
  ProjectIcon,
  StatusIcon,
  projectLabel,
} from "@/components/dashboard/task-ui";

/**
 * Popover-anchored task picker for the new-session page (tasks-and-projects
 * plan §6) — the sibling of WorktreePickerPopover. Selecting a task seeds the
 * session's first prompt with the task's title + description and links the
 * spawned instance back to the task (status auto-linkage §4).
 *
 * Fetches open tasks (not done/cancelled) grouped by project each time the
 * popover opens. Selection closes the popover; "No task" clears it.
 */
export interface TaskPickerPopoverProps {
  selectedTask: TaskResponse | null;
  onSelect: (task: TaskResponse | null) => void;
  disabled?: boolean;
  children: React.ReactNode;
}

const OPEN_STATUSES = new Set(["backlog", "todo", "in_progress", "in_review", "blocked"]);

// Order tasks within a project group by status: the ready-to-pick-up "Todo"
// first, then "Backlog", then the in-flight states. Deliberately distinct from
// the board's STATUS_ORDER (which leads with Backlog) — here the most likely
// pick tops the list. Unknown statuses sort last.
const PICKER_STATUS_ORDER: TaskResponse["status"][] = [
  "todo",
  "backlog",
  "in_progress",
  "in_review",
  "blocked",
];
const statusRank = (status: TaskResponse["status"]) => {
  const index = PICKER_STATUS_ORDER.indexOf(status);
  return index === -1 ? PICKER_STATUS_ORDER.length : index;
};

export function TaskPickerPopover({
  selectedTask,
  onSelect,
  disabled,
  children,
}: TaskPickerPopoverProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [tasks, setTasks] = useState<TaskResponse[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const backendApi = getBackendAPI();
      const [projectList, taskList] = await Promise.all([
        backendApi.listProjects(),
        backendApi.listTasks(),
      ]);
      setProjects(projectList);
      setTasks(taskList.filter((task) => OPEN_STATUSES.has(task.status)));
    } catch (e) {
      console.error("Failed to load tasks:", e);
      setError(true);
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // (Re)fetch each time the popover opens so the list reflects tasks created
  // in another tab since.
  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const select = (task: TaskResponse | null) => {
    onSelect(task);
    setOpen(false);
  };

  const groups = projects
    .map((project) => ({
      project,
      tasks: tasks
        .filter((task) => task.project_id === project.id)
        .sort(
          (a, b) =>
            statusRank(a.status) - statusRank(b.status) ||
            a.position - b.position ||
            a.created_at.localeCompare(b.created_at),
        ),
    }))
    .filter((group) => group.tasks.length > 0);

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild disabled={disabled}>
        {children}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        sideOffset={8}
        className="w-[max(var(--radix-popover-trigger-width),20rem)] p-3 space-y-2 border border-foreground/15 bg-[#2D2D2D] shadow-xl"
      >
        <div className="text-[11px] text-muted-foreground font-mono">Task</div>

        <button
          type="button"
          onClick={() => select(null)}
          className="flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/10 cursor-pointer"
        >
          <CircleSlash className="h-3 w-3 flex-shrink-0" />
          <span className="flex-1 text-left">No task</span>
          {selectedTask === null && <Check className="h-3 w-3 flex-shrink-0" />}
        </button>

        {loading && (
          <div className="flex items-center justify-center py-3 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          </div>
        )}

        {!loading && error && (
          <div className="px-2.5 py-1.5 text-[11px] font-mono">
            <span className="text-destructive">Couldn&apos;t load tasks. </span>
            <button type="button" onClick={load} className="underline cursor-pointer">
              Retry
            </button>
          </div>
        )}

        {!loading && !error && groups.length === 0 && (
          <div className="px-2.5 py-2 text-[11px] text-muted-foreground font-mono">
            No open tasks — create one on the Tasks page.
          </div>
        )}

        {!loading && !error && groups.length > 0 && (
          <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar pr-1">
            {groups.map(({ project, tasks: projectTasks }) => (
              <div key={project.id} className="space-y-0.5">
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground font-mono px-2.5">
                  <ProjectIcon project={project} />
                  {projectLabel(project)}
                </div>
                {projectTasks.map((task) => (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => select(task)}
                    className="flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/10 cursor-pointer"
                    title={task.title}
                  >
                    <StatusIcon status={task.status} className="h-3 w-3" />
                    <span className="flex-1 truncate text-left">{task.title}</span>
                    <PriorityIcon priority={task.priority} className="h-3 w-3" />
                    {selectedTask?.id === task.id && (
                      <Check className="h-3 w-3 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
