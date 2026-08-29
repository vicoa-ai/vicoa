'use client';

// Loading placeholder for the tasks body — mirrors the list view's grouped
// sections (h-10 status header + h-9 rows) so the first paint has the same
// shape it settles into, matching the sidebar/session skeleton style rather
// than a centered spinner.

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
