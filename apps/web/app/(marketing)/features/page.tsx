import { Metadata } from 'next';
import Image from 'next/image';
import {
  ListChecks,
  CalendarClock,
  Search,
  SquarePen,
  SquareTerminal,
  Gauge,
  Paperclip,
  StopCircle,
  MessageSquare,
  Navigation,
  Share2,
  Globe,
} from 'lucide-react';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/features', {
  title: 'Features | Vicoa: Run A Team of Coding Agents',
  description:
    'Run Claude Code, Codex, and OpenCode in parallel — each on its own git worktree — and steer them from any device. Explore Vicoa features: parallel agents, the desktop app, Tasks, Automations, file mentions, slash commands, voice dictation, and cross-device workflows.',
  openGraph: {
    title: 'Features | Vicoa: Run A Team of Coding Agents',
    description:
      'Run Claude Code, Codex, and OpenCode in parallel — each on its own git worktree — and steer them from any device. Parallel agents, the desktop app, Tasks, Automations, and more.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Features | Vicoa: Run A Team of Coding Agents',
    description:
      'Run Claude Code, Codex, and OpenCode in parallel — each on its own git worktree — and steer them from any device. Parallel agents, the desktop app, Tasks, Automations, and more.',
  },
});

interface Feature {
  title: string;
  description: string;
  details: string[];
  imageUrl: string;
  imageAlt: string;
}

interface CardFeature {
  icon: React.ReactNode;
  title: string;
  description: string;
  details: string[];
}

const features: Feature[] = [
  {
    title: 'Run a Team of Coding Agents in Parallel',
    description: 'Run Claude Code, Codex, and OpenCode side by side — each on its own git worktree — and watch every agent on one board.',
    details: [
      'Start several agents at once, each in its own git worktree so they never step on each other',
      'See every agent’s live status on a single board instead of juggling terminal tabs',
      'Set up and run the fleet from the desktop app — install, sign in, agents auto-detected'
    ],
    imageUrl: '/images/updates/mac-desktop-app-1.png',
    imageAlt: 'The Vicoa desktop app running coding agent sessions in parallel on macOS'
  },
  {
    title: 'Start at Your Desk, Steer from Any Device',
    description: 'Launch sessions from web, mobile, or desktop, and jump in the moment an agent needs you.',
    details: [
      'Start new Claude Code or Codex sessions from your phone, browser, or the desktop app',
      'Get a push notification the moment an agent needs input or finishes a task',
      'Approve changes and answer AskUserQuestion prompts with one tap, wherever you are'
    ],
    imageUrl: '/images/updates/start-sessions-anywhere-1.png',
    imageAlt: 'Starting a new coding agent session from the Vicoa mobile app'
  },
  {
    title: 'Every Coding Agent, One Workspace',
    description: 'Claude Code, Codex, OpenCode, and more — plus 300+ models from 60+ providers via OpenRouter.',
    details: [
      'Run Claude Code, Codex, and OpenCode, plus Gemini, Cursor, Copilot, Kimi, and Hermes via ACP',
      'Use 300+ models from 60+ providers through OpenRouter, and bring your own key',
      'Everything runs on your real machine and codebase — no lock-in, no usage markup'
    ],
    imageUrl: '/images/updates/opencode-support-1.png',
    imageAlt: 'Vicoa running OpenCode alongside Claude Code and Codex'
  },
  {
    title: 'Fuzzy Search for Files with @',
    description: 'Fuzzy search for files with @ in projects across web, mobile, desktop, and CLI.',
    details: [
      'Type @ followed by a file path to mention files in your messages',
      'Reference multiple files in a single message',
      'Give Claude Code and Codex immediate context from a live file index'
    ],
    imageUrl: 'https://embed.filekitcdn.com/e/tvBWeG7eCzTLX9Y3bLY1NY/rBDHJ4cbzh2wB9o2Fp5PjM',
    imageAlt: 'Fuzzy search for files with @ symbol in Vicoa'
  },
  {
    title: 'Slash Commands',
    description: 'Access powerful commands quickly by typing "/" in the chat interface.',
    details: [
      'Built-in Claude Code and Codex slash commands',
      'Custom commands from ~/.claude/commands, including subfolders and project .claude',
      'Quick access to frequently used workflows'
    ],
    imageUrl: 'https://embed.filekitcdn.com/e/tvBWeG7eCzTLX9Y3bLY1NY/98MVFz34QZ2uFdcvNaKSDE/email',
    imageAlt: 'Slash commands in Vicoa'
  },
  {
    title: 'Permission Modes & Thinking Toggle',
    description: 'Switch between permission modes and thinking status.',
    details: [
      'Permission modes: default, plan mode, accept edits, auto, and bypass permissions (YOLO)',
      'Toggle thinking on/off and change the model, effort, and permission mode mid-session'
    ],
    imageUrl: '/images/features/Bypass-Permission.webp',
    imageAlt: 'Permission modes and thinking toggle in Vicoa'
  },
  {
    title: 'Live Preview on Your Phone',
    description: 'Map your local dev server to a URL you can open in the app and watch your site change as your agent works.',
    details: [
      'Open your localhost in the Vicoa app while an agent codes',
      'Preview in both phone and desktop viewports',
      'See changes land in real time without leaving your chair — or your couch'
    ],
    imageUrl: '/images/updates/live-preview-1.png',
    imageAlt: 'Vicoa Live Preview showing a local website in phone and desktop viewports'
  },
  {
    title: 'Review Changes: Diffs & Commit History',
    description: 'See what every agent changed in Git diff format, then step through commit history.',
    details: [
      'Browse the Files and Changes panels with inline, per-file git diffs',
      'Step through commit history — commit graph, file list, and diffs — in the desktop app',
      'Review changes on mobile or web, then redirect without a separate editor'
    ],
    imageUrl: '/images/features/FileChanges.webp',
    imageAlt: 'Reviewing file changes and git diffs in Vicoa'
  },
  {
    title: 'Talk to Code (Dictation)',
    description: 'Convert your voice to text for hands-free coding on mobile.',
    details: [
      'Tap the microphone icon to speak your message',
      'Voice converts to text instantly, with improved accuracy',
      'Edit transcribed text before sending'
    ],
    imageUrl: '/images/features/Voice.webp',
    imageAlt: 'Voice dictation in Vicoa'
  },
  {
    title: 'Session Organization',
    description: 'Rename sessions, group by project or worktree, and find them fast with filtering.',
    details: [
      'Rename and pin sessions for easy identification',
      'Group sessions by project or git worktree',
      'Filter by agent (Claude Code, Codex, and more), status, and date range'
    ],
    imageUrl: 'https://embed.filekitcdn.com/e/tvBWeG7eCzTLX9Y3bLY1NY/4NJf6qcR9VLqnMQ7fdoNYM/email',
    imageAlt: 'Session organization in Vicoa'
  }
];

