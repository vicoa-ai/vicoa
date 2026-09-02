'use client';

/**
 * Injects the token overrides for the currently-selected plugin theme.
 *
 * The ThemeProvider applies the theme's *base* class (`.dark`/`.light`); this
 * component renders a single `<style>` that overrides the specific shadcn
 * tokens the plugin declared. Non-overridden tokens keep inheriting the base
 * palette from `globals.css`, which is why a plugin only has to specify the
 * handful of colors it actually changes.
 *
 * Safety: only whitelisted token names are emitted, and every value is
 * validated against a strict character set + length cap, so a plugin can never
 * break out of the declaration to inject arbitrary CSS. It renders nothing when
 * a non-plugin theme (dark/light/system) is active.
 *
 * It also registers the built-in example theme plugins on mount so the picker
 * has something to show before any real plugin catalog loads (P0).
 */

import { useEffect } from 'react';
import { useTheme } from '@/components/theme-provider';
import { usePluginThemes } from '@/lib/plugins/hooks';
import { pluginRegistry } from '@/lib/plugins/registry';
import { BUILTIN_PLUGIN_MANIFESTS } from '@/lib/plugins/builtin-themes';
import { isThemeToken, parsePluginThemeValue } from '@/lib/plugins/types';

/**
 * Permitted value characters: digits, letters, whitespace, and the punctuation
 * that appears in HSL triplets / lengths / hex / rgb()/hsl() functions. Notably
 * excludes `;` `{` `}` `<` `>` `"` `'` `\` `:` and `@`, so a value cannot close
 * the declaration or start a new rule/at-rule.
 */
const SAFE_VALUE = /^[0-9a-zA-Z%.,()/#\s_-]{1,64}$/;

function sanitizeTokenValue(value: string): string | null {
  const trimmed = value.trim();
  if (!SAFE_VALUE.test(trimmed)) return null;
  // Defense in depth: reject the two CSS constructs that could still fetch or
  // execute despite passing the char class if `(` is allowed for hsl()/rgb().
  const lower = trimmed.toLowerCase();
  if (lower.includes('url(') || lower.includes('expression')) return null;
  return trimmed;
}

export function PluginThemeStyle() {
  const { theme } = useTheme();
  const themes = usePluginThemes();

  // Register the built-in example themes once, after mount (idempotent).
  useEffect(() => {
    pluginRegistry.registerBuiltins(BUILTIN_PLUGIN_MANIFESTS);
  }, []);

  const parsed = parsePluginThemeValue(theme);
  if (!parsed) return null;

  const active = themes.find(
    (t) => t.pluginId === parsed.pluginId && t.id === parsed.themeId,
  );
  if (!active) return null;

  const declarations: string[] = [];
  for (const [name, rawValue] of Object.entries(active.tokens)) {
    if (!isThemeToken(name)) continue;
    const value = sanitizeTokenValue(rawValue);
    if (value === null) continue;
    declarations.push(`--${name}:${value};`);
  }
  if (declarations.length === 0) return null;

  // `:root` after globals.css wins over both the `:root` and `.dark` base
  // blocks by equal specificity + later source order, so these overrides apply
  // regardless of which base class the provider set.
  const css = `:root{${declarations.join('')}}`;

  return (
    <style
      data-plugin-theme={`${active.pluginId}/${active.id}`}
      // Values are whitelisted + sanitized above; this is a static CSS string.
      dangerouslySetInnerHTML={{ __html: css }}
    />
  );
}
