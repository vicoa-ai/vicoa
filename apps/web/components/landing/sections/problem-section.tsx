import {
  ProblemWaiting,
  ProblemCollision,
  ProblemBabysitting,
  ProblemTabs,
} from '@/components/landing/illustrations';

const pains = [
  {
    Art: ProblemWaiting,
    title: 'Chained to your desk',
    caption: 'It runs, then waits. You can’t leave.',
  },
  {
    Art: ProblemCollision,
    title: 'Agents trip over each other',
    caption: 'Two agents, one file, one merge mess.',
  },
  {
    Art: ProblemBabysitting,
    title: 'Babysitting every step',
    caption: 'Approve, nudge, repeat. By hand.',
  },
  {
    Art: ProblemTabs,
    title: 'A wall of terminal tabs',
    caption: 'Which one is stuck? Good luck.',
  },
];

export function ProblemSection() {
  return (
    <section className="relative overflow-hidden bg-muted/30 py-20 sm:py-28 lg:py-32">
      {/* Soft red wash to set a tension register before the relief section below */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 left-1/2 h-80 w-[46rem] -translate-x-1/2 rounded-full bg-red-500/[0.06] blur-3xl dark:bg-red-500/[0.09]"
      />

      <div className="relative z-10 mx-auto max-w-[85rem] px-4 sm:px-6 lg:px-6">
        <div className="mx-auto mb-14 max-w-3xl text-center sm:mb-20">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-red-500/20 bg-red-500/[0.06] px-3.5 py-1.5 text-xs font-medium uppercase tracking-[0.18em] text-red-600 dark:text-red-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
            The reality today
          </div>
          <h2 className="mb-5 text-3xl tracking-tight text-foreground sm:text-4xl lg:text-6xl">
            Coding agents were supposed
            <br className="hidden sm:block" /> to set you free
          </h2>
          <p className="text-lg text-muted-foreground sm:text-xl">
            You’ve got powerful AI agents. So why do you feel more drained than before?
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 sm:gap-6">
          {pains.map((pain, i) => {
            const Art = pain.Art;
            return (
              <div
                key={pain.title}
                className="group flex h-full flex-col overflow-hidden rounded-3xl border bg-card p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-red-300/70 hover:shadow-lg sm:p-6 dark:hover:border-red-500/40"
              >
                <Art />
                <div className="mt-6 flex items-baseline gap-3">
                  <span className="font-mono text-sm font-medium text-red-500/70 tabular-nums">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="text-xl font-medium text-card-foreground sm:text-2xl">
                    {pain.title}
                  </h3>
                </div>
                <p className="mt-2 text-base leading-relaxed text-muted-foreground">
                  {pain.caption}
                </p>
              </div>
            );
          })}
        </div>

        {/* Closing statement: the whole section lands on one line */}
        <div className="relative mt-14 overflow-hidden rounded-3xl border bg-gradient-to-br from-card to-muted/50 px-6 py-10 text-center shadow-sm sm:mt-20 sm:px-12 sm:py-14">
          <p className="mx-auto max-w-3xl text-2xl leading-snug text-foreground sm:text-3xl lg:text-4xl">
            The whole point of agents was to <span className="italic">not</span> sit and watch.
          </p>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground sm:text-xl">
            Yet here you are —{' '}
            <span className="font-medium text-red-600 dark:text-red-400">
              the bottleneck in your own workflow.
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}
