'use client';

// Loading placeholders for the tasks body, one per view mode: the list's
// grouped sections (h-10 status header + h-9 rows) and the board's columns of
// cards. Each mirrors the view it settles into so the first paint has the same
// shape, matching the sidebar/session skeleton style rather than a centered
// spinner.

import { BOARD_COL_WIDTH } from './task-board';

// A couple of sections with a few rows each; widths vary per row so the
// placeholder reads as content rather than a grid.
const SECTIONS = [
  ['w-40', 'w-56', 'w-44'],
  ['w-48', 'w-36', 'w-52', 'w-40'],
];

export function TaskListSkeleton() {
  return (
    <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2 pt-1" aria-hidden>
      <div className="animate-pulse space-y-4">
        {SECTIONS.map((rows, sectionIndex) => (
          <div key={sectionIndex} className="space-y-1">
            {/* Section header (task-list StatusAccordionItem) */}
            <div className="flex h-10 items-center gap-2 rounded-lg bg-muted/60 px-3">
              <div className="h-3.5 w-3.5 rounded-full bg-muted-foreground/20" />
              <div className="h-3 w-24 rounded-full bg-muted-foreground/15" />
              <div className="h-3 w-5 rounded-full bg-muted-foreground/10" />
            </div>
            {/* Task rows */}
            {rows.map((width, rowIndex) => (
              <div key={rowIndex} className="flex h-9 items-center gap-3 px-3">
                <div className="h-3.5 w-3.5 shrink-0 rounded-full bg-muted-foreground/15" />
                <div className={`h-3 rounded-full bg-muted-foreground/15 ${width}`} />
                <div className="ml-auto h-3 w-12 rounded-full bg-muted-foreground/10" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Cards per column; title widths vary so the columns read as content.
const COLUMNS = [
  ['w-40', 'w-48', 'w-32'],
  ['w-44', 'w-36'],
  ['w-48', 'w-40', 'w-44', 'w-32'],
  ['w-36'],
  ['w-44', 'w-40'],
];

export function TaskBoardSkeleton() {
  return (
    <div className="min-h-0 flex-1 overflow-hidden p-3" aria-hidden>
      <div className="flex h-full animate-pulse gap-3">
        {COLUMNS.map((cards, columnIndex) => (
          // Column (task-board BoardColumn): status heading, then cards.
          <div
            key={columnIndex}
            style={{ width: BOARD_COL_WIDTH }}
            className="flex shrink-0 flex-col rounded-xl bg-muted/40 p-2"
          >
            <div className="mb-2 flex h-6 items-center gap-2 px-1.5">
              <div className="h-3 w-3 rounded-full bg-muted-foreground/20" />
              <div className="h-3 w-20 rounded-full bg-muted-foreground/15" />
              <div className="h-3 w-4 rounded-full bg-muted-foreground/10" />
            </div>
            <div className="flex flex-col gap-2 p-1">
              {cards.map((width, cardIndex) => (
                // Card (task-board TaskCard): identifier, title, chips.
                <div
                  key={cardIndex}
                  className="rounded-lg border border-border/60 bg-card px-2.5 py-3"
                >
                  <div className="h-2.5 w-12 rounded-full bg-muted-foreground/10" />
                  <div className={`mt-2.5 h-3 rounded-full bg-muted-foreground/15 ${width}`} />
                  <div className="mt-3 flex gap-1.5">
                    <div className="h-4 w-14 rounded-full bg-muted-foreground/10" />
                    <div className="h-4 w-10 rounded-full bg-muted-foreground/10" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
