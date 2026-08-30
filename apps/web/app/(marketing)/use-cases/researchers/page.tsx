import { Metadata } from 'next';
import { Server, Cloud, Monitor, Check } from 'lucide-react';
import { pageMetadata, SITE_URL } from '@/lib/seo';
import { PostHogPageEvent } from '@/components/posthog-page-event';

// Reused landing sections (parameterized with researcher copy where needed).
import { HeroSection } from '@/components/landing/sections/hero-section';
import { DynamicPhrase } from '@/components/landing/sections/dynamic-phrase';
import {
  FeatureShowcaseSection,
  type Feature,
} from '@/components/landing/sections/feature-showcase-section';
import {
  HowItWorksSection,
  defaultSteps,
  type Step,
} from '@/components/landing/sections/how-it-works-section';
import { ScreenshotGallerySection } from '@/components/landing/sections/screenshot-gallery-section';
import {
  TestimonialsSection,
  type Testimonial,
} from '@/components/landing/sections/testimonials-section';
import { FeaturedSection } from '@/components/landing/sections/featured-section';
import { CTASection } from '@/components/landing/sections/cta-section';
import { FAQSection as BaseFAQSection } from '@/components/faq-section';

// Live feature demos (reused verbatim; only the surrounding copy changes).
import {
  DemoMachines,
  DemoSteer,
  DemoFleet,
  DemoTerminal,
  DemoDiff,
  DemoFiles,
} from '@/components/landing/feature-demos';

const PATH = '/use-cases/researchers';
const TITLE = 'Vicoa for Researchers: Run Coding Agents on Your GPU Server';
const DESCRIPTION =
  "Run Claude Code, Codex, or OpenCode on your remote GPU server or lab cluster and steer them from your laptop or phone. Built for ML researchers, PhD and master's students, and data scientists who run experiments on remote servers. No more SSH round-trips.";
const OG_IMAGE = '/images/hero.png';

