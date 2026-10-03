'use client';

// Loading placeholder for the task page. Mirrors the loaded layout: back
// link, identifier line, title, description, timeline and composer on the
// left, the property rail on the right. The first paint then has the shape the
// page settles into, in the same pulse-bar style as the task list and
// session skeletons, rather than a lone "Loading…" line.

const BAR = 'rounded-full bg-muted-foreground/15';
const FAINT_BAR = 'rounded-full bg-muted-foreground/10';

// Description lines; uneven widths so it reads as prose, not a grid.
const DESCRIPTION = ['w-full', 'w-11/12', 'w-4/5', 'w-2/5'];

// Rail groups and their row counts: Properties (status / priority /
// assignee), Project, Labels, Sessions.
const RAIL = [
  { label: 'w-16', rows: ['w-20', 'w-16', 'w-24'] },
  { label: 'w-12', rows: ['w-28'] },
  { label: 'w-10', rows: ['w-20'] },
  { label: 'w-14', rows: ['w-16'] },
];

/** One generated-activity line: avatar, sentence, time. */
function ActivityLine({ width }: { width: string }) {
  return (
    <div className="flex h-6 items-center gap-2 px-3">
      <div className="size-4 shrink-0 rounded-full bg-muted-foreground/15" />
      <div className={`h-2.5 ${FAINT_BAR} ${width}`} />
      <div className={`h-2.5 w-8 ${FAINT_BAR}`} />
    </div>
  );
}

export function TaskDetailSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8" aria-hidden>
      <div className="animate-pulse">
        {/* "← Tasks" */}
        <div className="mb-4 flex h-4 items-center gap-1.5">
          <div className={`size-3.5 ${FAINT_BAR}`} />
          <div className={`h-2.5 w-10 ${FAINT_BAR}`} />
        </div>

        <div className="flex gap-10">
          <div className="min-w-0 flex-1 space-y-6">
            <div className="space-y-3">
              {/* Identifier chip + project */}
              <div className="flex h-5 items-center gap-2">
                <div className="h-4 w-14 rounded bg-muted-foreground/15" />
                <div className={`h-2.5 w-24 ${FAINT_BAR}`} />
              </div>
              {/* Title (text-2xl) */}
              <div className="flex h-8 items-center">
                <div className="h-6 w-2/3 rounded-full bg-muted-foreground/20" />
              </div>
              {/* Description */}
              <div className="space-y-2.5 py-1.5">
                {DESCRIPTION.map((width, i) => (
                  <div key={i} className={`h-3 ${FAINT_BAR} ${width}`} />
                ))}
              </div>
            </div>

            {/* Timeline: activity, a comment card, more activity, composer */}
            <div className="space-y-3 border-t pt-6">
              <ActivityLine width="w-48" />
              <div className="space-y-2.5 rounded-lg border px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <div className="size-4 shrink-0 rounded-full bg-muted-foreground/15" />
                  <div className={`h-3 w-24 ${BAR}`} />
                  <div className={`h-2.5 w-10 ${FAINT_BAR}`} />
                </div>
                <div className={`h-3 w-10/12 ${FAINT_BAR}`} />
                <div className={`h-3 w-7/12 ${FAINT_BAR}`} />
              </div>
              <ActivityLine width="w-36" />
              <div className="h-[3.75rem] rounded-xl border border-border/50" />
            </div>
          </div>

          {/* Property rail */}
          <div className="w-60 shrink-0 space-y-5">
            {RAIL.map((group, i) => (
              <div key={i} className="space-y-1">
                <div className="flex h-4 items-center px-2">
                  <div className={`h-2 ${FAINT_BAR} ${group.label}`} />
                </div>
                <div className="space-y-0.5">
                  {group.rows.map((width, j) => (
                    <div key={j} className="flex h-8 items-center gap-1.5 px-2">
                      <div className="size-3.5 shrink-0 rounded-full bg-muted-foreground/15" />
                      <div className={`h-3 ${BAR} ${width}`} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
