'use client';

import type { CSSProperties, RefObject } from 'react';
import { createPortal } from 'react-dom';
import { FileText, Folder } from 'lucide-react';
import type { FileMention } from '@/lib/backend-api';
import { isFolderPath } from '@/lib/file-mention-match';

/**
 * The `@` file list. Shared by `MentionTextarea` and the task description
 * editor so both surfaces render an identical panel, the way
 * `SlashCommandSuggestions` is shared for `/`.
 *
 * Default: `absolute bottom-full`, the parent must be `relative`. Pass `portal`
 * (with a viewport-coordinate `panelStyle`) to render it `fixed` into a body
 * portal instead, for call sites inside an `overflow` ancestor.
 */
export function FileMentionSuggestions({
  files,
  selectedIndex,
  listRef,
  onSelect,
  onHover,
  portal = false,
  panelStyle,
}: {
  files: FileMention[];
  selectedIndex: number;
  listRef: RefObject<HTMLDivElement | null>;
  onSelect: (file: FileMention) => void;
  onHover: (index: number) => void;
  portal?: boolean;
  panelStyle?: CSSProperties;
}) {
  if (files.length === 0) return null;
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
      <FileMentionRows files={files} selectedIndex={selectedIndex} onSelect={onSelect} onHover={onHover} />
    </div>
  );
  return portal ? createPortal(panel, document.body) : panel;
}

/** The rows alone, for a caller that owns the panel around them (MentionTextarea
 * shares one panel between these and the `#` references). Each row is a direct
 * child of that panel, so index maps straight to `children[i]` for scrolling. */
export function FileMentionRows({
  files,
  selectedIndex,
  onSelect,
  onHover,
}: {
  files: FileMention[];
  selectedIndex: number;
  onSelect: (file: FileMention) => void;
  onHover: (index: number) => void;
}) {
  return (
    <>
      {files.map((file, index) => {
        const isSelected = index === selectedIndex;
        const isFirst = index === 0;
        const isLast = index === files.length - 1;
        const isFolder = isFolderPath(file.path);
        return (
          <button
            key={file.path}
            type="button"
            onClick={() => onSelect(file)}
            onMouseEnter={() => onHover(index)}
            className={`w-full px-4 py-2 text-left flex items-center gap-2.5 transition-colors duration-150 cursor-pointer ${
              isSelected ? 'bg-primary/10' : 'hover:bg-accent/40'
            } ${isFirst ? 'rounded-t-lg' : ''} ${isLast ? 'rounded-b-lg' : ''}`}
          >
            {isFolder ? (
              <Folder className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
            ) : (
              <FileText className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
            )}
            <span className="font-mono text-sm text-primary flex-1 truncate">{file.path}</span>
          </button>
        );
      })}
    </>
  );
}
