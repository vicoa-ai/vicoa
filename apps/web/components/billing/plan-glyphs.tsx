import { CircleCheck, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Included / not-included glyphs shared by the pricing cards and the
 * comparison table: a filled disc with a knocked-out check, and a faint
 * cross. Kept in one place so the two surfaces never drift apart.
 */
export function IncludedGlyph({ className, ...props }: React.ComponentProps<typeof CircleCheck>) {
  return (
    <CircleCheck
      aria-label="Included"
      className={cn('h-5 w-5 flex-shrink-0 fill-muted-foreground stroke-background', className)}
      {...props}
    />
  );
}

export function ExcludedGlyph({ className, ...props }: React.ComponentProps<typeof X>) {
  return (
    <X
      aria-label="Not included"
      className={cn('h-5 w-5 flex-shrink-0 text-muted-foreground/40', className)}
      {...props}
    />
  );
}
