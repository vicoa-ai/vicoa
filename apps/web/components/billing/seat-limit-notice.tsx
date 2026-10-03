'use client';

import Link from 'next/link';
import { SEATS_PAGE_HREF } from '@/lib/billing';
import { cn } from '@/lib/utils';

/**
 * The one place a 402 from a collaboration action is shown (plan §6).
 *
 * A 402 means "the action exists and you may ask for it, but it is metered":
 * adding a team member or giving someone outside your teams editor/admin
 * access takes a seat. The backend's `detail` is the overlay's reason; the
 * link goes straight to the seats page. The open / self-hosted build never
 * answers 402, so nothing here is reachable there.
 *
 * Pair with `seatLimitFromError(err)` from `lib/backend-api`.
 */
export function SeatLimitNotice({
  detail,
  className,
}: {
  detail?: string | null;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground/90',
        className,
      )}
    >
      <p className="font-medium">Seat limit reached</p>
      {detail ? <p className="mt-0.5 text-muted-foreground">{detail}</p> : null}
      <Link
        href={SEATS_PAGE_HREF}
        className="mt-1 inline-block cursor-pointer text-foreground underline underline-offset-2 hover:text-foreground/80"
      >
        Manage seats
      </Link>
    </div>
  );
}
