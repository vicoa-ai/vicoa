import { Check } from 'lucide-react';
import {
  DemoFleet,
  DemoSteer,
  DemoMachines,
  DemoDiff,
  DemoFiles,
  DemoTerminal,
  DemoTasks,
  DemoAutomations,
} from '@/components/landing/feature-demos';

export interface Feature {
  /** Live, animated demo of the capability (theme-aware, pure CSS + real logos). */
  Demo: React.ComponentType;
  /** Lead with the capability (positioning: capability first, never the feature). */
  capability: string;
  /** The mechanism that delivers it. */
  feature: string;
  /** Concrete, scannable proof points. */
  points: string[];
  /** The competitive anchor: one agent, one machine, one desk. */
  contrast: string;
}

// Each row leads with the capability, then feature → benefit → contrast, mapped
// against "one agent, one machine, one desk."
const defaultFeatures: Feature[] = [
  {
    Demo: DemoFleet,
    capability: 'Run a whole fleet, see it at a glance',
    feature:
      'Start Claude Code, Codex, OpenCode and more agents side by side, each on its own git worktree, and watch every session’s live status in one list.',
    points: [
      'Kick off many agents at once, each isolated on its own branch',
      'Spot the one that’s blocked, running, or finished without hunting',
    ],
    contrast: 'Instead of one agent, one terminal, one tab at a time',
  },
  {
    Demo: DemoMachines,
    capability: 'Any machine, from any device',
    feature:
      'Connect your Mac, Windows, Linux, or a remote server, and drive the agents running on all of them through Vicoa.',
    points: [
      'Your code and agents stay on your own machines',
      'Reach every machine from your phone, laptop, or the web',
    ],
    contrast: 'Instead of being tied to one computer on one network',
  },  
  {
    Demo: DemoSteer,
    capability: 'Steer any agent from your phone',
    feature:
      'Pick up the exact same session on your phone, the web, or your desktop, type a reply, approve a change, or redirect the agent, and it syncs everywhere instantly.',
    points: [
      'Type or talk to your agents right from the mobile app',
      'Every message stays in sync across phone, web, and desktop',
    ],
    contrast: 'Instead of being chained to the desktop it runs on',
  },
  {
    Demo: DemoFiles,
    capability: 'File explorer next to the chat',
    feature:
      'Open the file tree beside the conversation, browse any file, and drop a selected snippet straight into your next prompt.',
    points: [
      'A full file browser paired with the agent chat',
      'Select code and add it to the prompt in one move',
    ],
    contrast: 'Instead of copy-pasting between an editor and the agent',
  },  
  {
    Demo: DemoTerminal,
    capability: 'A real terminal, beside the agent',
    feature:
      'Run commands, tail logs, and watch a build in a live terminal that sits right next to the chat, on the same machine the agent uses.',
    points: [
      'Full terminal access without leaving the session',
      'Keep tests, servers, and logs running while the agent works',
    ],
    contrast: 'Instead of switching windows to see what actually happened',
  },  
  {
    Demo: DemoDiff,
    capability: 'Review what each agent did',
    feature:
      'Review every change as an inline git diff with word-level highlights, then flip to the files it touched or the terminal it ran, all in one view.',
    points: [
      'Per-file diffs and commit history',
      'Switch between Changes, Files, and Terminal without leaving the session',
    ],
    contrast: 'Instead of trusting a summary you can’t verify',
  },

  {
    Demo: DemoTasks,
    capability: 'Manage tasks for agents to execute',
    feature:
      'Organize work on a Linear-style task board, then right-click any task and start a session, an agent picks it up and get it done.',
    points: [
      'Board and list views with priorities, labels, and sub-tasks',
      'Right-click → Start a session to kick off Claude, Codex, or OpenCode',
    ],
    contrast: 'Instead of hand-wiring a prompt for every task, and wait for rate limit reset',
  },
  {
    Demo: DemoAutomations,
    capability: 'Put your agents on a schedule',
    feature:
      'Schedule recurring runs so your agents handle the routine work, daily briefing, weekly summary, nightly cleanups, on their own.',
    points: [
      'Cron automations that start sessions even when you don’t',
      'Runs while you’re away and reports back when they’re done',
    ],
    contrast: 'Instead of remembering to kick off every routine job',
  },
];

export function FeatureShowcaseSection({
  heading = 'One workspace for your agents',
  subheading = 'Run every coding agent side by side, review their work, and steer any one of them, from your desk or your phone.',
  features = defaultFeatures,
}: {
  heading?: string;
  subheading?: string;
  features?: Feature[];
} = {}) {
  return (
    <section className="bg-background py-20 sm:py-28 lg:py-32">
      <div className="mx-auto max-w-[85rem] px-4 sm:px-6 lg:px-8">
        <div className="mx-auto mb-16 max-w-3xl text-center sm:mb-24">
          {/* <div className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Everything you need
          </div> */}
          <h2 className="mb-5 text-3xl tracking-tight text-foreground sm:text-4xl lg:text-5xl">
            {heading}
          </h2>
          <p className="text-lg leading-relaxed text-muted-foreground sm:text-xl">
            {subheading}
          </p>
        </div>

        <div className="space-y-20 lg:space-y-28">
          {features.map((item, index) => {
            const isEven = index % 2 === 0;
            const Demo = item.Demo;
            return (
              <div
                key={item.capability}
                className={`flex flex-col ${
                  isEven ? 'lg:flex-row' : 'lg:flex-row-reverse'
                } items-center gap-12 lg:gap-16`}
              >
                {/* Live demo */}
                <div className="w-full lg:w-1/2">
                  <Demo />
                </div>

                {/* Copy: capability leads, then feature → benefit → contrast */}
                <div className="w-full lg:w-1/2">
                  <h3 className="mb-4 text-2xl text-foreground sm:text-3xl lg:text-4xl">
                    {item.capability}
                  </h3>
                  <p className="mb-6 text-base leading-relaxed text-muted-foreground sm:text-lg">
                    {item.feature}
                  </p>
                  <ul className="mb-6 space-y-3">
                    {item.points.map((point) => (
                      <li key={point} className="flex items-start gap-3">
                        <Check className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-500" />
                        <span className="text-muted-foreground">{point}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-sm italic text-muted-foreground/70">{item.contrast}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
