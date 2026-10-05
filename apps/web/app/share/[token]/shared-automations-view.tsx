'use client';

// A project's shared automations: the dashboard's list-and-detail shape with
// nothing to run, pause or edit. A row says what the automation is called and
// when it runs; picking one opens its prompt, agent and schedule beside the
// list (over it, on a phone). The server strips each one to what it does and
// when, so there is no author, machine or folder to show, and nothing here
// asks for one. Polled slowly, like the board: automations change on the
// order of days.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { AGENT_CATALOG_FALLBACK, sessionConfigSummaryRows } from '@/lib/agent-catalog';
import type { PublicProjectSummary } from '@/lib/backend-api';
import { ShareNotFoundError, fetchPublicAutomations, type PublicAutomation } from '@/lib/public-share-api';
import { POLL_IDLE_MS, useSharePoll } from '@/lib/use-share-poll';
import { cn } from '@/lib/utils';
import { SHARE_ROW_SELECTED, ShareHeader } from './share-shell';
import { formatShareTime, lastRunSummary, publicScheduleSummary, publicSessionConfig } from './share-view';

/** The dashboard's group label: sentence case, normal weight, muted. */
const GROUP_LABEL = 'px-1 text-[0.8rem] font-normal text-muted-foreground';

function titleOf(automation: PublicAutomation): string {
  return automation.title.trim() || 'Untitled automation';
}

function AutomationRow({
  automation,
  selected,
  onSelect,
}: {
  automation: PublicAutomation;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'flex w-full cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5 text-left transition-colors',
        selected ? SHARE_ROW_SELECTED : 'hover:bg-foreground/[0.04]',
      )}
    >
      <CalendarClock
        className={cn('h-4 w-4 shrink-0', automation.enabled ? 'text-muted-foreground' : 'text-muted-foreground/50')}
      />
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm', !automation.enabled && 'text-muted-foreground')}>
          {titleOf(automation)}
        </div>
        <div className="truncate text-xs text-muted-foreground">{publicScheduleSummary(automation)}</div>
      </div>
      {!automation.enabled && <span className="shrink-0 text-[11px] text-muted-foreground">Paused</span>}
    </button>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-[40px] items-start gap-3 px-3.5 py-2">
      <dt className="shrink-0 text-sm text-foreground/80">{label}</dt>
      <dd className="min-w-0 flex-1 text-right text-sm text-muted-foreground">{children}</dd>
    </div>
  );
}

const LAST_RUN_TONE: Partial<Record<NonNullable<PublicAutomation['last_run_status']>, string>> = {
  failed: 'text-destructive',
  missed_offline: 'text-warning',
};

function AutomationDetail({ automation, onClose }: { automation: PublicAutomation; onClose: () => void }) {
  const agentRows = useMemo(() => {
    const config = publicSessionConfig(automation.session_config);
    return config ? sessionConfigSummaryRows(AGENT_CATALOG_FALLBACK, config) : [];
  }, [automation.session_config]);
  const lastRunTone = automation.last_run_status ? LAST_RUN_TONE[automation.last_run_status] : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border/60 px-4">
        <span className="text-xs text-muted-foreground">{automation.enabled ? 'Active' : 'Paused'}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="ml-auto h-8 w-8"
          onClick={onClose}
          title="Close"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <h2 className="break-words text-base font-medium">{titleOf(automation)}</h2>

        <div className="space-y-1.5">
          <div className={GROUP_LABEL}>Prompt</div>
          <div className="whitespace-pre-wrap break-words rounded-lg border border-border/60 bg-card/40 px-3 py-2 text-sm">
            {automation.prompt}
          </div>
        </div>

        <div className="space-y-1.5">
          <div className={GROUP_LABEL}>Details</div>
          <dl className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border/60 bg-card/40">
            {agentRows.length > 0 && (
              <DetailRow label="Agent">
                {agentRows.map((row) => (
                  <span key={row.join('/')} className="block truncate">
                    {row.join(' · ')}
                  </span>
                ))}
              </DetailRow>
            )}
            <DetailRow label="Schedule">{publicScheduleSummary(automation)}</DetailRow>
            {automation.schedule_kind === 'recurring' && automation.timezone && (
              <DetailRow label="Time zone">{automation.timezone}</DetailRow>
            )}
            <DetailRow label="Next run">
              {!automation.enabled
                ? 'Paused'
                : automation.next_run_at
                  ? formatShareTime(automation.next_run_at)
                  : 'Not scheduled'}
            </DetailRow>
            <DetailRow label="Last run">
              <span className={lastRunTone}>{lastRunSummary(automation)}</span>
            </DetailRow>
          </dl>
        </div>
      </div>
    </div>
  );
}

export function SharedAutomationsView({
  token,
  project,
  selectedId,
  onSelect,
  openHref,
}: {
  token: string;
  project: PublicProjectSummary;
  /** The automation open beside the list (`?automation=`), if any. */
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** "Open in Vicoa" target for a signed-in viewer who owns the project. */
  openHref?: string | null;
}) {
  const [items, setItems] = useState<PublicAutomation[] | null>(null);
  const [error, setError] = useState<'gone' | 'error' | null>(null);

  const load = useCallback(async () => {
    try {
      const page = await fetchPublicAutomations(token);
      setItems(page.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ShareNotFoundError ? 'gone' : 'error');
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);
  useSharePoll(load, { intervalMs: POLL_IDLE_MS });

  // A deep link to an automation the link no longer carries opens the list.
  const selected = useMemo(
    () => (selectedId ? (items?.find((a) => a.id === selectedId) ?? null) : null),
    [items, selectedId],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ShareHeader openHref={openHref}>
        <div className="flex min-w-0 items-center gap-2">
          <ProjectIcon project={{ id: project.id, name: project.name, icon: project.icon }} className="size-4" />
          <h1 className="min-w-0 truncate font-mono text-sm font-normal">{project.name}</h1>
          <span className="min-w-0 truncate text-[11px] text-muted-foreground">
            {items ? `${items.length} automation${items.length === 1 ? '' : 's'}` : ''}
          </span>
        </div>
      </ShareHeader>

      {error === 'gone' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center text-sm text-muted-foreground">
          <p>This share is no longer available.</p>
          <p className="text-xs">The link may have been revoked or expired.</p>
        </div>
      ) : items === null ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
          {error === 'error' ? 'Could not load the automations. Try again in a moment.' : <Loader2 className="h-4 w-4 animate-spin" />}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted-foreground">
          No automations in this project yet.
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* With one open, the list narrows to a column beside it; on a
              phone the open one takes the whole pane and Close goes back. */}
          <div
            className={cn(
              'custom-scrollbar min-h-0 overflow-y-auto',
              selected ? 'hidden md:block md:w-80 md:shrink-0 md:border-r md:border-border/60' : 'flex-1',
            )}
          >
            <ul>
              {items.map((automation) => (
                <li key={automation.id}>
                  <AutomationRow
                    automation={automation}
                    selected={automation.id === selected?.id}
                    onSelect={() => onSelect(automation.id === selected?.id ? null : automation.id)}
                  />
                </li>
              ))}
            </ul>
            {error === 'error' && (
              <p className="px-3 py-2 text-center text-[11px] text-muted-foreground">
                Updates paused: connection problem.
              </p>
            )}
          </div>
          {selected && (
            <div className="min-w-0 flex-1">
              <AutomationDetail key={selected.id} automation={selected} onClose={() => onSelect(null)} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
