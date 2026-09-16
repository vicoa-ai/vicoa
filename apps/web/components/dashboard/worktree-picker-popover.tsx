"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GitBranch, Plus, Check, Loader2 } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import {
  rpcGitWorktreeCheckName,
  rpcGitWorktreeList,
  type WorktreeInfo,
  type WorktreeNameCheck,
} from "@/components/files-git-panel/rpc";
import { validateWorktreeName, type WorktreeMode } from "@/lib/worktree-selection";

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
 *
 * With `nameSupported`, "New worktree" also unfolds a name field: the name is
 * the branch (and the worktree's folder), blank means the daemon's random
 * slug. Format is checked locally as the user types; whether the name is
 * free is the daemon's call (`git-worktree-check-name`, debounced), which
 * also offers the first free `-2`/`-3` suffix when it's taken.
 */
export interface WorktreePickerPopoverProps {
  machineId: string;
  cwd: string;
  mode: WorktreeMode;
  selectedPath: string | null;
  /**
   * `name` is only meaningful for `mode === "new"`: the user's branch name,
   * or empty for a random one. Other modes always pass it empty.
   */
  onSelect: (
    mode: WorktreeMode,
    path: string | null,
    branch?: string | null,
    name?: string,
  ) => void;
  /** Show the name field under "New worktree" (daemon capability `worktree-name`). */
  nameSupported?: boolean;
  /** The committed name for a new worktree, echoed back into the field. */
  newName?: string;
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

const NAME_CHECK_DEBOUNCE_MS = 300;

export function WorktreePickerPopover({
  machineId,
  cwd,
  mode,
  selectedPath,
  onSelect,
  nameSupported = false,
  newName = "",
  disabled,
  side = "bottom",
  children,
}: WorktreePickerPopoverProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([]);

  // Name field: unfolded under "New worktree" while the popover is open. The
  // draft lives here until committed (Enter / ✓ / closing the popover with a
  // valid draft), so a half-typed name never reaches the chip.
  const [nameOpen, setNameOpen] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [checking, setChecking] = useState(false);
  // The daemon's verdict on the exact draft it was asked about — stale once
  // the draft moves on, so it's keyed by name rather than cleared eagerly.
  const [nameCheck, setNameCheck] = useState<
    { name: string; result: WorktreeNameCheck | "error" } | null
  >(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const checkSeqRef = useRef(0);

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
  // created by prior sessions. A "new" selection reopens with its name field
  // unfolded so the committed name is right there to edit.
  useEffect(() => {
    if (!open) return;
    void load();
    setNameDraft(newName);
    setNameOpen(nameSupported && mode === "new");
    setNameCheck(null);
    // Only the open transition should seed the draft — not every keystroke's
    // parent re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, load]);

  useEffect(() => {
    if (nameOpen) nameInputRef.current?.focus({ preventScroll: true });
  }, [nameOpen]);

  const trimmedDraft = nameDraft.trim();
  const formatError = validateWorktreeName(nameDraft);
  const verdict = nameCheck?.name === trimmedDraft ? nameCheck.result : null;
  const taken = verdict !== null && verdict !== "error" && !verdict.available;
  const nameCommittable = !formatError && !taken;

  // Ask the daemon whether a well-formed, non-empty draft is free. Debounced
  // per keystroke; a sequence number drops answers to drafts already left.
  useEffect(() => {
    if (!nameOpen || !trimmedDraft || formatError || !machineId || !cwd.trim()) {
      setChecking(false);
      return;
    }
    const seq = ++checkSeqRef.current;
    setChecking(true);
    const timer = setTimeout(async () => {
      let result: WorktreeNameCheck | "error";
      try {
        result = await rpcGitWorktreeCheckName(machineId, cwd.trim(), trimmedDraft);
      } catch {
        result = "error";
      }
      if (seq !== checkSeqRef.current) return;
      setNameCheck({ name: trimmedDraft, result });
      setChecking(false);
    }, NAME_CHECK_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [nameOpen, trimmedDraft, formatError, machineId, cwd]);

  const select = (m: WorktreeMode, path: string | null, branch?: string | null) => {
    onSelect(m, path, branch, "");
    setOpen(false);
  };

  const commitName = () => {
    if (!nameCommittable) return;
    onSelect("new", null, null, trimmedDraft);
    setOpen(false);
  };

  const chooseNew = () => {
    if (!nameSupported) {
      select("new", null);
      return;
    }
    // Switch the chip to "New worktree" right away (keeping whatever name was
    // committed before) and unfold the field; the popover stays open so the
    // user can type a name — or just click away for a random one.
    onSelect("new", null, null, newName);
    setNameOpen(true);
    nameInputRef.current?.focus({ preventScroll: true });
  };

  const handleOpenChange = (next: boolean) => {
    if (disabled) return;
    // Closing with the name field unfolded commits a valid draft so a typed
    // name isn't lost to an outside click; an invalid or taken one is dropped
    // and the previously committed name stands.
    if (!next && nameOpen && mode === "new" && nameCommittable && trimmedDraft !== newName) {
      onSelect("new", null, null, trimmedDraft);
    }
    setOpen(next);
  };

  const isRepo = error !== "not_a_repo";

  const nameStatus = (() => {
    if (formatError) return { tone: "error" as const, text: formatError };
    if (!trimmedDraft) return null;
    if (verdict === "error") return { tone: "muted" as const, text: "Couldn't check availability" };
    if (verdict && !verdict.available) {
      return {
        tone: "error" as const,
        text: verdict.reason === "name_taken" ? "Already exists" : "Not a valid branch name",
        suggestion: verdict.suggestion,
      };
    }
    return null;
  })();

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
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
            onClick={chooseNew}
            className="flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 cursor-pointer"
          >
            <Plus className="h-3 w-3 flex-shrink-0" />
            <span className="flex-1 text-left">New worktree</span>
            {mode === "new" && <Check className="h-3 w-3 flex-shrink-0" />}
          </button>
        )}

        {isRepo && nameSupported && nameOpen && (
          <div className="space-y-1 pl-2.5">
            {/* Borderless field on an inset surface, matching DirectoryPickerPopover. */}
            <div className="flex items-center gap-2 rounded-md bg-foreground/5 px-2">
              <Input
                ref={nameInputRef}
                value={nameDraft}
                placeholder="Branch name, empty for random"
                spellCheck={false}
                autoCapitalize="off"
                autoCorrect="off"
                aria-invalid={nameStatus?.tone === "error" || undefined}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    commitName();
                  }
                  // Escape folds the field first (mode stays "new"); a second
                  // Escape closes the popover.
                  if (e.key === "Escape") {
                    e.preventDefault();
                    e.stopPropagation();
                    setNameOpen(false);
                  }
                }}
                className="h-8 border-0 bg-transparent px-0 font-mono text-xs md:text-xs shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-0 focus-visible:border-0 aria-invalid:ring-0 aria-invalid:border-0"
              />
              {checking ? (
                <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin text-muted-foreground" />
              ) : (
                <button
                  type="button"
                  onClick={commitName}
                  disabled={!nameCommittable}
                  title="Use this name"
                  className="flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground cursor-pointer disabled:cursor-not-allowed"
                >
                  <Check className="h-3 w-3" />
                </button>
              )}
            </div>
            {nameStatus && (
              <div
                className={
                  nameStatus.tone === "error"
                    ? "px-2 text-[11px] font-mono text-destructive"
                    : "px-2 text-[11px] font-mono text-muted-foreground"
                }
              >
                {nameStatus.text}
                {nameStatus.suggestion && (
                  <>
                    {" · "}
                    <button
                      type="button"
                      onClick={() => setNameDraft(nameStatus.suggestion ?? "")}
                      className="underline cursor-pointer"
                    >
                      use {nameStatus.suggestion}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
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
