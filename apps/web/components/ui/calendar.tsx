'use client';

// Calendar primitive on react-day-picker, styled entirely with the app's
// semantic tokens (popover / accent / muted-foreground / primary) instead of
// the library stylesheet — the native `<input type="date">` it replaces
// rendered a white box with a black glyph regardless of theme.

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { DayPicker } from 'react-day-picker';

import { cn } from '@/lib/utils';

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

export function Calendar({ className, classNames, showOutsideDays = true, ...props }: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn('p-3', className)}
      classNames={{
        months: 'flex flex-col gap-4',
        month: 'flex flex-col gap-4',
        month_caption: 'flex h-7 items-center justify-center',
        caption_label: 'text-sm font-medium',
        nav: 'flex items-center gap-1 absolute right-3 top-3 z-10',
        button_previous: cn(
          'inline-flex size-7 cursor-pointer items-center justify-center rounded-md',
          'text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
          'disabled:pointer-events-none disabled:opacity-40',
        ),
        button_next: cn(
          'inline-flex size-7 cursor-pointer items-center justify-center rounded-md',
          'text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
          'disabled:pointer-events-none disabled:opacity-40',
        ),
        month_grid: 'w-full border-collapse',
        weekdays: 'flex',
        weekday: 'w-8 text-[0.7rem] font-normal text-muted-foreground',
        week: 'mt-1 flex w-full',
        day: 'size-8 p-0 text-center text-sm',
        day_button: cn(
          'size-8 cursor-pointer rounded-md font-normal transition-colors',
          'hover:bg-accent hover:text-accent-foreground',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
        ),
        selected: cn(
          '[&>button]:bg-primary [&>button]:text-primary-foreground',
          '[&>button]:hover:bg-primary [&>button]:hover:text-primary-foreground',
        ),
        today: '[&>button]:font-semibold [&>button]:text-foreground [&>button]:underline',
        outside: 'text-muted-foreground/50',
        disabled: 'text-muted-foreground/40',
        hidden: 'invisible',
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, ...rest }) =>
          orientation === 'left' ? (
            <ChevronLeft className="size-4" {...rest} />
          ) : (
            <ChevronRight className="size-4" {...rest} />
          ),
      }}
      {...props}
    />
  );
}
