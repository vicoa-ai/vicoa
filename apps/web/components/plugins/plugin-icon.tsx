'use client';

/**
 * Controlled icon set for plugins. A plugin references an icon by whitelisted
 * name (see ICON_WHITELIST in backend/src/protocol/plugin_manifest.py) and this
 * component maps it to a concrete lucide-react glyph. An unknown/absent name
 * falls back to the Puzzle icon, so a plugin can never pull in an arbitrary
 * component. Keep this map in sync with the backend whitelist.
 */

import {
  Bell,
  BookOpen,
  Bot,
  Bug,
  CalendarClock,
  Check,
  Clipboard,
  Cloud,
  Code,
  Command,
  Database,
  Download,
  ExternalLink,
  File,
  Folder,
  GitBranch,
  Globe,
  Key,
  Layers,
  Link as LinkIcon,
  ListTodo,
  Lock,
  MessageSquare,
  Palette,
  PanelLeft,
  Play,
  Plus,
  Puzzle,
  RefreshCw,
  Rocket,
  Search,
  Settings,
  Shield,
  Sparkles,
  Star,
  Terminal,
  Upload,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  'book-open': BookOpen,
  'list-todo': ListTodo,
  'calendar-clock': CalendarClock,
  layers: Layers,
  settings: Settings,
  terminal: Terminal,
  sparkles: Sparkles,
  zap: Zap,
  star: Star,
  link: LinkIcon,
  'external-link': ExternalLink,
  folder: Folder,
  file: File,
  search: Search,
  plus: Plus,
  play: Play,
  'refresh-cw': RefreshCw,
  bell: Bell,
  bot: Bot,
  code: Code,
  'git-branch': GitBranch,
  'message-square': MessageSquare,
  bug: Bug,
  wrench: Wrench,
  palette: Palette,
  puzzle: Puzzle,
  rocket: Rocket,
  globe: Globe,
  database: Database,
  cloud: Cloud,
  key: Key,
  lock: Lock,
  shield: Shield,
  check: Check,
  clipboard: Clipboard,
  download: Download,
  upload: Upload,
  command: Command,
  'panel-left': PanelLeft,
};

export function PluginIcon({
  name,
  className,
}: {
  name?: string;
  className?: string;
}) {
  const Icon = (name && ICONS[name]) || Puzzle;
  return <Icon className={className} />;
}
