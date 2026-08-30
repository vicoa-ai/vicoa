import { Check } from 'lucide-react';
import type { VsPricingColumn } from '@/lib/vs-source';

function PricingCard({
  name,
  col,
  recommended = false,
}: {
  name: string;
  col: VsPricingColumn;
  recommended?: boolean;
}) {
  return (
    <div
      className={`relative flex h-full flex-col rounded-2xl border p-6 ${
        recommended
          ? 'border-primary/40 bg-gradient-to-br from-primary/[0.10] via-card to-card shadow-md ring-1 ring-primary/20'
          : 'border-border bg-card'
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-foreground">{name}</h3>
        {recommended && (
          <span className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-2.5 py-0.5 text-xs font-medium text-white shadow-sm">
            Our pick
          </span>
        )}
      </div>
      <p className="text-base font-medium text-foreground">{col.price}</p>
      {col.rows && col.rows.length > 0 && (
        <ul className="mt-5 space-y-3">
          {col.rows.map((row, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm">
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                  recommended
                    ? 'bg-primary/15 text-primary'
                    : 'bg-foreground/10 text-foreground/60'
                }`}
              >
                <Check className="h-3.5 w-3.5" />
              </span>
              <span className="text-foreground/80">{row}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PricingCompare({
  competitor,
  vicoa,
  rival,
  note,
}: {
  competitor: string;
  vicoa: VsPricingColumn;
  rival: VsPricingColumn;
  note?: string;
}) {
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <PricingCard name="Vicoa" col={vicoa} recommended />
        <PricingCard name={competitor} col={rival} />
      </div>
      {note && (
        <p className="mt-4 text-center text-xs text-muted-foreground">{note}</p>
      )}
    </div>
  );
}
