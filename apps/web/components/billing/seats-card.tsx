'use client';

/**
 * Seats (collaboration §6): how many people the caller's plan pays for, the
 * over-seats state, and buying seats on the per-seat plan.
 *
 * A seat is anyone on a team you own, plus anyone outside them you gave edit
 * access; viewers and commenters are free. Pro includes a fixed number; the
 * per-seat plan is a Stripe subscription whose quantity is the seats bought.
 * Starting it goes through Stripe Checkout; changing an existing Stripe
 * subscription is done in place (prorated) and comes straight back.
 *
 * Hosted only: `GET /billing/seats` is served by the billing overlay, so on a
 * self-hosted build (seats unmetered) the card renders nothing. Shown only
 * once seats mean something to the caller — they share with someone, bought
 * seats, or are over — so a solo account never sees it.
 */

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { Loader2, Minus, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  getBackendAPI,
  type BillingInterval,
  type BillingSeats,
} from '@/lib/backend-api';
import { formatSeatPrice, getBillingProviderLabel, seatSummary } from '@/lib/billing';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import { webOrigin } from '@/lib/desktop-paywall';
import { cn } from '@/lib/utils';

export const BILLING_SEATS_KEY = 'billing-seats';

const MAX_SEATS = 1000;

function returnUrls(): { success_url: string; cancel_url: string } {
  // The desktop opens Checkout in the system browser, which cannot come back
  // to the app's local server; it lands on the web's done page instead.
  if (getDesktopAuthBridge()) {
    return {
      success_url: `${webOrigin()}/desktop-checkout-done`,
      cancel_url: `${webOrigin()}/desktop-checkout-done?cancelled=1`,
    };
  }
  const base = `${window.location.origin}/dashboard/settings?tab=billing`;
  return { success_url: `${base}&checkout=success`, cancel_url: base };
}

function openCheckout(url: string) {
  const bridge = getDesktopAuthBridge();
  if (bridge) bridge.openExternal(url);
  else window.location.assign(url);
}

