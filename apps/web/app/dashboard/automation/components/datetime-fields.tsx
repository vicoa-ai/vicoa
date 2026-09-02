'use client';

import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronDown, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { formatTime12 } from '../lib/frequency';
import { ROW_TRIGGER } from './controls';

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function ymdToDate(v: string): Date | undefined {
  return v ? new Date(`${v}T00:00:00`) : undefined;
}

function dateToYmd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function displayDate(v: string): string {
  const d = ymdToDate(v);
  return d
    ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Pick date';
}

/** Date field: borderless row-dropdown trigger → calendar popover. */
export function DateField({
  value,
  onChange,
}: {
  value: string; // 'yyyy-mm-dd' or ''
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={ROW_TRIGGER} title="Pick date">
          <CalendarDays className="h-3.5 w-3.5 flex-shrink-0" />
          <span className={cn('truncate', !value && 'text-muted-foreground')}>
            {displayDate(value)}
          </span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto rounded-xl p-0">
        <Calendar
          mode="single"
          autoFocus
          selected={ymdToDate(value)}
          defaultMonth={ymdToDate(value)}
          onSelect={(date) => {
            onChange(date ? dateToYmd(date) : '');
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

/**
 * One scrollable hour/minute column.
 *
 * Hoisted to module scope (not defined inside TimeField) so its component
 * identity is stable: a parent re-render — e.g. the 30s machine-liveness
 * refresh — reconciles the same DOM node and preserves the user's scroll
 * position, instead of remounting a fresh `<div>` that snaps back to the top.
 * On open it scrolls the selected value into view so a far-down value (say
 * hour 15) isn't hidden above the fold.
 */
function TimeColumn({
  values,
  selected,
  onPick,
}: {
  values: number[];
  selected: number;
  onPick: (n: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const el = selectedRef.current;
    if (!container || !el) return;
    container.scrollTop =
      el.offsetTop - container.clientHeight / 2 + el.clientHeight / 2;
    // Run once per open: the popover unmounts on close, so this mounts fresh.
  }, []);

  return (
    <div
      ref={containerRef}
      // `relative` makes this the offsetParent so `offsetTop` below is measured
      // from the column, not from some positioned ancestor of the popover.
      className="custom-scrollbar relative max-h-56 w-14 overflow-y-auto p-1"
    >
      {values.map((n) => (
        <button
          key={n}
          ref={n === selected ? selectedRef : undefined}
          type="button"
          onClick={() => onPick(n)}
          className={cn(
            'block w-full rounded-md px-2 py-1 text-center text-sm transition-colors',
            n === selected
              ? 'bg-foreground text-background'
              : 'text-foreground/80 hover:bg-foreground/[0.06] dark:hover:bg-foreground/10',
          )}
        >
          {pad2(n)}
        </button>
      ))}
    </div>
  );
}

/** Time field: borderless row-dropdown trigger → hour/minute columns. */
export function TimeField({
  value,
  onChange,
}: {
  value: string; // 'HH:MM'
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [h, m] = value.split(':').map(Number);
  const hour = Number.isNaN(h) ? 9 : h;
  const minute = Number.isNaN(m) ? 0 : m;
  const set = (hh: number, mm: number) => onChange(`${pad2(hh)}:${pad2(mm)}`);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={ROW_TRIGGER} title="Pick time">
          <Clock className="h-3.5 w-3.5 flex-shrink-0" />
          <span className={cn('truncate', !value && 'text-muted-foreground')}>
            {value ? formatTime12(value) : 'Pick time'}
          </span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto rounded-xl p-0">
        <div className="flex divide-x divide-border">
          <TimeColumn
            values={Array.from({ length: 24 }, (_, i) => i)}
            selected={hour}
            onPick={(hh) => set(hh, minute)}
          />
          <TimeColumn
            values={Array.from({ length: 60 }, (_, i) => i)}
            selected={minute}
            onPick={(mm) => set(hour, mm)}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
