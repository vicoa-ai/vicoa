'use client';

import { useRouter } from 'next/navigation';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { openUpgradeDialog } from '@/components/billing/upgrade-dialog';
import type { BillingSubscription } from '@/lib/backend-api';
import { accountPlanSummary } from '@/lib/billing';
import { openBillingSettings } from '@/lib/billing-subscription';
import { cn } from '@/lib/utils';

/**
 * The plan in the sidebar's account row, left of the Settings icon (desktop
 * and web), so it is in sight without opening the account menu; a click opens
 * the upgrade dialog. Free only: a paid plan or a seat keeps its row in the
 * account menu and shows nothing here, and so does an unknown plan, for the
 * same reason as `AccountPlanItem`.
 */
export function SidebarPlanButton({
  subscription,
  className,
}: {
  subscription: BillingSubscription | null | undefined;
  className?: string;
}) {
  if (!subscription) return null;
  const { label, action } = accountPlanSummary(subscription);
  if (action !== 'upgrade') return null;

  return (
    <button
      type="button"
      onClick={() => openUpgradeDialog('sidebar')}
      title="See plans"
      className={cn(
        'shrink-0 cursor-pointer whitespace-nowrap rounded-full border border-border/60 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground',
        className,
      )}
    >
      {label}
    </button>
  );
}

/**
 * The plan row under the account menu's identity header (desktop and web):
 * Free with Upgrade, which opens the upgrade dialog, or the paid plan with
 * Manage, which opens Billing. A seat someone else pays for has nothing to
 * manage, so it is shown without an action. Renders nothing while the plan is
 * unknown (loading, or the read failed): offering Upgrade to a paying
 * customer is worse than showing no plan.
 */
export function AccountPlanItem({
  subscription,
  className,
}: {
  subscription: BillingSubscription | null | undefined;
  className?: string;
}) {
  const router = useRouter();
  if (!subscription) return null;

  const { label, detail, action } = accountPlanSummary(subscription);

  const body = (
    <>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{label}</span>
        {detail && <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{detail}</span>}
      </span>
      {action && (
        <span
          className={cn(
            'shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium',
            action === 'upgrade' ? 'bg-foreground text-background' : 'border border-border text-foreground/80',
          )}
        >
          {action === 'upgrade' ? 'Upgrade' : 'Manage'}
        </span>
      )}
    </>
  );
  const cardClassName = cn(
    'flex items-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-xs',
    className,
  );

  if (!action) return <div className={cardClassName}>{body}</div>;
  return (
    <DropdownMenuItem
      className={cardClassName}
      onSelect={() =>
        action === 'upgrade' ? openUpgradeDialog('account_menu') : openBillingSettings((href) => router.push(href))
      }
    >
      {body}
    </DropdownMenuItem>
  );
}
