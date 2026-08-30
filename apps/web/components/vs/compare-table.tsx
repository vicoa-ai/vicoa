import { Check, X } from 'lucide-react';
import type { CompareCell, VsComparisonRow } from '@/lib/vs-source';

function Cell({ value, emphasized }: { value: CompareCell; emphasized?: boolean }) {
  if (typeof value === 'boolean') {
    return value ? (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/15">
          <Check className="h-3.5 w-3.5" />
        </span>
        Yes
      </span>
    ) : (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-red-500 dark:text-red-400">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500/15">
          <X className="h-3.5 w-3.5" />
        </span>
        No
      </span>
    );
  }
  return (
    <span
      className={`text-sm ${emphasized ? 'text-foreground' : 'text-muted-foreground'}`}
    >
      {value}
    </span>
  );
}

export function CompareTable({
  competitor,
  rows,
}: {
  competitor: string;
  rows: VsComparisonRow[];
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border shadow-sm">
      <div className="custom-scrollbar overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="w-[38%] px-5 py-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Feature
              </th>
              <th className="relative border-l border-border/60 bg-primary/[0.06] px-5 py-4">
                <span className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-blue-500 to-indigo-500" />
                <span className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    Vicoa
                  </span>
                  <span className="hidden rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white sm:inline">
                    Our pick
                  </span>
                </span>
              </th>
              <th className="px-5 py-4 text-sm font-medium text-foreground/70">
                {competitor}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border/60 transition-colors last:border-0 even:bg-muted/20 hover:bg-muted/40"
              >
                <td className="px-5 py-4 align-top text-sm font-medium text-foreground">
                  {row.feature}
                </td>
                <td className="border-l border-border/60 bg-primary/[0.05] px-5 py-4 align-top">
                  <Cell value={row.vicoa} emphasized />
                </td>
                <td className="px-5 py-4 align-top">
                  <Cell value={row.rival} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
