"use client";

import { useState, useEffect, useRef } from "react";
import { Check, Folder, FolderOpen } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { StartEllipsisText } from "@/components/ui/start-ellipsis-text";
import { getDesktopShellBridge } from "@/lib/desktop-shell";

/**
 * Popover-anchored directory picker. Trigger card renders the current value;
 * popover holds the input + a scrollable list of recent directories. Closes
 * on outside-click, Escape, or Enter inside the input.
 *
 * Web equivalent of the mobile bottom sheet — anchored to the card so the
 * user keeps spatial context while editing (Notion / Linear convention).
 */
export interface DirectoryPickerPopoverProps {
  value: string;
  onChange: (value: string) => void;
  recentDirectories: string[];
  disabled?: boolean;
  /** Card-style trigger rendered when the popover is closed. */
  children: React.ReactNode;
}

export function DirectoryPickerPopover({
  value,
  onChange,
  recentDirectories,
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
        className="w-[max(var(--radix-popover-trigger-width),18rem)] rounded-xl p-3 space-y-3 border border-foreground/15 bg-[#2D2D2D] shadow-xl"
        // Radix's default auto-focus triggers the browser's "select-all"
        // behavior on inputs containing existing text. Prevent it and place
        // the cursor at the end instead — the user is almost always editing,
        // not replacing, the path.
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
        <div className="space-y-1.5">
          <div className="text-[11px] text-muted-foreground font-mono">
            Project
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
            // inset surface against the #2D2D2D popover instead of a border.
            className="font-mono text-xs md:text-xs h-8 rounded-md border-0 bg-black/25 dark:bg-black/25 shadow-none focus-visible:ring-0 focus-visible:border-0"
          />
        </div>

        {recentDirectories.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[11px] text-muted-foreground font-mono">
              Recent
            </div>
            <div className="space-y-1 max-h-60 overflow-y-auto custom-scrollbar pr-1">
              {recentDirectories.map((path) => (
                <button
                  key={path}
                  type="button"
                  onClick={() => commit(path)}
                  // Match shadcn DropdownMenuItem's *actual* hover token —
                  // `focus:bg-foreground/10` (Radix promotes hover into
                  // focus on the menu items). On a plain <button> the
                  // equivalent is `hover:bg-foreground/10` (+ focus-visible
                  // for keyboard nav). bg-accent looked identical to the
                  // popover BG in this theme, so the hover wasn't visible.
                  className="flex w-full items-center gap-1.5 rounded-sm px-2.5 py-1 text-[11px] text-popover-foreground transition-colors hover:bg-foreground/10 focus-visible:bg-foreground/10 focus-visible:outline-none cursor-pointer"
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
              className="flex w-full items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-[11px] font-mono text-popover-foreground transition-colors hover:bg-foreground/10 focus-visible:bg-foreground/10 focus-visible:outline-none cursor-pointer"
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
