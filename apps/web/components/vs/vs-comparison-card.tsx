import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { VsPage, getVsPageData, getVsUrl } from '@/lib/vs-source';

export function VsComparisonCard({ page }: { page: VsPage }) {
  const data = getVsPageData(page);
  const description = data.description as string;
  const competitor = data.competitor as string;
  const url = getVsUrl(page);

  return (
    <Link href={url} className="group block">
      <Card className="flex h-full flex-col gap-3 border border-border p-6 transition-all duration-300 hover:border-primary/50">
        {/* "Vicoa vs <competitor>" doubles as the card title */}
        <h2 className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold text-foreground/80 transition-colors group-hover:text-primary">
            Vicoa
          </span>
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            vs
          </span>
          <span className="text-lg font-semibold text-foreground/80 transition-colors group-hover:text-primary">
            {competitor}
          </span>
        </h2>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {description}
        </p>
      </Card>
    </Link>
  );
}
