'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { MentionTextarea } from '@/components/mention-textarea';
import { SlashCommandSuggestions } from '@/components/dashboard/slash-command-suggestions';
import { useSlashCommands } from '@/lib/hooks/use-slash-commands';
import { applySlashCommandSelection, commandInsertText, detectSlashCommand, slashCommandMatches } from '@/lib/slash-command-utils';
import type { AgentType } from '@/lib/constants/slash-commands';
import { getCaretViewportRect } from '@/lib/textarea-caret';

const SLASH_PANEL_MAX_HEIGHT = 320;

interface MentionPromptFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Which agent's command/skill set to offer. Defaults to Claude. */
  agentType?: AgentType;
  machineId?: string | null;
  projectPath?: string;
  machine?: { metadata?: Record<string, unknown> | null } | null;
  /** Enables `@` file mentions (needs a project path). */
  mentionsEnabled?: boolean;
  /** Enables the `/` slash-command menu. */
  commandsEnabled?: boolean;
  placeholder?: string;
  /** Classes for the underlying textarea. */
  className?: string;
  /** Classes for the outermost wrapper (e.g. to flex-grow inside a column). */
  wrapperClassName?: string;
  /** Classes for the `MentionTextarea`'s own container div. */
  containerClassName?: string;
  autoFocus?: boolean;
  rows?: number;
}

/**
 * A description/prompt textarea with both `@` file mentions and `/` slash
 * commands + skills, sharing the exact fuzzy-file index and command index the
 * chat composer uses.
 *
 * `@` is delegated wholesale to `MentionTextarea`; this component layers the
 * slash menu on top (mutually exclusive with the mention panel) and reuses the
 * chat composer's prefix-detection and insertion semantics. Both suggestion
 * panels render into a body portal so the field works inside dialogs and
 * scroll containers without being clipped.
 *
 * Used by the task dialog description and the automation prompt.
 */
export function MentionPromptField({
  value,
  onChange,
  agentType = 'claude',
  machineId,
  projectPath,
  machine,
  mentionsEnabled = true,
  commandsEnabled = true,
  placeholder,
  className,
  wrapperClassName,
  containerClassName,
  autoFocus,
  rows = 3,
}: MentionPromptFieldProps) {
  // No `machine` here on purpose: passing it gates the live `scan-commands`
  // RPC on the daemon advertising the `command-index` capability in its stored
  // metadata, which is unreliable (only register/agent-scan persist it — the
  // heartbeat drops the write). A false-negative silently demotes to the REST
  // DB copy, a per-(user, agent) row that isn't scoped to `projectPath`, so the
  // repo's project-local skills go missing. Mirrors the chat composer, which
  // skips the gate; the store still falls back to REST on `no_handler`. (The
  // `machine` prop is still used below for the `@`-mention capability gate.)
  const { commands } = useSlashCommands({
    agentType,
    machineId,
    projectPath,
    enabled: commandsEnabled,
  });

  const [showSlash, setShowSlash] = useState(false);
  const [filtered, setFiltered] = useState(commands);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties>();

  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Caret the slash menu is anchored to (the "/word" the query came from), so
  // selection replaces the right word even after a suggestion click blurs the
  // field; live selectionStart wins while it's still focused.
  const slashCaretRef = useRef(0);
  const currentCaret = useCallback(
    () => textareaRef.current?.selectionStart ?? slashCaretRef.current,
    [],
  );

  // Same caret-aware "/"-command detection as the chat composer: the panel opens
  // when the caret is inside a "/command" word (start of input or after
  // whitespace) and filters by that word alone — so a draft or a typed argument
  // no longer suppresses it.
  const handleChange = useCallback(
    (next: string) => {
      onChange(next);
      const caret = textareaRef.current?.selectionStart ?? next.length;
      const { active, query } = commandsEnabled
        ? detectSlashCommand(next, caret)
        : { active: false, query: '' };
      if (active) {
        slashCaretRef.current = caret;
        const matches = commands.filter((cmd) => slashCommandMatches(cmd, query));
        setFiltered(matches);
        setShowSlash(matches.length > 0);
        setSelectedIndex(0);
      } else {
        setShowSlash(false);
      }
    },
    [commands, commandsEnabled, onChange],
  );

  const insertSelected = useCallback(() => {
    const cmd = filtered[selectedIndex];
    if (!cmd) return;
    const { value: next, cursor } = applySlashCommandSelection(value, commandInsertText(cmd), currentCaret());
    onChange(next);
    setShowSlash(false);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus({ preventScroll: true });
        el.setSelectionRange(cursor, cursor);
      }
    });
  }, [filtered, selectedIndex, value, onChange, currentCaret]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (!showSlash || filtered.length === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((p) => (p < filtered.length - 1 ? p + 1 : 0));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((p) => (p > 0 ? p - 1 : filtered.length - 1));
      } else if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        insertSelected();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlash(false);
      }
    },
    [showSlash, filtered, insertSelected],
  );

  // Keep the highlighted row in view during keyboard nav.
  useEffect(() => {
    if (!showSlash || !listRef.current) return;
    const el = listRef.current.children[selectedIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex, showSlash]);

  // Close on outside click / Escape (the portalled panel is a body sibling, so
  // check it as well as the field).
  useEffect(() => {
    if (!showSlash) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const inside =
        containerRef.current?.contains(target) || listRef.current?.contains(target);
      if (!inside) setShowSlash(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowSlash(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
  }, [showSlash]);

  // Position the portalled slash panel next to the caret line, flipping below
  // when there isn't room above — mirrors `MentionTextarea`'s portal placement.
  useEffect(() => {
    if (!showSlash) return;
    const measure = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      const textarea = textareaRef.current;
      if (!rect || !textarea) return;
      const caret = getCaretViewportRect(textarea);
      const spaceAbove = caret.top;
      const openDown = spaceAbove < SLASH_PANEL_MAX_HEIGHT + 16;
      setPanelStyle({
        left: rect.left,
        width: rect.width,
        maxHeight: Math.max(
          120,
          Math.min(
            SLASH_PANEL_MAX_HEIGHT,
            (openDown ? window.innerHeight - caret.bottom : spaceAbove) - 16,
          ),
        ),
        ...(openDown ? { top: caret.bottom + 8 } : { bottom: window.innerHeight - caret.top + 8 }),
      });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [showSlash, filtered.length, value]);

  return (
    <div ref={containerRef} className={`relative w-full ${wrapperClassName ?? ''}`}>
      <SlashCommandSuggestions
        commands={showSlash ? filtered : []}
        selectedIndex={selectedIndex}
        listRef={listRef}
        onSelect={(cmd) => {
          const { value: next, cursor } = applySlashCommandSelection(value, commandInsertText(cmd), currentCaret());
          onChange(next);
          setShowSlash(false);
          requestAnimationFrame(() => {
            const el = textareaRef.current;
            if (el) {
              el.focus({ preventScroll: true });
              el.setSelectionRange(cursor, cursor);
            }
          });
        }}
        onHover={setSelectedIndex}
        portal
        panelStyle={panelStyle}
      />
      <MentionTextarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onMentionOpenChange={(open) => {
          if (open) setShowSlash(false);
        }}
        projectPath={projectPath}
        machineId={machineId}
        machine={machine}
        mentionsEnabled={mentionsEnabled}
        portalMentionPanel
        containerClassName={containerClassName}
        placeholder={placeholder}
        className={className}
        autoFocus={autoFocus}
        rows={rows}
      />
    </div>
  );
}
