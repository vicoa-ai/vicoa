'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { getPtyRpc } from '@/lib/pty-rpc';
import { TerminalPane, createRpcPtyTransport } from '@/components/terminal-pane';
import {
  clearWorkspaceLayout,
  loadTerminals,
  saveTerminals,
  type SavedTerminals,
} from '@/components/files-git-panel/panel-storage';

/**
 * Keep-alive terminal sessions (desktop only).
 *
 * Terminal panes used to live inside FilesGitPanel, so switching sessions
 * unmounted them and killed their ptys. This provider owns every terminal for
 * the lifetime of the app instead: panes are mounted in a layer that never
 * unmounts (until the tab is closed), and the visible pane is geometry-synced
 * over the panel's body area (the "viewport" the panel registers). Hidden
 * panes are display:none — xterm keeps its buffer, and TerminalPane's own
 * ResizeObserver re-fits on reveal.
 *
 * Geometry overlay instead of a React portal on purpose: changing a portal's
 * container remounts its children, which would kill the pty on every session
 * switch — the exact bug this exists to fix.
 *
 * Persistence (desktop): a session's terminal *layout* (which tabs, at which
 * cwd) is written to localStorage so it can be restored after an app quit. The
 * shell process itself dies with the daemon on quit, so restore re-spawns fresh
 * shells at the saved directories — scrollback and running commands are not
 * preserved. Only sessions that have been touched this app-run (restored via
 * `restoreSession` or mutated via `addTerminal`) are persisted, so a not-yet-
 * reopened session's saved layout is never clobbered by the empty initial map.
 */

export interface TerminalTabInfo {
  id: string;
  machineId: string;
  cwd: string;
}

export interface SessionTerminals {
  terminals: TerminalTabInfo[];
  /** The terminal tab the session last had selected (null = a fixed tab). */
  activeId: string | null;
}

export const EMPTY_SESSION_TERMINALS: SessionTerminals = { terminals: [], activeId: null };

/** Project the live session state down to the persisted shape. */
function toSavedTerminals(session: SessionTerminals | undefined): SavedTerminals {
  if (!session || session.terminals.length === 0) {
    return { terminals: [], activeIndex: -1 };
  }
  const activeIndex = session.activeId
    ? session.terminals.findIndex((t) => t.id === session.activeId)
    : -1;
  return {
    terminals: session.terminals.map((t) => ({ cwd: t.cwd, machineId: t.machineId })),
    activeIndex,
  };
}

interface Viewport {
  instanceId: string;
  el: HTMLElement;
}

interface TerminalSessionsApi {
  sessions: Record<string, SessionTerminals>;
  /** Create a terminal tab for a session and make it active. Returns the new
      tab's id so callers can focus exactly that pane (see focusTerminal). */
  addTerminal: (instanceId: string, machineId: string, cwd: string) => string;
  /** Close a tab: its pane unmounts and the pty is killed. */
  closeTerminal: (instanceId: string, terminalId: string) => void;
  setActiveTerminal: (instanceId: string, terminalId: string | null) => void;
  /** Re-open a session's persisted terminals as fresh shells. Idempotent: the
      first call for a session this app-run restores it; later calls no-op, so
      re-opening the panel after a session switch never double-spawns. */
  restoreSession: (instanceId: string, machineId: string) => void;
  /** Tear a session down entirely (archived/deleted): every pane unmounts (so
      each pty is killed) and the session's persisted layout is dropped. */
  closeSession: (instanceId: string) => void;
  /** Register (el) / unregister (null) the panel-body area that should show
      the session's active terminal. */
  attachViewport: (instanceId: string, el: HTMLElement | null) => void;
  /** Focus a session's terminal, retrying briefly while a freshly revealed
      pane's xterm (loaded async) mounts and becomes visible. Pass the target
      `terminalId` when switching tabs — the just-queued active-tab change isn't
      in state yet, so falling back to the stored activeId would focus the tab
      you're leaving. Omit it to focus whatever is active. */
  focusTerminal: (instanceId: string, terminalId?: string) => void;
}

const TerminalSessionsContext = createContext<TerminalSessionsApi | null>(null);

export function useTerminalSessions(): TerminalSessionsApi {
  const api = useContext(TerminalSessionsContext);
  if (api === null) {
    throw new Error('useTerminalSessions must be used within TerminalSessionsProvider');
  }
  return api;
}