const cardFeatures: CardFeature[] = [
  {
    icon: <ListChecks className="h-8 w-8" />,
    title: 'Tasks',
    description: 'Plan work on a board or list, then hand it to an agent.',
    details: [
      'Board and list views with labels and sub-tasks',
      'Start a session from a task with your first prompt seeded',
      'Linked task status follows the session it spawned'
    ]
  },
  {
    icon: <CalendarClock className="h-8 w-8" />,
    title: 'Automations',
    description: 'Schedule recurring agent runs so work happens without you.',
    details: [
      'Set a frequency and let agents run on a schedule',
      'Run now on demand and jump straight to the spawned session',
      'Review run history and toggle automations on or off'
    ]
  },
  {
    icon: <Search className="h-8 w-8" />,
    title: 'Workspace Search (⌘K)',
    description: 'Jump to any session, project, or command from one palette.',
    details: [
      'Open the command palette with ⌘K',
      'Search across your whole workspace in an instant',
      'A commands tier for quick actions'
    ]
  },
  {
    icon: <SquarePen className="h-8 w-8" />,
    title: 'Edit Files in Place',
    description: 'Open and edit files in the Files panel, not just preview them.',
    details: [
      'In-place editing with syntax highlighting',
      'A conflict check guards against overwriting agent changes',
      'Review and tweak without a separate editor'
    ]
  },
  {
    icon: <SquareTerminal className="h-8 w-8" />,
    title: 'Built-in Terminals',
    description: 'Run terminals on your machine, remotely, or in the browser.',
    details: [
      'Multi-terminal tabs with keep-alive sessions',
      'Open terminals on remote machines over the relay',
      'Web terminals restore across restarts'
    ]
  },
  {
    icon: <Gauge className="h-8 w-8" />,
    title: 'Usage at a Glance',
    description: 'See how much context and rate limit a session has left.',
    details: [
      'Context-window usage surfaced for Claude sessions',
      'Rate-limit usage shown inline in chat',
      'Know when an agent is near its limits'
    ]
  },
  {
    icon: <Paperclip className="h-8 w-8" />,
    title: 'Image & File Attachments',
    description: 'Send screenshots and attach files to any agent.',
    details: [
      'Attach and render images in chat',
      'Upload arbitrary files alongside images',
      'Delivered to headless Claude, Codex, and ACP agents'
    ]
  },
  {
    icon: <StopCircle className="h-8 w-8" />,
    title: 'Interrupt Anytime',
    description: 'Stop a running agent at any time with a single tap.',
    details: [
      'The send button becomes Stop while a turn runs',
      'Change direction mid-execution',
      'Provide additional context when needed'
    ]
  },
  {
    icon: <MessageSquare className="h-8 w-8" />,
    title: 'Draft & Queued Messages',
    description: 'Never lose a prompt, and line up your next ones.',
    details: [
      'Unfinished prompts save automatically as drafts',
      'Queue messages while an agent is busy',
      'Cancel a queued message before it sends'
    ]
  },
  {
    icon: <Navigation className="h-8 w-8" />,
    title: 'Unseen-Message Navigation',
    description: 'Never lose your place in long conversations.',
    details: [
      'One tap to jump to unseen messages',
      'One tap to scroll to the latest messages',
      'Group sub-agent activity under a collapsible header'
    ]
  },
  {
    icon: <Share2 className="h-8 w-8" />,
    title: 'Share & Export Messages',
    description: 'Copy individual or multiple messages to share with others.',
    details: [
      'Long-press a message to select it',
      'Select and copy multiple messages',
      'Export a conversation to share'
    ]
  },
  {
    icon: <Globe className="h-8 w-8" />,
    title: 'Cross-Device Workflow',
    description: 'Real-time sync across all your devices over WebSocket.',
    details: [
      'Start on laptop or desktop, continue on mobile',
      'Instant message delivery and session events',
      'Alerts when an agent needs your input'
    ]
  }
];

