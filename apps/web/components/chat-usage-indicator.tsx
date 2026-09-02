'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { SessionUsage, SessionUsageWindow } from '@/lib/backend-api';
import {
  deriveUsageView,
  formatCost,
  formatReset,
  formatTokens,
} from '@/lib/usage-view';

/**
 * Compact context-window ring + usage popover for the chat composer.
 *
 * The ring shows the per-conversation context fill (used / max tokens); the
 * popover breaks out the account's session/weekly rate-limit windows and any
 * credit balance. Data comes in-band from the agent (Claude + Codex) via
 * `instance_metadata.usage` — see plans/todos/usage-indicators.md.
 *
 * The in-band rate-limit windows only refresh when a turn completes, so they
 * go stale (or never appear) on idle sessions. When `fetchLimits` is provided
 * (Claude sessions with a reachable machine), opening the popover fetches a
 * fresh snapshot from the machine's daemon and overlays it; `fetchOnMount`
 * additionally fetches as soon as the component mounts — used on the
 * new-session page, where there is no session (and no in-band usage) yet.
 *
 * Renders nothing until there's something worth showing, so the composer stays
 * clean for agents/sessions that don't report usage. Presentation logic lives
 * in `lib/usage-view.ts` (unit-tested); this file is rendering only.
 */

// Client-side spacing between daemon fetches. The daemon caches for 30s too;
// this just avoids pointless RPC round-trips on rapid popover toggling.
const FETCH_INTERVAL_MS = 30_000;

// The indicator is intentionally monochrome: the ring and every meter use one
// neutral tone regardless of fill, so a high context/limit reading never turns
// the composer amber or red.
function Ring({ pct, size = 14 }: { pct: number; size?: number }) {
  const r = size / 2 - 1.5;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={1.5}
        className="stroke-foreground/15"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={1.5}
        strokeLinecap="round"
        className="stroke-muted-foreground"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - clamped / 100)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

function WindowBar({ window }: { window: SessionUsageWindow }) {
  const pct = Math.max(0, Math.min(100, window.used_pct));
  const reset = formatReset(window.resets_at);
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="text-muted-foreground">{window.label}</span>
        <span className="flex items-baseline gap-1.5">
          <span className="text-muted-foreground">{Math.round(pct)}%</span>
          {reset && <span className="text-muted-foreground/60">{reset}</span>}
        </span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-foreground/10">
        <div className="h-full rounded-full bg-muted-foreground" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export interface ChatUsageIndicatorProps {
  usage?: SessionUsage | null;
  /** Fetches fresh rate-limit windows from the machine's daemon; null = keep stale. */
  fetchLimits?: () => Promise<SessionUsageWindow[] | null>;
  /** Also fetch immediately on mount (new-session page: no in-band usage exists). */
  fetchOnMount?: boolean;
}

export function ChatUsageIndicator({
  usage,
  fetchLimits,
  fetchOnMount = false,
}: ChatUsageIndicatorProps) {
  const [open, setOpen] = useState(false);
  // Fresh windows from the daemon override the (possibly stale) in-band ones.
  const [freshWindows, setFreshWindows] = useState<SessionUsageWindow[] | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const lastFetchAtRef = useRef(0);

  // No cancellation on purpose: under dev StrictMode the mount effect runs
  // twice, and cancelling run #1 while the throttle blocks run #2 discarded
  // the only fetch — leaving the indicator permanently hidden on the
  // new-session page. A late resolution is harmless (React 18 no-ops setState
  // after unmount, and machine switches remount via `key`).
  const refreshLimits = useCallback(() => {
    if (!fetchLimits) return;
    const now = Date.now();
    if (now - lastFetchAtRef.current < FETCH_INTERVAL_MS) return;
    lastFetchAtRef.current = now;
    setIsFetching(true);
    void fetchLimits()
      .then((windows) => {
        if (windows) setFreshWindows(windows);
      })
      .finally(() => {
        setIsFetching(false);
      });
  }, [fetchLimits]);

  useEffect(() => {
    if (fetchOnMount) refreshLimits();
  }, [fetchOnMount, refreshLimits]);

  const effectiveUsage = useMemo<SessionUsage | null | undefined>(() => {
    if (!freshWindows) return usage;
    return {
      ...(usage ?? {}),
      limits: {
        windows: freshWindows,
        credits: usage?.limits?.credits ?? null,
      },
    };
  }, [usage, freshWindows]);

  const view = useMemo(() => deriveUsageView(effectiveUsage), [effectiveUsage]);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) refreshLimits();
  };

  if (!view.hasAnything) return null;

  // What the collapsed chip shows: prefer the context ring, else the tightest limit.
  const triggerPct = view.contextPct ?? view.tightest;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title="Usage"
          // Circular icon-button shape so the click/hover highlight matches
          // the neighbouring interrupt / send icon buttons.
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted-foreground/10 hover:text-foreground"
        >
          {triggerPct !== null ? (
            <Ring pct={triggerPct} size={18} />
          ) : view.context ? (
            <span className="text-xs">{formatTokens(view.context.used_tokens)}</span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        className="w-72 space-y-3 p-3 font-mono text-xs bg-menu border-foreground/15 shadow-xl rounded-xl"
      >
        <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground/60">
          <span>Usage</span>
          {isFetching && <span>Refreshing…</span>}
        </div>
        {view.context && (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-foreground">Context window</span>
              {view.contextPct !== null && (
                <span className="text-muted-foreground">
                  {Math.round(view.contextPct)}%
                </span>
              )}
            </div>
            {view.contextPct !== null && (
              <div className="h-1 w-full overflow-hidden rounded-full bg-foreground/10">
                <div
                  className="h-full rounded-full bg-muted-foreground"
                  style={{ width: `${view.contextPct}%` }}
                />
              </div>
            )}
            <div className="flex items-baseline justify-between gap-2 text-muted-foreground">
              <span>
                {formatTokens(view.context.used_tokens)}
                {view.context.max_tokens ? ` / ${formatTokens(view.context.max_tokens)} tokens` : ' tokens'}
              </span>
              {view.context.cost_usd != null && (
                <span className="text-muted-foreground/70">Session cost {formatCost(view.context.cost_usd)}</span>
              )}
            </div>
          </div>
        )}

        {view.windows.length > 0 && (
          <div className="space-y-2 border-t border-foreground/10 pt-3">
            {view.windows.map((w) => (
              <WindowBar key={w.id} window={w} />
            ))}
          </div>
        )}

        {view.credits && (
          <div className="flex items-baseline justify-between gap-2 border-t border-foreground/10 pt-3">
            <span className="text-muted-foreground">Credits</span>
            <span className="text-foreground">${view.credits.remaining.toFixed(2)} left</span>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
