'use client';

import type { CSSProperties, RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { SlashCommand } from '@/lib/constants/slash-commands';

/**
 * Slash-command suggestion list shown above the message box. Shared by the
 * chat input (`components/chat-input.tsx`), the new-session prompt
 * (`app/dashboard/agents/new-session/page.tsx`), and the reusable
 * `MentionPromptField` so every surface renders an identical panel.
 *
 * Default: `absolute bottom-full` — the parent must be `relative`. Pass
 * `portal` (with a viewport-coordinate `panelStyle`) to render it `fixed` into
 * a body portal instead, which the dialog/scroll-container call sites need to
 * escape an `overflow` ancestor that would clip the inline panel.
 */
export function SlashCommandSuggestions({
  commands,
  selectedIndex,
  listRef,
  onSelect,
  onHover,
  portal = false,
  panelStyle,
}: {
  commands: SlashCommand[];
  selectedIndex: number;
  listRef: RefObject<HTMLDivElement | null>;
  onSelect: (command: SlashCommand) => void;
  onHover: (index: number) => void;
  portal?: boolean;
  panelStyle?: CSSProperties;
}) {
  if (commands.length === 0) return null;
  const panel = (
    <div
      ref={listRef}
      style={portal ? panelStyle : undefined}
      className={
        portal
          ? 'fixed bg-popover border border-border rounded-lg shadow-lg overflow-y-auto z-50 max-h-[320px] custom-scrollbar'
          : 'absolute bottom-full left-0 right-0 mb-2 bg-popover border border-border rounded-lg shadow-lg overflow-y-auto z-50 max-h-[320px] custom-scrollbar'
      }
    >
      {commands.map((cmd, index) => {
        const isSelected = index === selectedIndex;
        const isFirst = index === 0;
        const isLast = index === commands.length - 1;
        return (
          <button
            key={cmd.command}
            type="button"
            onClick={() => onSelect(cmd)}
            onMouseEnter={() => onHover(index)}
            className={`w-full px-4 py-2 text-left flex items-start gap-3 transition-colors duration-150 cursor-pointer ${
              isSelected ? 'bg-primary/10' : 'hover:bg-accent/40'
            } ${isFirst ? 'rounded-t-lg' : ''} ${isLast ? 'rounded-b-lg' : ''}`}
          >
            <span className="font-mono text-sm font-medium text-primary min-w-[80px]">
              {cmd.command}
            </span>
            {cmd.description && (
              <span className="text-sm text-muted-foreground flex-1">
                {cmd.description}
              </span>
            )}
            {cmd.kind === 'skill' && (
              <span className="shrink-0 self-center rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                Skill
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
  return portal ? createPortal(panel, document.body) : panel;
}
