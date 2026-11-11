/**
 * Plugin system — shared type surface (renderer side).
 *
 * A plugin ships a `plugin.json` manifest that the daemon reads off disk,
 * validates, and returns through the `plugin-catalog` RPC. The renderer
 * aggregates manifests from every connected machine in `registry.ts`.
 *
 * Version 1 contributions are declarative (themes, sidebar rows, composer
 * actions). Version 2 adds pages (`surfaces`): a single HTML file the host runs
 * in a sandboxed iframe, talking to Vicoa only through the `window.vicoa`
 * bridge (`lib/plugins/bridge/`), limited by the declared `permissions`,
 * `files` and `network`.
 *
 * The Python side mirrors this schema in
 * `backend/src/protocol/plugin_manifest.py` — keep the two in sync.
 */

/** Manifests declaring a higher apiVersion than this are rejected by the host. */
export const PLUGIN_API_VERSION = 2 as const;

/**
 * Theme tokens a plugin is allowed to override. Mirrors the shadcn custom
 * properties defined in `app/globals.css` (`:root` / `.dark`). Anything a
 * plugin sends outside this set is dropped, so a theme can never inject
 * arbitrary CSS custom properties.
 *
 * `radius` is the only non-HSL token (a length like `0.5rem`); every other
 * value is a bare HSL triplet ("240 21% 15%") consumed as `hsl(var(--token))`.
 */
export const THEME_TOKEN_WHITELIST = [
  'background',
  'foreground',
  'card',
  'card-foreground',
  'popover',
  'popover-foreground',
  'primary',
  'primary-foreground',
  'secondary',
  'secondary-foreground',
  'muted',
  'muted-foreground',
  'accent',
  'accent-foreground',
  'destructive',
  'destructive-foreground',
  'border',
  'input',
  'ring',
  'chart-1',
  'chart-2',
  'chart-3',
  'chart-4',
  'chart-5',
  'sidebar-background',
  'sidebar-foreground',
  'sidebar-primary',
  'sidebar-primary-foreground',
  'sidebar-accent',
  'sidebar-accent-foreground',
  'sidebar-border',
  'sidebar-ring',
  'message-text',
  'menu',
  'menu-foreground',
  'menu-border',
  'menu-elevated',
  'surface-nav',
  'surface-canvas',
  'success',
  'warning',
  'info',
  'user-bubble',
  'composer',
  'radius',
] as const;

export type ThemeToken = (typeof THEME_TOKEN_WHITELIST)[number];

/** Fast membership test for the token whitelist. */
const TOKEN_SET: ReadonlySet<string> = new Set(THEME_TOKEN_WHITELIST);

export function isThemeToken(name: string): name is ThemeToken {
  return TOKEN_SET.has(name);
}

/** Which of the two built-in base palettes a plugin theme builds upon. */
export type ThemeBase = 'dark' | 'light';

export interface PluginThemeContribution {
  /** Unique within the plugin. */
  id: string;
  /** Human label shown in the theme picker. */
  label: string;
  /** Base palette the theme inherits; also the `.dark`/`.light` class applied. */
  base: ThemeBase;
  /** Token name (without the leading `--`) → value. Unknown tokens are dropped. */
  tokens: Record<string, string>;
}

/**
 * What a sidebar item does when clicked. There used to be an `rpc` action that
 * called any daemon method; it was removed, and an older daemon that still
 * reports one has that row dropped by `isSupportedSidebarAction`.
 */
export type SidebarItemAction =
  /** Open a URL (external link or in-app route). */
  | { type: 'open-url'; url: string; external?: boolean }
  /** Navigate to one of the plugin's own pages (`surfaces`). */
  | { type: 'surface'; surfaceId: string };

export interface PluginSidebarItem {
  id: string;
  label: string;
  /** Icon name from the controlled `<Icon>` whitelist; falls back to a default. */
  icon?: string;
  /** Where the row appears in the sidebar. Defaults to `nav`. */
  slot?: 'nav' | 'footer';
  action: SidebarItemAction;
}

