'use client';

/**
 * Theme picker that lists the three built-in modes plus every theme contributed
 * by an active plugin, grouped by plugin. Selecting a plugin theme stores the
 * `plugin:<pluginId>/<themeId>` value; the ThemeProvider applies its base class
 * and <PluginThemeStyle/> injects the token overrides.
 *
 * Styled to match the settings selects (see GeneralSection's notifications row).
 */

import { useEffect, useMemo, useState } from 'react';
import { useTheme } from '@/components/theme-provider';
import { usePluginThemes } from '@/lib/plugins/hooks';
import { pluginThemeValue } from '@/lib/plugins/types';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const BASE_LABELS: Record<string, string> = {
  dark: 'Dark',
  light: 'Light',
  system: 'System',
};

export function ThemeSelect() {
  const { theme, setTheme } = useTheme();
  const pluginThemes = usePluginThemes();
  const [mounted, setMounted] = useState(false);

  // `theme` is only meaningful after the provider reads localStorage post-mount.
  useEffect(() => setMounted(true), []);

  // Group plugin themes by their owning plugin for a tidy menu.
  const grouped = useMemo(() => {
    const byPlugin = new Map<string, { name: string; themes: typeof pluginThemes }>();
    for (const t of pluginThemes) {
      const entry = byPlugin.get(t.pluginId) ?? { name: t.pluginName, themes: [] };
      entry.themes.push(t);
      byPlugin.set(t.pluginId, entry);
    }
    return Array.from(byPlugin.values());
  }, [pluginThemes]);

  const currentLabel = useMemo(() => {
    if (BASE_LABELS[theme]) return BASE_LABELS[theme];
    const active = pluginThemes.find((t) => pluginThemeValue(t.pluginId, t.id) === theme);
    return active?.label ?? 'Dark';
  }, [theme, pluginThemes]);

  if (!mounted) return null;

  return (
    <Select value={theme} onValueChange={(v) => setTheme(v as Parameters<typeof setTheme>[0])}>
      <SelectTrigger
        aria-label="Theme"
        className="h-7 w-auto gap-1.5 border-border/70 bg-foreground/[0.06] px-2.5 py-0 text-xs shadow-none focus:ring-0 focus:ring-offset-0"
      >
        <SelectValue>{currentLabel}</SelectValue>
      </SelectTrigger>
      <SelectContent align="end" className="bg-menu font-mono">
        <SelectGroup>
          {Object.entries(BASE_LABELS).map(([value, label]) => (
            <SelectItem key={value} value={value} className="text-xs">
              {label}
            </SelectItem>
          ))}
        </SelectGroup>
        {grouped.map((g) => (
          <SelectGroup key={g.name}>
            <SelectSeparator />
            <SelectLabel className="text-[11px] text-muted-foreground">{g.name}</SelectLabel>
            {g.themes.map((t) => (
              <SelectItem
                key={`${t.pluginId}/${t.id}`}
                value={pluginThemeValue(t.pluginId, t.id)}
                className="text-xs"
              >
                {t.label}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