export function TerminalSessionsProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<Record<string, SessionTerminals>>({});
  const [viewport, setViewport] = useState<Viewport | null>(null);
  const counterRef = useRef(0);
  // Live lookups for focusTerminal (which runs on retry timers, so it must
  // read current state, not a stale closure).
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;
  const paneElsRef = useRef(new Map<string, HTMLElement>());
  // Sessions restored or mutated this app-run. Only these are persisted, so an
  // untouched session's saved layout survives until it is reopened (otherwise
  // the empty initial `sessions` map would overwrite it on first render).
  const hydratedRef = useRef<Set<string>>(new Set());

  // Write-through persistence: whenever the map changes, re-serialize every
  // hydrated session. Cheap (a handful of sessions, a handful of tabs each) and
  // it keeps localStorage in lockstep with add/close/reorder/active changes.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    for (const instanceId of hydratedRef.current) {
      const session = sessions[instanceId];
      saveTerminals(window.localStorage, instanceId, toSavedTerminals(session));
    }
  }, [sessions]);

  const addTerminal = useCallback((instanceId: string, machineId: string, cwd: string) => {
    counterRef.current += 1;
    // Renderer state only — Math.random is fine here.
    const id = `term-${counterRef.current}-${Math.random().toString(36).slice(2, 8)}`;
    hydratedRef.current.add(instanceId);
    setSessions((prev) => {
      const current = prev[instanceId] ?? EMPTY_SESSION_TERMINALS;
      return {
        ...prev,
        [instanceId]: {
          terminals: [...current.terminals, { id, machineId, cwd }],
          activeId: id,
        },
      };
    });
    return id;
  }, []);

  const restoreSession = useCallback((instanceId: string, machineId: string) => {
    // First reopen of this session this app-run wins; a later remount of the
    // panel (e.g. after switching away and back) must not re-spawn the shells
    // that are already alive in the keep-alive layer.
    if (hydratedRef.current.has(instanceId)) return;
    hydratedRef.current.add(instanceId);
    if (typeof window === 'undefined') return;
    const saved = loadTerminals(window.localStorage, instanceId);
    if (saved.terminals.length === 0) return;
    const terminals: TerminalTabInfo[] = saved.terminals.map((t) => {
      counterRef.current += 1;
      const id = `term-${counterRef.current}-${Math.random().toString(36).slice(2, 8)}`;
      // Spawn on the session's current machine; the saved machineId is only a
      // hint (a session can't move between machines), so `machineId` wins.
      return { id, machineId, cwd: t.cwd };
    });
    const activeId =
      saved.activeIndex >= 0 && saved.activeIndex < terminals.length
        ? terminals[saved.activeIndex].id
        : null;
    setSessions((prev) => {
      // Guard against a concurrent addTerminal having populated it already.
      if (prev[instanceId] && prev[instanceId].terminals.length > 0) return prev;
      return { ...prev, [instanceId]: { terminals, activeId } };
    });
  }, []);

  const closeSession = useCallback((instanceId: string) => {
    hydratedRef.current.delete(instanceId);
    if (typeof window !== 'undefined') {
      clearWorkspaceLayout(window.localStorage, instanceId);
    }
    setSessions((prev) => {
      if (!(instanceId in prev)) return prev;
      const next = { ...prev };
      delete next[instanceId];
      return next;
    });
  }, []);

  const closeTerminal = useCallback((instanceId: string, terminalId: string) => {
    setSessions((prev) => {
      const current = prev[instanceId];
      if (!current) return prev;
      const index = current.terminals.findIndex((t) => t.id === terminalId);
      const terminals = current.terminals.filter((t) => t.id !== terminalId);
      const activeId =
        current.activeId === terminalId
          ? terminals.length
            ? terminals[Math.min(index, terminals.length - 1)].id
            : null
          : current.activeId;
      return { ...prev, [instanceId]: { terminals, activeId } };
    });
  }, []);

  const setActiveTerminal = useCallback((instanceId: string, terminalId: string | null) => {
    setSessions((prev) => {
      const current = prev[instanceId] ?? EMPTY_SESSION_TERMINALS;
      if (current.activeId === terminalId) return prev;
      return { ...prev, [instanceId]: { ...current, activeId: terminalId } };
    });
  }, []);

  const attachViewport = useCallback((instanceId: string, el: HTMLElement | null) => {
    setViewport((prev) => {
      if (el === null) {
        // Only clear our own registration — a new page may have attached first.
        return prev?.instanceId === instanceId ? null : prev;
      }
      if (prev !== null && prev.instanceId === instanceId && prev.el === el) return prev;
      return { instanceId, el };
    });
  }, []);

  const focusTerminal = useCallback((instanceId: string, terminalId?: string) => {
    const attempt = (triesLeft: number) => {
      const session = sessionsRef.current[instanceId];
      const targetId = terminalId ?? session?.activeId ?? session?.terminals[0]?.id;
      if (targetId) {
        const pane = paneElsRef.current.get(`${instanceId}:${targetId}`);
        const textarea = pane?.querySelector('textarea');
        if (textarea) {
          textarea.focus();
          // A just-revealed pane is display:none for a beat (the keep-alive
          // layer sets its rect in a passive effect), and focus() is a no-op on
          // a hidden textarea — so only stop once focus has actually landed.
          if (document.activeElement === textarea) return;
        }
      }
      if (triesLeft > 0) setTimeout(() => attempt(triesLeft - 1), 50);
    };
    // Defer the first pass: an active-tab switch is queued, not yet in state, so
    // reading it synchronously would target (and briefly focus) the outgoing,
    // still-on-screen terminal. One macrotask lets the render commit first.
    setTimeout(() => attempt(40), 0); // ~2s: covers panel open + xterm's async load
  }, []);

  const api = useMemo(
    () => ({
      sessions,
      addTerminal,
      closeTerminal,
      setActiveTerminal,
      restoreSession,
      closeSession,
      attachViewport,
      focusTerminal,
    }),
    [
      sessions,
      addTerminal,
      closeTerminal,
      setActiveTerminal,
      restoreSession,
      closeSession,
      attachViewport,
      focusTerminal,
    ],
  );

  return (
    <TerminalSessionsContext.Provider value={api}>
      {children}
      {Object.entries(sessions).flatMap(([instanceId, session]) =>
        session.terminals.map((info) => {
          const paneKey = `${instanceId}:${info.id}`;
          return (
            <TerminalKeepAlive
              key={paneKey}
              info={info}
              registerEl={(el) => {
                if (el === null) paneElsRef.current.delete(paneKey);
                else paneElsRef.current.set(paneKey, el);
              }}
              viewportEl={
                viewport !== null &&
                viewport.instanceId === instanceId &&
                session.activeId === info.id
                  ? viewport.el
                  : null
              }
            />
          );
        }),
      )}
    </TerminalSessionsContext.Provider>
  );
}

