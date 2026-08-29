import { Metadata } from 'next';
import { getAllVsPages } from '@/lib/vs-source';
import { VsComparisonCard } from '@/components/vs/vs-comparison-card';
import { pageMetadata } from '@/lib/seo';

const TITLE = 'Vicoa vs Alternatives: Honest Comparisons';
const DESCRIPTION =
  'How Vicoa compares to other tools for running Claude Code, Codex, and AI coding agents from your phone, desktop, and web. Honest, up-to-date comparisons.';

export const metadata: Metadata = pageMetadata('/vs', {
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

export default function VsIndexPage() {
  const pages = getAllVsPages();

  return (
    <>
      <div className="bg-background">
        {/* Header */}
        <div className="bg-muted/30">
          <div className="container mx-auto max-w-7xl px-4 py-16 text-center">
            <h1 className="mb-4 text-4xl md:text-5xl">How Vicoa compares</h1>
            <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
              Vicoa runs a team of coding agents in parallel, automates your
              tasks and workflows, and works on any device. See how it compares
              to the alternatives.
            </p>
          </div>
        </div>

        <div className="container mx-auto max-w-7xl px-4 py-12">
          {pages.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-lg text-muted-foreground">
                Comparisons are coming soon. Check back shortly.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
              {pages.map((page) => (
                <VsComparisonCard key={page.info.path} page={page} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
