'use client';

// Emoji picker for project icons and avatars.
//
// Opens on a curated list — two of them, because the two jobs want different
// vocabularies: a project wants nouns for *work* (folders, tools, charts), an
// avatar wants a character (a role, a creature, a mark), and 📁 makes a poor
// face. Pick with `variant`.
//
// "All emoji" switches to the complete set (1,900+, `unicode-emoji-json`),
// **dynamically imported on first use**. That is the whole reason a curated list
// existed in the first place — the objection to emoji-mart was never the emoji,
// it was paying ~1.5 MB up front to pick a folder glyph. Behind a click the data
// is its own chunk: zero bytes for the common case, everything available for the
// user who wants 🦩.

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

const PROJECT_GROUPS: EmojiGroup[] = [
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

// For an agent or a person: something that reads as a character at 24px. Roles
// first (an agent is usually "the reviewer", "the researcher"), then creatures
// as mascots, then the handful of marks that stand in for a job.
const AVATAR_GROUPS: EmojiGroup[] = [
  {
    label: 'Roles',
    entries: [
      { emoji: '🤖', keywords: 'robot bot agent ai automation' },
      { emoji: '🧑‍💻', keywords: 'developer coder programmer engineer dev' },
      { emoji: '👩‍💻', keywords: 'developer coder programmer engineer dev' },
      { emoji: '🧙', keywords: 'wizard magic expert guru' },
      { emoji: '🕵️', keywords: 'detective investigate debug search sleuth' },
      { emoji: '🧑‍🔬', keywords: 'scientist research experiment analysis' },
      { emoji: '🧑‍🏫', keywords: 'teacher explain docs mentor tutor' },
      { emoji: '🧑‍⚖️', keywords: 'judge review critic arbiter' },
      { emoji: '👷', keywords: 'builder construction infra worker' },
      { emoji: '🧑‍🚀', keywords: 'astronaut explorer launch space' },
      { emoji: '🧑‍🍳', keywords: 'chef cook recipe bake' },
      { emoji: '🧑‍🎨', keywords: 'artist design ui creative' },
      { emoji: '💂', keywords: 'guard security sentry watch' },
      { emoji: '🥷', keywords: 'ninja stealth fast fixer' },
      { emoji: '🦸', keywords: 'hero superhero rescue fix' },
      { emoji: '👻', keywords: 'ghost background quiet spooky' },
      { emoji: '👾', keywords: 'alien invader game retro bot' },
      { emoji: '🧚', keywords: 'fairy magic polish sparkle' },
    ],
  },
  {
    label: 'Creatures',
    entries: [
      { emoji: '🦊', keywords: 'fox clever quick' },
      { emoji: '🦉', keywords: 'owl wise night review' },
      { emoji: '🐙', keywords: 'octopus multitask parallel' },
      { emoji: '🐝', keywords: 'bee busy worker diligent' },
      { emoji: '🐜', keywords: 'ant tireless small worker' },
      { emoji: '🦫', keywords: 'beaver builder go golang' },
      { emoji: '🐢', keywords: 'turtle slow careful steady' },
      { emoji: '🐇', keywords: 'rabbit fast quick hare' },
      { emoji: '🦅', keywords: 'eagle sharp oversight watch' },
      { emoji: '🐺', keywords: 'wolf pack hunter' },
      { emoji: '🐨', keywords: 'koala calm chill' },
      { emoji: '🐼', keywords: 'panda calm friendly' },
      { emoji: '🦁', keywords: 'lion bold lead' },
      { emoji: '🐳', keywords: 'whale docker container big' },
      { emoji: '🐧', keywords: 'penguin linux' },
      { emoji: '🦀', keywords: 'crab rust' },
      { emoji: '🐍', keywords: 'snake python' },
      { emoji: '🦆', keywords: 'duck rubber debug' },
      { emoji: '🐛', keywords: 'bug defect issue fix' },
      { emoji: '🐉', keywords: 'dragon powerful big model' },
    ],
  },
  {
    label: 'Marks',
    entries: [
      { emoji: '🧠', keywords: 'brain ai model thinking reasoning' },
      { emoji: '⚡', keywords: 'zap fast speed haiku quick' },
      { emoji: '🔥', keywords: 'fire hot urgent hotfix' },
      { emoji: '✨', keywords: 'sparkles polish new shiny' },
      { emoji: '🎯', keywords: 'target focus goal precise' },
      { emoji: '🚀', keywords: 'rocket ship launch release' },
      { emoji: '🔍', keywords: 'search find review inspect audit' },
      { emoji: '🧪', keywords: 'test experiment lab qa' },
      { emoji: '🛡️', keywords: 'shield security guard defense' },
      { emoji: '🧹', keywords: 'broom cleanup refactor tidy' },
      { emoji: '🪄', keywords: 'wand magic auto fix' },
      { emoji: '📝', keywords: 'memo writing docs notes' },
      { emoji: '📈', keywords: 'chart growth metrics analytics' },
      { emoji: '⚙️', keywords: 'gear settings infra ops' },
      { emoji: '🔑', keywords: 'key auth secret access' },
      { emoji: '🧭', keywords: 'compass direction plan strategy' },
      { emoji: '🎨', keywords: 'art design ui palette' },
      { emoji: '☕', keywords: 'coffee java patient long' },
      { emoji: '🌙', keywords: 'moon night overnight background' },
      { emoji: '♻️', keywords: 'recycle refactor cleanup reuse' },
    ],
  },
];

// Reactions want a third vocabulary again: not nouns for work and not a
// character, but the small set of things people actually answer a comment with.
// Everything else is one click away behind "All emoji".
const REACTION_GROUPS: EmojiGroup[] = [
  {
    label: 'Common',
    entries: [
      { emoji: '\u{1F44D}', keywords: 'thumbs up yes agree approve lgtm +1' },
      { emoji: '\u{1F44E}', keywords: 'thumbs down no disagree reject -1' },
      { emoji: '\u{2764}\u{FE0F}', keywords: 'heart love like' },
      { emoji: '\u{1F389}', keywords: 'tada party celebrate shipped done' },
      { emoji: '\u{1F680}', keywords: 'rocket ship launch shipped fast' },
      { emoji: '\u{1F440}', keywords: 'eyes looking reviewing watching' },
      { emoji: '\u{1F525}', keywords: 'fire hot great burn' },
      { emoji: '\u{1F4AF}', keywords: 'hundred perfect score exactly' },
      { emoji: '\u{2705}', keywords: 'check done complete resolved fixed' },
      { emoji: '\u{274C}', keywords: 'cross no wrong failed broken' },
      { emoji: '\u{1F914}', keywords: 'thinking hmm unsure question' },
      { emoji: '\u{1F64F}', keywords: 'pray thanks please thank you' },
    ],
  },
  {
    label: 'Faces',
    entries: [
      { emoji: '\u{1F604}', keywords: 'smile happy grin laugh' },
      { emoji: '\u{1F602}', keywords: 'joy laughing tears funny lol' },
      { emoji: '\u{1F60D}', keywords: 'heart eyes love adore' },
      { emoji: '\u{1F62E}', keywords: 'surprised wow open mouth' },
      { emoji: '\u{1F622}', keywords: 'cry sad tear' },
      { emoji: '\u{1F621}', keywords: 'angry mad rage' },
      { emoji: '\u{1F605}', keywords: 'sweat smile nervous phew close call' },
      { emoji: '\u{1F643}', keywords: 'upside down irony sarcasm' },
      { emoji: '\u{1F9D0}', keywords: 'monocle inspect scrutiny suspicious' },
      { emoji: '\u{1F634}', keywords: 'sleeping tired boring zzz' },
    ],
  },
  {
    label: 'Work',
    entries: [
      { emoji: '\u{1F41B}', keywords: 'bug defect issue broken' },
      { emoji: '\u{1F6A2}', keywords: 'ship shipped release deploy' },
      { emoji: '\u{1F6A8}', keywords: 'siren alert urgent incident' },
      { emoji: '\u{1F44F}', keywords: 'clap applause well done nice' },
      { emoji: '\u{1F91D}', keywords: 'handshake agree deal thanks' },
      { emoji: '\u{1F4A1}', keywords: 'idea bulb suggestion insight' },
      { emoji: '\u{26A0}\u{FE0F}', keywords: 'warning caution careful risk' },
      { emoji: '\u{1F6D1}', keywords: 'stop blocked halt' },
    ],
  },
];

export type EmojiPickerVariant = 'project' | 'avatar' | 'reaction';

/** The full Unicode set, grouped, as `unicode-emoji-json` ships it. */
type RawEmojiGroup = {
  slug: string;
  emojis: { emoji: string; name: string }[];
};

// Their slugs are machine-shaped ("smileys_emotion"); these are the standard
// Unicode category names as a person would read them.
const FULL_GROUP_LABELS: Record<string, string> = {
  smileys_emotion: 'Smileys',
  people_body: 'People',
  animals_nature: 'Animals & Nature',
  food_drink: 'Food & Drink',
  travel_places: 'Travel & Places',
  activities: 'Activities',
  objects: 'Objects',
  symbols: 'Symbols',
  flags: 'Flags',
};

// Module-level so reopening the popover — or toggling back and forth — never
// re-parses 400 KB of JSON. The dynamic import is cached by the bundler too;
// this just skips the remapping.
let fullGroupsCache: EmojiGroup[] | null = null;

async function loadFullEmojiGroups(): Promise<EmojiGroup[]> {
  if (fullGroupsCache) return fullGroupsCache;
  const mod = await import('unicode-emoji-json/data-by-group.json');
  const raw = ((mod as { default?: RawEmojiGroup[] }).default ??
    mod) as unknown as RawEmojiGroup[];
  fullGroupsCache = raw.map((group) => ({
    label: FULL_GROUP_LABELS[group.slug] ?? group.slug,
    // `name` is already the lowercase human name ("grinning face"), which is
    // exactly the substring search the curated keywords use.
    entries: group.emojis.map((entry) => ({
      emoji: entry.emoji,
      keywords: entry.name,
    })),
  }));
  return fullGroupsCache;
}

const GROUPS_BY_VARIANT: Record<EmojiPickerVariant, EmojiGroup[]> = {
  project: PROJECT_GROUPS,
  avatar: AVATAR_GROUPS,
  reaction: REACTION_GROUPS,
};

export function EmojiPicker({
  onSelect,
  onClear,
  clearLabel = 'Remove icon',
  variant = 'project',
}: {
  onSelect: (emoji: string) => void;
  /** Renders the clear action when provided. */
  onClear?: () => void;
  /** What the clear action is called — "icon" on a project, "emoji" on an avatar. */
  clearLabel?: string;
  /** Which curated set to offer. See the module comment. */
  variant?: EmojiPickerVariant;
}) {
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [fullGroups, setFullGroups] = useState<EmojiGroup[] | null>(fullGroupsCache);
  const [loadingAll, setLoadingAll] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openAll = () => {
    setShowAll(true);
    if (fullGroups) return;
    setLoadingAll(true);
    void loadFullEmojiGroups()
      .then(setFullGroups)
      .catch(() => {
        // Nothing to recover: fall back to the curated list rather than
        // stranding the user on an empty grid.
        setShowAll(false);
      })
      .finally(() => setLoadingAll(false));
  };

  const groups = useMemo(() => {
    const all = showAll ? (fullGroups ?? []) : GROUPS_BY_VARIANT[variant];
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    const matches = all
      .flatMap((group) => group.entries)
      .filter((entry) => entry.keywords.includes(needle) || entry.emoji === needle);
    return matches.length ? [{ label: 'Results', entries: matches }] : [];
  }, [query, variant, showAll, fullGroups]);

  return (
    <div className="w-64">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Search className="size-3.5 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={showAll ? 'Search all emoji…' : 'Search emoji…'}
          autoFocus
          className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground/60"
        />
      </div>

      <div className="custom-scrollbar max-h-56 overflow-y-auto p-2">
        {loadingAll ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">
            Loading emoji…
          </p>
        ) : groups.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-muted-foreground">No emoji found</p>
        ) : (
          groups.map((group) => (
            <div
              key={group.label}
              className="mb-2 last:mb-0"
              // The full set mounts ~1,900 buttons at once. This lets the
              // browser skip layout and paint for the groups scrolled out of
              // the 224px window; `contain-intrinsic-size` keeps the scrollbar
              // honest meanwhile. A no-op where unsupported, and on the curated
              // lists (which are small enough not to care).
              style={
                showAll
                  ? { contentVisibility: 'auto', containIntrinsicSize: '0 240px' }
                  : undefined
              }
            >
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

      <div className="flex items-center gap-2 border-t px-2 py-1.5">
        <button
          type="button"
          onClick={() => (showAll ? setShowAll(false) : openAll())}
          className="cursor-pointer rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {showAll ? 'Suggested' : 'All emoji'}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="ml-auto cursor-pointer rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            {clearLabel}
          </button>
        )}
      </div>
    </div>
  );
}