/** One keep-alive pane: mounted for the tab's whole life, shown as a fixed
    overlay tracking the registered viewport, display:none otherwise. */
function TerminalKeepAlive({
  info,
  viewportEl,
  registerEl,
}: {
  info: TerminalTabInfo;
  viewportEl: HTMLElement | null;
  registerEl: (el: HTMLElement | null) => void;
}) {
  // Pass a FACTORY, not an instance: the pane creates a fresh transport per
  // mount so React StrictMode's dev-only remount can't spawn onto a transport
  // its own cleanup already killed. Stable per machineId; the pane reads it via
  // a ref at effect start, so its identity doesn't drive re-spawns.
  const createTransport = useCallback(
    () => createRpcPtyTransport(getPtyRpc(info.machineId)),
    [info.machineId],
  );

  const [rect, setRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null);

  useEffect(() => {
    if (viewportEl === null) {
      setRect(null);
      return;
    }
    const update = () => {
      const r = viewportEl.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(viewportEl);
    window.addEventListener('resize', update);
    // Capture-phase scroll: the viewport can move without resizing (e.g. a
    // scrollable ancestor); rare in the panel, cheap to cover.
    window.addEventListener('scroll', update, true);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [viewportEl]);

  const visible = viewportEl !== null && rect !== null;

  return (
    <div
      data-terminal-pane
      ref={registerEl}
      style={
        visible
          ? {
              position: 'fixed',
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
              // Above the overlay-mode panel (z-40), below menus/dialogs (z-50).
              zIndex: 45,
            }
          : { display: 'none' }
      }
    >
      <TerminalPane createTransport={createTransport} cwd={info.cwd} />
    </div>
  );
}
