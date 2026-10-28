'use client';

// Label filter for the tasks page header: pick any number of labels and the
// list/board keeps the tasks that carry at least one of them. The selection
// lives on the active view (task-views.ts `labelFilter`), like the project
// filter beside it.

import { useState } from 'react';
import { Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PickerItem } from '@/components/dashboard/task-ui';
import type { TaskLabelResponse } from '@/lib/backend-api';

export function TaskLabelFilter({
  labels,
  selected,
  onChange,
}: {
  /** Every label the filter can offer (task-views.ts `labelFilterOptions`). */
  labels: TaskLabelResponse[];
  /** Active label ids, already narrowed to labels that exist. */
  selected: Set<string>;
  onChange: (labelIds: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const picked = labels.filter((label) => selected.has(label.id));
  const needle = query.trim().toLowerCase();
  const visible = needle
    ? labels.filter((label) => label.name.toLowerCase().includes(needle))
    : labels;

  // Writes back from `selected`, so an id whose label was deleted drops out of
  // the saved view on the next toggle.
  const toggle = (labelId: string) => {
    const next = new Set(selected);
    if (next.has(labelId)) next.delete(labelId);
    else next.add(labelId);
    onChange([...next]);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setQuery('');
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          title="Filter by label"
        >
          <Tag className="size-3.5 text-muted-foreground" />
          {picked.length > 0 && (
            <span className="flex items-center gap-0.5">
              {picked.slice(0, 3).map((label) => (
                <span
                  key={label.id}
                  className="size-2 rounded-full"
                  style={{ backgroundColor: label.color }}
                />
              ))}
            </span>
          )}
          <span className="hidden max-w-28 truncate md:inline">
            {picked.length === 0
              ? 'Labels'
              : picked.length === 1
                ? picked[0].name
                : `${picked.length} labels`}
          </span>
        </Button>
      </PopoverTrigger>
      {/* bg-menu to match the neighbouring header dropdowns (see
          task-display-menu.tsx). */}
      <PopoverContent align="end" className="w-56 bg-menu p-0">
        <div className="border-b px-2 py-1.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter labels…"
            className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="custom-scrollbar max-h-64 overflow-y-auto p-1">
          {visible.map((label) => (
            <PickerItem
              key={label.id}
              selected={selected.has(label.id)}
              onClick={() => toggle(label.id)}
            >
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: label.color }}
              />
              <span className="truncate">{label.name}</span>
            </PickerItem>
          ))}
          {visible.length === 0 && (
            <p className="px-2 py-2 text-center text-xs text-muted-foreground">
              {labels.length === 0 ? 'No labels yet' : 'No matching labels'}
            </p>
          )}
        </div>
        {picked.length > 0 && (
          <div className="border-t p-1">
            <button
              type="button"
              onClick={() => onChange([])}
              className="flex w-full cursor-pointer items-center rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              Clear filter
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
