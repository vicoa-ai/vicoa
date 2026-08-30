import Image from 'next/image';
import Link from 'next/link';
import { Check, Clock } from 'lucide-react';

import { Footer } from '@/components/footer';
import { FAQSection, type FAQItem } from '@/components/faq-section';
import { NavigationHeader } from '@/components/navigation-header';
import { cn } from '@/lib/utils';
import { pageMetadata } from '@/lib/seo';

export const metadata = pageMetadata('/coding-agents', {
  title: 'Supported AI Coding Agents - Vicoa',
  description:
    'Explore the supported AI coding agents in Vicoa, including Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, Kimi, Hermes, and more.',
  openGraph: {
    title: 'Supported AI Coding Agents - Vicoa',
    description:
      'Explore the supported AI coding agents in Vicoa, including Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, Kimi, Hermes, and more.',
    type: 'website'
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Supported AI Coding Agents - Vicoa',
    description:
      'Explore the supported AI coding agents in Vicoa, including Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, Kimi, Hermes, and more.'
  }
});

type IntegrationStatus = 'default' | 'supported' | 'via' | 'viaOpencode' | 'newSession' | 'soon';

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
  default: {
    label: 'Supported by default',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  supported: {
    label: 'Supported',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  via: {
    label: 'Supported via Claude Code',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  viaOpencode: {
    label: 'Supported via OpenCode',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  newSession: {
    label: 'Start from a new session',
    className: 'border-foreground/50 bg-transparent',
    icon: Check
  },
  soon: {
    label: 'Coming soon',
    className: 'border-border bg-muted/40 text-muted-foreground',
    icon: Clock
  }
};

const integrations: Integration[] = [
  {
    company: 'Anthropic',
    product: 'Claude Code',
    description: 'The default coding agent supported by Vicoa.',
    status: 'supported',
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
    description: 'Start Codex with `vicoa codex` command or set default to Codex easily.',
    status: 'supported',
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
    description: 'Use OpenCode as a supported coding agent in Vicoa.',
    status: 'supported',
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
    description: 'Start Gemini directly from a new session in the web dashboard or app.',
    status: 'newSession',
    logoSrc: '/images/integrations/gemini-color.svg',
    logoAlt: 'Gemini logo',
    logoClassName: 'h-8 w-8',
    links: [
      {
        label: 'How to use more agents',
        href: '/docs/agents/more-coding-agents'
      }
    ]
  },
  {
    company: 'Cursor',
    product: 'Cursor',
    description: 'Start the Cursor CLI directly from a new session.',
    status: 'newSession',
    logoSrc: '/images/integrations/cursor.svg',
    logoAlt: 'Cursor logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [
      {
        label: 'How to use more agents',
        href: '/docs/agents/more-coding-agents'
      }
    ]
  },
  {
    company: 'GitHub',
    product: 'Copilot',
    description: 'Start the GitHub Copilot CLI directly from a new session.',
    status: 'newSession',
    logoSrc: '/images/integrations/githubcopilot.svg',
    logoAlt: 'GitHub Copilot logo',
    logoClassName: 'h-8 w-8 dark:invert',
    links: [
      {
        label: 'How to use more agents',
        href: '/docs/agents/more-coding-agents'
      }
    ]
  },
  {
    company: 'Moonshot',
    product: 'Kimi',
    description: 'Start the Kimi CLI from a new session, or use Kimi K2 via Claude Code.',
    status: 'newSession',
    logoSrc: '/images/integrations/kimi-color.svg',
    logoAlt: 'Kimi logo',
    logoClassName: 'h-8 w-8',
    links: [
      {
        label: 'How to use more agents',
        href: '/docs/agents/more-coding-agents'
      },
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
    status: 'newSession',
    logoSrc: '/images/integrations/hermes.svg',
    logoAlt: 'Hermes logo',
    logoClassName: 'h-8 w-8',
    logoWrapperClassName: 'bg-white',
    links: [
      {
        label: 'How to use more agents',
        href: '/docs/agents/more-coding-agents'
      }
    ]
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
      'Vicoa supports Claude Code, Codex, and OpenCode as built-in agents. You can also start Gemini, Cursor, Copilot, Kimi, and Hermes directly from a new session in the web dashboard or mobile app.'
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
    question: 'How do I use Gemini, Cursor, Copilot, Kimi, or Hermes?',
    answer: (
      <span>
        Update Vicoa CLI to v1.6.1+ and the app to v1.6.8+, install the agent&apos;s CLI on your machine, then start a new
        session from the web or app and pick the agent. See the{' '}
        <Link href="/docs/agents/more-coding-agents" className="text-blue-600 hover:text-blue-700 underline">
          More Coding Agents
        </Link>{' '}
        guide.
      </span>
    ),
    answerText:
      'Update Vicoa CLI to v1.6.1+ and the app to v1.6.8+, install the agent CLI on your machine, then start a new session and pick the agent. See the More Coding Agents guide at /docs/agents/more-coding-agents.'
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
        , and{' '}
        <Link href="/docs/agents/opencode" className="text-blue-600 hover:text-blue-700 underline">
          OpenCode
        </Link>
        , and{' '}
        <Link href="/docs/agents/more-coding-agents" className="text-blue-600 hover:text-blue-700 underline">
          More Coding Agents
        </Link>{' '}
        docs.
      </span>
    ),
    answerText:
      'See the Claude Code, Codex, OpenCode, and More Coding Agents docs under /docs/agents for setup guides.'
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
              Supported AI Coding Agents
            </h1>
            <p className="text-lg text-muted-foreground">
              Vicoa connects the best AI coding agents, allowing you to use them on your phone easily on the go.
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
                          className="inline-flex items-center gap-2 rounded-full border border-border bg-foreground/10 px-4 py-2 text-xs font-semibold text-foreground transition hover:bg-muted hover:border-foreground"
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
            Want another integration sooner? Email{' '}
            <Link href="mailto:hi@vicoa.ai" className="font-semibold text-foreground">
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
