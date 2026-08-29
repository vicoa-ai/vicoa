import React from 'react';
import { Check } from 'lucide-react';

/**
 * Two-up "who should choose X / who should choose Y" cards for comparison pages.
 * Wrapped in `not-prose` so the surrounding `.prose` typography doesn't restyle
 * the list. Use inside an MDX `/vs` article:
 *
 * <ChooseCards>
 *   <ChooseCard product="Vicoa" recommended points={["…", "…"]} ideal="…" />
 *   <ChooseCard product="Happy" points={["…", "…"]} ideal="…" />
 * </ChooseCards>
 */
export function ChooseCards({ children }: { children: React.ReactNode }) {
  return (
    <div className="not-prose my-8 grid gap-4 sm:grid-cols-2">{children}</div>
  );
}

interface ChooseCardProps {
  product: string;
  points: string[];
  ideal?: string;
  recommended?: boolean;
}

export function ChooseCard({
  product,
  points,
  ideal,
  recommended = false,
}: ChooseCardProps) {
  return (
    <div
      className={`relative flex h-full flex-col rounded-2xl border p-6 ${
        recommended
          ? 'border-primary/40 bg-gradient-to-br from-primary/[0.10] via-card to-card shadow-md ring-1 ring-primary/20'
          : 'border-border bg-card'
      }`}
    >
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-foreground">
          Choose {product}
        </h3>
        {recommended && (
          <span className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-2.5 py-0.5 text-xs font-medium text-white shadow-sm">
            Recommended
          </span>
        )}
      </div>
      <ul className="space-y-3 text-sm text-muted-foreground">
        {points.map((point, i) => (
          <li key={i} className="flex items-start gap-2.5">
            <span
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                recommended
                  ? 'bg-primary/15 text-primary'
                  : 'bg-foreground/10 text-foreground/60'
              }`}
            >
              <Check className="h-3.5 w-3.5" />
            </span>
            <span>{point}</span>
          </li>
        ))}
      </ul>
      {ideal && (
        <p className="mt-5 border-t border-border/70 pt-4 text-sm text-foreground/80">
          <span className="font-medium text-foreground">Ideal for:</span> {ideal}
        </p>
      )}
    </div>
  );
}
