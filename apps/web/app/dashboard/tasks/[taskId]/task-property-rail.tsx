'use client';

// The task page's right-hand rail: properties, project, labels and the
// session count with "Start session". Page variant only; the peek panel packs
// the key properties into one row of pills under its title instead
// (task-detail-panel.tsx).

import { Play, Plus } from 'lucide-react';

import { TaskResponse } from '@/lib/backend-api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { agentsForProject, labelsForProject } from '@/lib/project-vocabulary';
import {
  AssigneePickerPill,
  DatePickerPill,
  LabelPickerPill,
  ParentPickerPill,
  PriorityPickerPill,
  ProjectPickerPill,
  PropertyRows,
  StatusPickerPill,
  toDateOnly,
  dateOnlyToLocalDate,
} from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';
import type { TaskDetailModel } from './use-task-detail';

// Properties that stay out of the rail until they carry a value or the user
// picks them from "Other properties". Status / priority / assignee / project /
// labels are always shown — they are the ones you scan for.
const OPTIONAL_PROPERTIES: {
  key: string;
  label: string;
  isSet: (task: TaskResponse) => boolean;
}[] = [
  { key: 'due_date', label: 'Due date', isSet: (t) => t.due_date !== null },
  { key: 'start_date', label: 'Start date', isSet: (t) => t.start_date !== null },
  { key: 'parent', label: 'Parent task', isSet: (t) => t.parent_task_id !== null },
];

function RailGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="px-2 text-xs text-muted-foreground/60">{label}</div>
      <PropertyRows>{children}</PropertyRows>
    </div>
  );
}

export function TaskPropertyRail({
  task,
  model,
  revealed,
  onReveal,
  onStartSession,
}: {
  task: TaskResponse;
  model: TaskDetailModel;
  /** Optional properties the user asked for that have no value yet. Held by
   *  the caller, so they survive the rail being swapped for an error state. */
  revealed: Set<string>;
  onReveal: (key: string) => void;
  onStartSession: () => void;
}) {
  const {
    canEdit,
    isOwner,
    viewer,
    projects,
    labels,
    agentProfiles,
    allTasks,
    sessions,
    patchTask,
    createLabelAndAttach,
  } = model;

  // A property earns a slot when it has a value or the user asked for it.
  const isShown = (key: string) => revealed.has(key) || OPTIONAL_PROPERTIES.find((p) => p.key === key)?.isSet(task);
  const hidden = OPTIONAL_PROPERTIES.filter((p) => !isShown(p.key));

  return (
    // Below editor the whole rail is inert: a disabled fieldset turns
    // every picker trigger inside it into a plain, unclickable label.
    <fieldset
      disabled={!canEdit}
      className={cn(
        'w-60 shrink-0 space-y-5',
        !canEdit && '[&_button]:cursor-default',
      )}
    >
      {/* Grouped, not labelled per field: one heading over a column of
          icon + value rows reads as a property list, whereas an uppercase
          caption above every single pill is eight captions to skip past.
          The row shape comes from <PropertyRows>. */}
      <RailGroup label="Properties">
        <StatusPickerPill
          status={task.status}
          onSelect={(status) => void patchTask({ status })}
        />
        <PriorityPickerPill
          priority={task.priority}
          onSelect={(priority) => void patchTask({ priority })}
        />
        <AssigneePickerPill
          assignee={task.assignee}
          viewer={viewer}
          agentProfiles={agentsForProject(
            agentProfiles,
            projects.find((p) => p.id === task.project_id),
          )}
          onSelect={(next) =>
            void patchTask({
              assignee_type: next?.type ?? null,
              assignee_id: next?.id ?? null,
            })
          }
        />
        {isShown('due_date') && (
          <DatePickerPill
            label="Due date"
            value={task.due_date ? toDateOnly(new Date(task.due_date)) : ''}
            onChange={(value) =>
              void patchTask({
                due_date: value ? dateOnlyToLocalDate(value)?.toISOString() ?? null : null,
              })
            }
          />
        )}
        {isShown('start_date') && (
          <DatePickerPill
            label="Start date"
            icon="start"
            value={task.start_date ? toDateOnly(new Date(task.start_date)) : ''}
            onChange={(value) =>
              void patchTask({
                start_date: value
                  ? dateOnlyToLocalDate(value)?.toISOString() ?? null
                  : null,
              })
            }
          />
        )}
        {isShown('parent') && (
          <ParentPickerPill
            tasks={allTasks}
            currentTaskId={task.id}
            parentId={task.parent_task_id}
            onSelect={(parentId) => void patchTask({ parent_task_id: parentId })}
          />
        )}
        {canEdit && hidden.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
              >
                <Plus className="size-3.5" />
                Other properties
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-44">
              {hidden.map((property) => (
                <DropdownMenuItem
                  key={property.key}
                  className="cursor-pointer"
                  onSelect={() => onReveal(property.key)}
                >
                  {property.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </RailGroup>

      <RailGroup label="Project">
        <ProjectPickerPill
          projects={projects}
          projectId={task.project_id}
          onSelect={(projectId) => void patchTask({ project_id: projectId })}
        />
      </RailGroup>

      <RailGroup label="Labels">
        <LabelPickerPill
          labels={labelsForProject(
            labels,
            projects.find((p) => p.id === task.project_id),
            task.labels,
          )}
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
      </RailGroup>

      {/* Sessions are a count on purpose: each already renders as a card in
          the timeline, and listing them twice says the same thing twice. */}
      <RailGroup label="Sessions">
        <span className="px-2 text-sm text-muted-foreground">
          {sessions.length === 0 ? 'None yet' : `${sessions.length} linked`}
        </span>
        {/* Only the owner starts sessions from a task: a session runs on
            your own machine and links back to the task, and the link is
            an owner-side write (§4's owner-only lens). */}
        {isOwner && (
          <button
            type="button"
            onClick={onStartSession}
            className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          >
            <Play className="size-3.5" />
            Start session
          </button>
        )}
      </RailGroup>
    </fieldset>
  );
}
