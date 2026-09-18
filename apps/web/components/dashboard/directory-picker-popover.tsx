"use client";

import { useState, useEffect, useRef } from "react";
import { Check, Folder, FolderOpen } from "lucide-react";

import { ProjectIcon } from "@/components/dashboard/task-ui";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { StartEllipsisText } from "@/components/ui/start-ellipsis-text";
import type { ProjectResponse } from "@/lib/backend-api";
import { getDesktopShellBridge } from "@/lib/desktop-shell";

/**
 * Popover-anchored project/folder picker for the new-session page. Trigger
 * card renders the current value; the popover holds, top to bottom, the
 * projects linked to a folder on the selected machine (newest activity
 * first), a path input for any other folder — a project's subfolder, or a
 * brand-new one the backend mints a project for on the first spawn — and, on
 * desktop, the native folder dialog. Closes on outside-click, Escape, or Enter
 * inside the input.
 *
 * Web equivalent of the mobile bottom sheet — anchored to the card so the
 * user keeps spatial context while editing (Notion / Linear convention).
 */
export interface DirectoryPickerProject {
  project: ProjectResponse;
  /** The project's linked folder on the selected machine. */
  path: string;
}

export interface DirectoryPickerPopoverProps {
  value: string;
  onChange: (value: string) => void;
  /** Projects linked to a folder on the selected machine, newest first
   * (the new-session picker). */
  projects?: DirectoryPickerProject[];
  /** The project `value` falls under, when any — its row shows the check. */
  selectedProjectId?: string | null;
  /** Plain folders to offer instead of / besides projects — the automation
   * editor and the project-directory link, where a project list is not the
   * point. */
  recentDirectories?: string[];
  disabled?: boolean;
  /** Card-style trigger rendered when the popover is closed. */
  children: React.ReactNode;
}

export function DirectoryPickerPopover({
  value,
  onChange,
  projects = [],
  selectedProjectId = null,
  recentDirectories = [],
  disabled,
  children,
}: DirectoryPickerPopoverProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset the draft whenever the popover opens or the external value changes
  // while closed — keeps the popover stateless across opens.
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  const commit = (next: string) => {
    const trimmed = next.trim();
    if (!trimmed) return;
    onChange(trimmed);
    setOpen(false);
  };

  const rowClass =
    // Match shadcn DropdownMenuItem's *actual* hover token —
    // `focus:bg-foreground/[0.06] dark:focus:bg-foreground/10` (Radix promotes
    // hover into focus on the menu items). On a plain <button> the equivalent
    // is `hover:bg-foreground/[0.06] dark:hover:bg-foreground/10` (+
    // focus-visible for keyboard nav).
    "flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 focus-visible:bg-foreground/10 focus-visible:outline-none cursor-pointer";

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild disabled={disabled}>
        {children}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="bottom"
        sideOffset={8}
        // Match the trigger card width so the popover reads as an inline
        // editor, AND lift it visually (thicker bordered, stronger shadow)
        // so it clearly sits apart from the trigger card rather than blending
        // in. Opens downward, flipping up on collision (Radix avoidCollisions).
        className="w-[max(var(--radix-popover-trigger-width),20rem)] rounded-xl p-3 space-y-3 border border-foreground/15 bg-menu shadow-xl"
        // Radix's default auto-focus would land on the first project row (or
        // select-all the input). Focus the input with the cursor at the end
        // instead: the list is one click away, and a typed path is the other
        // half of the picker.
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          const input = inputRef.current;
          if (input) {
            input.focus({ preventScroll: true });
            const len = input.value.length;
            input.setSelectionRange(len, len);
          }
        }}
      >
        {projects.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[11px] text-muted-foreground font-mono">
              Projects
            </div>
            <div className="space-y-0.5 max-h-60 overflow-y-auto custom-scrollbar pr-1">
              {projects.map(({ project, path }) => {
                const selected = project.id === selectedProjectId;
                return (
                  <button
                    key={project.id}
                    type="button"
                    onClick={() => commit(path)}
                    className={rowClass}
                    title={path}
                  >
                    <ProjectIcon project={project} className="size-3.5" />
                    <span className="max-w-[45%] shrink-0 truncate text-xs">{project.name}</span>
                    <StartEllipsisText
                      value={path}
                      className="min-w-0 flex-1 text-[10px] font-mono text-muted-foreground"
                    />
                    {selected && <Check className="h-3 w-3 flex-shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {recentDirectories.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[11px] text-muted-foreground font-mono">
              Recent
            </div>
            <div className="space-y-0.5 max-h-60 overflow-y-auto custom-scrollbar pr-1">
              {recentDirectories.map((path) => (
                <button
                  key={path}
                  type="button"
                  onClick={() => commit(path)}
                  className={rowClass}
                  title={path}
                >
                  <Folder className="h-3 w-3 flex-shrink-0" />
                  <StartEllipsisText value={path} className="min-w-0 flex-1 text-[11px] font-mono" />
                  {path === value && <Check className="h-3 w-3 flex-shrink-0" />}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <div className="text-[11px] text-muted-foreground font-mono">
            Folder
          </div>
          <Input
            ref={inputRef}
            value={draft}
            placeholder="~/projects/my-app"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit(draft);
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setOpen(false);
              }
            }}
            // Borderless: the field reads as editable through its darker
            // inset surface against the --menu popover instead of a border.
            className="font-mono text-xs md:text-xs h-8 rounded-md border-0 bg-foreground/5 shadow-none focus-visible:ring-0 focus-visible:border-0"
          />
        </div>

        {/* Native folder picker — desktop app only (browsers can't hand a
            real filesystem path to the page). */}
        {getDesktopShellBridge() !== null && (
          <div>
            <div className="-mx-3 mb-1.5 h-px bg-border" />
            <button
              type="button"
              onClick={() => {
                void getDesktopShellBridge()?.pickFolder().then((path) => {
                  if (path) commit(path);
                });
              }}
              className="flex w-full items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-[11px] font-mono text-popover-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 focus-visible:bg-foreground/10 focus-visible:outline-none cursor-pointer"
            >
              <FolderOpen className="h-3 w-3 flex-shrink-0" />
              Open folder…
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
