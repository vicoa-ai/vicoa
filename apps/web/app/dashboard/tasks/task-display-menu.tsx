'use client';

// Display options popover for the tasks page (multica's "Display" control):
// a "Show sub-tasks" switch plus per-property toggles that decide which chips
// render on list rows / board cards. All state lives on the active view.

import { ArrowDown, ArrowUp, Check, ChevronDown, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Switch } from '@/components/ui/switch';
import {
  TASK_PROPERTY_OPTIONS,
  TASK_SORT_OPTIONS,
  TaskSortDirection,
  TaskSortField,
  TaskViewProperties,
} from './task-views';

export function TaskDisplayMenu({
  showSubTasks,
  properties,
  sortBy,
  sortDirection,
  onShowSubTasksChange,
  onPropertyChange,
  onSortByChange,
  onSortDirectionChange,
}: {
  showSubTasks: boolean;
  properties: TaskViewProperties;
  sortBy: TaskSortField;
  sortDirection: TaskSortDirection;
  onShowSubTasksChange: (value: boolean) => void;
  onPropertyChange: (key: keyof TaskViewProperties, value: boolean) => void;
  onSortByChange: (value: TaskSortField) => void;
  onSortDirectionChange: (value: TaskSortDirection) => void;
}) {
  const sortLabel =
    TASK_SORT_OPTIONS.find((o) => o.key === sortBy)?.label ?? 'Manual';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          title="Display options"
        >
          <SlidersHorizontal className="size-3.5" />
          <span className="hidden md:inline">Display</span>
        </Button>
      </PopoverTrigger>
      {/* Match the neighbouring header dropdowns (project filter, view) which
          use bg-menu rather than the lighter bg-popover. */}
      <PopoverContent align="end" className="w-64 bg-menu p-0 text-sm">
        <label className="flex cursor-pointer items-center justify-between border-b px-3 py-2.5">
          <span>Show sub-tasks</span>
          <Switch checked={showSubTasks} onCheckedChange={onShowSubTasksChange} />
        </label>
        {/* Ordering — sort field + a direction toggle (hidden for Manual). */}
        <div className="border-b px-3 py-2.5">
          <span className="text-xs font-medium text-muted-foreground">Ordering</span>
          <div className="mt-2 flex items-center gap-1.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 flex-1 justify-between text-xs"
                >
                  {sortLabel}
                  <ChevronDown className="size-3 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-44 text-xs">
                {TASK_SORT_OPTIONS.map((opt) => (
                  <DropdownMenuItem key={opt.key} onSelect={() => onSortByChange(opt.key)}>
                    {opt.label}
                    {sortBy === opt.key && <Check className="ml-auto size-3" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            {sortBy !== 'position' && (
              <Button
                variant="outline"
                size="sm"
                className="size-7 shrink-0 p-0"
                title={sortDirection === 'asc' ? 'Ascending' : 'Descending'}
                onClick={() =>
                  onSortDirectionChange(sortDirection === 'asc' ? 'desc' : 'asc')
                }
              >
                {sortDirection === 'asc' ? (
                  <ArrowUp className="size-3.5" />
                ) : (
                  <ArrowDown className="size-3.5" />
                )}
              </Button>
            )}
          </div>
        </div>
        <div className="px-3 py-2.5">
          <span className="text-xs font-medium text-muted-foreground">Properties</span>
          <div className="mt-2 space-y-2">
            {TASK_PROPERTY_OPTIONS.map((opt) => (
              <label
                key={opt.key}
                className="flex cursor-pointer items-center justify-between"
              >
                <span>{opt.label}</span>
                <Switch
                  checked={properties[opt.key]}
                  onCheckedChange={(v) => onPropertyChange(opt.key, v)}
                />
              </label>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
