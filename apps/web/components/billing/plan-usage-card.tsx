'use client';

/**
 * What this account has used of its plan, one row per metered resource.
 *
 * Every number comes from `GET /limits`; nothing here knows what a plan
 * includes. That is the point of the endpoint — repricing a plan is a
 * server-side change, and this renders whatever it is told.
 *
 * Renders nothing at all when every resource is unlimited, which is the whole
 * list on Pro and in a self-hosted build with no billing overlay: a wall of
 * "Unlimited" rows is noise, and a section that says nothing should not be a
 * section. It also stays quiet while loading and on failure — this is a
 * secondary read on a settings page, so an error card here would be louder
 * than what it tells you.
 */

import useSWR from 'swr';
import { getBackendAPI, type LimitStatus } from '@/lib/backend-api';

const LIMITS_KEY = 'plan-limits';

function usageLine(row: LimitStatus): string {
  return `${row.used} of ${row.limit}`;
}

export function PlanUsageCard({ className }: { className?: string }) {
  const { data } = useSWR(LIMITS_KEY, () => getBackendAPI().getLimits());

  const capped = (data?.limits ?? []).filter((row) => !row.unlimited && row.limit !== null);
  if (capped.length === 0) return null;

  return (
    <div className={className}>
      <p className="text-sm text-muted-foreground">Usage</p>
      <ul className="mt-3 space-y-2">
        {capped.map((row) => {
          const atLimit = row.remaining === 0;
          return (
            <li key={row.key} className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-foreground/80">{row.label}</span>
              <span className={atLimit ? 'text-warning' : 'text-muted-foreground'}>
                {usageLine(row)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
