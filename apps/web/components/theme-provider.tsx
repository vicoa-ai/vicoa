"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePluginRegistry } from "@/lib/plugins/hooks";
import { findPluginTheme } from "@/lib/plugins/registry";
import { isPluginThemeValue, parsePluginThemeValue } from "@/lib/plugins/types";

// A theme is one of the three built-in modes, or a plugin theme encoded as
// `plugin:<pluginId>/<themeId>` (see lib/plugins/types.ts). The plugin theme's
// token overrides are injected by <PluginThemeStyle/>; here we only resolve and
// apply its base palette class.
type Theme = "dark" | "light" | "system" | `plugin:${string}`;

type ThemeProviderProps = {
  children: React.ReactNode;
  defaultTheme?: Theme;
  storageKey?: string;
};

type ThemeProviderState = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const initialState: ThemeProviderState = {
  theme: "dark",
  setTheme: () => null,
};

const ThemeProviderContext = createContext<ThemeProviderState>(initialState);

export function ThemeProvider({
  children,
  defaultTheme = "dark",
  storageKey = "ui-theme",
  ...props
}: ThemeProviderProps) {
  const [theme, setTheme] = useState<Theme>(defaultTheme);
  const [mounted, setMounted] = useState(false);
  // Re-run the class effect when plugins load: a `plugin:` theme restored from
  // localStorage may arrive before its owning plugin's catalog does, so we need
  // to re-resolve its base palette once the registry is populated.
  const plugins = usePluginRegistry();

  // Initialize theme from localStorage on client side only
  useEffect(() => {
    setMounted(true);
    const storedTheme = localStorage?.getItem(storageKey) as Theme;
    if (storedTheme) {
      setTheme(storedTheme);
    }
  }, [storageKey]);

  useEffect(() => {
    if (!mounted) return;

    const root = window.document.documentElement;

    root.classList.remove("light", "dark");

    if (theme === "system") {
      const systemTheme = window.matchMedia("(prefers-color-scheme: dark)")
        .matches
        ? "dark"
        : "light";

      root.classList.add(systemTheme);
      return;
    }

    if (isPluginThemeValue(theme)) {
      // Apply the plugin theme's base palette class (dark/light). If the plugin
      // hasn't loaded yet, fall back to dark until this effect re-runs with a
      // populated `plugins` snapshot.
      const parsed = parsePluginThemeValue(theme);
      const resolved = parsed
        ? findPluginTheme(parsed.pluginId, parsed.themeId, plugins)
        : null;
      root.classList.add(resolved?.base ?? "dark");
      return;
    }

    root.classList.add(theme);
  }, [theme, mounted, plugins]);

  const value = {
    theme,
    setTheme: (theme: Theme) => {
      localStorage.setItem(storageKey, theme);
      setTheme(theme);
    },
  };

  // Always render the Provider so the tree shape stays stable across the
  // mounted flip. Conditionally returning a bare Fragment before mount swaps
  // the element type at this position (Fragment -> Provider), which forces
  // React to unmount/remount the entire subtree on hydration and can surface
  // as "Rendered more hooks than during the previous render" (React #310).
  // The <html> tag already uses suppressHydrationWarning for the theme class.
  return (
    <ThemeProviderContext.Provider {...props} value={value}>
      {children}
    </ThemeProviderContext.Provider>
  );
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext);

  if (context === undefined)
    throw new Error("useTheme must be used within a ThemeProvider");

  return context;
};