export function SeatsCard({ className }: { className?: string }) {
  const { data: seats, error, mutate } = useSWR<BillingSeats>(
    BILLING_SEATS_KEY,
    () => getBackendAPI(true).getBillingSeats(),
    // No refetch on focus: the stepper below starts from this data, and a
    // background refresh would reset a quantity the user is still choosing.
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );
  const [quantity, setQuantity] = useState(1);
  const [interval, setBillingInterval] = useState<BillingInterval>('monthly');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!seats) return;
    // Start from what they pay for now; a new per-seat plan starts one seat
    // above what their current plan includes, never below what is in use.
    const floor = Math.max(seats.used, 1);
    setQuantity(
      seats.purchased ?? Math.max(floor, seats.included !== null ? seats.included + 1 : floor),
    );
    if (seats.billing_interval) setBillingInterval(seats.billing_interval);
  }, [seats]);

  if (error || !seats) return null;
  if (seats.used <= 1 && !seats.purchased && !seats.over) return null;

  const summary = seatSummary(seats);
  const floor = Math.max(seats.used, 1);
  const price = seats.prices ? seats.prices[interval] : null;
  const onPerSeat = seats.purchased !== null;
  const changed = !onPerSeat || quantity !== seats.purchased || interval !== seats.billing_interval;
  const storeLabel =
    seats.provider === 'apple' || seats.provider === 'google'
      ? getBillingProviderLabel(seats.provider)
      : null;

  const submit = async () => {
    if (busy || !changed) return;
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await getBackendAPI(true).changeBillingSeats({
        quantity,
        billing_interval: interval,
        ...returnUrls(),
      });
      if (result.status === 'checkout' && result.checkout_url) {
        openCheckout(result.checkout_url);
        // In the desktop the page stays; let the button settle.
        if (getDesktopAuthBridge()) setBusy(false);
        return;
      }
      if (result.seats) await mutate(result.seats, { revalidate: false });
      setNotice(`You now pay for ${quantity} ${quantity === 1 ? 'seat' : 'seats'}.`);
      setBusy(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update seats.');
      setBusy(false);
    }
  };

  return (
    <div className={cn('rounded-xl border border-border/60 bg-foreground/[0.03] p-5', className)}>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">Seats</p>
        <p className={cn('text-sm', seats.over ? 'text-warning' : 'text-foreground/90')}>
          {summary.headline}
        </p>
        <p className="text-xs text-muted-foreground">{summary.detail}</p>
      </div>

      {seats.per_seat_available && (
        <div className="mt-5 space-y-4 border-t border-border/50 pt-4">
          <div className="space-y-1">
            <p className="text-sm text-foreground">
              {onPerSeat ? 'Seats you pay for' : 'Pay per seat'}
            </p>
            <p className="text-xs text-muted-foreground">
              {price
                ? `${formatSeatPrice(price)} per seat per ${interval === 'annual' ? 'year' : 'month'}, you included. Includes Pro for you.`
                : 'Billed per seat, you included. Includes Pro for you.'}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center rounded-lg border border-border/70">
              <button
                type="button"
                aria-label="Fewer seats"
                disabled={busy || quantity <= floor}
                onClick={() => setQuantity((q) => Math.max(floor, q - 1))}
                className="cursor-pointer px-2.5 py-1.5 text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Minus className="h-3.5 w-3.5" />
              </button>
              <input
                aria-label="Seats"
                inputMode="numeric"
                value={quantity}
                onChange={(e) => {
                  const next = Number.parseInt(e.target.value.replace(/\D/g, ''), 10);
                  if (!Number.isNaN(next)) setQuantity(Math.min(MAX_SEATS, next));
                }}
                onBlur={() => setQuantity((q) => Math.min(MAX_SEATS, Math.max(floor, q)))}
                className="w-12 bg-transparent text-center text-sm tabular-nums outline-none"
              />
              <button
                type="button"
                aria-label="More seats"
                disabled={busy || quantity >= MAX_SEATS}
                onClick={() => setQuantity((q) => Math.min(MAX_SEATS, q + 1))}
                className="cursor-pointer px-2.5 py-1.5 text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="flex rounded-full border border-border/70 p-0.5 text-xs">
              {(['monthly', 'annual'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  disabled={busy || !seats.prices?.[value]}
                  onClick={() => setBillingInterval(value)}
                  className={cn(
                    'cursor-pointer rounded-full px-3 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-40',
                    interval === value
                      ? 'bg-foreground text-background'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {value === 'monthly' ? 'Monthly' : 'Annual'}
                </button>
              ))}
            </div>

            <Button
              size="sm"
              onClick={() => void submit()}
              disabled={busy || !changed || quantity < floor}
              className="cursor-pointer"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : onPerSeat ? (
                'Update seats'
              ) : (
                'Continue to checkout'
              )}
            </Button>
          </div>

          {price && (
            <p className="text-xs text-muted-foreground">
              {`${quantity} ${quantity === 1 ? 'seat' : 'seats'}: ${formatSeatPrice({
                ...price,
                unit_amount: price.unit_amount * quantity,
              })} per ${interval === 'annual' ? 'year' : 'month'}.`}
              {onPerSeat ? ' Changes are prorated.' : ''}
            </p>
          )}
          {storeLabel && !onPerSeat && (
            <p className="text-xs text-muted-foreground">
              Your Pro subscription is billed through {storeLabel}. After switching, cancel it there
              so you aren&apos;t charged twice.
            </p>
          )}
          {seats.used > 1 && (
            <p className="text-xs text-muted-foreground">
              {`${seats.used} are in use now, so that is the fewest you can pay for. Remove people to go lower.`}
            </p>
          )}
        </div>
      )}

      {notice && <p className="mt-3 text-xs text-success">{notice}</p>}
      {actionError && <p className="mt-3 text-xs text-destructive">{actionError}</p>}
    </div>
  );
}
