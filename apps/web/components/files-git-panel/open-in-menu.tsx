'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Code, ExternalLink, FolderOpen, Terminal } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { rpcOpenPath, type OpenApp, type OpenAppKind } from './rpc';
import { groupOpenApps, loadOpenApps, openErrorMessage } from './open-in-apps';

/**
 * "Open in Finder / VS Code / Ghostty…" for a project path.
 *
 * The files live on the session's machine, not in the browser, so both halves
 * are daemon RPCs: `list-open-apps` reports what is actually installed *there*
 * (so a Linux machine offers Konsole and a Mac offers Finder, with no
 * platform branching here), and `open-path` launches it. The client never
 * sends a command — only an app id the daemon looks up in its own catalog.
 *
 * Renders nothing at all when the machine can't be reached or its daemon
 * predates the `open-in` RPCs, so an old daemon shows no dead affordance.
 */

const KIND_ICON: Record<OpenAppKind, typeof FolderOpen> = {
  'file-manager': FolderOpen,
  editor: Code,
  terminal: Terminal,
};

export interface OpenInMenuProps {
  machineId: string | null;
  /** The session's project directory (the daemon expands a leading `~`). */
  cwd: string | null;
  /** Project-relative path to open. `''` (the default) is the project root. */
  path?: string;
  /** `labeled` shows "Open in ▾"; `icon` is a bare icon button for tight rows. */
  variant?: 'labeled' | 'icon';
  /** Tooltip text — say what will be opened, since the path isn't visible. */
  tooltip?: string;
  className?: string;
}

export function OpenInMenu({
  machineId,
  cwd,
  path = '',
  variant = 'icon',
  tooltip = 'Open in…',
  className = '',
}: OpenInMenuProps) {
  const [apps, setApps] = useState<OpenApp[] | null>(null);
  const [open, setOpen] = useState(false);
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

  useEffect(() => {
    if (!open) setError(null);
  }, [open]);

  const groups = useMemo(() => groupOpenApps(apps ?? []), [apps]);

  const handleOpen = useCallback(
    (appId: string) => {
      if (!machineId || !cwd) return;
      rpcOpenPath(machineId, cwd, path, appId)
        .then(() => {
          if (mounted.current) setOpen(false);
        })
        .catch((err: unknown) => {
          if (mounted.current) setError(openErrorMessage(err));
        });
    },
    [machineId, cwd, path],
  );

  if (!machineId || !cwd || !apps || apps.length === 0) return null;

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
      <DropdownMenuContent align="end" className="min-w-[11rem] font-mono">
        {groups.flatMap((group, index) => {
          const Icon = KIND_ICON[group.kind];
          const rows = group.apps.map((app) => (
            <DropdownMenuItem
              key={app.id}
              className="cursor-pointer text-xs"
              // Held open deliberately: the launch is async, so closing on
              // select would swallow a failure with nowhere to report it.
              // `handleOpen` closes the menu itself once the daemon confirms.
              onSelect={(event) => {
                event.preventDefault();
                handleOpen(app.id);
              }}
            >
              <Icon className="h-3.5 w-3.5" />
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
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
