'use client';

/**
 * The Team card on Billing (collaboration §6): how many people the caller's
 * plan pays for and the over-seats state, with a link to the seats page
 * (`/dashboard/seats`, `SeatsCheckout`), where Vicoa Team is bought or its
 * seats changed.
 *
 * Every editor needs a seat; viewers, commenters and people with their own
 * Pro are free.
 *
 * Hosted only: `GET /billing/seats` is served by the billing overlay, so on a
 * self-hosted build (seats unmetered) the card renders nothing. A team owner
 * always sees it; anyone else once seats mean something to them (they share
 * edit access, bought seats, or are over), so a solo account never does.
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
  if (!seats.owns_team && seats.used <= 1 && seats.purchased === null && !seats.over) return null;

  const summary = seatSummary(seats);
  const onTeam = seats.purchased !== null;

  return (
    <div
      className={cn(
        'flex flex-col gap-4 rounded-xl border border-border/60 bg-foreground/[0.03] p-5 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">{onTeam ? 'Seats' : 'Vicoa Team'}</p>
        <p className={cn('text-sm', seats.over ? 'text-warning' : 'text-foreground/90')}>
          {summary.headline}
        </p>
        <p className="text-xs text-muted-foreground">{summary.detail}</p>
      </div>
      {seats.per_seat_available && (
        <Button asChild variant="outline" className="shrink-0 cursor-pointer">
          <Link href={SEATS_PAGE_HREF}>{onTeam ? 'Manage seats' : 'Get Vicoa Team'}</Link>
        </Button>
      )}
    </div>
  );
}
