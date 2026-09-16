'use client';

import { useState } from 'react';
import { Gift, TriangleAlert, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import {
  bannerViewForStatus,
  checkForUpdates,
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
 * card and mounted just above the account row. The main process downloads a
 * newer version on its own, so this only appears once the update is ready and
 * asks for a single click: Install & Restart. A user-triggered failure (the
 * install itself, or a retry check) shows an error/retry card. Renders nothing
 * on web/SSR (null bridge → idle status) or in non-actionable states.
 */
export function SidebarUpdateCallout() {
  const status = useDesktopUpdateStatus();
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null);
  const [userActed, setUserActed] = useState(false);

  const view = bannerViewForStatus(status, dismissedVersion, userActed);
  if (!view) return null;

  const handleDismiss = () => {
    // A failed action hides by clearing the user-acted flag; a ready update
    // snoozes this exact version for the session (a newer one re-shows).
    if (view.kind === 'error') {
      setUserActed(false);
      return;
    }
    setDismissedVersion(view.version);
  };

  const install = () => {
    setUserActed(true);
    void quitAndInstallUpdate();
  };

  const retry = () => {
    // Re-check; main auto-downloads again on a hit.
    setUserActed(true);
    void checkForUpdates();
  };

  const isError = view.kind === 'error';

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
          {isError ? (
            <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-warning" />
          ) : (
            <Gift className="h-3.5 w-3.5 shrink-0 text-foreground" />
          )}
          <span className="truncate text-xs text-foreground">
            {isError ? 'Update failed' : 'Update available'}
          </span>
        </div>
        <button
          type="button"
          aria-label="Dismiss"
          onClick={handleDismiss}
          className="flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded text-muted-foreground/70 transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      <div className="flex flex-col gap-1">
        {descriptionLinesFor(view).map((line) => (
          <p key={line} className="text-[11px] leading-relaxed text-muted-foreground">
            {line}
          </p>
        ))}
      </div>

      {isError ? (
        <CalloutActions primaryLabel="Retry" onPrimary={retry} />
      ) : (
        <CalloutActions primaryLabel="Install & Restart" onPrimary={install} />
      )}
    </div>
  );
}

function descriptionLinesFor(view: UpdateBannerView): string[] {
  if (view.kind === 'error') return [simplifyErrorMessage(view.message)];
  return [`${formatVersion(view.version)} is ready to install.`, UPGRADE_WARNING];
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