/** What a composer action inserts/triggers. Tier 1 stays within safe primitives. */
export type ComposerActionBehavior =
  /** Insert literal text at the cursor. */
  | { type: 'insert-text'; text: string }
  /** Insert an `@`-mention reference to an absolute path. */
  | { type: 'insert-path-ref'; path: string }
  /** Trigger an existing composer panel by id (e.g. the file/command pickers). */
  | { type: 'panel'; panelId: string };

export interface PluginComposerAction {
  id: string;
  label: string;
  icon?: string;
  /** `menu` = a row in the "+" menu; `toolbar` = a standalone icon button. */
  placement?: 'menu' | 'toolbar';
  behavior: ComposerActionBehavior;
}

export interface PluginSlashCommand {
  id: string;
  /** The command trigger, e.g. "/review". */
  command: string;
  label?: string;
  /** Text inserted into the composer when the command is chosen. */
  insertText: string;
}

/** What a plugin's pages may do through the bridge; listed in the trust prompt. */
export const PLUGIN_PERMISSIONS = [
  'projects:read',
  'tasks:read',
  'tasks:write',
  'sessions:read',
  'sessions:write',
  'sessions:start',
  'automations:read',
  'automations:run',
  'backend',
] as const;

export type PluginPermission = (typeof PLUGIN_PERMISSIONS)[number];

export type PluginSettingType = 'string' | 'number' | 'boolean' | 'array' | 'object';

/** One declared setting. Arrays are string arrays. */
export interface PluginSettingSpec {
  type: PluginSettingType;
  default: unknown;
  title?: string;
  description?: string;
  /** `machine`: stored by the daemon, same on every device. `device`: this browser only. */
  scope: 'machine' | 'device';
  /** Allowed values for a string setting. */
  enum?: string[];
  items?: 'string';
}

export type PluginSettingsSchema = Record<string, PluginSettingSpec>;

/** A page (and later a panel or modal) the plugin draws itself. */
export interface PluginSurface {
  id: string;
  /** Only `page` is routable today; `panel` and `modal` arrive with in-app slots. */
  kind: 'page' | 'panel' | 'modal';
  title?: string;
  /** Plugin-relative path of the single HTML file. */
  entry: string;
  icon?: string;
}

/** The full parsed contents of a plugin's `plugin.json`. */
export interface PluginManifest {
  id: string;
  apiVersion: number;
  name?: string;
  description?: string;
  version?: string;
  author?: string;
  homepage?: string;
  themes?: PluginThemeContribution[];
  sidebarItems?: PluginSidebarItem[];
  composerActions?: PluginComposerAction[];
  slashCommands?: PluginSlashCommand[];
  /** `{ vicoa: ">=1.10.0" }`: checked by the daemon against its own version. */
  requirements?: { vicoa?: string };
  permissions?: PluginPermission[];
  /** Absolute or `~/` globs of local files the pages may read (`vicoa.files`). */
  files?: string[];
  /** Origins (`https://host[:port]`) the pages may load from; nothing else is reachable. */
  network?: string[];
  settings?: PluginSettingsSchema;
  surfaces?: PluginSurface[];
  /** Plugin logic and backend entry points (not run yet). */
  client?: string;
  server?: string;
  /** Legacy flag from the v1 catalog; unused. */
  hasClientBundle?: boolean;
}

/** A theme value encoded for the ThemeProvider: `plugin:<pluginId>/<themeId>`. */
export function pluginThemeValue(pluginId: string, themeId: string): string {
  return `plugin:${pluginId}/${themeId}`;
}

/** Parse a `plugin:<pluginId>/<themeId>` value back into its parts, or null. */
export function parsePluginThemeValue(
  value: string,
): { pluginId: string; themeId: string } | null {
  if (!value.startsWith('plugin:')) return null;
  const rest = value.slice('plugin:'.length);
  const slash = rest.indexOf('/');
  if (slash <= 0 || slash === rest.length - 1) return null;
  return { pluginId: rest.slice(0, slash), themeId: rest.slice(slash + 1) };
}

export function isPluginThemeValue(value: string): boolean {
  return value.startsWith('plugin:');
}
