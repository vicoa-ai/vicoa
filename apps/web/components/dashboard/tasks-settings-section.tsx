'use client';

/**
 * Settings → Tasks: the user's label vocabulary. Labels are owner-scoped — one
 * set across every project (and a team's set across its projects), not
 * per-project — which is why they live at the top level of Settings and not in
 * a project's pane. Self-contained: loads and mutates through the API directly.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ConfirmDeleteDialog } from '@/components/dashboard/session-dialogs';
import { INLINE_LABEL_COLORS, LabelChip, inlineLabelColor } from '@/components/dashboard/task-ui';
import { getBackendAPI, type TaskLabelResponse } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

const byName = (a: TaskLabelResponse, b: TaskLabelResponse) => a.name.localeCompare(b.name);

export function TasksSettingsSection() {
  const [labels, setLabels] = useState<TaskLabelResponse[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [deleting, setDeleting] = useState<TaskLabelResponse | null>(null);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLabels((await getBackendAPI(true).listTaskLabels()).sort(byName));
      setLoadError(false);
    } catch {
      setLoadError(true);
      setLabels((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Color derives from the name (same rule as inline creation from the task
  // picker), so a label created here matches one created on the board.
  const create = useCallback(async () => {
    const trimmed = newName.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const label = await getBackendAPI(true).createTaskLabel({
        name: trimmed,
        color: inlineLabelColor(trimmed),
      });
      setLabels((prev) => [...(prev ?? []), label].sort(byName));
      setNewName('');
    } catch (err) {
      console.error('Failed to create label:', err);
    } finally {
      setCreating(false);
    }
  }, [newName, creating]);

  const update = useCallback(async (labelId: string, patch: { name?: string; color?: string }) => {
    try {
      const updated = await getBackendAPI(true).updateTaskLabel(labelId, patch);
      setLabels((prev) => (prev ?? []).map((l) => (l.id === labelId ? updated : l)).sort(byName));
    } catch (err) {
      console.error('Failed to update label:', err);
    }
  }, []);

  return (
    <section>
      <h1 className="text-2xl font-light tracking-tight text-foreground">Tasks</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Labels tag tasks on the board. One set is shared across all your projects.
      </p>

      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Labels</h2>
        {labels === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading labels…
          </div>
        ) : (
          <div className="space-y-1">
            {labels.map((label) => (
              <LabelRow
                key={label.id}
                label={label}
                onUpdate={(patch) => update(label.id, patch)}
                onRequestDelete={() => setDeleting(label)}
              />
            ))}

            <div className="flex items-center gap-2 rounded-lg border border-dashed px-2 py-1.5">
              {creating ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
              ) : (
                <Plus className="size-4 shrink-0 text-muted-foreground" />
              )}
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void create();
                  }
                }}
                placeholder="New label…"
                aria-label="New label"
                className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
              />
            </div>
          </div>
        )}
        {loadError && (
          <p className="mt-2 text-xs text-destructive">Couldn&apos;t load labels — check your connection.</p>
        )}
      </div>

      <ConfirmDeleteDialog
        open={deleting !== null}
        onOpenChange={(next) => {
          if (!next) setDeleting(null);
        }}
        title="Delete label"
        description="Are you sure you want to delete this label? It will be removed from every task that uses it. This action cannot be undone."
        subject={deleting ? <LabelChip label={deleting} /> : null}
        onConfirm={async () => {
          if (!deleting) return;
          await getBackendAPI(true).deleteTaskLabel(deleting.id);
          setLabels((prev) => (prev ?? []).filter((l) => l.id !== deleting.id));
        }}
      />
    </section>
  );
}

function LabelRow({
  label,
  onUpdate,
  onRequestDelete,
}: {
  label: TaskLabelResponse;
  onUpdate: (patch: { name?: string; color?: string }) => Promise<void>;
  onRequestDelete: () => void;
}) {
  const [name, setName] = useState(label.name);
  const [colorOpen, setColorOpen] = useState(false);

  useEffect(() => setName(label.name), [label.name]);

  const commitName = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === label.name) {
      setName(label.name);
      return;
    }
    void onUpdate({ name: trimmed });
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border px-2 py-1.5">
      <Popover open={colorOpen} onOpenChange={setColorOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`Color for ${label.name}`}
            style={{ backgroundColor: label.color }}
            className="size-4 shrink-0 cursor-pointer rounded-full ring-offset-2 ring-offset-popover transition-shadow hover:ring-2 hover:ring-ring/50"
          />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-2">
          <div className="grid grid-cols-5 gap-1.5">
            {INLINE_LABEL_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={color}
                style={{ backgroundColor: color }}
                onClick={() => {
                  setColorOpen(false);
                  void onUpdate({ color });
                }}
                className={cn(
                  'size-6 cursor-pointer rounded-full transition-transform hover:scale-110',
                  color === label.color && 'ring-2 ring-ring ring-offset-2 ring-offset-popover',
                )}
              />
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
          if (e.key === 'Escape') {
            setName(label.name);
            e.currentTarget.blur();
          }
        }}
        aria-label={`Name for ${label.name}`}
        className="min-w-0 flex-1 rounded-md bg-transparent px-1.5 py-1 text-sm outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
      />

      <LabelChip label={label} />

      <button
        type="button"
        aria-label={`Delete ${label.name}`}
        onClick={onRequestDelete}
        className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
