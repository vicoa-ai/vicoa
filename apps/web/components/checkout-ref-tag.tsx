import { checkoutRefTag, type CheckoutRef } from '@/lib/checkout-ref';
import { cn } from '@/lib/utils';

/**
 * The small "detached" / "rebasing" tag beside a checkout's label, explained
 * on hover. Renders nothing for a checkout on a branch. Styled like the
 * sidebar's "deleted" tag: these are states to notice, not errors.
 */
export function CheckoutRefTag({
  checkoutRef,
  className,
}: {
  checkoutRef: CheckoutRef;
  className?: string;
}) {
  const tag = checkoutRefTag(checkoutRef);
  if (!tag) return null;
  return (
    <span
      title={tag.title}
      className={cn(
        'shrink-0 rounded border border-border/60 px-1 text-[9px] leading-4 text-muted-foreground/50',
        className,
      )}
    >
      {tag.text}
    </span>
  );
}
