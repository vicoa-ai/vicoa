import Image from 'next/image';
import { Check } from 'lucide-react';

interface Highlight {
  /** Lead with the capability (positioning: capability first, never the feature). */
  capability: string;
  /** The mechanism that delivers it. */
  feature: string;
  /** Concrete, scannable proof points. */
  points: string[];
  /** The competitive anchor: one agent, one machine, or a wall of terminal tabs. */
  contrast: string;
  imageUrl: string;
  imageAlt: string;
}

// Straight from the positioning "Product highlights" table: each row leads with the
// capability, then feature → benefit, mapped against "one agent, one machine."
const highlights: Highlight[] = [
  {
    capability: 'Run a whole fleet in parallel',
    feature:
      'Start Claude Code, Codex, and OpenCode side by side, each on its own git worktree so they never step on each other.',
    points: [
      'Kick off several agents at once and ship many tasks in parallel',
      'Worktree isolation keeps every branch and file change separate',
    ],
    contrast: 'Instead of one agent, one session, serial work',
    imageUrl: '/images/updates/mac-desktop-app-1.png',
    imageAlt: 'The Vicoa desktop app running several coding agent sessions in parallel',
  },
  {
    capability: 'See every agent at a glance',
    feature:
      'One board shows every agent’s live status, so a push notification pulls you straight to whichever one needs you.',
    points: [
      'No tab-juggling, spot the blocked or finished agent instantly',
      'Get notified the moment an agent needs input or completes a task',
    ],
    contrast: 'Instead of flipping between terminal tabs, hunting for who’s stuck',
    imageUrl: '/images/features/overall-with-file-tree.png',
    imageAlt: 'Vicoa workspace showing multiple agent sessions with live status and a file tree',
  },
  {
    capability: 'Steer any agent from any device',
    feature:
      'Approve a change, answer an agent’s question, or redirect it with one tap, from your phone, the web, or your desktop.',
    points: [
      'One-tap approvals and AskUserQuestion answers wherever you are',
      'Voice-to-code for hands-free prompting on the go',
    ],
    contrast: 'Instead of an agent sitting blocked while you’re away',
    imageUrl: '/images/updates/start-sessions-anywhere-1.png',
    imageAlt: 'Starting and steering a coding agent session from the Vicoa mobile app',
  },
  {
    capability: 'Put the fleet on a schedule',
    feature:
      'Plan work on a task board, start a session straight from a task, and schedule recurring automations.',
    points: [
      'Board and list views with labels, sub-tasks, and start-a-session-from-a-task',
      'Cron automations run agents even when you don’t kick them off',
    ],
    contrast: 'Instead of manually starting every run',
    imageUrl: '/images/features/automation.webp',
    imageAlt: 'Vicoa Automations scheduling a recurring coding agent run',
  },
  {
    capability: 'See and judge what each agent did',
    feature:
      'Review every change as an inline git diff, step through commit history, and edit files in place, no separate editor.',
    points: [
      'Files and Changes panels with per-file diffs and commit graph',
      'Diffs come to mobile too, so you can review and redirect from anywhere',
    ],
    contrast: 'Instead of not being able to judge anything from a phone terminal',
    imageUrl: '/images/features/FileChanges.webp',
    imageAlt: 'Reviewing an agent’s file changes and git diffs in Vicoa',
  },
  {
    capability: 'Every agent you use, one workspace',
    feature:
      'Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, plus 300+ models via OpenRouter. Bring your own key.',
    points: [
      'Everything runs on your real machine and codebase, no lock-in, no usage markup',
      'Swap the agent or model mid-session without leaving Vicoa',
    ],
    contrast: 'Instead of a single-agent, GitHub-only first-party app',
    imageUrl: '/images/updates/opencode-support-1.png',
    imageAlt: 'Vicoa running OpenCode alongside Claude Code and Codex',
  },
];

export function ProductHighlightsSection() {
  return (
    <section className="py-16 sm:py-20 lg:py-24 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16 sm:mb-20">
          <div className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">
            Everything you need to run a team of agents
          </div>
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-4">
            One workspace for your whole fleet
          </h2>
          <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-3xl mx-auto">
            Set them up on your desktop, watch them on one board, and steer any one of them
            from any device.
          </p>
        </div>

        <div className="space-y-20 lg:space-y-28">
          {highlights.map((item, index) => {
            const isEven = index % 2 === 0;
            return (
              <div
                key={item.capability}
                className={`flex flex-col ${
                  isEven ? 'lg:flex-row' : 'lg:flex-row-reverse'
                } gap-10 lg:gap-20 items-center`}
              >
                {/* Screenshot */}
                <div className="w-full lg:w-1/2">
                  <div className="relative rounded-xl overflow-hidden shadow-xl border border-border">
                    <Image
                      src={item.imageUrl}
                      alt={item.imageAlt}
                      width={1200}
                      height={800}
                      sizes="(max-width: 1024px) 100vw, 50vw"
                      className="w-full h-auto"
                      priority={index < 1}
                    />
                  </div>
                </div>

                {/* Copy column: capability leads, then feature → benefit → contrast */}
                <div className="w-full lg:w-1/2">
                  <h3 className="text-2xl sm:text-3xl lg:text-4xl text-foreground mb-4">
                    {item.capability}
                  </h3>
                  <p className="text-base sm:text-lg text-muted-foreground mb-6 leading-relaxed">
                    {item.feature}
                  </p>
                  <ul className="space-y-3 mb-6">
                    {item.points.map((point) => (
                      <li key={point} className="flex items-start gap-3">
                        <Check className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">{point}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-sm text-muted-foreground/70 italic">
                    {item.contrast}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
