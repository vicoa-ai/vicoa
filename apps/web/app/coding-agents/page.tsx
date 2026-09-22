import Image from 'next/image';
import Link from 'next/link';
import { Check, Clock, Plug, Terminal } from 'lucide-react';

import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { Footer } from '@/components/footer';
import { FAQSection, type FAQItem } from '@/components/faq-section';
import { NavigationHeader } from '@/components/navigation-header';
import { ACP_CATALOG_AGENTS } from '@/lib/acp-catalog-agents';
import { cn } from '@/lib/utils';
import { pageMetadata } from '@/lib/seo';

const PAGE_TITLE = 'Supported AI Coding Agents (40+) - Vicoa';
const PAGE_DESCRIPTION =
  'Vicoa runs 40+ AI coding agents from any device: Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, Kimi, Hermes, Pi, Oh My Pi, and Antigravity built in, plus 30+ more like Cline, goose, Kiro, Qwen Code, and Devin via the Agent Client Protocol.';

export const metadata = pageMetadata('/coding-agents', {
  title: PAGE_TITLE,
  description: PAGE_DESCRIPTION,
  openGraph: {
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    type: 'website'
  },
  twitter: {
    card: 'summary_large_image',
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION
  }
});

// `native` = Vicoa drives the agent through its own SDK / RPC (the deepest
// integration: model + mode pickers, steering mid-turn). `acp` = built in, but
// wired over the Agent Client Protocol the agent's CLI speaks. Both ship with
// Vicoa and start from a new session; the difference is only how deep the
// plumbing goes. Keep in sync with backend/src/protocol/agent_catalog.py.
type IntegrationStatus = 'native' | 'acp' | 'via' | 'soon';

type IntegrationLink = {
  label: string;
  href: string;
};

type Integration = {
  company: string;
  product: string;
  description: string;
  status: IntegrationStatus;
  logoSrc?: string;
  logoAlt?: string;
  logoClassName?: string;
  logoWrapperClassName?: string;
  logoText?: string;
  links?: IntegrationLink[];
};

