'use client';

import {
  forwardRef,
  startTransition,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { TextareaHTMLAttributes } from 'react';
import { createPortal } from 'react-dom';
import { Folder, FileText } from 'lucide-react';
import { useFileMentions } from '@/lib/hooks/use-file-mentions';
import type { FileMention } from '@/lib/backend-api';
import { getCaretViewportRect } from '@/lib/textarea-caret';

/** Index entries for folders carry a trailing "/" (see the daemon's
 * `scan_project_files`); everything else is a file. */
function isFolderPath(path: string): boolean {
  return path.endsWith('/');
}

/** Keep in sync with the panel's `max-h-[320px]` class. */
const MENTION_PANEL_MAX_HEIGHT = 320;

// Cap fuzzy-match scan cost on huge repos. Browsing 20k file paths through
// `fuzzyMatch` per keystroke pegs the main thread; the panel only shows 50
// results anyway, so scanning the most-relevant 5k is plenty.
const MENTION_SEARCH_CAP = 5000;

function fuzzyMatch(search: string, target: string): number {
  const searchLower = search.toLowerCase();
  const targetLower = target.toLowerCase();

  let searchIndex = 0;
  let score = 0;
  let consecutiveMatches = 0;

  for (let i = 0; i < targetLower.length && searchIndex < searchLower.length; i++) {
    if (targetLower[i] === searchLower[searchIndex]) {
      searchIndex++;
      consecutiveMatches++;
      score += 1 + consecutiveMatches;
      if (i > 0 && targetLower[i - 1] === '/') score += 5;
      if (i === 0) score += 10;
    } else {
      consecutiveMatches = 0;
    }
  }

  if (searchIndex < searchLower.length) return 0;
  score -= target.length * 0.1;
  return score;
}

export interface MentionTextareaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange' | 'value'> {
  value: string;
  onChange: (value: string) => void;
  projectPath?: string;
  // Machine the project lives on. With it, mentions read the live daemon index
  // (so files the agent just created are mentionable); without it they read the
  // CLI-synced copy in the DB, which only refreshes when a session starts.
  machineId?: string | null;
  // Machine object when the caller has one — lets the store skip an RPC that
  // an older daemon can't serve. Optional; the store copes without it.
  machine?: { metadata?: Record<string, unknown> | null } | null;
  mentionsEnabled?: boolean;
  onMentionOpenChange?: (open: boolean) => void;
  // Increment to imperatively insert "@" at the cursor and open the mention
  // panel — the web counterpart of the mobile Add-to-chat sheet's "Mention
  // files" action. Each new value (vs. the previous render) triggers one insert.
  openMentionSignal?: number;
  // Render the suggestion panel into a body portal, positioned above the
  // textarea. Needed inside scroll containers and dialogs, where the default
  // absolutely-positioned panel is clipped by an `overflow` ancestor. The
  // prompt boxes don't need it, so it stays opt-in.
  portalMentionPanel?: boolean;
  // Extra classes for the wrapper <div> around the textarea. The default
  // wrapper is content-height (`relative w-full`), so a `flex-1` on the
  // textarea alone can't grow it; pass e.g. `flex-1 min-h-0 flex flex-col`
  // here (and `h-full`/`flex-1` in `className`) to let it fill a flex column.
  containerClassName?: string;
}

