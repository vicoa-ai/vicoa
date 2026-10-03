'use client';

/**
 * The seats page (`/dashboard/seats`): buy seats or change them, on a page of
 * its own, apart from the plan picker at `/dashboard/upgrade`. Every seat
 * entry point (the team page, Billing, a "Seat limit reached" notice) lands
 * here directly, so a payer already on per-seat billing never passes back
 * through the plans, and a Pro payer adding someone goes straight to Team.
 *
 * Three starting points, one page:
 * - already on Team (`purchased`): change the quantity or interval in place,
 *   prorated on the next invoice;
 * - Pro billed by Stripe: that same subscription switches to Team, in place
 *   (the backend never opens a second, double-billed one);
 * - anyone else (Free, or Pro billed by a store): Stripe Checkout.
 *
 * Which of those happens is the backend's call (`change_mode`), the same test
 * `POST /billing/seats` runs. An in-place change bills the live subscription
 * at once, so it is confirmed first; Checkout is its own confirmation. Team
 * starts at `min_quantity` seats (two).
 *
 * Hosted only: `GET /billing/seats` is served by the billing overlay. On a
 * self-hosted build (seats unmetered) it 404s and the page says so.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR, { mutate as globalMutate } from 'swr';
import { ArrowLeft, Clock, Loader2, Minus, Plus, Users } from 'lucide-react';

import { ConfirmChargeDialog } from '@/components/billing/confirm-charge-dialog';
import { BILLING_SEATS_KEY } from '@/components/billing/seats-card';
import { Button } from '@/components/ui/button';
import {
  getBackendAPI,
  type BackendApiError,
  type BillingInterval,
  type BillingSeats,
  type BillingSubscription,
  type SeatPrice,
} from '@/lib/backend-api';
import {
  SEAT_EXPLAINER,
  formatBillingDate,
  formatSeatPrice,
  getBillingProviderLabel,
  seatSummary,
} from '@/lib/billing';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import { webOrigin } from '@/lib/desktop-paywall';
import { cn } from '@/lib/utils';

const BILLING_SUBSCRIPTION_KEY = 'billing-subscription';
const BILLING_HREF = '/dashboard/settings?tab=billing';

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
  const origin = window.location.origin;
  return {
    success_url: `${origin}${BILLING_HREF}&checkout=success`,
    cancel_url: `${origin}${window.location.pathname}`,
  };
}

function openCheckout(url: string) {
  const bridge = getDesktopAuthBridge();
  if (bridge) bridge.openExternal(url);
  else window.location.assign(url);
}

function seatCount(n: number): string {
  return `${n} ${n === 1 ? 'seat' : 'seats'}`;
}

function times(price: SeatPrice, quantity: number): SeatPrice {
  return { ...price, unit_amount: price.unit_amount * quantity };
}

function Step({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Clock;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex gap-4">
      <Icon className="mt-1 size-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1 space-y-4">
        <h2 className="text-lg font-medium text-foreground sm:text-xl">{title}</h2>
        {children}
      </div>
    </section>
  );
}

function SummaryRow({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: React.ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className={cn('text-sm', strong ? 'font-medium text-foreground' : 'text-muted-foreground')}>
        {label}
      </span>
      <span
        className={cn(
          'tabular-nums text-foreground',
          strong ? 'text-2xl font-medium' : 'text-sm',
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function SeatsCheckout() {
  const router = useRouter();
  const { data: seats, error, mutate } = useSWR<BillingSeats>(
    BILLING_SEATS_KEY,
    () => getBackendAPI(true).getBillingSeats(),
    // No refetch on focus: the stepper below starts from this data, and a
    // background refresh would reset a quantity the user is still choosing.
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );
  const { data: subscription } = useSWR<BillingSubscription>(
    BILLING_SUBSCRIPTION_KEY,
    () => getBackendAPI(true).getBillingSubscription(),
    { shouldRetryOnError: false },
  );
  const [quantity, setQuantity] = useState(1);
  const [interval, setBillingInterval] = useState<BillingInterval>('annual');
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!seats) return;
    // Start from what they pay for now; a new Team starts one seat above what
    // their current plan includes, never below what is in use or Team's
    // minimum.
    const floor = Math.max(seats.used, seats.min_quantity);
    setQuantity(
      seats.purchased ?? Math.max(floor, seats.included !== null ? seats.included + 1 : floor),
    );
    // Keep the interval a Stripe subscription is billed at now (changing it
    // in place bills at once); a new subscription defaults to yearly.
    setBillingInterval(seats.billing_interval ?? (seats.prices?.annual ? 'annual' : 'monthly'));
  }, [seats]);

  const goBack = () => {
    if (window.history.length > 1) router.back();
    else router.push(BILLING_HREF);
  };

  const header = (title: string, subtitle?: string) => (
    <>
      <div className="mb-8">
        <Button
          variant="ghost"
          size="icon"
          className="size-14 rounded-full"
          aria-label="Back"
          onClick={goBack}
        >
          <ArrowLeft className="size-5" />
        </Button>
      </div>
      <h1 className="text-3xl text-foreground sm:text-4xl">{title}</h1>
      {subtitle && (
        <p className="mt-3 max-w-2xl text-sm text-muted-foreground sm:text-base">{subtitle}</p>
      )}
    </>
  );

  const shell = (children: React.ReactNode) => (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8 lg:py-12">{children}</div>
  );

  if (error) {
    const unmetered = (error as Partial<BackendApiError>).status === 404;
    return shell(
      header(
        'Seats',
        unmetered
          ? 'Seats are not billed on this server, so there is nothing to buy.'
          : 'Seat details are unavailable right now.',
      ),
    );
  }
  if (!seats) {
    return shell(
      <>
        {header('Seats')}
        <div className="mt-10 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading seats...
        </div>
      </>,
    );
  }

  const summary = seatSummary(seats);
  const onPerSeat = seats.purchased !== null;
  if (!seats.per_seat_available) {
    return shell(
      header('Seats', `${summary.headline}. Buying seats is not available yet.`),
    );
  }

  const floor = Math.max(seats.used, seats.min_quantity);
  const price = seats.prices ? seats.prices[interval] : null;
  const unit = interval === 'annual' ? 'year' : 'month';
  // A live Stripe subscription is changed in place (prorated on the next
  // invoice); anything else goes through Checkout and is paid today. The
  // backend says which, so this can never promise Checkout and bill at once.
  const inPlace = seats.change_mode === 'in_place';
  const changed = !onPerSeat || quantity !== seats.purchased || interval !== seats.billing_interval;
  const storeLabel =
    seats.provider === 'apple' || seats.provider === 'google'
      ? getBillingProviderLabel(seats.provider)
      : null;
  const nextPayment = formatBillingDate(subscription?.current_period_end);
  const currentPrice =
    onPerSeat && seats.purchased !== null && seats.billing_interval && seats.prices
      ? seats.prices[seats.billing_interval]
      : null;
  // Stripe resets the billing date and invoices at once when a subscription
  // changes interval, so it can't be "prorated on the next invoice".
  const intervalChanges =
    inPlace && seats.billing_interval !== null && interval !== seats.billing_interval;
  const currentUnit = seats.billing_interval === 'annual' ? 'year' : 'month';
  const monthly = seats.prices?.monthly;
  const annual = seats.prices?.annual;
  const annualSaving =
    monthly && annual && monthly.currency === annual.currency && monthly.unit_amount > 0
      ? Math.round((1 - annual.unit_amount / (monthly.unit_amount * 12)) * 100)
      : 0;

  const proration = intervalChanges
    ? `You're charged today, with credit for the rest of your current ${currentUnit}, and your billing date moves to today.`
    : `The difference is prorated on your next invoice${nextPayment ? `, ${nextPayment}` : ''}.`;

  const submit = async () => {
    if (busy || !changed) return;
    // An in-place change bills the live subscription the moment it is made,
    // so it goes through the confirmation; Checkout confirms on its own page.
    if (inPlace) {
      setConfirmOpen(true);
      return;
    }
    await change();
  };

  const change = async () => {
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
      void globalMutate(BILLING_SUBSCRIPTION_KEY);
      setNotice(`You now pay for ${seatCount(quantity)}.`);
      setBusy(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update seats.');
      setBusy(false);
    }
  };

  const title = onPerSeat ? 'Manage seats' : 'Upgrade to Vicoa Team';
  const subtitle = onPerSeat
    ? `${summary.headline}. ${summary.detail}`
    : `Every seat is a full Pro, billed to you. ${SEAT_EXPLAINER}`;
  const cta = onPerSeat ? 'Update seats' : inPlace ? 'Switch to Team' : 'Continue to checkout';
  const newTotal = price ? `${formatSeatPrice(times(price, quantity))} per ${unit}` : seatCount(quantity);

  return shell(
    <>
      {header(title, subtitle)}

      <div className="mt-10 grid gap-10 border-t border-border/60 pt-10 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-16">
        <div className="space-y-10">
          <Step icon={Clock} title="How often do you want to be billed?">
            <div
              role="radiogroup"
              aria-label="Billing interval"
              className="inline-flex overflow-hidden rounded-lg border border-border/70"
            >
              {(['annual', 'monthly'] as const).map((value) => {
                const checked = interval === value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={checked}
                    disabled={busy || !seats.prices?.[value]}
                    onClick={() => setBillingInterval(value)}
                    className={cn(
                      'flex cursor-pointer items-center gap-2.5 px-4 py-2.5 text-sm transition-colors not-first:border-l not-first:border-border/70 disabled:cursor-not-allowed disabled:opacity-40',
                      checked
                        ? 'bg-foreground/[0.06] text-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        'size-3.5 rounded-full border',
                        checked ? 'border-[4px] border-primary' : 'border-muted-foreground/60',
                      )}
                    />
                    {value === 'monthly' ? 'Pay monthly' : 'Pay yearly'}
                    {value === 'annual' && annualSaving > 0 && (
                      <span className="text-xs text-muted-foreground">Save {annualSaving}%</span>
                    )}
                  </button>
                );
              })}
            </div>
          </Step>

          <Step icon={Users} title="How many seats do you want?">
            <div className="inline-flex items-stretch overflow-hidden rounded-lg border border-border/70">
              <button
                type="button"
                aria-label="Fewer seats"
                disabled={busy || quantity <= floor}
                onClick={() => setQuantity((q) => Math.max(floor, q - 1))}
                className="cursor-pointer px-4 py-2.5 text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Minus className="size-4" />
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
                className="w-16 border-x border-border/70 bg-transparent text-center text-base tabular-nums outline-none"
              />
              <button
                type="button"
                aria-label="More seats"
                disabled={busy || quantity >= MAX_SEATS}
                onClick={() => setQuantity((q) => Math.min(MAX_SEATS, q + 1))}
                className="cursor-pointer px-4 py-2.5 text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus className="size-4" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground">
              {price ? `Each seat costs ${formatSeatPrice(price)} per ${unit}, you included. ` : ''}
              {`Vicoa Team starts at ${seatCount(seats.min_quantity)}. You are using ${seatCount(seats.used)} now`}
              {seats.own_pro > 0
                ? `, and ${seats.own_pro} more ${seats.own_pro === 1 ? 'person brings' : 'people bring'} their own Pro`
                : ''}
              {seats.used > seats.min_quantity
                ? '. That is the fewest you can pay for; remove people to go lower.'
                : '.'}
            </p>
          </Step>
        </div>

        <aside className="h-fit space-y-5 rounded-xl border border-border/60 bg-foreground/[0.03] p-5 lg:sticky lg:top-8">
          {changed && currentPrice && seats.purchased !== null && (
            <SummaryRow
              label={`Now, ${seatCount(seats.purchased)}`}
              value={`${formatSeatPrice(times(currentPrice, seats.purchased))} / ${seats.billing_interval === 'annual' ? 'year' : 'month'}`}
            />
          )}
          <SummaryRow
            label={`New ${interval === 'annual' ? 'yearly' : 'monthly'} total`}
            value={price ? `${formatSeatPrice(times(price, quantity))} / ${unit}` : seatCount(quantity)}
          />
          <div className="border-t border-border/50" />
          {inPlace ? (
            <p className="text-sm text-muted-foreground">
              {onPerSeat ? '' : 'Your Pro subscription switches to Vicoa Team. '}
              {proration}
            </p>
          ) : (
            <SummaryRow
              label="Due today"
              value={price ? formatSeatPrice(times(price, quantity)) : seatCount(quantity)}
              strong
            />
          )}

          <Button
            size="lg"
            onClick={() => void submit()}
            disabled={busy || !changed || quantity < floor}
            className="w-full cursor-pointer"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : cta}
          </Button>

          {!onPerSeat && (
            <p className="text-xs text-muted-foreground">Every seat includes Pro, yours too.</p>
          )}
          {storeLabel && !onPerSeat && (
            <p className="text-xs text-muted-foreground">
              Your Pro subscription is billed through {storeLabel}. After switching, cancel it there
              so you aren&apos;t charged twice.
            </p>
          )}
          {notice && <p className="text-xs text-success">{notice}</p>}
          {actionError && <p className="text-xs text-destructive">{actionError}</p>}
        </aside>
      </div>

      <ConfirmChargeDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={onPerSeat ? `Change to ${seatCount(quantity)}?` : 'Switch to Vicoa Team?'}
        description={
          onPerSeat
            ? `Your Vicoa Team subscription changes now. ${proration}`
            : `Your Pro subscription becomes Vicoa Team with ${seatCount(quantity)}, starting now. ${proration}`
        }
        summary={
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-muted-foreground">New total</span>
            <span className="tabular-nums text-foreground">{newTotal}</span>
          </div>
        }
        confirmLabel={cta}
        onConfirm={change}
      />
    </>,
  );
}
