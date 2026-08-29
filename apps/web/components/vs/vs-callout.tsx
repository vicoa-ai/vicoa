import React from 'react';
import { Info, CheckCircle2, Lightbulb } from 'lucide-react';

type CalloutVariant = 'note' | 'verdict' | 'tip';

const VARIANTS: Record<
  CalloutVariant,
  {
    icon: React.ComponentType<{ className?: string }>;
    wrap: string;
    chip: string;
  }
> = {
  note: {
    icon: Info,
    wrap: 'border-border bg-muted/40',
    chip: 'bg-foreground/10 text-foreground/70',
  },
  verdict: {
    icon: CheckCircle2,
    wrap: 'border-blue-500/25 bg-gradient-to-br from-blue-500/[0.12] via-indigo-500/[0.05] to-transparent',
    chip: 'bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm',
  },
  tip: {
    icon: Lightbulb,
    wrap: 'border-amber-500/30 bg-gradient-to-br from-amber-500/[0.12] to-transparent',
    chip: 'bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-sm',
  },
};

/**
 * Highlighted box for a verdict / key takeaway inside a `/vs` article. Set
 * `title` for a bolded lead line (e.g. "Bottom line"). Children keep prose
 * styling so links and emphasis render normally. The icon sits in a filled,
 * gradient "chip" and the box carries a soft tinted gradient per variant.
 */
export function Callout({
  variant = 'note',
  title,
  children,
}: {
  variant?: CalloutVariant;
  title?: string;
  children: React.ReactNode;
}) {
  const v = VARIANTS[variant];
  const Icon = v.icon;
  return (
    <div
      className={`my-6 flex gap-4 rounded-2xl border p-5 sm:p-6 ${v.wrap}`}
    >
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${v.chip}`}
      >
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0 [&>:first-child]:mt-0 [&>:last-child]:mb-0">
        {title && (
          <p className="mb-1 font-semibold text-foreground">{title}</p>
        )}
        {children}
      </div>
    </div>
  );
}
