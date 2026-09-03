// Terminal pane patterns adapted from Orca (https://github.com/stablyai/orca),
// MIT License, Copyright (c) 2026 Lovecast Inc.
//
// <TerminalPane> mounts one xterm.js terminal bound to a PtyTransport.
// Construction order (Orca's pane-lifecycle): new Terminal -> open(container)
// -> load fit/search/unicode11/webLinks addons -> activate unicode11 ->
// initial fit deferred to rAF -> spawn. Disposal runs the reverse order.
//
// xterm touches `self` at module-eval time, so it must never load during SSR:
// the JS modules are dynamically imported inside the mount effect ('use
// client' alone is not enough — client components still server-render).

'use client';

import '@xterm/xterm/css/xterm.css';
// Bundled "Symbols Nerd Font Mono" @font-face (powerline + Nerd Font glyphs).
import './terminal-fonts.css';
// Modifier-aware pointer cursor over links (see terminal-links.ts).
import './terminal-links.css';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Terminal } from '@xterm/xterm';
import type { PtyTransport } from './pty-transport';
import { buildTerminalOptions, VICOA_TERMINAL_BACKGROUND } from './terminal-options';
import { openTerminalLink, trackLinkModifier } from './terminal-links';
import { RpcError } from '@/lib/ws-client';

const RESIZE_DEBOUNCE_MS = 50;

/** Turn a spawn failure into something the user can act on. A remote machine
 *  whose daemon predates remote-terminal support answers `no_handler`; an
 *  offline machine answers `target_disconnected`. */
function describeSpawnError(err: unknown): string {
  if (err instanceof RpcError) {
    if (err.code === 'no_handler') {
      return "This machine's Vicoa needs updating to open a terminal from another device.";
    }
    if (err.code === 'target_disconnected') {
      return 'That machine is offline.';
    }
  }
  return err instanceof Error ? err.message : 'Failed to start terminal';
}

export interface TerminalPaneProps {
  /** Factory, not an instance: the pane creates a fresh transport per mount so
   *  React StrictMode's dev-only mount → unmount → mount can't spawn onto a
   *  transport its own cleanup already killed ("PtyTransport is closed"). */
  createTransport: () => PtyTransport;
  cwd: string;
  className?: string;
  /** Written to the shell once, right after its first output (or a short
   *  fallback delay) — worktree setup commands run here, visibly. Sent on the
   *  first spawn only; a manual restart does not resend it. */
  initialInput?: string;
}

// How long to wait for the shell's first output before writing `initialInput`
// anyway. A login shell always prints a prompt, so the first-output path
// normally wins; this only covers a silent shell so setup can't hang unsent.
const INITIAL_INPUT_FALLBACK_MS = 750;

type PaneStatus =
  | { kind: 'loading' }
  | { kind: 'spawning' }
  | { kind: 'running' }
  | { kind: 'exited'; exitCode: number | null }
  | { kind: 'error'; message: string };

