'use client';

import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DAY_LABELS } from '../lib/frequency';

export const ROW_TRIGGER =
  'flex h-7 max-w-full items-center gap-1.5 rounded-lg px-2 text-sm text-foreground/90 transition-colors hover:bg-foreground/10 disabled:opacity-50';

/** A right-aligned enum picker rendered as a "value ⌄" dropdown. */
export function ValueDropdown<T extends string>({
  value,
  options,
  onChange,
  title,
  side = 'bottom',
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
  title?: string;
  side?: 'top' | 'bottom';
}) {
  const current = options.find((o) => o.id === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={ROW_TRIGGER} title={title}>
          <span className="truncate">{current?.label ?? value}</span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side={side} className="min-w-40">
        {options.map((o) => (
          <DropdownMenuItem
            key={o.id}
            onClick={() => onChange(o.id)}
            className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm"
          >
            <span className="flex-1">{o.label}</span>
            {o.id === value && <Check className="h-3.5 w-3.5 flex-shrink-0" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Small bounded integer input with optional leading/trailing text. */
export function NumberStepper({
  value,
  onChange,
  min = 0,
  max = 999,
  prefix,
  suffix,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <div className="flex items-center gap-1.5 text-sm text-foreground/80">
      {prefix && <span>{prefix}</span>}
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isNaN(n)) return;
          onChange(Math.max(min, Math.min(max, n)));
        }}
        // Borderless, transparent (blends into the row), right-aligned so the
        // gap to the trailing word stays constant regardless of digit count.
        // No up/down spinner buttons.
        className={cn(
          'h-7 w-10 rounded-md bg-transparent px-1 text-right text-sm outline-none focus-visible:outline-none focus-visible:ring-0',
          '[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none',
        )}
      />
      {suffix && <span>{suffix}</span>}
    </div>
  );
}

/** Weekday multiselect (Sun–Sat) as a dropdown with a chip row. */
export function WeekdayPicker({
  value,
  onChange,
}: {
  value: number[];
  onChange: (v: number[]) => void;
}) {
  const toggle = (d: number) =>
    onChange(
      value.includes(d) ? value.filter((x) => x !== d) : [...value, d].sort((a, b) => a - b),
    );
  const label =
    value.length > 0
      ? [...value].sort((a, b) => a - b).map((d) => DAY_LABELS[d]).join(', ')
      : 'Choose days';
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={ROW_TRIGGER} title="Days of week">
          <span className="truncate">{label}</span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-auto rounded-xl p-2">
        <div className="flex gap-1">
          {DAY_LABELS.map((dayLabel, d) => (
            <button
              key={d}
              type="button"
              onClick={() => toggle(d)}
              className={cn(
                'h-7 w-9 rounded-md text-xs font-medium transition-colors',
                value.includes(d)
                  ? 'bg-foreground text-background'
                  : 'bg-muted/40 text-muted-foreground hover:bg-foreground/10',
              )}
            >
              {dayLabel}
            </button>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Month-day multiselect (1–31) as a dropdown with a chip grid. */
export function MonthdayPicker({
  value,
  onChange,
}: {
  value: number[];
  onChange: (v: number[]) => void;
}) {
  const toggle = (d: number) =>
    onChange(
      value.includes(d) ? value.filter((x) => x !== d) : [...value, d].sort((a, b) => a - b),
    );
  const label =
    value.length > 0 ? [...value].sort((a, b) => a - b).join(', ') : 'Choose days';
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={ROW_TRIGGER} title="Days of month">
          <span className="truncate">{label}</span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64 p-2">
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => toggle(d)}
              className={cn(
                'h-7 rounded-md text-xs transition-colors',
                value.includes(d)
                  ? 'bg-foreground text-background'
                  : 'bg-muted/40 text-muted-foreground hover:bg-foreground/10',
              )}
            >
              {d}
            </button>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
