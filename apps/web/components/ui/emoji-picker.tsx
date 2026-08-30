'use client';

// Emoji picker for project icons. Deliberately a curated list rather than a
// full emoji set: multica pulls in emoji-mart + its ~1.5 MB data JSON, which
// is a lot of payload for picking a folder glyph. These are the categories
// that actually read as "a project" in a sidebar, searchable by keyword.

import { useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';

import { cn } from '@/lib/utils';

interface EmojiEntry {
  emoji: string;
  /** Space-separated search keywords (matched as substrings). */
  keywords: string;
}

interface EmojiGroup {
  label: string;
  entries: EmojiEntry[];
}

const EMOJI_GROUPS: EmojiGroup[] = [
  {
    label: 'Files',
    entries: [
      { emoji: '📁', keywords: 'folder file directory' },
      { emoji: '📂', keywords: 'folder open file directory' },
      { emoji: '🗂️', keywords: 'dividers folder files index' },
      { emoji: '📦', keywords: 'package box parcel release ship' },
      { emoji: '📚', keywords: 'books library docs reading' },
      { emoji: '📖', keywords: 'book docs documentation guide' },
      { emoji: '📝', keywords: 'memo notes writing draft' },
      { emoji: '📄', keywords: 'page document file' },
      { emoji: '📋', keywords: 'clipboard tasks list backlog' },
      { emoji: '🗒️', keywords: 'notepad notes spiral' },
      { emoji: '🔖', keywords: 'bookmark tag label' },
      { emoji: '📌', keywords: 'pushpin pin pinned' },
    ],
  },
  {
    label: 'Code',
    entries: [
      { emoji: '💻', keywords: 'laptop computer code dev' },
      { emoji: '🖥️', keywords: 'desktop computer monitor machine' },
      { emoji: '⌨️', keywords: 'keyboard typing input' },
      { emoji: '🖱️', keywords: 'mouse pointer click' },
      { emoji: '🧑‍💻', keywords: 'developer coder programmer engineer' },
      { emoji: '🤖', keywords: 'robot bot agent ai automation' },
      { emoji: '🧠', keywords: 'brain ai model thinking ml' },
      { emoji: '🐛', keywords: 'bug defect issue fix' },
      { emoji: '🔧', keywords: 'wrench tool fix maintenance' },
      { emoji: '🔨', keywords: 'hammer build tool' },
      { emoji: '🛠️', keywords: 'tools build maintenance infra' },
      { emoji: '⚙️', keywords: 'gear settings config infra' },
      { emoji: '🧪', keywords: 'test experiment lab qa' },
      { emoji: '🧬', keywords: 'dna research science' },
      { emoji: '🔬', keywords: 'microscope research analysis' },
      { emoji: '🗄️', keywords: 'database cabinet storage archive' },
      { emoji: '🖧', keywords: 'network nodes infra' },
      { emoji: '🔌', keywords: 'plug integration connector api' },
      { emoji: '🔑', keywords: 'key auth secret credentials' },
      { emoji: '🔒', keywords: 'lock security private auth' },
      { emoji: '🛡️', keywords: 'shield security defense' },
      { emoji: '☁️', keywords: 'cloud infra hosting server' },
      { emoji: '🌐', keywords: 'globe web internet www site' },
      { emoji: '📡', keywords: 'satellite antenna signal api' },
    ],
  },
  {
    label: 'Work',
    entries: [
      { emoji: '🚀', keywords: 'rocket launch ship release growth' },
      { emoji: '🎯', keywords: 'target goal objective focus' },
      { emoji: '📈', keywords: 'chart growth metrics analytics up' },
      { emoji: '📊', keywords: 'chart bar analytics data stats' },
      { emoji: '💡', keywords: 'idea lightbulb insight feature' },
      { emoji: '🧭', keywords: 'compass direction strategy roadmap' },
      { emoji: '🗺️', keywords: 'map roadmap plan' },
      { emoji: '🏗️', keywords: 'construction building wip infra' },
      { emoji: '🧱', keywords: 'brick foundation platform' },
      { emoji: '🏢', keywords: 'office building company work' },
      { emoji: '💼', keywords: 'briefcase business work client' },
      { emoji: '💰', keywords: 'money revenue billing pricing' },
      { emoji: '💳', keywords: 'card payment billing stripe' },
      { emoji: '📣', keywords: 'megaphone marketing announce growth' },
      { emoji: '✉️', keywords: 'email mail newsletter' },
      { emoji: '📱', keywords: 'phone mobile app ios android' },
      { emoji: '🛒', keywords: 'cart shop ecommerce store' },
      { emoji: '🎨', keywords: 'art design ui palette' },
      { emoji: '✏️', keywords: 'pencil edit design draft' },
      { emoji: '📐', keywords: 'ruler design spec layout' },
    ],
  },
  {
    label: 'Status',
    entries: [
      { emoji: '⭐', keywords: 'star favorite important' },
      { emoji: '🔥', keywords: 'fire hot urgent trending' },
      { emoji: '⚡', keywords: 'zap fast performance speed' },
      { emoji: '✨', keywords: 'sparkles new shiny polish' },
      { emoji: '🎉', keywords: 'party celebrate launch done' },
      { emoji: '✅', keywords: 'check done complete success' },
      { emoji: '❗', keywords: 'exclamation important urgent' },
      { emoji: '⚠️', keywords: 'warning caution risk' },
      { emoji: '🚧', keywords: 'construction wip blocked progress' },
      { emoji: '🧊', keywords: 'ice frozen paused cold' },
      { emoji: '🕐', keywords: 'clock time schedule later' },
      { emoji: '♻️', keywords: 'recycle refactor cleanup' },
    ],
  },
  {
    label: 'Nature',
    entries: [
      { emoji: '🌱', keywords: 'seedling growth new start' },
      { emoji: '🌳', keywords: 'tree growth stable mature' },
      { emoji: '🍀', keywords: 'clover luck fortune' },
      { emoji: '🌊', keywords: 'wave water flow stream' },
      { emoji: '🌙', keywords: 'moon night dark' },
      { emoji: '☀️', keywords: 'sun day light bright' },
      { emoji: '🌈', keywords: 'rainbow color pride' },
      { emoji: '🐳', keywords: 'whale docker container' },
      { emoji: '🐧', keywords: 'penguin linux' },
      { emoji: '🦀', keywords: 'crab rust' },
      { emoji: '🐍', keywords: 'snake python' },
      { emoji: '🦆', keywords: 'duck rubber debug' },
    ],
  },
];

const ALL_ENTRIES = EMOJI_GROUPS.flatMap((group) => group.entries);

export function EmojiPicker({
  onSelect,
  onClear,
}: {
  onSelect: (emoji: string) => void;
  /** Renders a "Remove icon" action when provided. */
  onClear?: () => void;
}) {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return EMOJI_GROUPS;
    const matches = ALL_ENTRIES.filter(
      (entry) => entry.keywords.includes(needle) || entry.emoji === needle,
    );
    return matches.length ? [{ label: 'Results', entries: matches }] : [];
  }, [query]);

  return (
    <div className="w-64">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Search className="size-3.5 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search emoji…"
          autoFocus
          className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground/60"
        />
      </div>

      <div className="max-h-56 overflow-y-auto p-2">
        {groups.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">No emoji found</p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-2 last:mb-0">
              <p className="px-1 pb-1 text-[0.65rem] uppercase tracking-wider text-muted-foreground">
                {group.label}
              </p>
              <div className="grid grid-cols-8 gap-0.5">
                {group.entries.map((entry) => (
                  <button
                    key={entry.emoji}
                    type="button"
                    title={entry.keywords.split(' ')[0]}
                    onClick={() => onSelect(entry.emoji)}
                    className={cn(
                      'flex size-7 cursor-pointer items-center justify-center rounded-md text-base',
                      'transition-colors hover:bg-accent',
                    )}
                  >
                    {entry.emoji}
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {onClear && (
        <div className="border-t px-2 py-1.5">
          <button
            type="button"
            onClick={onClear}
            className="w-full cursor-pointer rounded px-1.5 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Remove icon
          </button>
        </div>
      )}
    </div>
  );
}