export default function FeaturesPage() {
  return (
    <div className="bg-background">
      {/* Header */}
      <div className="bg-muted/30">
        <div className="container mx-auto px-4 py-16 max-w-7xl text-center">
          <h1 className="text-4xl md:text-5xl mb-4">Features</h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Vicoa features for running coding agents like Claude Code, Codex, OpenCode, and more running in parallel.
          </p>
        </div>
      </div>

      {/* Features - Interleaved Layout */}
      <div className="container mx-auto px-4 py-16 max-w-7xl">
        <div className="space-y-24">
          {features.map((feature, index) => {
            const isEven = index % 2 === 0;
            return (
              <div
                key={index}
                className={`flex flex-col ${isEven ? 'lg:flex-row' : 'lg:flex-row-reverse'} gap-12 lg:gap-20 items-center`}
              >
                {/* Image */}
                <div className="w-full lg:w-5/12">
                  <div className="relative rounded-lg overflow-hidden shadow-xl border border-border max-w-md mx-auto">
                    <Image
                      src={feature.imageUrl}
                      alt={feature.imageAlt}
                      width={600}
                      height={450}
                      sizes="(max-width: 768px) 100vw, (max-width: 1024px) 50vw, 448px"
                      className="w-full h-auto"
                      priority={index < 2}
                    />
                  </div>
                </div>

                {/* Content */}
                <div className="w-full lg:w-7/12">
                  <h2 className="text-3xl md:text-4xl mb-4">
                    {feature.title}
                  </h2>
                  <p className="text-lg text-muted-foreground mb-6">
                    {feature.description}
                  </p>
                  <ul className="space-y-3">
                    {feature.details.map((detail, detailIndex) => (
                      <li key={detailIndex} className="flex items-start">
                        <svg
                          className="h-6 w-6 text-blue-500 mr-3 flex-shrink-0"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                        <span className="text-muted-foreground">{detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Additional Features - Card Layout */}
      <div className="bg-muted/30 py-32 pb-32">
        <div className="container mx-auto px-4 max-w-7xl">
          <h2 className="text-3xl md:text-4xl mb-12 text-center">
            More Features
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {cardFeatures.map((feature, index) => (
              <div
                key={index}
                className="border border-border rounded-lg p-6 hover:shadow-lg transition-shadow bg-card"
              >
                <div className="flex items-start space-x-4">
                  <div className="flex-shrink-0 text-primary">
                    {feature.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl mb-2">{feature.title}</h3>
                    <p className="text-muted-foreground mb-4">{feature.description}</p>
                    <ul className="space-y-2">
                      {feature.details.map((detail, detailIndex) => (
                        <li key={detailIndex} className="text-sm text-muted-foreground flex items-start">
                          <span className="mr-2">•</span>
                          <span>{detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="border-t border-border bg-muted/30">
        <div className="container mx-auto px-4 py-16 max-w-7xl text-center">
          <h2 className="text-3xl md:text-4xl mb-4">
            Ready to Run a Team of Coding Agents?
          </h2>
          <p className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto">
            Get started with Vicoa and run coding agents in parallel.
          </p>
          <div className="flex justify-center">
            <a
              href="/download"
              className="inline-flex items-center justify-center px-6 py-3 border border-gray-400 text-base font-medium rounded-md text-black bg-white shadow-sm hover:bg-gray-100 hover:border-gray-600 transition-colors"
            >
              Download for macOS
            </a>
          </div>
        </div>
      </div>

    </div>
  );
}
