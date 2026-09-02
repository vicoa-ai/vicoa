'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  Loader2,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { getBackendAPI } from '@/lib/backend-api';
import type { AutomationRunResponse, AutomationRunStatus } from '@/lib/backend-api';
import { FieldGroup } from './field-row';

type Api = ReturnType<typeof getBackendAPI>;

const STATUS_META: Record<
  AutomationRunStatus,
  { icon: LucideIcon; color: string; label: string }
> = {
  fired: { icon: CheckCircle2, color: 'text-green-500', label: 'Ran' },
  missed_offline: { icon: CircleAlert, color: 'text-warning', label: 'Missed — offline' },
  failed: { icon: XCircle, color: 'text-red-500', label: 'Failed' },
  skipped: { icon: MinusCircle, color: 'text-muted-foreground', label: 'Skipped' },
};

export function RunHistorySection({
  api,
  automationId,
  title,
  refreshKey = 0,
}: {
  api: Api;
  automationId: string;
  /** Shown as each run's title (the automation the run executed). */
  title: string;
  refreshKey?: number;
}) {
  const [runs, setRuns] = useState<AutomationRunResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listAutomationRuns(automationId)
      .then((r) => !cancelled && setRuns(r))
      .catch(() => !cancelled && setRuns([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [api, automationId, refreshKey]);

  return (
    <FieldGroup title="Run history">
      {loading ? (
        <div className="flex h-16 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : runs.length === 0 ? (
        <div className="px-3.5 py-4 text-center text-xs text-muted-foreground">
          No runs yet.
        </div>
      ) : (
        runs.map((run) => {
          const meta = STATUS_META[run.status];
          const Icon = meta.icon;
          return (
            <div key={run.id} className="flex items-center gap-2.5 px-3.5 py-2">
              <Icon
                className={cn('h-4 w-4 flex-shrink-0', meta.color)}
                aria-label={meta.label}
              />
              {/* Title ellipsizes; status + time sit at the right of the row. */}
              <span className="min-w-0 flex-1 truncate text-sm" title={title}>
                {title}
              </span>
              <span
                className="flex-shrink-0 whitespace-nowrap text-xs text-muted-foreground"
                title={run.detail ?? undefined}
              >
                {meta.label} · {new Date(run.fired_at).toLocaleString()}
              </span>
              {/* ↗ opens the session this run spawned. */}
              {run.agent_instance_id && (
                <Link
                  href={`/dashboard/agents/${run.agent_instance_id}`}
                  className="flex-shrink-0 text-muted-foreground hover:text-foreground"
                  title="Open session"
                >
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              )}
            </div>
          );
        })
      )}
    </FieldGroup>
  );
}