export const MentionTextarea = forwardRef<HTMLTextAreaElement, MentionTextareaProps>(
  function MentionTextarea(
    {
      value,
      onChange,
      projectPath,
      machineId,
      machine,
      mentionsEnabled = true,
      onMentionOpenChange,
      openMentionSignal,
      portalMentionPanel = false,
      containerClassName = '',
      onKeyDown,
      ...textareaProps
    },
    ref
  ) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const fileListRef = useRef<HTMLDivElement>(null);
    const pendingCursorRef = useRef<number | null>(null);

    const { files: fileMentions, refresh: refreshFileMentions } = useFileMentions({
      projectPath,
      machineId,
      machine,
      enabled: mentionsEnabled && !!projectPath,
    });

    // Stable scan slice — recomputes only when the file list changes, not on
    // every keystroke. Avoids re-allocating a 5k-element array per char.
    const searchableFiles = useMemo(
      () => (fileMentions.length > MENTION_SEARCH_CAP ? fileMentions.slice(0, MENTION_SEARCH_CAP) : fileMentions),
      [fileMentions],
    );

    const [showFileMentions, setShowFileMentions] = useState(false);
    const [filteredFiles, setFilteredFiles] = useState<FileMention[]>([]);
    const [selectedFileIndex, setSelectedFileIndex] = useState(0);
    const lastSearchKeyRef = useRef<string | null>(null);
    const prevOpenSignalRef = useRef(openMentionSignal);
    const didRefreshMentionsRef = useRef(false);

    useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement, []);

    useEffect(() => {
      onMentionOpenChange?.(showFileMentions);
    }, [showFileMentions, onMentionOpenChange]);

    // One background refresh per mount, fired the first time the panel opens.
    // Mirrors the mobile policy in `agent_chat_model.dart`: the list on screen
    // keeps rendering while it runs, and the *next* `@` picks up whatever the
    // agent has created since. Refreshing on open rather than on every
    // keystroke keeps a monorepo scan off the typing path.
    useEffect(() => {
      if (!showFileMentions || didRefreshMentionsRef.current) return;
      didRefreshMentionsRef.current = true;
      refreshFileMentions();
    }, [showFileMentions, refreshFileMentions]);

    const focusTextarea = useCallback(() => {
      textareaRef.current?.focus({ preventScroll: true });
    }, []);

    const detectMention = useCallback(
      (text: string, cursorIndex: number): boolean => {
        if (!mentionsEnabled) return false;
        const lastAtIndex = text.lastIndexOf('@');
        if (lastAtIndex === -1) return false;

        const afterAt = text.slice(lastAtIndex + 1);
        const whitespaceIndex = afterAt.search(/\s/);
        const searchText = whitespaceIndex === -1 ? afterAt : afterAt.slice(0, whitespaceIndex);
        const tokenEndIndex =
          whitespaceIndex === -1 ? text.length : lastAtIndex + 1 + whitespaceIndex;
        const beforeAt = text.slice(0, lastAtIndex);
        const isCursorWithinToken = cursorIndex >= lastAtIndex && cursorIndex <= tokenEndIndex;

        if (!isCursorWithinToken) return false;
        if (lastAtIndex !== 0 && !/\s/.test(beforeAt[beforeAt.length - 1])) return false;

        // Skip the expensive fuzzy-match scan if the active search token hasn't
        // changed since the last keystroke (e.g., user moves the cursor inside
        // the token, or types a char that doesn't change the mention slice).
        const searchKey = `${lastAtIndex}:${searchText}`;
        if (searchKey === lastSearchKeyRef.current && showFileMentions) return true;
        lastSearchKeyRef.current = searchKey;

        if (searchText === '') {
          const allFiles = searchableFiles.slice(0, 50);
          if (allFiles.length === 0) return false;
          startTransition(() => {
            setFilteredFiles(allFiles);
            setShowFileMentions(true);
            setSelectedFileIndex(0);
          });
          return true;
        }

        const matches = searchableFiles
          .map((file) => ({ file, score: fuzzyMatch(searchText, file.path) }))
          .filter(({ score }) => score > 0)
          .sort((a, b) => b.score - a.score)
          .slice(0, 50)
          .map(({ file }) => file);

        if (matches.length === 0) return false;
        startTransition(() => {
          setFilteredFiles(matches);
          setShowFileMentions(true);
          setSelectedFileIndex(0);
        });
        return true;
      },
      [searchableFiles, mentionsEnabled, showFileMentions]
    );

    const handleChange = useCallback(
      (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const next = e.target.value;
        const cursorIndex = e.target.selectionStart ?? next.length;
        onChange(next);
        const matched = detectMention(next, cursorIndex);
        if (!matched && showFileMentions) setShowFileMentions(false);
      },
      [onChange, detectMention, showFileMentions]
    );

    // Imperative "@" insertion driven by `openMentionSignal` (incremented by
    // the Add-to-chat "+" menu). Inserts "@" at the cursor — with a leading
    // space when the preceding char isn't whitespace, so mention detection
    // (which requires "@" at index 0 or after whitespace) always fires — then
    // opens the panel via detectMention. Guarded so it runs once per new value.
    useEffect(() => {
      if (openMentionSignal === undefined || openMentionSignal === prevOpenSignalRef.current) {
        return;
      }
      prevOpenSignalRef.current = openMentionSignal;
      const el = textareaRef.current;
      const cursor = el?.selectionStart ?? value.length;
      const before = value.slice(0, cursor);
      const after = value.slice(cursor);
      const needsLeadingSpace = before.length > 0 && !/\s/.test(before[before.length - 1]);
      const insert = needsLeadingSpace ? ' @' : '@';
      const next = before + insert + after;
      const newCursor = before.length + insert.length;
      pendingCursorRef.current = newCursor;
      onChange(next);
      detectMention(next, newCursor);
    }, [openMentionSignal, value, onChange, detectMention]);

    const insertFileMention = useCallback(
      (filePath: string) => {
        const lastAtIndex = value.lastIndexOf('@');
        if (lastAtIndex === -1) {
          const next = `${value}@${filePath} `;
          pendingCursorRef.current = next.length;
          onChange(next);
          return;
        }
        const afterAt = value.slice(lastAtIndex + 1);
        const whitespaceIndex = afterAt.search(/\s/);
        const endIndex =
          whitespaceIndex === -1 ? value.length : lastAtIndex + 1 + whitespaceIndex;
        const beforeAt = value.slice(0, lastAtIndex);
        const afterToken = value.slice(endIndex);
        const needsSpace = afterToken === '' || !afterToken.startsWith(' ');
        const next = `${beforeAt}@${filePath}${needsSpace ? ' ' : ''}${afterToken}`;
        pendingCursorRef.current =
          beforeAt.length + 1 + filePath.length + (needsSpace ? 1 : 0);
        onChange(next);
      },
      [value, onChange]
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // While an IME is composing (e.g. Chinese Pinyin), Enter/Arrows/Escape
        // belong to the candidate window — they commit/navigate/cancel a
        // candidate, they don't send. Hand every key back to the textarea
        // natively: don't intercept the mention dropdown and don't delegate to
        // the parent's onKeyDown (which would send). keyCode 229 is the legacy
        // signal for Safari/older browsers that don't set isComposing on the
        // committing keydown.
        if (e.nativeEvent.isComposing || e.keyCode === 229) return;

        if (showFileMentions) {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedFileIndex((prev) =>
              prev < filteredFiles.length - 1 ? prev + 1 : 0
            );
            return;
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedFileIndex((prev) =>
              prev > 0 ? prev - 1 : filteredFiles.length - 1
            );
            return;
          }
          if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
            e.preventDefault();
            if (filteredFiles[selectedFileIndex]) {
              insertFileMention(filteredFiles[selectedFileIndex].path);
              setShowFileMentions(false);
              focusTextarea();
            }
            return;
          }
          if (e.key === 'Escape') {
            e.preventDefault();
            setShowFileMentions(false);
            return;
          }
        }
        onKeyDown?.(e);
      },
      [
        showFileMentions,
        filteredFiles,
        selectedFileIndex,
        insertFileMention,
        focusTextarea,
        onKeyDown,
      ]
    );

    useEffect(() => {
      if (pendingCursorRef.current === null || !textareaRef.current) return;
      const pos = pendingCursorRef.current;
      pendingCursorRef.current = null;
      requestAnimationFrame(() => {
        textareaRef.current?.setSelectionRange(pos, pos);
        focusTextarea();
      });
    }, [value, focusTextarea]);

    useEffect(() => {
      if (showFileMentions && fileListRef.current) {
        const el = fileListRef.current.children[selectedFileIndex] as
          | HTMLElement
          | undefined;
        el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }, [selectedFileIndex, showFileMentions]);

    useEffect(() => {
      if (!showFileMentions) return;
      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowFileMentions(false);
        }
      };
      const handleClick = (e: MouseEvent) => {
        const target = e.target as Node;
        // The panel is a sibling of the container when portalled, so check it
        // too — otherwise this mousedown closes the list before the result's
        // click lands and selection silently does nothing.
        const inside =
          containerRef.current?.contains(target) || fileListRef.current?.contains(target);
        if (!inside) setShowFileMentions(false);
      };
      document.addEventListener('keydown', handleEscape);
      document.addEventListener('mousedown', handleClick);
      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.removeEventListener('mousedown', handleClick);
      };
    }, [showFileMentions]);

    // Viewport coordinates for the portalled panel: sits above the textarea
    // like the inline one, flipping below when there isn't room. Measured each
    // time the panel opens (and on the file list changing, which resizes it).
    const [portalPanelStyle, setPortalPanelStyle] = useState<React.CSSProperties>();
    useEffect(() => {
      if (!portalMentionPanel || !showFileMentions) return;
      const measure = () => {
        const rect = containerRef.current?.getBoundingClientRect();
        const textarea = textareaRef.current;
        if (!rect || !textarea) return;
        // Anchor vertically to the caret line, not the field edges: in a tall
        // expanded field the bottom can be far below the line being typed.
        const caret = getCaretViewportRect(textarea);
        const spaceAbove = caret.top;
        const openDown = spaceAbove < MENTION_PANEL_MAX_HEIGHT + 16;
        setPortalPanelStyle({
          left: rect.left,
          width: rect.width,
          maxHeight: Math.max(
            120,
            Math.min(
              MENTION_PANEL_MAX_HEIGHT,
              (openDown ? window.innerHeight - caret.bottom : spaceAbove) - 16,
            ),
          ),
          ...(openDown
            ? { top: caret.bottom + 8 }
            : { bottom: window.innerHeight - caret.top + 8 }),
        });
      };
      measure();
      window.addEventListener('resize', measure);
      window.addEventListener('scroll', measure, true);
      return () => {
        window.removeEventListener('resize', measure);
        window.removeEventListener('scroll', measure, true);
      };
      // `value` is included so the panel follows the caret as the token is
      // typed, not just when the match count changes.
    }, [portalMentionPanel, showFileMentions, filteredFiles.length, value]);

    const panel = showFileMentions && filteredFiles.length > 0 && (
      <div
        ref={fileListRef}
        style={portalMentionPanel ? portalPanelStyle : undefined}
        className={
          portalMentionPanel
            ? 'fixed bg-popover border border-border rounded-lg shadow-lg overflow-y-auto z-50 max-h-[320px] custom-scrollbar'
            : 'absolute bottom-full left-0 right-0 mb-2 bg-popover border border-border rounded-lg shadow-lg overflow-y-auto z-50 max-h-[320px] custom-scrollbar'
        }
      >
        {filteredFiles.map((file, index) => {
          const isSelected = index === selectedFileIndex;
          const isFirst = index === 0;
          const isLast = index === filteredFiles.length - 1;
          const isFolder = isFolderPath(file.path);
          return (
            <button
              key={file.path}
              type="button"
              onClick={() => {
                insertFileMention(file.path);
                setShowFileMentions(false);
                focusTextarea();
              }}
              onMouseEnter={() => setSelectedFileIndex(index)}
              className={`w-full px-4 py-2 text-left flex items-center gap-2.5 transition-colors duration-150 cursor-pointer ${
                isSelected ? 'bg-primary/10' : 'hover:bg-accent/40'
              } ${isFirst ? 'rounded-t-lg' : ''} ${isLast ? 'rounded-b-lg' : ''}`}
            >
              {isFolder ? (
                <Folder className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
              ) : (
                <FileText className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
              )}
              <span className="font-mono text-sm text-primary flex-1 truncate">
                {file.path}
              </span>
            </button>
          );
        })}
      </div>
    );

    return (
      <div ref={containerRef} className={`relative w-full ${containerClassName}`}>
        {portalMentionPanel
          ? panel && createPortal(panel, document.body)
          : panel}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          {...textareaProps}
        />
      </div>
    );
  }
);
