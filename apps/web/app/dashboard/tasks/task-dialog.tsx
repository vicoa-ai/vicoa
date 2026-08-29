'use client';

// Create/edit task dialog in multica's manual-create style: breadcrumb
// header, borderless title + description, property pill row, footer with
// the primary action. Also hosts the small create-project dialog.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarClock,
  CalendarDays,
  ChevronRight,
  CornerDownRight,
  CornerUpRight,
  Folder,
  Loader2,
  Maximize2,
  MessageCircle,
  Minimize2,
  MoreHorizontal,
  Plus,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmojiPicker } from '@/components/ui/emoji-picker';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Switch } from '@/components/ui/switch';
import { MentionPromptField } from '@/components/mention-prompt-field';
import { loadPersistedSelection } from '@/lib/agent-catalog';
import { getPref, setPref } from '@/lib/desktop-prefs';
import {
  AgentInstanceResponse,
  ProjectResponse,
  TaskLabelResponse,
  TaskPriority,
  TaskResponse,
  TaskStatus,
} from '@/lib/backend-api';
import {
  formatSidebarTime,
  getSessionTitle,
} from '@/components/dashboard/session-display';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import {
  DatePickerPill,
  LabelPickerPill,
  ParentPickerPill,
  PillButton,
  PriorityPickerPill,
  ProjectPickerPill,
  StatusIcon,
  StatusPickerPill,
  useAutoFocus,
} from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';

/** Persisted (desktop settings.json / localStorage) dialog size preference. */
const DIALOG_EXPANDED_PREF = 'tasks:dialogExpanded';

/** Optional properties that live behind the "…" overflow until added. */
type OptionalField = 'parent' | 'subtasks' | 'start' | 'due';

export interface TaskFormValues {
  title: string;
  description: string;
  project_id: string;
  status: TaskStatus;
  priority: TaskPriority;
  label_ids: string[];
  parent_task_id: string | null;
  start_date: string; // yyyy-mm-dd or ''
  due_date: string;
}

/** yyyy-mm-dd for a date input, from an ISO timestamp. */
function toDateInputValue(iso: string | null): string {
  if (!iso) return '';
  return iso.slice(0, 10);
}

/** Last path segment of a session's project dir, for a compact right-side tag. */
function projectBasename(project: string | null | undefined): string | null {
  if (!project) return null;
  return project.split('/').filter(Boolean).pop() ?? null;
}

