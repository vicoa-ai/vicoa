import { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { pageMetadata } from '@/lib/seo';
import { VsSection } from '@/components/vs/vs-sections';

const PATH = '/use-cases';
const TITLE = 'Use cases: Vicoa for your workflow';
const DESCRIPTION =
  'See how Vicoa fits your work — run AI coding agents like Claude Code, Codex, and OpenCode on remote machines and steer them from any device. Tailored guides by role and workflow.';

export const metadata: Metadata = pageMetadata(PATH, {
  title: `${TITLE} | Vicoa`,
  description: DESCRIPTION,
  openGraph: {
    title: `${TITLE} | Vicoa`,
    description: DESCRIPTION,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: `${TITLE} | Vicoa`,
    description: DESCRIPTION,
  },
});

// Extend this list as new use-case pages ship (founders, freelancers, PIs …).
const USE_CASES: { title: string; description: string; href: string }[] = [
  {
    title: 'For researchers',
    description:
      "Run coding agents on your GPU server or lab cluster and steer them from your laptop or phone — for ML researchers, PhD & master's students, and data scientists.",
    href: '/use-cases/researchers',
  },
];

export default function UseCasesIndexPage() {
  return (
    <div className="bg-background">
      <section className="container mx-auto max-w-5xl px-4 pt-16 pb-4 text-center md:pt-24">
        <div className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-primary">
          Use cases
        </div>
        <h1 className="mx-auto max-w-3xl text-3xl font-semibold leading-tight text-foreground md:text-5xl">
          Vicoa for your workflow
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Run Claude Code, Codex, and OpenCode wherever your work lives — and drive
          them from any device. Pick the guide that matches how you build.
        </p>
      </section>

      <VsSection>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {USE_CASES.map((uc) => (
            <Link
              key={uc.href}
              href={uc.href}
              className="group flex cursor-pointer flex-col rounded-2xl border border-border bg-card p-6 transition-colors hover:border-primary/50"
            >
              <h2 className="mb-2 text-lg font-medium text-foreground">
                {uc.title}
              </h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {uc.description}
              </p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary">
                Read the guide
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </VsSection>

      <div className="py-8" />
    </div>
  );
}