export function TerminalPane({
  createTransport,
  cwd,
  className,
  initialInput,
}: TerminalPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // The terminal lives in refs so parent re-renders never touch it. The
  // transport factory is read through a ref at effect start: prop-identity
  // churn must not re-spawn — only a real cwd change does (effect deps below).
  const createTransportRef = useRef(createTransport);
  createTransportRef.current = createTransport;
  // Read at effect start like the transport factory — `initialInput` is fixed
  // per tab, so it must not be an effect dep (that would re-spawn the shell).
  const initialInputRef = useRef(initialInput);
  initialInputRef.current = initialInput;
  const termRef = useRef<Terminal | null>(null);
  const respawnRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<PaneStatus>({ kind: 'loading' });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    // Fresh transport per effect-run (StrictMode-safe): this run owns its
    // spawn → kill lifecycle end to end.
    const boundTransport = createTransportRef.current();
    let disposed = false;
    let observer: ResizeObserver | null = null;
    let fitTimer: number | null = null;
    let initialFitRafId: number | null = null;
    const unsubs: Array<() => void> = [];

    // Worktree setup: one-shot input written once the shell is live, then
    // cleared so a manual restart (which reuses spawn/onData) never resends it.
    let pendingInitialInput = initialInputRef.current || null;
    let initialInputTimer: number | null = null;
    const flushInitialInput = (): void => {
      if (initialInputTimer !== null) {
        window.clearTimeout(initialInputTimer);
        initialInputTimer = null;
      }
      if (pendingInitialInput === null || disposed) return;
      const data = pendingInitialInput;
      pendingInitialInput = null;
      boundTransport.write(data);
    };

    // Armed synchronously (not inside the async import below) so the pane is
    // never briefly in a state where holding ⌘/Ctrl doesn't register.
    unsubs.push(trackLinkModifier(container));

    setStatus({ kind: 'loading' });

    void (async () => {
      const [{ Terminal }, { FitAddon }, { SearchAddon }, { Unicode11Addon }, { WebLinksAddon }] =
        await Promise.all([
          import('@xterm/xterm'),
          import('@xterm/addon-fit'),
          import('@xterm/addon-search'),
          import('@xterm/addon-unicode11'),
          import('@xterm/addon-web-links'),
        ]);
      if (disposed) return;

      const term = new Terminal(buildTerminalOptions());
      const fitAddon = new FitAddon();
      term.open(container);
      term.loadAddon(fitAddon);
      term.loadAddon(new SearchAddon());
      term.loadAddon(new Unicode11Addon());
      // ⌘/Ctrl+click opens the URL outside the app; a plain click is left to
      // the shell/TUI underneath (see terminal-links.ts).
      term.loadAddon(new WebLinksAddon(openTerminalLink));
      // Activate wide-char tables before any write, or CJK/emoji cells bake in
      // at single width (Orca's pane-lifecycle ordering).
      term.unicode.activeVersion = '11';
      termRef.current = term;

      const safeFit = (): void => {
        try {
          fitAddon.fit();
        } catch {
          /* container hidden or zero-sized; keep previous grid */
        }
      };

      // Only forward grids the pty hasn't seen; identical re-fits (tab
      // reveals, ResizeObserver double-fires) must not spam pty-resize.
      let lastCols = 0;
      let lastRows = 0;
      const pushResizeIfChanged = (): void => {
        if (term.cols === lastCols && term.rows === lastRows) return;
        lastCols = term.cols;
        lastRows = term.rows;
        boundTransport.resize(term.cols, term.rows);
      };

      const spawn = async (): Promise<void> => {
        setStatus({ kind: 'spawning' });
        try {
          await boundTransport.spawn({ cwd, cols: term.cols, rows: term.rows });
          lastCols = term.cols;
          lastRows = term.rows;
          if (!disposed) {
            setStatus({ kind: 'running' });
            term.focus();
            // Fallback: send setup even if the shell prints nothing. The
            // first-output path (onData below) normally fires first and clears
            // this timer.
            if (pendingInitialInput !== null && initialInputTimer === null) {
              initialInputTimer = window.setTimeout(flushInitialInput, INITIAL_INPUT_FALLBACK_MS);
            }
          }
        } catch (err) {
          if (!disposed) {
            setStatus({ kind: 'error', message: describeSpawnError(err) });
          }
        }
      };
      respawnRef.current = () => void spawn();

      unsubs.push(
        boundTransport.onData((bytes) => {
          term.write(bytes);
          // First output ⇒ the shell is up and has (almost always) printed its
          // prompt: safe to type the setup commands now.
          flushInitialInput();
        }),
      );
      unsubs.push(
        boundTransport.onExit((exitCode) => {
          if (!disposed) setStatus({ kind: 'exited', exitCode });
        }),
      );
      const inputDisposable = term.onData((data) => boundTransport.write(data));
      unsubs.push(() => inputDisposable.dispose());

      observer = new ResizeObserver(() => {
        if (fitTimer !== null) window.clearTimeout(fitTimer);
        fitTimer = window.setTimeout(() => {
          fitTimer = null;
          if (disposed) return;
          safeFit();
          pushResizeIfChanged();
        }, RESIZE_DEBOUNCE_MS);
      });
      observer.observe(container);

      // Initial fit deferred one frame so layout has settled, then spawn with
      // the fitted grid.
      initialFitRafId = requestAnimationFrame(() => {
        initialFitRafId = null;
        if (disposed) return;
        safeFit();
        void spawn();
      });

      // The bundled Nerd Font (terminal-fonts.css) is a webfont: it may still
      // be loading when xterm first paints, so powerline/icon glyphs can flash
      // as tofu and the canvas atlas caches those misses. Force the load, then
      // re-measure (metrics are unchanged since the symbols font has no Latin
      // glyphs, so this is a no-op resize) and refresh so cached glyphs repaint
      // from the now-available font. Guarded by `disposed` — no cleanup needed.
      const fontApi = typeof document !== 'undefined' ? document.fonts : undefined;
      if (fontApi?.load) {
        void fontApi
          .load(`${term.options.fontSize ?? 14}px "Symbols Nerd Font Mono"`)
          .catch(() => undefined)
          .then(() => {
            if (disposed) return;
            safeFit();
            pushResizeIfChanged();
            try {
              term.refresh(0, term.rows - 1);
            } catch {
              /* terminal torn down mid-refresh */
            }
          });
      }
    })().catch((err: unknown) => {
      if (!disposed) {
        setStatus({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Failed to load terminal',
        });
      }
    });

    return () => {
      if (disposed) return;
      disposed = true;
      respawnRef.current = null;
      // Disposal order (Orca): pending timers/rAF -> observer -> listeners ->
      // transport -> terminal.
      if (fitTimer !== null) window.clearTimeout(fitTimer);
      if (initialInputTimer !== null) window.clearTimeout(initialInputTimer);
      if (initialFitRafId !== null) cancelAnimationFrame(initialFitRafId);
      observer?.disconnect();
      observer = null;
      for (const unsub of unsubs) {
        try {
          unsub();
        } catch {
          /* ignore */
        }
      }
      unsubs.length = 0;
      void boundTransport.kill().catch(() => undefined);
      try {
        termRef.current?.dispose();
      } catch {
        /* ignore */
      }
      termRef.current = null;
    };
    // Re-run (kill + re-spawn) only when the working directory really changes.
  }, [cwd]);

  const handleRestart = useCallback(() => {
    respawnRef.current?.();
  }, []);

  return (
    <div
      className={`relative h-full w-full overflow-hidden ${className ?? ''}`}
      style={{ backgroundColor: VICOA_TERMINAL_BACKGROUND }}
    >
      <div ref={containerRef} className="absolute inset-0 pl-2 pt-1 pb-0.5" />
      {status.kind !== 'running' && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center"
          style={{
            backgroundColor:
              status.kind === 'exited' || status.kind === 'error'
                ? 'rgba(22, 28, 36, 0.85)'
                : VICOA_TERMINAL_BACKGROUND,
          }}
        >
          <div className="flex flex-col items-center gap-3 px-4 text-center">
            {(status.kind === 'loading' || status.kind === 'spawning') && (
              <p className="text-sm text-slate-400">
                {status.kind === 'loading' ? 'Loading terminal…' : 'Starting shell…'}
              </p>
            )}
            {status.kind === 'exited' && (
              <p className="text-sm text-slate-400">
                Process exited
                {status.exitCode !== null ? ` (code ${status.exitCode})` : ''}
              </p>
            )}
            {status.kind === 'error' && (
              <p className="max-w-md break-words text-sm text-red-400">{status.message}</p>
            )}
            {(status.kind === 'exited' || status.kind === 'error') && (
              <button
                type="button"
                onClick={handleRestart}
                className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:bg-slate-700/40"
              >
                Restart
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
