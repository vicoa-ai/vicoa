'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ExternalLink } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { rpcOpenPath, type OpenApp } from './rpc';
import { groupOpenApps, loadOpenApps, openErrorMessage } from './open-in-apps';
import { OpenAppIcon } from './open-in-app-icons';

/**
 * "Open in Finder / VS Code / Ghostty…" for a project path.
 *
 * The files live on the session's machine, not in the browser, so both halves
 * are daemon RPCs: `list-open-apps` reports what is actually installed *there*
 * (so a Linux machine offers Konsole and a Mac offers Finder, with no
 * platform branching here), and `open-path` launches it. The client never
 * sends a command — only an app id the daemon looks up in its own catalog.
 *
 * Two presentations share all of that: {@link OpenInMenu}, a menu of its own
 * for the files panel's toolbar, and {@link OpenInSubMenu}, a submenu to nest
 * inside the session's three-dot menu. Both render nothing when the machine
 * can't be reached or its daemon predates the `open-in` RPCs, so an old daemon
 * shows no dead affordance.
 */

export interface OpenInTarget {
  machineId: string | null;
  /** The session's project directory (the daemon expands a leading `~`). */
  cwd: string | null;
  /** Project-relative path to open. `''` (the default) is the project root. */
  path?: string;
}

/**
 * Loads the machine's app list and launches one. `apps` is null while loading
 * and when there is nothing to offer — callers render nothing in both cases.
 *
 * `onOpened` fires only on a confirmed launch, so a caller that controls menu
 * state can leave the menu open to show `error` instead of closing on failure.
 */
function useOpenIn({ machineId, cwd, path = '' }: OpenInTarget, onOpened: () => void) {
  const [apps, setApps] = useState<OpenApp[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Survives the async open: a menu unmounted mid-flight must not setState.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setApps(null);
    if (!machineId || !cwd) return;
    let cancelled = false;
    void loadOpenApps(machineId).then((loaded) => {
      if (!cancelled) setApps(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [machineId, cwd]);

  const openWith = useCallback(
    (appId: string) => {
      if (!machineId || !cwd) return;
      rpcOpenPath(machineId, cwd, path, appId)
        .then(() => {
          if (mounted.current) onOpened();
        })
        .catch((err: unknown) => {
          if (mounted.current) setError(openErrorMessage(err));
        });
    },
    [machineId, cwd, path, onOpened],
  );

  const groups = useMemo(() => groupOpenApps(apps ?? []), [apps]);
  const ready = !!machineId && !!cwd && !!apps && apps.length > 0;
  return { groups, ready, error, setError, openWith };
}

/** The app rows themselves, identical in a menu and in a submenu. */
function OpenInRows({
  groups,
  error,
  openWith,
}: {
  groups: ReturnType<typeof groupOpenApps>;
  error: string | null;
  openWith: (appId: string) => void;
}) {
  return (
    <>
      {groups.flatMap((group, index) => {
        const rows = group.apps.map((app) => (
          <DropdownMenuItem
            key={app.id}
            className="cursor-pointer gap-2.5 px-2 py-1 text-xs"
            // Held open deliberately: the launch is async, so closing on
            // select would swallow a failure with nowhere to report it. The
            // owning menu closes itself once the daemon confirms.
            onSelect={(event) => {
              event.preventDefault();
              openWith(app.id);
            }}
          >
            <OpenAppIcon app={app} />
            {app.label}
          </DropdownMenuItem>
        ));
        return index === 0
          ? rows
          : [<DropdownMenuSeparator key={`sep-${group.kind}`} />, ...rows];
      })}
      {error && (
        <div className="px-2 py-1.5 text-[11px] leading-snug text-red-600 dark:text-red-400">
          {error}
        </div>
      )}
    </>
  );
}

export interface OpenInMenuProps extends OpenInTarget {
  /** `labeled` shows "Open in ▾"; `icon` is a bare icon button for tight rows. */
  variant?: 'labeled' | 'icon';
  /** Tooltip text — say what will be opened, since the path isn't visible. */
  tooltip?: string;
  className?: string;
}

/** Standalone "Open in" control — the files panel's toolbar. */
export function OpenInMenu({
  machineId,
  cwd,
  path = '',
  variant = 'icon',
  tooltip = 'Open in…',
  className = '',
}: OpenInMenuProps) {
  const [open, setOpen] = useState(false);
  const onOpened = useCallback(() => setOpen(false), []);
  const { groups, ready, error, setError, openWith } = useOpenIn(
    { machineId, cwd, path },
    onOpened,
  );

  useEffect(() => {
    if (!open) setError(null);
  }, [open, setError]);

  if (!ready) return null;

  const trigger =
    variant === 'labeled' ? (
      <button
        type="button"
        aria-label={tooltip}
        className={`flex cursor-pointer items-center gap-1 rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground ${className}`}
      >
        <ExternalLink className="h-3.5 w-3.5" />
        Open in
        <ChevronDown className="h-3 w-3" />
      </button>
    ) : (
      <button
        type="button"
        aria-label={tooltip}
        className={`inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded p-0 text-muted-foreground hover:bg-muted hover:text-foreground ${className}`}
      >
        <ExternalLink className="h-4 w-4" />
      </button>
    );

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      {/* Own provider: this renders in the session header too, which sits
          outside the page's TooltipProvider. Nesting one is harmless. */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent
            side="bottom"
            className="border border-menu-border bg-menu text-menu-foreground shadow-md"
          >
            {tooltip}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <DropdownMenuContent align="end" className="min-w-[8.5rem] font-mono">
        <OpenInRows groups={groups} error={error} openWith={openWith} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * "Open in ▸" as a submenu, for nesting inside the session's three-dot menu —
 * the project directory is a session-level target, so it belongs with the rest
 * of the session's actions rather than in a second menu next door.
 *
 * Must be rendered inside a `DropdownMenuContent`; closing is left to the
 * parent menu, which Radix handles on a successful select.
 */
export function OpenInSubMenu({ machineId, cwd, path = '' }: OpenInTarget) {
  const noop = useCallback(() => {}, []);
  const { groups, ready, error, openWith } = useOpenIn({ machineId, cwd, path }, noop);

  if (!ready) return null;

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="cursor-pointer gap-2 px-2 py-1 text-xs">
        <ExternalLink className="h-3 w-3" />
        Open in
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="min-w-[8.5rem] font-mono">
        <OpenInRows groups={groups} error={error} openWith={openWith} />
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
