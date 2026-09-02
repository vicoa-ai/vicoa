'use client';

import { useState } from 'react';
import { Gift, Loader2, RotateCw, TriangleAlert, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import {
  bannerViewForStatus,
  checkForUpdates,
  downloadUpdate,
  quitAndInstallUpdate,
  useDesktopUpdateStatus,
  type UpdateBannerView,
} from '@/lib/desktop-updates';

const CHANGELOG_URL = `${process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai'}/docs/changelog`;

const UPGRADE_WARNING =
  'Upgrading the app will stop running agents and close terminal sessions.';

/** `1.2.3` / `v1.2.3` → `v1.2.3` (single, normalized prefix). */
function formatVersion(version: string): string {
  return `v${version.replace(/^v/i, '')}`;
}

/**
 * Collapse electron-updater's verbose failures into one actionable line. The
 * read-only-volume error (running from Downloads / a mounted DMG) repeats
 * itself three times upstream; everything else falls through unchanged.
 */
function simplifyErrorMessage(message: string): string {
  if (/read-only volume/i.test(message)) {
    return "Vicoa can't update while running from a read-only location. Move it to your Applications folder and try again.";
  }
  return message || 'Something went wrong.';
}

function openChangelog() {
  // Route through the shell bridge so the changelog opens in the user's real
  // browser instead of hijacking the desktop window's dashboard route.
  void getDesktopAuthBridge()?.openExternal(CHANGELOG_URL);
}

/**
 * Sidebar callout for the desktop auto-updater, styled after Paseo's sidebar
 * card and mounted just above the account row. Reuses the exact status/logic of
 * the former top-of-window banner (see lib/desktop-updates): detect → Install &
 * Restart → progress → Restart, with a user-triggered error/retry path. Renders
 * nothing on web/SSR (null bridge → idle status) or in non-actionable states.
 */
export function SidebarUpdateCallout() {
  const status = useDesktopUpdateStatus();
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null);
  const [userActed, setUserActed] = useState(false);

  const view = bannerViewForStatus(status, dismissedVersion, userActed);
  if (!view) return null;

  const handleDismiss = () => {
    // A failed check hides by clearing the user-acted flag; available/downloaded
    // snooze this exact version for the session (a newer one re-shows).
    if (view.kind === 'error') {
      setUserActed(false);
      return;
    }
    if (status.state === 'available' || status.state === 'downloaded') {
      setDismissedVersion(status.version);
    }
  };

  const startDownload = () => {
    setUserActed(true);
    void downloadUpdate();
  };

  const retry = () => {
    setUserActed(true);
    void checkForUpdates();
  };

  const isError = view.kind === 'error';
  const dismissible = view.kind !== 'downloading';
  const descriptionLines = descriptionLinesFor(view);

  return (
    <div
      role="alert"
      data-testid="sidebar-update-callout"
      className={cn(
        'flex flex-col gap-2 border-t px-3 py-3',
        isError ? 'border-amber-500/40' : 'border-border',
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <CalloutIcon kind={view.kind} />
          <span className="truncate text-xs text-foreground">{titleFor(view)}</span>
        </div>
        {dismissible && (
          <button
            type="button"
            aria-label="Dismiss"
            onClick={handleDismiss}
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground/70 transition-colors hover:bg-foreground/10 hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {descriptionLines.length > 0 && (
        <div className="flex flex-col gap-1">
          {descriptionLines.map((line) => (
            <p key={line} className="text-[11px] leading-relaxed text-muted-foreground">
              {line}
            </p>
          ))}
        </div>
      )}

      {view.kind === 'downloading' && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-foreground/15">
            <div
              className="h-full rounded-full bg-foreground transition-[width] duration-300"
              style={{ width: `${view.percent}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
            {Math.round(view.percent)}%
          </span>
        </div>
      )}

      {view.kind === 'available' && (
        <CalloutActions primaryLabel="Install & Restart" onPrimary={startDownload} />
      )}
      {view.kind === 'downloaded' && (
        <CalloutActions primaryLabel="Restart" onPrimary={() => void quitAndInstallUpdate()} />
      )}
      {view.kind === 'error' && <CalloutActions primaryLabel="Retry" onPrimary={retry} />}
    </div>
  );
}

function CalloutIcon({ kind }: { kind: UpdateBannerView['kind'] }) {
  const className = 'h-3.5 w-3.5 shrink-0';
  switch (kind) {
    case 'downloading':
      return <Loader2 className={cn(className, 'animate-spin text-muted-foreground')} />;
    case 'downloaded':
      return <RotateCw className={cn(className, 'text-foreground')} />;
    case 'error':
      return <TriangleAlert className={cn(className, 'text-warning')} />;
    default:
      return <Gift className={cn(className, 'text-foreground')} />;
  }
}

function titleFor(view: UpdateBannerView): string {
  switch (view.kind) {
    case 'downloading':
      return 'Downloading update';
    case 'downloaded':
      return 'Update ready';
    case 'error':
      return 'Update failed';
    default:
      return 'Update available';
  }
}

function descriptionLinesFor(view: UpdateBannerView): string[] {
  switch (view.kind) {
    case 'downloading':
      // Progress is conveyed by the bar + percentage, not prose.
      return [];
    case 'downloaded':
      return [`${formatVersion(view.version)} is ready to install.`, UPGRADE_WARNING];
    case 'error':
      return [simplifyErrorMessage(view.message)];
    default:
      return [`${formatVersion(view.version)} is ready to install.`, UPGRADE_WARNING];
  }
}

/** What's New (bordered secondary) + the state's primary action, two equal columns. */
function CalloutActions({
  primaryLabel,
  onPrimary,
}: {
  primaryLabel: string;
  onPrimary: () => void;
}) {
  return (
    <div className="flex gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={openChangelog}
        className="h-7 flex-1 text-xs font-normal"
      >
        What&apos;s New
      </Button>
      <Button
        variant="default"
        size="sm"
        onClick={onPrimary}
        className="h-7 flex-1 text-xs font-normal shadow-none bg-foreground text-background hover:bg-foreground/90 hover:text-background"
      >
        {primaryLabel}
      </Button>
    </div>
  );
}
