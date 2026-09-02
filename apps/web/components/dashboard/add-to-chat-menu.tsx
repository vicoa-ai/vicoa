'use client';

import type { ReactNode } from 'react';
import { Plus, AtSign, Paperclip, FolderPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

/** An additional "+" menu row, e.g. contributed by a plugin. */
export interface AddToChatExtraItem {
  id: string;
  label: string;
  /** Pre-rendered icon node so this component stays plugin-agnostic. */
  icon?: ReactNode;
  onSelect: () => void;
}

/**
 * "+" (Add to chat) affordance shared by the chat input and the new-session
 * prompt — the web counterpart of the mobile `showAddToChatMenu` bottom sheet
 * (`vicoa-app/.../components/add_to_chat_sheet.dart`).
 *
 * Tapping the button opens a small dropdown panel (styled like the gear's
 * session-config panel) with two actions whose only job is to insert a trigger
 * character into the message box so the existing mention / slash panels surface:
 *   - "Mention files" inserts "@"
 *   - "Skills or Commands" / "Commands" inserts "/"
 *
 * The actual insertion + panel-opening lives in the parent (it owns the
 * textarea + draft state); this component just renders the menu and forwards
 * the two callbacks.
 */
export function AddToChatMenu({
  onAddFiles,
  onAddFolder,
  onMentionFiles,
  onCommands,
  hasSkills,
  disabled,
  extraItems,
}: {
  // Opens the system file picker for attachments (images or any other file).
  // Optional — surfaces without an instance to upload against omit it.
  onAddFiles?: () => void;
  // Opens the native OS folder picker and references the chosen folder by path
  // (the agent reads it in place — no upload). Desktop app only: the browser
  // can't hand a real filesystem path to the page, so callers omit this on web.
  onAddFolder?: () => void;
  onMentionFiles: () => void;
  onCommands: () => void;
  // Claude / OpenCode surface both skills and commands through the same slash
  // trigger ("Skills or Commands"); Codex (and ACP agents) only have commands.
  hasSkills: boolean;
  disabled?: boolean;
  // Extra rows contributed by plugins (Tier 1 composer actions, placement "menu").
  extraItems?: AddToChatExtraItem[];
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 rounded-full w-9 h-9 p-0 border-0 outline-none ring-0 hover:bg-muted-foreground/10 focus-visible:ring-0 focus-visible:border-transparent focus-visible:outline-none"
          title="Add to chat"
          disabled={disabled}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      {/* Same lifted surface as the config chip dropdowns (Model/Effort/…). */}
      <DropdownMenuContent
        align="start"
        side="top"
        sideOffset={8}
        // Every action here moves focus itself — the composer (Mention files /
        // Commands) or an OS dialog (Add files / folder). Radix's default is to
        // restore focus to the "+" trigger on close, which races against and
        // usually wins over the parent's own textarea focus(), leaving the field
        // unfocused. Suppressing the auto-restore lets that focus() stick.
        onCloseAutoFocus={(e) => e.preventDefault()}
        className="w-52 border border-foreground/15 p-1 font-mono shadow-xl"
      >
        {onAddFiles && (
          <DropdownMenuItem
            onClick={onAddFiles}
            className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
          >
            <Paperclip className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
            <span className="truncate">Add files or photos</span>
          </DropdownMenuItem>
        )}
        {onAddFolder && (
          <DropdownMenuItem
            onClick={onAddFolder}
            className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
          >
            <FolderPlus className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
            <span className="truncate">Add folder</span>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onClick={onMentionFiles}
          className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
        >
          <AtSign className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
          <span className="truncate">Mention files</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={onCommands}
          className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
        >
          <SlashGlyph />
          <span className="truncate">{hasSkills ? 'Skills or Commands' : 'Commands'}</span>
        </DropdownMenuItem>
        {extraItems && extraItems.length > 0 && (
          <>
            <DropdownMenuSeparator />
            {extraItems.map((item) => (
              <DropdownMenuItem
                key={item.id}
                onClick={item.onSelect}
                className="flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer"
              >
                <span className="flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center text-muted-foreground">
                  {item.icon}
                </span>
                <span className="truncate">{item.label}</span>
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Bordered "/" glyph, mirroring the mobile sheet's Commands-row affordance so
 * the option reads as the same slash trigger that surfaces the command list.
 */
function SlashGlyph() {
  return (
    <span className="flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-[4px] border border-muted-foreground/70 text-[9px] font-bold leading-none text-muted-foreground">
      /
    </span>
  );
}