const statusMeta: Record<IntegrationStatus, { label: string; className: string; icon: typeof Check }> = {
  native: {
    label: 'Native integration',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  acp: {
    label: 'Built in via ACP',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  via: {
    label: 'Supported via Claude Code',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  soon: {
    label: 'Coming soon',
    className: 'border-border bg-muted/40 text-muted-foreground',
    icon: Clock
  }
};

const moreAgentsLink: IntegrationLink = {
  label: 'How to use more agents',
  href: '/docs/agents/more-coding-agents'
};

const integrations: Integration[] = [
  {
    company: 'Anthropic',
    product: 'Claude Code',
    description: 'The default coding agent in Vicoa, with model, thinking, and permission-mode pickers.',
    status: 'native',
    logoSrc: '/images/integrations/claude-color.svg',
    logoAlt: 'Claude logo',
    logoClassName: 'h-8 w-8',
    links: [
      {
        label: 'Get Started',
        href: '/docs/getting-started'
      }
    ]
  },
  {
    company: 'OpenAI',
    product: 'Codex',
    description: 'Start Codex with the `vicoa codex` command, or make it the default agent.',
    status: 'native',
    logoSrc: '/images/integrations/openai.svg',
    logoAlt: 'OpenAI logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [
      {
        label: 'Codex setup guide',
        href: '/docs/agents/codex'
      }
    ]
  },
  {
    company: 'OpenCode',
    product: 'OpenCode',
    description: 'Start OpenCode with `vicoa opencode`, with its own models and build/plan modes.',
    status: 'acp',
    logoSrc: '/images/integrations/opencode.svg',
    logoAlt: 'OpenCode logo',
    logoClassName: 'h-8 w-8',
    links: [
      {
        label: 'OpenCode setup guide',
        href: '/docs/agents/opencode'
      }
    ]
  },
  {
    company: 'Google',
    product: 'Gemini',
    description: 'Start the Gemini CLI directly from a new session in the web dashboard or app.',
    status: 'acp',
    logoSrc: '/images/integrations/gemini-color.svg',
    logoAlt: 'Gemini logo',
    logoClassName: 'h-8 w-8',
    links: [moreAgentsLink]
  },
  {
    company: 'Google',
    product: 'Antigravity',
    description: 'Start the Antigravity CLI (`agy`) from a new session, with Gemini and Claude models to pick from.',
    status: 'native',
    logoSrc: '/images/integrations/antigravity.svg',
    logoAlt: 'Antigravity logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [moreAgentsLink]
  },
  {
    company: 'Cursor',
    product: 'Cursor',
    description: 'Start the Cursor CLI directly from a new session.',
    status: 'acp',
    logoSrc: '/images/integrations/cursor.svg',
    logoAlt: 'Cursor logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [moreAgentsLink]
  },
  {
    company: 'GitHub',
    product: 'Copilot',
    description: 'Start the GitHub Copilot CLI directly from a new session.',
    status: 'acp',
    logoSrc: '/images/integrations/githubcopilot.svg',
    logoAlt: 'GitHub Copilot logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [moreAgentsLink]
  },
  {
    company: 'Moonshot',
    product: 'Kimi',
    description: 'Start the Kimi CLI from a new session, or use Kimi K2 via Claude Code.',
    status: 'acp',
    logoSrc: '/images/integrations/kimi-color.svg',
    logoAlt: 'Kimi logo',
    logoClassName: 'h-8 w-8',
    links: [
      moreAgentsLink,
      {
        label: 'Kimi K2 setup guide',
        href: '/blog/use-claude-code-with-kimi-k2'
      }
    ]
  },
  {
    company: 'Nous Research',
    product: 'Hermes',
    description: 'Start Hermes directly from a new session.',
    status: 'acp',
    logoSrc: '/images/integrations/hermes.svg',
    logoAlt: 'Hermes logo',
    logoClassName: 'h-8 w-8',
    logoWrapperClassName: 'bg-white',
    links: [moreAgentsLink]
  },
  {
    company: 'Earendil',
    product: 'Pi',
    description: 'Start Pi directly from a new session, a native integration like Claude Code and Codex.',
    status: 'native',
    logoSrc: '/images/integrations/pi.svg',
    logoAlt: 'Pi logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [moreAgentsLink]
  },
  {
    company: 'Oh My Pi',
    product: 'Oh My Pi',
    description: 'Start Oh My Pi (`omp`), the Pi fork, from a new session, natively integrated with Vicoa host tools.',
    status: 'native',
    logoSrc: '/images/integrations/omp.svg',
    logoAlt: 'Oh My Pi logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [moreAgentsLink]
  },
  {
    company: 'OpenRouter',
    product: '300+ models',
    description: 'Route Claude Code to 300+ models for cost control and model choice.',
    status: 'via',
    logoSrc: '/images/integrations/openrouter.svg',
    logoAlt: 'OpenRouter logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [
      {
        label: 'OpenRouter setup guide',
        href: '/blog/use-claude-code-with-openrouter'
      }
    ]
  }
];

const codingAgentsFaqs: FAQItem[] = [
  {
    question: 'Which coding agents are supported in Vicoa?',
    answer:
      'Vicoa supports 40+ coding agents. Eleven are built in and start from a new session in the web dashboard, desktop, or mobile app: Claude Code, Codex, OpenCode, Gemini, Antigravity, Cursor, GitHub Copilot, Kimi, Hermes, Pi, and Oh My Pi. 30+ more (Amp, Cline, Devin, Factory Droid, goose, Grok, Junie, Kiro, Mistral Vibe, Qwen Code, TRAE, and others) are supported via the Agent Client Protocol (ACP), and any other ACP agent works with your own launch command.'
  },
  {
    question: 'What does "native" vs "via ACP" mean?',
    answer:
      'Native integrations (Claude Code, Codex, Pi, Oh My Pi, Antigravity) are driven through the agent’s own SDK or RPC, so Vicoa can offer model, thinking, and permission-mode pickers and steer a running turn. ACP agents connect over the Agent Client Protocol, an open standard many agent CLIs already speak; the agent reports its own models and modes once a session starts. Either way the agent runs on your machine and every session syncs across desktop, web, and mobile.'
  },
  {
    question: 'How do I add one of the 30+ ACP agents?',
    answer: (
      <span>
        In the app, open Settings → Providers → More agents and click Add, or run{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-sm">vicoa provider add cline</code> on the machine that
        runs your agents. Vicoa writes the launch command; agents distributed through npx or uvx download on the first
        session, others need their CLI installed first. Run{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-sm">vicoa provider check &lt;id&gt;</code> to confirm it
        works. See the{' '}
        <Link href="/docs/agents/custom-agents" className="text-blue-600 hover:text-blue-700 underline">
          Custom agents
        </Link>{' '}
        guide.
      </span>
    ),
    answerText:
      'In the app, open Settings → Providers → More agents and click Add, or run `vicoa provider add <id>` on the machine that runs your agents. Vicoa writes the launch command; npx/uvx agents download on the first session, others need their CLI installed first. Run `vicoa provider check <id>` to confirm it works. See the Custom agents guide at /docs/agents/custom-agents.'
  },
  {
    question: 'How do I start a session with Codex or OpenCode?',
    answer: (
      <span>
        Launch a session from the CLI with{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-sm">vicoa codex</code> or{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-sm">vicoa opencode</code>. You can also set a default agent in the
        app settings.
      </span>
    ),
    answerText:
      'Launch a session from the CLI with vicoa codex or vicoa opencode. You can also set a default agent in the app settings.'
  },
  {
    question: 'Do I need my own API keys?',
    answer:
      'Yes. Vicoa connects to your own provider credentials so you stay in control of usage and billing for each agent.'
  },
  {
    question: 'How do I use Gemini, Antigravity, Cursor, Copilot, Kimi, Hermes, Pi, or Oh My Pi?',
    answer: (
      <span>
        Update Vicoa to the latest version, install the agent&apos;s
        CLI on your machine, then start a new session from the web or app and pick the agent. See the{' '}
        <Link href="/docs/agents/more-coding-agents" className="text-blue-600 hover:text-blue-700 underline">
          More Coding Agents
        </Link>{' '}
        guide.
      </span>
    ),
    answerText:
      'Update Vicoa to the latest version, install the agent CLI on your machine, then start a new session and pick the agent. See the More Coding Agents guide at /docs/agents/more-coding-agents.'
  },
  {
    question: 'Where can I find setup guides for each agent?',
    answer: (
      <span>
        See the{' '}
        <Link href="/docs/agents/claude-code" className="text-blue-600 hover:text-blue-700 underline">
          Claude Code
        </Link>
        ,{' '}
        <Link href="/docs/agents/codex" className="text-blue-600 hover:text-blue-700 underline">
          Codex
        </Link>
        ,{' '}
        <Link href="/docs/agents/opencode" className="text-blue-600 hover:text-blue-700 underline">
          OpenCode
        </Link>
        ,{' '}
        <Link href="/docs/agents/more-coding-agents" className="text-blue-600 hover:text-blue-700 underline">
          More Coding Agents
        </Link>
        , and{' '}
        <Link href="/docs/agents/custom-agents" className="text-blue-600 hover:text-blue-700 underline">
          Custom agents
        </Link>{' '}
        docs.
      </span>
    ),
    answerText:
      'See the Claude Code, Codex, OpenCode, More Coding Agents, and Custom agents docs under /docs/agents for setup guides.'
  }
];

export default function CodingAgentsPage() {
  return (
    <section className="flex min-h-screen flex-col bg-background text-foreground">
      <NavigationHeader />
      <main className="flex-1 px-6 py-18 sm:px-10 lg:px-16">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
          <div className="mx-auto max-w-4xl space-y-4 text-center">
            <h1 className="text-4xl tracking-tight sm:text-5xl">
              40+ AI Coding Agents, One Workspace
            </h1>
            <p className="text-lg text-muted-foreground">
              Run the coding agents you already use on your own machine, and steer them from your desktop,
              browser, or phone. Eleven are built in, and 30+ more connect through the Agent Client Protocol.
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {integrations.map((integration) => {
              const status = statusMeta[integration.status];
              const StatusIcon = status.icon;

              return (
                <div
                  key={`${integration.company}-${integration.product}`}
                  className="flex h-full flex-col gap-6 rounded-2xl border border-border bg-card/80 p-6 shadow-sm"
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={cn(
                        'flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-muted/40',
                        integration.logoWrapperClassName
                      )}
                    >
                      {integration.logoSrc ? (
                        <Image
                          src={integration.logoSrc}
                          alt={integration.logoAlt ?? integration.product}
                          width={32}
                          height={32}
                          className={cn('h-8 w-8', integration.logoClassName)}
                        />
                      ) : (
                        <span className="text-sm font-semibold text-foreground">
                          {integration.logoText}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-1 flex-wrap items-start justify-between gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">{integration.company}</p>
                        <h2 className="text-xl">{integration.product}</h2>
                      </div>
                      <span
                        className={cn(
                          'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide',
                          status.className
                        )}
                      >
                        <StatusIcon className="h-3.5 w-3.5" />
                        {status.label}
                      </span>
                    </div>
                  </div>

                  <p className="text-sm text-muted-foreground">{integration.description}</p>

                  {integration.links && integration.links.length > 0 ? (
                    <div className="flex flex-wrap gap-3">
                      {integration.links.map((link) => (
                        <Link
                          key={link.href}
                          href={link.href}
                          className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border bg-foreground/10 px-4 py-2 text-xs font-semibold text-foreground transition hover:bg-muted hover:border-foreground"
                        >
                          {link.label}
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          {/* ACP catalog */}
          <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm sm:p-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="max-w-2xl space-y-2">
                <div className="flex items-center gap-2">
                  <Plug className="h-5 w-5 text-muted-foreground" />
                  <h2 className="text-2xl">30+ more agents via ACP</h2>
                </div>
                <p className="text-sm text-muted-foreground">
                  Any agent that speaks the Agent Client Protocol (ACP) plugs straight into Vicoa. Pick one in
                  Settings → Providers → More agents, or run{' '}
                  <code className="rounded bg-muted px-1 py-0.5 text-xs">vicoa provider add &lt;id&gt;</code>, sign
                  in with the agent&apos;s own account, and it behaves like every built-in agent: run it in parallel
                  on its own worktree, steer it from your phone, review its diffs, and get pinged when it needs you.
                </p>
              </div>
              <Link
                href="/docs/agents/custom-agents"
                className="inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-full border border-border bg-foreground/10 px-4 py-2 text-xs font-semibold text-foreground transition hover:bg-muted hover:border-foreground"
              >
                Custom agents guide
              </Link>
            </div>

            <ul className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {ACP_CATALOG_AGENTS.map((agent) => (
                <li
                  key={agent.id}
                  className="flex items-center gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-2.5"
                >
                  {/* The same monochrome mark the app shows in Settings → Providers
                      (public/images/acp/<id>.svg, painted over currentColor). */}
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground/10 text-foreground">
                    <AgentTypeIcon agentTypeName={agent.id} size={18} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-foreground">{agent.name}</span>
                    {agent.by ? (
                      <span className="block truncate text-xs text-muted-foreground">{agent.by}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Bring your own ACP agent */}
          <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card/80 p-6 shadow-sm sm:flex-row sm:items-start sm:gap-6 sm:p-8">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-border bg-muted/40">
              <Terminal className="h-7 w-7 text-foreground" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl">Bring any other ACP agent</h2>
              <p className="text-sm text-muted-foreground">
                Using an agent that isn&apos;t listed? If it speaks ACP, it works too. Give Vicoa its launch command
                in <code className="rounded bg-muted px-1 py-0.5 text-xs">~/.vicoa/config.json</code> and it appears
                as a new agent the next time you start a session, no Vicoa update needed. The same trick runs a
                second profile of any agent with separate credentials, or points one at a proxy.
              </p>
              <Link
                href="/docs/agents/custom-agents#add-an-acp-agent-by-hand"
                className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border bg-foreground/10 px-4 py-2 text-xs font-semibold text-foreground transition hover:bg-muted hover:border-foreground"
              >
                Add an ACP agent by hand
              </Link>
            </div>
          </div>

          <FAQSection
            title="FAQ"
            subtitle="Quick answers about supported agents and setup guide"
            faqs={codingAgentsFaqs}
            idPrefix="coding-agents-faq"
            sectionClassName="py-16 bg-background"
            headerClassName="text-center mb-12"
            titleClassName="text-2xl sm:text-3xl lg:text-4xl font-semibold text-foreground mb-4"
            subtitleClassName="text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto"
          />

          <div className="rounded-2xl border border-border bg-muted/40 px-6 py-5 text-sm text-muted-foreground">
            Using an agent that doesn&apos;t speak ACP yet? Email{' '}
            <Link href="mailto:hi@vicoa.ai" className="cursor-pointer font-semibold text-foreground">
              hi@vicoa.ai
            </Link>{' '}
            with the coding agents you hope to use with Vicoa.
          </div>
        </div>
      </main>
      <Footer />
    </section>
  );
}
