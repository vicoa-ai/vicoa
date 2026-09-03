'use client';

import { useEffect, useState } from 'react';

/**
 * The palette painted right now, read straight off the `dark` / `light` class
 * <ThemeProvider> puts on <html>. A blocking script in app/layout.tsx sets that
 * class before first paint, so this is already correct by the time any client
 * effect runs. Returns `dark` (what the server renders) when there is no
 * document, so it is safe to call during SSR.
 */
export function resolvedThemeNow(): 'dark' | 'light' {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

/**
 * {@link resolvedThemeNow} as reactive state.
 *
 * `useTheme().theme` is the stored *preference*, which can be `system` or a
 * `plugin:<id>/<theme>` value; neither tells you which palette won. Anything
 * that has to pick a colour in JS (CodeMirror themes, canvas/SVG paints) needs
 * the resolved answer, so read it off the class the provider already applied
 * and track it with a MutationObserver — that covers the mode switcher, the
 * OS-level change under `system`, and a plugin theme loading late.
 *
 * The first render returns `dark` so SSR and hydration agree; the effect
 * corrects it on mount. Code that runs only on the client (an effect, an
 * imperative editor setup) should read {@link resolvedThemeNow} directly to
 * skip that one-render lag.
 */
export function useResolvedTheme(): 'dark' | 'light' {
  const [resolved, setResolved] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    const root = document.documentElement;
    const read = () => setResolved(resolvedThemeNow());
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return resolved;
}

/** Convenience wrapper around {@link useResolvedTheme}. */
export function useIsDarkTheme(): boolean {
  return useResolvedTheme() === 'dark';
}
