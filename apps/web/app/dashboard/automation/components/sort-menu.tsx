'use client';

import { ArrowDown, ArrowUp, ArrowUpDown, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  SORT_OPTIONS,
  type AutomationSort,
  type AutomationSortDirection,
  type AutomationSortField,
} from '../lib/sort';

/**
 * The list's ordering, apart from the Show menu's filtering. It reads "Sort"
 * until an ordering is picked (`sort` is null, and nothing in the menu is
 * ticked; the list is in its drag order, as under Manual). Once picked, the
 * button names it and, for any but Manual, its direction, the way the Show
 * button names what it narrows. The label gives way to the bare icon when the
 * list column is narrow (it can be 280px). Manual has no direction, so that
 * part of the menu appears only for the other orderings.
 */
export function SortMenu({
  sort,
  onChange,
}: {
  sort: AutomationSort | null;
  onChange: (patch: Partial<AutomationSort>) => void;
}) {
  const sortBy = sort?.sortBy ?? null;
  const sortDirection = sort?.sortDirection ?? 'asc';
  // Has a direction: ordered by a field, not by hand.
  const sorted = sortBy !== null && sortBy !== 'position';
  const sortLabel = SORT_OPTIONS.find((o) => o.key === sortBy)?.label ?? null;
  const title = !sortLabel
    ? 'Sort'
    : sorted
      ? `Sort: ${sortLabel}, ${sortDirection === 'asc' ? 'ascending' : 'descending'}`
      : `Sort: ${sortLabel}`;
  const Arrow = sortDirection === 'asc' ? ArrowUp : ArrowDown;

  const field = (key: AutomationSortField, label: string) => (
    <DropdownMenuItem key={key} className="cursor-pointer" onSelect={() => onChange({ sortBy: key })}>
      {label}
      {sortBy === key && <Check className="ml-auto h-3 w-3" />}
    </DropdownMenuItem>
  );
  const direction = (value: AutomationSortDirection, label: string) => (
    <DropdownMenuItem
      key={value}
      className="cursor-pointer"
      onSelect={() => onChange({ sortDirection: value })}
    >
      {label}
      {sortDirection === value && <Check className="ml-auto h-3 w-3" />}
    </DropdownMenuItem>
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 shrink-0 cursor-pointer gap-1.5 text-xs"
          title={title}
          aria-label={title}
        >
          <ArrowUpDown className="size-3.5 text-muted-foreground" />
          <span className="flex items-center gap-1 @max-sm:hidden">
            {sortLabel ?? 'Sort'}
            {sorted && <Arrow className="size-3 text-muted-foreground" />}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44 text-xs">
        <DropdownMenuLabel className="text-[0.8rem] font-normal text-muted-foreground">
          Sort by
        </DropdownMenuLabel>
        {SORT_OPTIONS.map((o) => field(o.key, o.label))}
        {sorted && (
          <>
            <DropdownMenuSeparator />
            {direction('asc', 'Ascending')}
            {direction('desc', 'Descending')}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
