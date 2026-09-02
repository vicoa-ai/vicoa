"use client";

import { useCallback, useEffect, useState } from "react";
import { GitBranch, Plus, Check, Loader2 } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  rpcGitWorktreeList,
  type WorktreeInfo,
} from "@/components/files-git-panel/rpc";
import { type WorktreeMode } from "@/lib/worktree-selection";

/**
 * Popover-anchored worktree picker for the new-session page — the web
 * equivalent of the mobile worktree bottom sheet. Lets the user run in the
 * current branch, fork a new worktree, or reuse an existing one.
 *
 * Removal lives on the sidebar now (right-click a worktree group), not here —
 * this picker is purely about choosing where a new session runs.
 *
 * Fetches the repo's worktrees on open; a non-git directory degrades to just
 * "Current branch". Selection closes the popover.
 */
export interface WorktreePickerPopoverProps {
  machineId: string;
  cwd: string;
  mode: WorktreeMode;
  selectedPath: string | null;
  onSelect: (mode: WorktreeMode, path: string | null, branch?: string | null) => void;
  disabled?: boolean;
  /**
   * Which side of the trigger the popover opens on. Defaults to `"bottom"`
   * (the automation editor, where the chip sits high in a form). The
   * new-session page pins its setup chips to the bottom of the viewport and so
   * passes `"top"` to always open the list upward.
   */
  side?: "top" | "bottom";
  children: React.ReactNode;
}

export function WorktreePickerPopover({
  machineId,
  cwd,
  mode,
  selectedPath,
  onSelect,
  disabled,
  side = "bottom",
  children,
}: WorktreePickerPopoverProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([]);

  const load = useCallback(async () => {
    if (!machineId || !cwd.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const list = await rpcGitWorktreeList(machineId, cwd.trim());
      setWorktrees(list);
    } catch (e) {
      setError(e instanceof Error ? (e as { code?: string }).code ?? e.message : "error");
      setWorktrees([]);
    } finally {
      setLoading(false);
    }
  }, [machineId, cwd]);

  // (Re)fetch each time the popover opens so the list reflects worktrees
  // created by prior sessions.
  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const select = (m: WorktreeMode, path: string | null, branch?: string | null) => {
    onSelect(m, path, branch);
    setOpen(false);
  };

  const isRepo = error !== "not_a_repo";

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild disabled={disabled}>
        {children}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side={side}
        sideOffset={8}
        className="w-[max(var(--radix-popover-trigger-width),18rem)] rounded-xl p-3 space-y-2 border border-foreground/15 bg-menu shadow-xl"
      >
        <div className="text-[11px] text-muted-foreground font-mono">
          Worktree
        </div>

        <button
          type="button"
          onClick={() => select("none", null)}
          className="flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 cursor-pointer"
        >
          <GitBranch className="h-3 w-3 flex-shrink-0" />
          <span className="flex-1 text-left">Current branch</span>
          {mode === "none" && <Check className="h-3 w-3 flex-shrink-0" />}
        </button>

        {isRepo && (
          <button
            type="button"
            onClick={() => select("new", null)}
            className="flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 cursor-pointer"
          >
            <Plus className="h-3 w-3 flex-shrink-0" />
            <span className="flex-1 text-left">New worktree</span>
            {mode === "new" && <Check className="h-3 w-3 flex-shrink-0" />}
          </button>
        )}

        {loading && (
          <div className="flex items-center justify-center py-3 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          </div>
        )}

        {!loading && error === "not_a_repo" && (
          <div className="px-2.5 py-2 text-[11px] text-muted-foreground font-mono">
            Not a git repository — only the current branch is available.
          </div>
        )}

        {!loading && error && error !== "not_a_repo" && (
          <div className="px-2.5 py-1.5 text-[11px] font-mono">
            <span className="text-destructive">Couldn&apos;t load worktrees. </span>
            <button type="button" onClick={load} className="underline cursor-pointer">
              Retry
            </button>
          </div>
        )}

        {!loading && !error && worktrees.length > 0 && (
          <div className="space-y-1 pt-1">
            <div className="text-[11px] text-muted-foreground font-mono px-2.5">Existing</div>
            <div className="space-y-1 max-h-56 overflow-y-auto custom-scrollbar pr-1">
              {worktrees.map((wt) => {
                const isSelected = mode === "existing" && selectedPath === wt.path;
                return (
                  <div
                    key={wt.path}
                    className="flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-[11px] hover:bg-foreground/[0.06] dark:hover:bg-foreground/10"
                  >
                    <button
                      type="button"
                      onClick={() => select("existing", wt.path, wt.branch)}
                      className="flex min-w-0 flex-1 items-center gap-1.5 text-left cursor-pointer"
                      title={wt.path}
                    >
                      <GitBranch className="h-3 w-3 flex-shrink-0" />
                      <span className="font-mono truncate">
                        {wt.branch || "(detached)"}
                      </span>
                      {isSelected && <Check className="h-3 w-3 flex-shrink-0" />}
                    </button>
                    {!wt.managed && (
                      <span className="text-[10px] text-muted-foreground/60 font-mono">ext</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
