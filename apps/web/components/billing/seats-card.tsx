'use client';

/**
 * Seats on Billing (collaboration §6): how many people the caller's plan pays
 * for and the over-seats state, with a link to the seats page
 * (`/dashboard/seats`, `SeatsCheckout`), where seats are bought or changed.
 *
 * A seat is anyone on a team you own, plus anyone outside them you gave edit
 * access; viewers and commenters are free.
 *
 * Hosted only: `GET /billing/seats` is served by the billing overlay, so on a
 * self-hosted build (seats unmetered) the card renders nothing. Shown only
 * once seats mean something to the caller — they share with someone, bought
 * seats, or are over — so a solo account never sees it.
 */

import Link from 'next/link';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { getBackendAPI, type BillingSeats } from '@/lib/backend-api';
import { SEATS_PAGE_HREF, seatSummary } from '@/lib/billing';
import { cn } from '@/lib/utils';

export const BILLING_SEATS_KEY = 'billing-seats';

export function SeatsCard({ className }: { className?: string }) {
  const { data: seats, error } = useSWR<BillingSeats>(
    BILLING_SEATS_KEY,
    () => getBackendAPI(true).getBillingSeats(),
    { shouldRetryOnError: false },
  );

  if (error || !seats) return null;
  if (seats.used <= 1 && !seats.purchased && !seats.over) return null;

  const summary = seatSummary(seats);

  return (
    <div
      className={cn(
        'flex flex-col gap-4 rounded-xl border border-border/60 bg-foreground/[0.03] p-5 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">Seats</p>
        <p className={cn('text-sm', seats.over ? 'text-warning' : 'text-foreground/90')}>
          {summary.headline}
        </p>
        <p className="text-xs text-muted-foreground">{summary.detail}</p>
      </div>
      {seats.per_seat_available && (
        <Button asChild variant="outline" className="shrink-0 cursor-pointer">
          <Link href={SEATS_PAGE_HREF}>{seats.purchased ? 'Manage seats' : 'Add seats'}</Link>
        </Button>
      )}
    </div>
  );
}