export const metadata: Metadata = pageMetadata(PATH, {
  title: `${TITLE} | Vicoa`,
  description: DESCRIPTION,
  keywords: [
    'AI coding agent for researchers',
    'run Claude Code on remote GPU server',
    'control ML experiments from phone',
    'SSH tmux alternative for coding agents',
    'Claude Code for PhD students',
    'remote coding agent lab cluster',
  ],
  openGraph: {
    title: `${TITLE} | Vicoa`,
    description: DESCRIPTION,
    type: 'website',
    images: [{ url: OG_IMAGE, alt: 'Driving a coding agent on a remote GPU server with Vicoa' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: `${TITLE} | Vicoa`,
    description: DESCRIPTION,
    images: [OG_IMAGE],
  },
});

// Rotating phrase after "Run a team of coding agents", tuned for researchers.
const HERO_PHRASES = [
  'on your GPU server',
  'from your phone',
  'on the GPU cluster',
  'on a cloud VM',
  'from anywhere',
  'on your commute',
  'while the GPUs run',
  'from the lab',
];

// Same demos as the homepage, reordered + reworded for remote-compute work.
const RESEARCHER_FEATURES: Feature[] = [
  {
    Demo: DemoMachines,
    capability: 'Drive the server your GPUs run on',
    feature:
      'Connect your GPU server, cluster nodes, or a cloud VM and drive the agents running on it through Vicoa. No SSH gymnastics, no VNC round-trip.',
    points: [
      'Your code and checkpoints stay on your own server',
      'Reach every machine from your phone, laptop, or the web',
    ],
    contrast: 'Instead of SSH in every time you want to check a run',
  },
  {
    Demo: DemoSteer,
    capability: 'Steer agents from your phone',
    feature:
      'Pick up the exact same session on your phone, approve a step, or redirect the agent, and it syncs everywhere instantly.',
    points: [
      'Approve the risky or expensive step from anywhere',
      'Catch a broken run at 6pm, even when you are not at your desk',
    ],
    contrast: 'Instead of being chained to the terminal at your desk',
  },
  {
    Demo: DemoFleet,
    capability: 'Agent team for parallel idea validation',
    feature:
      'Run several agents at once: one tries a new approach, another runs an experiment, another digs into the analysis.',
    points: [
      'Explore several ideas at once, each isolated on its own branch',
      'See which agent is running, blocked, or done at a glance',
    ],
    contrast: 'Instead of one agent, one idea, one experiment at a time',
  },
  {
    Demo: DemoFiles,
    capability: 'Analyze your results',
    feature:
      'Open the file tree beside the conversation to inspect logs, metrics, checkpoints, and plots, then ask the agent to dig into what they show.',
    points: [
      'Browse outputs and artifacts without a separate transfer',
      'Point the agent at a result and have it take the next step',
    ],
    contrast: 'Instead of scp-ing files back just to look at them',
  },
  {
    Demo: DemoDiff,
    capability: 'Review what the agent changed',
    feature:
      'Review every change as an inline git diff with word-level highlights, then flip to the files it touched or the terminal it ran, all in one view.',
    points: [
      'Per-file diffs and commit history',
      'Verify the change instead of trusting a summary you can’t check',
    ],
    contrast: 'Instead of trusting a summary you can’t verify',
  },
  {
    Demo: DemoTerminal,
    capability: 'A real terminal, on the server',
    feature:
      'Run commands, tail training logs, and watch a job in a live terminal on the same machine the agent uses.',
    points: [
      'Full shell access without leaving the session',
      'Keep jobs, servers, and logs running while the agent works',
    ],
    contrast: 'Instead of juggling a second stack of SSH tabs',
  },
];

// Reuse the homepage's three-step visuals; only the wording changes.
const RESEARCHER_STEPS: Step[] = defaultSteps.map((step) => {
  if (step.number === '01') {
    return {
      ...step,
      title: 'Install on your server',
      description:
        'Install the Vicoa CLI on your lab server or cloud VM and sign in, and it auto-detects Claude Code, Codex, or OpenCode.',
    };
  }
  if (step.number === '02') {
    return {
      ...step,
      title: 'Run experiments in parallel',
      description:
        'Start agents on the server, each on its own git worktree, and see every session in one workspace.',
    };
  }
  return {
    ...step,
    description:
      'Grab the mobile app to approve, redirect, and answer questions from anywhere.',
  };
});

// Where Vicoa runs (three environments) for the setup section.
const ENVIRONMENTS: { icon: typeof Server; title: string; body: string }[] = [
  {
    icon: Server,
    title: 'Lab & cluster',
    body: 'Your lab’s GPU server, or a node on the cluster.',
  },
  {
    icon: Cloud,
    title: 'Cloud VMs',
    body: 'Lambda, RunPod, Vast.ai, AWS, GCP, or Azure.',
  },
  {
    icon: Monitor,
    title: 'Your own hardware',
    body: 'A workstation or desktop at home.',
  },
];

const AUDIENCES: { title: string; body: string }[] = [
  {
    title: 'ML & AI researchers',
    body: 'Training runs, evals, and demos on a remote GPU server, kicked off and steered without living in a terminal.',
  },
  {
    title: 'PhD & master’s students',
    body: 'Your experiments run on the lab cluster or a cloud VM; check on them and nudge them between classes, from any device.',
  },
  {
    title: 'Data scientists',
    body: 'Iterate on pipelines and models where the data and compute already are, and review the agent’s changes easily.',
  },
  {
    title: 'Labs & PIs',
    body: 'Equip the whole lab. When your students run more experiments and spend less time babysitting them, your lab produces more.',
  },
];

// Researcher-flavored testimonials.
const RESEARCHER_TESTIMONIALS: Testimonial[] = [
  {
    text: 'I kick off three experiments before my morning meeting and check them from my phone between talks. I used to lose time and momentum just SSH back and forth.',
    author: 'Lena Ortiz',
    role: 'Postdoc, Computer Vision',
  },
  {
    text: 'Half my agents explore new ideas while the others crunch the analysis. It feels like a small lab team running on one server.',
    author: 'Arjun Mehta',
    role: 'PhD Candidate, NLP',
  },
  {
    text: 'Getting pinged when a run finishes or needs input changed everything. No more babysitting a terminal at 2am.',
    author: 'Sofia Ricci',
    role: 'ML Research Engineer',
  },
  {
    text: 'A training run started to diverge while I was out. I caught it from my phone, redirected the agent, and saved a whole night of GPU time.',
    author: 'Daniel Kim',
    role: 'PhD Student, Reinforcement Learning',
  },
  {
    text: 'Our datasets are too big to move, so I run the agent right where the data lives and drive it from my laptop, with no local setup and no data copies.',
    author: 'Priya Nair',
    role: 'Data Scientist',
  },
  {
    text: 'I review each agent’s changes as a real git diff instead of a summary, so I know exactly what produced every result.',
    author: 'Marco Bianchi',
    role: 'Research Scientist',
  },
];

const FAQS = [
  {
    question: 'Does my code leave my machine?',
    answer:
      'No. The coding agent runs on your own machine or server, so your code and checkpoints stay exactly where they already are. Vicoa relays your prompts and the agent’s output through a secure relay so you can drive that machine from another device. It relays the conversation, not your codebase.',
  },
  {
    question: 'Which coding agents and models does Vicoa support?',
    answer:
      'Claude Code, Codex, and OpenCode, plus Gemini, Cursor, and 300+ models via OpenRouter. Bring your own subscription or API key. Vicoa does not resell model access, so you keep using the models you already pay for.',
  },
  {
    question: 'Do I have to keep my laptop open?',
    answer:
      'No. The agent runs on your remote server or VM, so it keeps working after you close your laptop. You check in and steer it from your laptop, phone, or tablet whenever you like.',
  },
  {
    question: 'Does it work with my university’s cluster?',
    answer:
      'It works best on a machine where you can keep a process alive: a dedicated lab server, a cloud VM, or an interactive cluster allocation.',
  },
  {
    question: 'Can my labmates join a session?',
    answer:
      'Yes. You can share a running session so labmate can follow along and review the agent’s work, which is useful for feedback before anything lands.',
  },
  {
    question: 'Is Vicoa free to use?',
    answer:
      'Vicoa offers a free tier to get started, and you bring your own agent key, so there is no model cost added on top. For heavier use and advanced features, check the pricing page.',
  },
];

export default function ResearchersUseCasePage() {
  const url = `${SITE_URL}${PATH}`;

  const jsonLd: Record<string, unknown>[] = [
    {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: TITLE,
      description: DESCRIPTION,
      image: `${SITE_URL}${OG_IMAGE}`,
      publisher: {
        '@type': 'Organization',
        name: 'Vicoa',
        logo: { '@type': 'ImageObject', url: `${SITE_URL}/images/vicoa-light.png` },
      },
      mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'Use cases', item: `${SITE_URL}/use-cases` },
        { '@type': 'ListItem', position: 3, name: 'Researchers', item: url },
      ],
    },
  ];

  return (
    <>
      {jsonLd.map((node, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(node) }}
        />
      ))}

      <main>
        <PostHogPageEvent event="use_case_researchers_viewed" />

        <HeroSection
          title={
            <>
              Run a team of coding agents
              <br />
              <DynamicPhrase phrases={HERO_PHRASES} />
            </>
          }
          subtitle={
            <>
              Claude Code, Codex, and OpenCode, running where your GPUs are.
              <br />
              Start them at your desk, steer them from your phone.
            </>
          }
        />

        <FeatureShowcaseSection
          heading="One workspace for your experiments"
          subheading="Drive the agents on your remote server, review what they did, and steer any of them, from your desktop or your phone."
          features={RESEARCHER_FEATURES}
        />

        {/* Researcher-specific: where it runs */}
        <section className="py-20 bg-muted/30">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
                Cloud GPUs, lab servers, or your own hardware
              </h2>
              <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-2xl mx-auto">
                Vicoa runs anywhere you can run a coding agent, and your codebase never leave that machine.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {ENVIRONMENTS.map((env) => {
                const Icon = env.icon;
                return (
                  <div
                    key={env.title}
                    className="rounded-2xl border border-border bg-card p-6 text-center"
                  >
                    <span className="mx-auto mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <Icon className="h-5 w-5" />
                    </span>
                    <h3 className="mb-1.5 text-base font-medium text-foreground">
                      {env.title}
                    </h3>
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      {env.body}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <HowItWorksSection
          content={{
            stepsTitle: 'From your server to your phone',
            stepsDescription: 'Point Vicoa at the machine your experiments run on, in three steps',
          }}
          steps={RESEARCHER_STEPS}
        />

        <ScreenshotGallerySection />

        {/* Researcher-specific: the SSH + tmux objection */}
        <section className="py-20 bg-background">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
                Already living in SSH + tmux?
              </h2>
              <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-3xl mx-auto">
                Keep it. tmux keeps your session alive when you disconnect. Vicoa adds the
                workspace around it: run agents in parallel, review their work, and steer
                them from any device, at your desk or away from it.
              </p>
            </div>
            <div className="grid max-w-3xl mx-auto gap-4 sm:grid-cols-2">
              {/* What tmux does */}
              <div className="rounded-2xl border border-border bg-card p-6">
                <h3 className="mb-2 text-lg font-semibold text-foreground">
                  What tmux does
                </h3>
                <p className="mb-4 text-sm text-muted-foreground">
                  Keeps your session alive.
                </p>
                <ul className="space-y-3 text-sm text-muted-foreground">
                  {['Your job keeps running after you disconnect', 'Reattach from the same terminal'].map(
                    (point) => (
                      <li key={point} className="flex items-start gap-2.5">
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-foreground/10 text-foreground/60">
                          <Check className="h-3.5 w-3.5" />
                        </span>
                        <span>{point}</span>
                      </li>
                    )
                  )}
                </ul>
              </div>
              {/* What Vicoa adds */}
              <div className="relative rounded-2xl border border-primary/40 bg-gradient-to-br from-primary/[0.10] via-card to-card p-6 shadow-md ring-1 ring-primary/20">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-lg font-semibold text-foreground">
                    What Vicoa adds
                  </h3>
                  <span className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-2.5 py-0.5 text-xs font-medium text-white shadow-sm">
                    Desk or away
                  </span>
                </div>
                <p className="mb-4 text-sm text-muted-foreground">
                  A full workspace for your agents, on any device.
                </p>
                <ul className="space-y-3 text-sm text-muted-foreground">
                  {[
                    'Run many agents in parallel, in one view',
                    'Review diffs, logs, and results as they land',
                    'Steer and approve from your desk or your phone',
                    'Get pinged when a run finishes or needs you',
                  ].map((point) => (
                    <li key={point} className="flex items-start gap-2.5">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                        <Check className="h-3.5 w-3.5" />
                      </span>
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Researcher-specific: who it's for */}
        <section className="py-20 bg-muted/30">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-16">
              <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
                Who it’s for
              </h2>
            </div>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {AUDIENCES.map((a) => (
                <div
                  key={a.title}
                  className="rounded-2xl border border-border bg-card p-6"
                >
                  <h3 className="mb-2 text-base font-medium text-foreground">
                    {a.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {a.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <TestimonialsSection
          title="Loved by researchers"
          testimonials={RESEARCHER_TESTIMONIALS}
        />

        <FeaturedSection />

        <BaseFAQSection
          title="Frequently Asked Questions"
          subtitle="Answers for researchers running agents on remote machines"
          faqs={FAQS}
        />

        <CTASection
          heading={
            <>
              Run a team of agents
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400">
                on your server.
              </span>
            </>
          }
          subheading="Set them up on your server, then steer, review, and approve from any device. Free to start with the agents you already use."
        />
      </main>
    </>
  );
}