export function TaskDialog({
  open,
  task,
  /** Preset fields for create mode (e.g. the section's status). */
  defaults,
  projects,
  labels,
  allTasks = [],
  childTasks = [],
  sessions = [],
  onCreateLabel,
  onAddSubtask,
  onOpenTask,
  onOpenSession,
  onClose,
  onSubmit,
}: {
  open: boolean;
  /** null → create mode */
  task: TaskResponse | null;
  defaults?: Partial<Pick<TaskFormValues, 'status' | 'project_id' | 'parent_task_id'>>;
  projects: ProjectResponse[];
  labels: TaskLabelResponse[];
  /** Every task, for the parent picker + resolving the parent breadcrumb. */
  allTasks?: TaskResponse[];
  /** Sub-tasks of `task` (edit mode). */
  childTasks?: TaskResponse[];
  /** Agent sessions started from `task` (edit mode), newest first. */
  sessions?: AgentInstanceResponse[];
  onCreateLabel?: (name: string) => Promise<TaskLabelResponse>;
  onAddSubtask?: (parent: TaskResponse, title: string) => Promise<void>;
  onOpenTask?: (task: TaskResponse) => void;
  /** Navigate to one of the task's linked sessions. */
  onOpenSession?: (instanceId: string) => void;
  onClose: () => void;
  /** Returns the created/updated task so create-mode can attach sub-tasks. */
  onSubmit: (values: TaskFormValues) => Promise<TaskResponse | void>;
}) {
  const inbox = projects.find((p) => p.is_inbox);
  const [values, setValues] = useState<TaskFormValues>(() => ({
    title: '',
    description: '',
    project_id: inbox?.id ?? '',
    status: 'backlog',
    priority: 'none',
    label_ids: [],
    parent_task_id: null,
    start_date: '',
    due_date: '',
  }));
  const [subtaskTitle, setSubtaskTitle] = useState('');
  const [addingSubtask, setAddingSubtask] = useState(false);
  // Sub-tasks stay collapsed until there's something to show (existing
  // children) or the user opens it from the Sub-tasks pill.
  const [subtasksOpen, setSubtasksOpen] = useState(false);
  // Create mode buffers sub-task titles (there's no parent id yet); they're
  // created right after the parent on submit.
  const [pendingSubtasks, setPendingSubtasks] = useState<string[]>([]);
  // Optional properties revealed from the "…" overflow (parent/subtasks/dates).
  // A field also shows once it has a value; this just tracks manual reveals.
  const [revealed, setRevealed] = useState<Set<OptionalField>>(new Set());
  const [saving, setSaving] = useState(false);
  // Create mode: keep the dialog open after creating so several tasks can be
  // added in a row (reusing project + parent). No effect in edit mode.
  const [createAnother, setCreateAnother] = useState(false);
  // Larger two-thirds-height dialog; remembered across opens per user.
  const [expanded, setExpanded] = useState(false);
  // Autofocus the title on open; a second ref lets us re-focus it after a
  // "Create another" reset (the open effect doesn't re-run then). The merged
  // ref must be stable (useCallback) — an inline ref would re-run every render
  // and keep stealing focus back to the title.
  const autoFocusTitle = useAutoFocus<HTMLInputElement>(open);
  const titleNodeRef = useRef<HTMLInputElement | null>(null);
  const titleRef = useCallback(
    (node: HTMLInputElement | null) => {
      titleNodeRef.current = node;
      autoFocusTitle(node);
    },
    [autoFocusTitle],
  );

  useEffect(() => {
    setExpanded(getPref<boolean>(DIALOG_EXPANDED_PREF) ?? false);
  }, []);

  const toggleExpanded = () => {
    setExpanded((prev) => {
      const next = !prev;
      setPref(DIALOG_EXPANDED_PREF, next);
      return next;
    });
  };

  // Re-seed the form whenever the dialog opens for a different task/preset.
  useEffect(() => {
    if (!open) return;
    setValues({
      title: task?.title ?? '',
      description: task?.description ?? '',
      project_id: task?.project_id ?? defaults?.project_id ?? inbox?.id ?? '',
      status: task?.status ?? defaults?.status ?? 'backlog',
      priority: task?.priority ?? 'none',
      label_ids: task?.labels.map((label) => label.id) ?? [],
      parent_task_id: task?.parent_task_id ?? defaults?.parent_task_id ?? null,
      start_date: toDateInputValue(task?.start_date ?? null),
      due_date: toDateInputValue(task?.due_date ?? null),
    });
    setSubtaskTitle('');
    setPendingSubtasks([]);
    setRevealed(new Set());
    // Show existing sub-tasks by default; a task with none starts collapsed so
    // the whole body goes to the description.
    setSubtasksOpen(childTasks.length > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task?.id]);

  const set = <K extends keyof TaskFormValues>(key: K, value: TaskFormValues[K]) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  // `@` file search in the description runs against the selected project's
  // linked folder. A project can be linked on several machines, so prefer the
  // one whose machine you last started a session on; otherwise take the first.
  // No link → a plain textarea, since there'd be no index to search.
  //
  // The machine goes along with the path: mentions try the live daemon index
  // first. Here that usually misses — you compose a task while the laptop is
  // asleep — and falls back to the CLI-synced DB copy, which is exactly what
  // that fallback exists for.
  const mentionTarget = useMemo(() => {
    const links = projects.find((p) => p.id === values.project_id)?.directories ?? [];
    if (links.length === 0) return undefined;
    const lastMachineId = loadPersistedSelection().lastMachineId;
    const link = links.find((d) => d.machine_id === lastMachineId) ?? links[0];
    return { path: link.local_path, machineId: link.machine_id ?? null };
  }, [projects, values.project_id]);
  const mentionPath = mentionTarget?.path;

  // Which optional properties currently show inline: a field appears once it
  // has a value or the user revealed it from the "…" menu. Sub-tasks also
  // count the create-mode buffer.
  const hasSubtasks = task ? childTasks.length > 0 : pendingSubtasks.length > 0;
  const shownFields: Record<OptionalField, boolean> = {
    parent: values.parent_task_id !== null || revealed.has('parent'),
    subtasks: hasSubtasks || revealed.has('subtasks'),
    start: !!values.start_date || revealed.has('start'),
    due: !!values.due_date || revealed.has('due'),
  };
  const hiddenFields = (['parent', 'subtasks', 'start', 'due'] as OptionalField[]).filter(
    (f) => !shownFields[f],
  );

  const revealField = (field: OptionalField) => {
    setRevealed((prev) => new Set(prev).add(field));
    if (field === 'subtasks') setSubtasksOpen(true);
  };

  const canSubmit = !!values.title.trim() && !saving;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      const saved = await onSubmit(values);
      // Create mode: attach the buffered sub-tasks to the new parent, in order.
      if (!task && saved && onAddSubtask) {
        for (const title of pendingSubtasks) {
          await onAddSubtask(saved, title);
        }
      }
      if (!task && createAnother) {
        // Keep the dialog open and reset for the next task, carrying over the
        // project and parent so a batch of related tasks lands in one place.
        setValues((prev) => ({
          title: '',
          description: '',
          project_id: prev.project_id,
          status: prev.status,
          priority: 'none',
          label_ids: [],
          parent_task_id: prev.parent_task_id,
          start_date: '',
          due_date: '',
        }));
        setPendingSubtasks([]);
        setRevealed(new Set());
        setSubtasksOpen(false);
        requestAnimationFrame(() => titleNodeRef.current?.focus());
      } else {
        onClose();
      }
    } catch {
      // Error surfaced by the caller; keep the dialog open for retry.
    } finally {
      setSaving(false);
    }
  };

  // Persist the current task (edit mode) before navigating away, so edits
  // aren't lost when jumping to a linked task or session. On a failed save we
  // stay put. onSubmit updates the existing row without closing.
  const persistThen = async (navigate: () => void) => {
    if (task && canSubmit) {
      setSaving(true);
      try {
        await onSubmit(values);
      } catch {
        setSaving(false);
        return; // keep the dialog open on the current task if the save failed
      }
      setSaving(false);
    }
    navigate();
  };

  const saveAndOpen = async (target: TaskResponse) => {
    if (!onOpenTask) return;
    await persistThen(() => onOpenTask(target));
  };

  const saveAndOpenSession = async (instanceId: string) => {
    if (!onOpenSession) return;
    await persistThen(() => onOpenSession(instanceId));
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent
        className={cn(
          'flex flex-col gap-0 overflow-hidden p-0 transition-[width,height] sm:rounded-xl',
          expanded ? 'h-[85vh] max-w-4xl' : 'h-[26rem] max-w-2xl',
        )}
      >
        <DialogTitle className="sr-only">{task ? 'Edit task' : 'New task'}</DialogTitle>

        {/* Header: breadcrumb + expand/close */}
        <div className="flex shrink-0 items-center justify-between px-5 pb-2 pt-3">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Tasks</span>
            <ChevronRight className="size-3 text-muted-foreground/50" />
            <span className="font-medium">{task ? 'Edit task' : 'New task'}</span>
          </div>
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              onClick={toggleExpanded}
              aria-label={expanded ? 'Collapse dialog' : 'Expand dialog'}
              title={expanded ? 'Collapse' : 'Expand'}
              className="cursor-pointer rounded-sm p-1.5 opacity-70 transition-all hover:bg-accent/60 hover:opacity-100"
            >
              {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="cursor-pointer rounded-sm p-1.5 opacity-70 transition-all hover:bg-accent/60 hover:opacity-100"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        {/* Title (parent is shown by the Parent pill / list-row chip). */}
        <div className="shrink-0 px-5 pb-2">
          <input
            ref={titleRef}
            value={values.title}
            onChange={(e) => set('title', e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void handleSubmit();
            }}
            placeholder="Task title"
            className="w-full bg-transparent text-lg font-semibold outline-none placeholder:text-muted-foreground/50"
          />
        </div>

        {/* Description + sub-tasks */}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5">
          <MentionPromptField
            value={values.description}
            onChange={(value) => set('description', value)}
            projectPath={mentionPath}
            machineId={mentionTarget?.machineId}
            mentionsEnabled={!!mentionPath}
            placeholder={
              mentionPath
                ? 'Add description… @ for files, / for skills (for the agent to handle this task)'
                : 'Add description… / for skills (for the agent to handle this task)'
            }
            // The wrapper must flex-grow for the textarea to fill the free
            // space; without this the description sits at min-h-24 and leaves
            // dead space above the pills. With it, the description takes ALL
            // the room between the title and the pills when sub-tasks are off,
            // and simply gets more of it as the dialog is expanded.
            wrapperClassName="flex min-h-0 flex-1 flex-col"
            containerClassName="flex min-h-0 flex-1 flex-col"
            className={cn(
              'h-full w-full min-h-24 resize-none bg-transparent text-sm leading-relaxed',
              'custom-scrollbar outline-none placeholder:text-muted-foreground/50',
            )}
          />

          {/* Sub-tasks. Toggled from the "Sub-tasks" pill; hidden entirely when
              off so the whole body goes to the description. Height-capped and
              scrollable so a long list never crowds the description out. In
              create mode the titles are buffered (no parent id yet) and created
              on submit; in edit mode each is added immediately. */}
          {onAddSubtask && subtasksOpen && (
            <div className="mb-2 mt-2 shrink-0 border-t pt-2">
              <div className="max-h-40 overflow-y-auto custom-scrollbar">
                {task
                  ? childTasks.map((child) => (
                      <button
                        key={child.id}
                        type="button"
                        onClick={() => void saveAndOpen(child)}
                        className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors hover:bg-accent/50"
                      >
                        <StatusIcon status={child.status} className="h-3.5 w-3.5" />
                        <span
                          className={cn(
                            'truncate',
                            (child.status === 'done' || child.status === 'cancelled') &&
                              'text-muted-foreground line-through',
                          )}
                        >
                          {child.title}
                        </span>
                      </button>
                    ))
                  : pendingSubtasks.map((title, i) => (
                      <div
                        key={i}
                        className="group/pending flex items-center gap-2 rounded-md px-2 py-1 text-sm"
                      >
                        <StatusIcon status="backlog" className="h-3.5 w-3.5" />
                        <span className="min-w-0 flex-1 truncate">{title}</span>
                        <button
                          type="button"
                          aria-label="Remove sub-task"
                          onClick={() =>
                            setPendingSubtasks((prev) => prev.filter((_, idx) => idx !== i))
                          }
                          className="shrink-0 opacity-0 transition-opacity hover:text-foreground group-hover/pending:opacity-100"
                        >
                          <X className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </div>
                    ))}
              </div>
              <div className="flex items-center gap-2 px-2 py-1">
                {addingSubtask ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                ) : (
                  <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <input
                  autoFocus={(task ? childTasks.length : pendingSubtasks.length) === 0}
                  value={subtaskTitle}
                  onChange={(e) => setSubtaskTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter' || !subtaskTitle.trim() || addingSubtask) return;
                    e.preventDefault();
                    const title = subtaskTitle.trim();
                    if (task) {
                      setAddingSubtask(true);
                      onAddSubtask(task, title)
                        .then(() => setSubtaskTitle(''))
                        .catch((err) => console.error('Failed to add sub-task:', err))
                        .finally(() => setAddingSubtask(false));
                    } else {
                      // Create mode: buffer until the parent exists.
                      setPendingSubtasks((prev) => [...prev, title]);
                      setSubtaskTitle('');
                    }
                  }}
                  placeholder="Add sub-task…"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
                />
              </div>
            </div>
          )}
        </div>

        {/* Property pills. Status / Priority / Project / Labels are always
            inline; parent, sub-tasks and the dates live behind the "…" menu
            until added (multica's overflow pattern). */}
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 px-4 py-2">
          <StatusPickerPill status={values.status} onSelect={(s) => set('status', s)} />
          <PriorityPickerPill
            priority={values.priority}
            onSelect={(p) => set('priority', p)}
          />
          <ProjectPickerPill
            projects={projects}
            projectId={values.project_id || null}
            onSelect={(id) => set('project_id', id)}
          />
          <LabelPickerPill
            labels={labels}
            selectedIds={values.label_ids}
            onToggle={(labelId) =>
              set(
                'label_ids',
                values.label_ids.includes(labelId)
                  ? values.label_ids.filter((id) => id !== labelId)
                  : [...values.label_ids, labelId],
              )
            }
            onCreate={
              onCreateLabel
                ? (name) => {
                    onCreateLabel(name)
                      .then((label) => set('label_ids', [...values.label_ids, label.id]))
                      .catch((err) => console.error('Failed to create label:', err));
                  }
                : undefined
            }
          />
          {shownFields.parent && (
            <ParentPickerPill
              tasks={allTasks}
              currentTaskId={task?.id ?? null}
              parentId={values.parent_task_id}
              onSelect={(id) => set('parent_task_id', id)}
            />
          )}
          {shownFields.subtasks && onAddSubtask && (
            <PillButton
              onClick={() => setSubtasksOpen((v) => !v)}
              className={cn(subtasksOpen && 'bg-accent text-accent-foreground')}
            >
              <CornerDownRight className="h-3 w-3 shrink-0" />
              <span>Sub-tasks</span>
            </PillButton>
          )}
          {shownFields.start && (
            <DatePickerPill
              label="Start date"
              icon="start"
              value={values.start_date}
              onChange={(v) => set('start_date', v)}
            />
          )}
          {shownFields.due && (
            <DatePickerPill
              label="Due date"
              icon="due"
              value={values.due_date}
              onChange={(v) => set('due_date', v)}
            />
          )}
          {hiddenFields.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <PillButton aria-label="Add property" title="Add property">
                  <MoreHorizontal className="h-3.5 w-3.5 shrink-0" />
                </PillButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-44 text-xs">
                {hiddenFields.includes('parent') && (
                  <DropdownMenuItem onSelect={() => revealField('parent')}>
                    <CornerUpRight className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                    Set parent task
                  </DropdownMenuItem>
                )}
                {hiddenFields.includes('subtasks') && onAddSubtask && (
                  <DropdownMenuItem onSelect={() => revealField('subtasks')}>
                    <CornerDownRight className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                    Add sub-tasks
                  </DropdownMenuItem>
                )}
                {hiddenFields.includes('start') && (
                  <DropdownMenuItem onSelect={() => revealField('start')}>
                    <CalendarClock className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                    Add start date
                  </DropdownMenuItem>
                )}
                {hiddenFields.includes('due') && (
                  <DropdownMenuItem onSelect={() => revealField('due')}>
                    <CalendarDays className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                    Add due date
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Linked sessions (edit mode): the agent sessions started from this
            task. Hidden when the task never ran one. A row saves any pending
            edits, then jumps into the session. */}
        {task && onOpenSession && sessions.length > 0 && (
          <div className="shrink-0 border-t px-3 py-2">
            <div className="flex items-center gap-1.5 px-1 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground/70">
              <MessageCircle className="h-3 w-3 shrink-0" />
              <span>
                {sessions.length === 1 ? 'Session' : `Sessions · ${sessions.length}`}
              </span>
            </div>
            <div className="custom-scrollbar max-h-28 space-y-0.5 overflow-y-auto">
              {sessions.map((session) => {
                const project = projectBasename(session.project);
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => void saveAndOpenSession(session.id)}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors hover:bg-accent/50"
                  >
                    <SessionAgentIcon
                      agentTypeName={session.agent_type_name}
                      status={session.status}
                      size={14}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      {getSessionTitle(session)}
                    </span>
                    {project && (
                      <span className="hidden max-w-[120px] shrink-0 truncate text-xs text-muted-foreground sm:inline">
                        {project}
                      </span>
                    )}
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatSidebarTime(session)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Footer (close via the header ✕; no Cancel button). */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t px-4 py-3">
          {/* Create mode: keep the dialog open to add several tasks in a row. */}
          {!task && (
            <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-muted-foreground">
              <span>Create another</span>
              <Switch
                aria-label="Create another"
                checked={createAnother}
                onCheckedChange={setCreateAnother}
              />
            </label>
          )}
          <Button size="sm" onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : task ? (
              'Save'
            ) : (
              'Create task'
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CreateProjectDialog({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (values: { name: string; icon: string | null }) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const nameRef = useAutoFocus<HTMLInputElement>(open);

  useEffect(() => {
    if (open) {
      setName('');
      setIcon('');
    }
  }, [open]);

  const canSubmit = !!name.trim() && !saving;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      await onSubmit({ name: name.trim(), icon: icon.trim() || null });
      onClose();
    } catch {
      // Error surfaced by the caller; keep the dialog open for retry.
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="flex max-w-md flex-col gap-0 overflow-hidden p-0 sm:rounded-xl">
        <DialogTitle className="sr-only">New project</DialogTitle>

        <div className="flex shrink-0 items-center justify-between px-5 pb-2 pt-3">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Projects</span>
            <ChevronRight className="size-3 text-muted-foreground/50" />
            <span className="font-medium">New project</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-sm p-1.5 opacity-70 transition-all hover:bg-accent/60 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-2 px-5 pb-4 pt-1">
          <Popover open={iconPickerOpen} onOpenChange={setIconPickerOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label="Project icon"
                className={cn(
                  'flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-md border border-input text-base',
                  'transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                )}
              >
                {icon || <Folder className="size-4 text-muted-foreground" />}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-auto p-0">
              <EmojiPicker
                onSelect={(emoji) => {
                  setIcon(emoji);
                  setIconPickerOpen(false);
                }}
                onClear={
                  icon
                    ? () => {
                        setIcon('');
                        setIconPickerOpen(false);
                      }
                    : undefined
                }
              />
            </PopoverContent>
          </Popover>
          <input
            ref={nameRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleSubmit();
            }}
            placeholder="Project name"
            className="w-full bg-transparent text-lg font-semibold outline-none placeholder:text-muted-foreground/50"
          />
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 border-t px-4 py-3">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create project'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
