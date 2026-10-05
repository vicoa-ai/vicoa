'use client';

// The rows of the sidebar's filter menu (the ListFilter dropdown), shared by
// the dashboard sidebar and the public share page so both read the same.

import { Check } from 'lucide-react';
import {
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

// Same selected-row treatment as the sidebar's session rows.
const ITEM_SELECTED = 'bg-foreground/[0.08] dark:bg-foreground/10 text-foreground';

/** One dimension row in the filter menu: label left, current value right,
    options in a submenu (the built-in SubTrigger chevron closes the row). */
export function FilterSubRow({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <DropdownMenuSub>
      {/* Label takes the slack (flex-1) so the value hugs the built-in chevron
          at the right edge instead of floating mid-row. */}
      <DropdownMenuSubTrigger className="gap-2 py-1.5 text-[11px]">
        <span className="flex-1 text-foreground/90">{label}</span>
        <span className="max-w-24 truncate font-normal text-muted-foreground">{value}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-40 border-menu-border bg-menu-elevated font-mono text-[11px]">
        {children}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

/** A submenu option: check on the right; selecting closes the menu unless
    `keepOpen` (multi-select rows like the Project visibility toggles). */
export function FilterOptionItem({
  label,
  selected,
  onSelect,
  keepOpen = false,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
  keepOpen?: boolean;
}) {
  return (
    <DropdownMenuItem
      className={cn('gap-2 py-1 text-[11px]', selected && ITEM_SELECTED)}
      onSelect={(event) => {
        if (keepOpen) event.preventDefault();
        onSelect();
      }}
    >
      <span className="truncate">{label}</span>
      <span className="ml-auto w-3 flex-shrink-0">
        {selected && <Check className="h-3 w-3" />}
      </span>
    </DropdownMenuItem>
  );
}
