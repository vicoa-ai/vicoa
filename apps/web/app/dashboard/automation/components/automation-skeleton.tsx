'use client';

// Loading placeholder for the automations list — mirrors AutomationList's
// search bar + two-line rows (status dot, title, schedule) so the first paint
// keeps the same shape, matching the sidebar/session skeleton style rather
// than a centered spinner.

// Per-row title/subtitle widths so the placeholder reads as content.
const ROWS = [
  ['w-40', 'w-24'],
  ['w-52', 'w-28'],
  ['w-36', 'w-20'],
  ['w-48', 'w-24'],
  ['w-44', 'w-28'],
  ['w-32', 'w-20'],
];

export function AutomationListSkeleton() {
  return (
    <div className="flex h-full flex-col" aria-hidden>
      {/* Search bar placeholder (AutomationList's search input) */}
      <div className="border-b border-border p-2">
        <div className="h-8 rounded-lg bg-muted/40" />
      </div>
      {/* Rows */}
      <div className="animate-pulse">
        {ROWS.map(([title, subtitle], i) => (
          <div
            key={i}
            className="flex items-center gap-2.5 border-b border-border/50 px-3 py-2.5"
          >
            <div className="h-4 w-4 shrink-0 rounded-full bg-muted-foreground/15" />
            <div className="min-w-0 flex-1 space-y-2">
              <div className={`h-3 rounded-full bg-muted-foreground/15 ${title}`} />
              <div className={`h-2.5 rounded-full bg-muted-foreground/10 ${subtitle}`} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
