'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Plus,
  Terminal as TerminalIcon,
  RefreshCw,
  WrapText,
  ChevronsDownUp,
  ChevronsUpDown,
  Pilcrow,
  Columns2,
  FolderGit2,
  Copy,
  Check,
  PanelRight,
  Eye,
  Code,
  ChevronDown,
  ChevronRight,
  Save,
  Loader2,
  AlertTriangle,
  RotateCcw,
  Maximize2,
  Minimize2,
  GitCompareArrows,
  FileText,
  FileDiff,
  PanelBottom,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ListTree,
  MoreHorizontal,
  Link as LinkIcon,
} from 'lucide-react';
import { getDesktopConfig } from '@/lib/runtime-config';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { useDesktopWindows } from '@/components/desktop/window-chrome';
import { comboInline, matchesShortcut } from '@/lib/desktop-shortcuts';
import {
  EMPTY_SESSION_TERMINALS,
  useTerminalSessions,
} from '@/components/terminal-pane/terminal-sessions';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { rpcWorktreeRunSetup, rpcWorktreeTrustGrant } from './rpc';
import { usePanelState } from './use-panel-state';
import { useFilesTab } from './use-files-tab';
import { useGitTab } from './use-git-tab';
import { useCommits } from './use-commits';
import { FileSearchResults, FileSearchRow, FilesTab, gitStatusColor } from './files-tab';
import { ChangedFilesList, changedFileEntries } from './changed-files-list';
import { FileViewer } from './file-viewer';
import type { DiffNav } from './diff-editor';
import { FileTypeIcon } from './file-type-icon';
import { GitTab, BranchInfo } from './git-tab';
import { CommitsSection } from './commits-section';
import { isMarkdownPath } from './file-icon';
import { isEditable } from './file-tabs';
import { FileFindBar } from './file-find-bar';
import { useInFileFind, type FindOptions } from './use-in-file-find';
import { useCmFind } from './use-cm-find';
import { ancestorPaths } from './tree';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { SCROLL_STYLE, TAB_SCROLL_STYLE } from './styles';
import { useFileMentions } from '@/lib/hooks/use-file-mentions';
import { toAbsolutePath } from '@/lib/utils';

export { usePanelState } from './use-panel-state';
export type { PanelTab } from './panel-storage';

/**
 * A one-shot intent the parent hands the panel to run once, on mount. Used so a
 * closed-panel ⌘T can open the panel and land on a fresh terminal tab: the page
 * can't touch this panel's file-tab state, so it flags the intent and lets the
 * panel spawn the tab itself (clearing any reopened file so the terminal shows).
 */
export type PanelPendingAction = 'new-terminal';

/** The panel background — a fixed dark surface, independent of the theme token. */
const PANEL_BG = '#171717';
/** Dropdown/menu surface — slightly lighter than the panel for contrast. */
const DROPDOWN_BG = '#2D2D2D';

interface FilesGitPanelProps {
  machineId: string | null;
  cwd: string | null;
  homeDir: string | null;
  instanceId: string;
  panel: ReturnType<typeof usePanelState>;
  /** Render as a full-width layer that fills its (relative) parent — the chat
   * messages area, between the session header and the composer — instead of the
   * fixed-width right rail. The caller (the instance page) picks this when the
   * panel is maximized on a wide layout. Distinct from `panel.isOverlay`, which
   * is the narrow-viewport full-screen sheet handled below. */
  overlay?: boolean;
  /** Show the maximize (focus) control. Only the instance page implements the
   * center-overlay presentation, so the new-session preview leaves this off. */
  canMaximize?: boolean;
  /** One-shot intent from the parent, consumed once on mount. Lets a ⌘T pressed
   * while the panel was closed (this component unmounted, so its own shortcut
   * handler wasn't listening) still open a fresh terminal tab: the page sets the
   * ref and opens the panel, and the freshly-mounted panel runs the action. */
  pendingAction?: { current: PanelPendingAction | null };
  /** Open a specific project file, e.g. from the ⌘P file finder. The `nonce`
   * bumps per request so repeat-opening the same path still fires; reactive
   * (unlike `pendingAction`) so it works whether the panel was already open or
   * is being opened by this same request. */
  openFileRequest?: { path: string; nonce: number } | null;
}

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

function saveErrorMessage(code: string): string {
  const byCode: Record<string, string> = {
    permission_denied: 'permission denied',
    write_failed: 'write failed on the machine',
    not_a_file: 'not a regular file',
    outside_project: 'path is outside the project',
    target_disconnected: 'machine is offline',
    not_connected: 'not connected',
    no_handler: 'update the daemon on this machine to edit files',
    timeout: 'request timed out',
  };
  return byCode[code] ?? code;
}

export function FilesGitPanel({ machineId, cwd, homeDir, instanceId, panel, overlay, canMaximize, pendingAction, openFileRequest }: FilesGitPanelProps) {
  // `desktop` is present exactly when the Electron preload injected a desktop
  // config. Safe to read directly — this component never server-renders
  // (panel.open starts false until the hydration effect runs).
  const desktop = getDesktopConfig() !== null;
  // Windows desktop app. The bundled daemon has no ConPTY backend yet, so a
  // `pty-spawn` against it always fails ("pty-spawn returned no pty_id"). Until
  // ConPTY lands we hide the terminal affordance on Windows rather than offer a
  // button that only errors. false on macOS/web (and in a plain browser even on
  // Windows — no desktop platform signal — so remote terminals to a Mac/Linux
  // machine are unaffected).
  const isWindows = useDesktopWindows();
  // Terminals are offered on desktop (local 127.0.0.1 socket for this machine,
  // relay for another) AND in the plain web dashboard (always via the relay),
  // whenever the session has a machine to reach. An old daemon without the
  // `terminal` capability surfaces a friendly "update" message rather than
  // failing silently (see terminal-pane.tsx). Keyboard shortcuts stay
  // desktop-only below — ⌘T/⌘W collide with the browser's own tab shortcuts.
  const canUseTerminal = (desktop || machineId !== null) && !isWindows;

  const files = useFilesTab({ machineId, cwd, instanceId });
  const git = useGitTab({ machineId, cwd });
  const commits = useCommits({ machineId, cwd });

  // Only worth a toolbar slot when this repo actually has a changed submodule.
  // Also gates on the daemon: `is_submodule` is absent before the
  // `submodule-diff` capability, so an old daemon simply never shows the button.
  const hasChangedSubmodule =
    (git.status?.staged.some((e) => e.is_submodule) ?? false) ||
    (git.status?.unstaged.some((e) => e.is_submodule) ?? false);

  // Docked side panes shown next to an open file (mutually exclusive — they
  // share one slot): the file tree, or the changed-files switcher. Declared up
  // here so the file-index fetch below can stay enabled while the tree drawer
  // is docked, even when the active tab is Changes.
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false);
  const [changesDrawerOpen, setChangesDrawerOpen] = useState(false);

  // Filename search over the project index (same list @-mentions use). Fetched
  // lazily — while the Files tab shows, or while the tree drawer is docked next
  // to an open file (its search box searches the same index).
  const [fileSearch, setFileSearch] = useState('');
  useEffect(() => setFileSearch(''), [instanceId]);
  const absoluteProject = toAbsolutePath(cwd ?? undefined, homeDir);
  const { files: projectFileIndex, isLoading: fileIndexLoading } = useFileMentions({
    projectPath: absoluteProject,
    enabled: panel.open && (panel.activeTab === 'files' || treeDrawerOpen),
  });

  // ── Tab-state model ──────────────────────────────────────────────────────
  // The two fixed tabs (Files / Changes) live in panel state and persist
  // (panel.activeTab). Terminal tabs live in the keep-alive
  // TerminalSessionsProvider, keyed by instanceId — so they (and their shells)
  // survive session switches. In the default (unsplit) layout,
  // `activeTerminalId !== null` means a terminal tab is the visible tab;
  // otherwise it's panel.activeTab. In the split layout (`panel.split`) the
  // terminals move out of the main strip into an always-visible dock stacked
  // below (or above) the files/changes area, with its own mini tab strip —
  // then `activeTerminalId` is the dock's selection and the main strip's
  // visible tab is independent of it.
  const {
    sessions: terminalSessions,
    addTerminal: addSessionTerminal,
    closeTerminal: closeSessionTerminal,
    setActiveTerminal,
    restoreSession,
    attachViewport,
    focusTerminal,
  } = useTerminalSessions();
  const { terminals, activeId: activeTerminalId } =
    terminalSessions[instanceId] ?? EMPTY_SESSION_TERMINALS;
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  // Fixed-viewport coords for the "+" menu. It must be position:fixed, not
  // absolute: the tab strip is `overflow-x-auto`, which computes overflow-y to
  // `auto` too and would clip an absolutely-positioned dropdown that opens
  // below the strip (the bug where "+" appeared to do nothing).
  const [addMenuPos, setAddMenuPos] = useState<{ top: number; left: number } | null>(null);
  const addMenuRef = useRef<HTMLDivElement>(null);
  // The menu is portaled to <body> (see below), so it's not a DOM descendant of
  // addMenuRef — track it separately for the outside-click close handler.
  const addMenuContentRef = useRef<HTMLDivElement>(null);
  const termMachineId = machineId ?? 'local';

  // Restore this session's persisted terminal tabs (desktop) once its machine
  // and project dir are known — the provider re-spawns fresh shells at the
  // saved cwds. Idempotent in the provider (keyed by instanceId), so switching
  // away and back, which remounts this panel, never double-spawns.
  useEffect(() => {
    if (!desktop || isWindows || !machineId || !cwd) return;
    restoreSession(instanceId, machineId);
  }, [desktop, isWindows, machineId, cwd, instanceId, restoreSession]);

  // Run a worktree's setup. Where a terminal is available (desktop/web, non-
  // Windows) it runs — visibly — in a new terminal tab, typed stop-on-failure via
  // `&&`, leaving an interactive shell after (Paseo-style). Where no PTY exists
  // (Windows) it falls back to a background run on the daemon (output → daemon
  // log); `sourceRepo` is the config source + trust key for that path.
  const startWorktreeSetup = useCallback(
    (commands: string[], sourceRepo: string) => {
      if (!cwd) return;
      if (canUseTerminal) {
        const id = addSessionTerminal(
          instanceId,
          termMachineId,
          cwd,
          `${commands.join(' && ')}\r`,
        );
        focusTerminal(instanceId, id);
        return;
      }
      // No terminal (Windows): let the daemon run it in the background.
      if (sourceRepo) {
        void rpcWorktreeRunSetup(termMachineId, cwd, sourceRepo).catch(() => {
          /* daemon offline / untrusted — setup just doesn't run this time */
        });
      }
    },
    [canUseTerminal, cwd, addSessionTerminal, instanceId, termMachineId, focusTerminal],
  );

  // Untrusted committed vicoa.json awaiting the user's confirm (a cloned repo
  // could ship a malicious setup command); null when nothing is pending.
  const [pendingSetup, setPendingSetup] = useState<{
    commands: string[];
    sourceRepo: string;
  } | null>(null);

  // A freshly-created worktree may carry setup commands (committed vicoa.json),
  // handed over by the new-session page via sessionStorage. Run them once, then
  // clear the hand-off so a later visit or panel remount never reruns setup. A
  // trusted repo runs straight away; an untrusted one asks first. Runs on every
  // platform — the terminal-vs-background choice is inside startWorktreeSetup.
  useEffect(() => {
    if (!cwd || typeof window === 'undefined') return;
    const key = `vicoa.session.${instanceId}.setupCommands`;
    let raw: string | null;
    try {
      raw = window.sessionStorage.getItem(key);
      if (raw !== null) window.sessionStorage.removeItem(key);
    } catch {
      return; // sessionStorage unavailable — setup just won't auto-run
    }
    if (raw === null) return;
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }
    if (typeof payload !== 'object' || payload === null) return;
    const { commands, trusted, sourceRepo } = payload as {
      commands?: unknown;
      trusted?: unknown;
      sourceRepo?: unknown;
    };
    const setup = Array.isArray(commands)
      ? commands.filter((c): c is string => typeof c === 'string' && c.trim().length > 0)
      : [];
    if (setup.length === 0) return;
    const repo = typeof sourceRepo === 'string' ? sourceRepo : '';
    if (trusted === true) {
      startWorktreeSetup(setup, repo);
    } else {
      setPendingSetup({ commands: setup, sourceRepo: repo });
    }
  }, [cwd, instanceId, startWorktreeSetup]);

  // Confirm → trust the repo for next time (persisted daemon-side, per repo/
  // machine) and run setup now. A grant failure (daemon offline) still runs it
  // this once; the next spawn re-asks.
  const confirmWorktreeSetup = useCallback(async () => {
    const p = pendingSetup;
    if (!p) return;
    setPendingSetup(null);
    if (p.sourceRepo) {
      try {
        await rpcWorktreeTrustGrant(termMachineId, p.sourceRepo);
      } catch {
        /* grant failed — run once anyway; trust just isn't remembered */
      }
    }
    startWorktreeSetup(p.commands, p.sourceRepo);
  }, [pendingSetup, termMachineId, startWorktreeSetup]);

  // Split layout: terminals dock below/above the files area instead of being
  // ordinary tabs. Only meaningful where terminals are offered at all.
  const splitActive = canUseTerminal && panel.split;

  const showTerminal =
    canUseTerminal && !splitActive && activeTerminalId !== null && files.activeFilePath === null;

  const selectFixedTab = useCallback(
    (tab: 'files' | 'git') => {
      files.activateFile(null);
      // In split layout the dock keeps its own selection — clearing it would
      // blank the always-visible terminal region.
      if (!splitActive) setActiveTerminal(instanceId, null);
      panel.setActiveTab(tab);
      if (tab === 'files') files.refreshAll();
      else {
        git.refresh();
        commits.refresh();
      }
    },
    [setActiveTerminal, instanceId, panel, files, git, commits, splitActive],
  );

  const addTerminal = useCallback(() => {
    if (!cwd) return; // no project directory → nothing to spawn a shell in
    const id = addSessionTerminal(instanceId, termMachineId, cwd);
    setAddMenuOpen(false);
    // Put the cursor in the freshly-opened terminal. Spawn-time term.focus()
    // alone is racy (the pane may not have mounted yet), so focus explicitly by
    // id — the helper retries until that new pane's textarea is visible.
    focusTerminal(instanceId, id);
  }, [addSessionTerminal, instanceId, termMachineId, cwd, focusTerminal]);

  const closeTerminal = useCallback(
    (id: string) => {
      // Closing the dock's last terminal collapses the split — an empty
      // always-visible dock is dead space.
      if (panel.split && terminals.length <= 1) panel.setSplit(false);
      closeSessionTerminal(instanceId, id);
    },
    [closeSessionTerminal, instanceId, panel, terminals.length],
  );

  // Toggle the terminal dock. Turning it on guarantees a live terminal to
  // show (spawning one for a session that has none); turning it off returns
  // the terminals to ordinary tabs — inactive when a file keeps the viewer,
  // otherwise the active terminal simply becomes the visible tab.
  const toggleSplit = useCallback(() => {
    if (panel.split) {
      panel.setSplit(false);
      if (files.activeFilePath !== null) setActiveTerminal(instanceId, null);
      return;
    }
    panel.setSplit(true);
    if (terminals.length === 0) {
      if (cwd) addSessionTerminal(instanceId, termMachineId, cwd);
    } else if (activeTerminalId === null) {
      setActiveTerminal(instanceId, terminals[terminals.length - 1].id);
    }
    focusTerminal(instanceId);
  }, [
    panel,
    files.activeFilePath,
    setActiveTerminal,
    instanceId,
    terminals,
    activeTerminalId,
    cwd,
    addSessionTerminal,
    termMachineId,
    focusTerminal,
  ]);

  // A persisted split must come back with a terminal in the dock. Deferred a
  // tick so the provider's restoreSession state (queued in the mount effect
  // above) lands first — spawning immediately would race the restore and
  // shadow the saved tabs. The ref makes the spawn once-per-session, so a
  // StrictMode double-run can't open two shells.
  const [restoreSettled, setRestoreSettled] = useState(false);
  const splitEnsureRef = useRef<string | null>(null);
  useEffect(() => {
    setRestoreSettled(false);
    const t = window.setTimeout(() => setRestoreSettled(true), 0);
    return () => window.clearTimeout(t);
  }, [instanceId]);
  useEffect(() => {
    if (!splitActive || !restoreSettled) return;
    if (terminals.length > 0) {
      if (activeTerminalId === null) {
        setActiveTerminal(instanceId, terminals[terminals.length - 1].id);
      }
      return;
    }
    if (splitEnsureRef.current === instanceId) return;
    splitEnsureRef.current = instanceId;
    if (cwd) addSessionTerminal(instanceId, termMachineId, cwd);
    else panel.setSplit(false);
  }, [
    splitActive,
    restoreSettled,
    terminals,
    activeTerminalId,
    setActiveTerminal,
    instanceId,
    cwd,
    addSessionTerminal,
    termMachineId,
    panel,
  ]);

  // Where the active terminal renders: the keep-alive layer geometry-syncs
  // the pane over this area while it's registered.
  const terminalViewportRef = useCallback(
    (el: HTMLDivElement | null) => {
      attachViewport(instanceId, el);
    },
    [attachViewport, instanceId],
  );

  // Ctrl+Tab / Ctrl+Shift+Tab cycle through the panel tabs (Files → Changes →
  // open files → terminals), wrapping at both ends; opens the panel when closed.
  // In the split layout the terminals aren't main-strip tabs (the dock is
  // always visible), so the cycle covers the top region only.
  const cycleTab = useCallback(
    (direction: 1 | -1) => {
      const order: Array<
        | { kind: 'fixed'; tab: 'files' | 'git' }
        | { kind: 'file'; path: string }
        | { kind: 'term'; id: string }
      > = [
        { kind: 'fixed', tab: 'files' },
        { kind: 'fixed', tab: 'git' },
        ...files.openFiles.map((f) => ({ kind: 'file' as const, path: f.path })),
        ...(desktop && !splitActive
          ? terminals.map((t) => ({ kind: 'term' as const, id: t.id }))
          : []),
      ];
      const currentIndex =
        showTerminal && activeTerminalId !== null
          ? order.findIndex((entry) => entry.kind === 'term' && entry.id === activeTerminalId)
          : files.activeFilePath !== null
            ? order.findIndex((entry) => entry.kind === 'file' && entry.path === files.activeFilePath)
            : order.findIndex((entry) => entry.kind === 'fixed' && entry.tab === panel.activeTab);
      const next = order[(currentIndex + direction + order.length) % order.length];
      panel.setOpen(true);
      if (next.kind === 'fixed') {
        selectFixedTab(next.tab);
      } else if (next.kind === 'file') {
        if (!splitActive) setActiveTerminal(instanceId, null);
        files.activateFile(next.path);
      } else {
        files.activateFile(null);
        setActiveTerminal(instanceId, next.id);
        // Cycling onto a terminal should land the cursor in it, like clicking
        // the tab does — pass the id since the active-tab change isn't in state
        // yet.
        focusTerminal(instanceId, next.id);
      }
    },
    [desktop, terminals, showTerminal, activeTerminalId, panel, files, selectFixedTab, setActiveTerminal, focusTerminal, instanceId, splitActive],
  );

  // A ⌘T pressed while the panel was closed can't be handled here (we were
  // unmounted). The page opens the panel and flags `pendingAction` instead; run
  // it now, once, on mount. This lands *after* useFilesTab's restore effect (it
  // runs its hook first), so activateFile(null) wins over any reopened file and
  // the new terminal is what shows.
  useEffect(() => {
    if (pendingAction?.current !== 'new-terminal') return;
    pendingAction.current = null;
    if (!canUseTerminal) return;
    // Split layout: the dock shows the new terminal alongside whatever file is
    // open, so don't clear the viewer.
    if (!splitActive) files.activateFile(null);
    addTerminal();
    // Mount-only: a fresh ref value means a fresh mount (the panel just opened).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Panel keyboard shortcuts (desktop only), rebindable in Settings →
  // Keyboard shortcuts (matchesShortcut reads the live bindings). Capture
  // phase so a focused terminal/textarea can't swallow the combo. Defaults:
  //   ⌘⇧D — open the diff (Changes) view
  //   ⌘⇧T — new terminal tab (anywhere)
  //   ⌘T  — new terminal tab (only while a terminal is focused)
  //   ⌘W  — close the active tab: the showing terminal or the open file
  //   Ctrl+Tab / Ctrl+⇧Tab — cycle panel tabs (fixed, handled inline below)
  useEffect(() => {
    if (!desktop) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const inTerminal = Boolean(
        (document.activeElement as HTMLElement | null)?.closest('[data-terminal-pane]'),
      );
      if (matchesShortcut(event, 'open-diff')) {
        event.preventDefault();
        panel.setOpen(true);
        selectFixedTab('git');
      } else if (matchesShortcut(event, 'open-files')) {
        event.preventDefault();
        panel.setOpen(true);
        selectFixedTab('files');
      } else if (canUseTerminal && matchesShortcut(event, 'terminal-new')) {
        event.preventDefault();
        panel.setOpen(true);
        addTerminal();
      } else if (canUseTerminal && matchesShortcut(event, 'terminal-new-focused')) {
        event.preventDefault();
        if (inTerminal) {
          // Terminal already focused → open another tab.
          addTerminal();
        } else {
          // From anywhere else ⌘T jumps to the terminal, opening the panel
          // and creating a tab if the session has none yet. With the dock up
          // the open file stays — the terminal is visible beside it.
          panel.setOpen(true);
          if (!splitActive) files.activateFile(null);
          if (activeTerminalId === null) {
            if (terminals.length > 0) {
              setActiveTerminal(instanceId, terminals[terminals.length - 1].id);
            } else if (cwd) {
              addSessionTerminal(instanceId, termMachineId, cwd);
            }
          }
          focusTerminal(instanceId);
        }
      } else if (matchesShortcut(event, 'terminal-close')) {
        // ⌘W closes whichever tab is currently showing — the active terminal
        // or the open file. (The fixed Files/Changes tabs aren't closable, so
        // it's a no-op there and left unprevented for the app to handle.)
        // With the dock up both surfaces show at once, so focus decides: a
        // focused terminal closes, anything else closes the open file.
        if (splitActive && inTerminal && activeTerminalId !== null) {
          event.preventDefault();
          closeTerminal(activeTerminalId);
        } else if (showTerminal && activeTerminalId !== null) {
          event.preventDefault();
          closeTerminal(activeTerminalId);
        } else if (files.activeFilePath !== null) {
          event.preventDefault();
          files.closeFileTab(files.activeFilePath);
        }
      } else if (event.ctrlKey && event.code === 'Tab' && !event.metaKey && !event.altKey) {
        // Ctrl+Tab / Ctrl+Shift+Tab cycle the panel tabs (VSCode/browser
        // convention). Tab has no text-editing meaning, so — unlike the old
        // ⌘←/→ binding — this fires even while editing a file or in a terminal.
        // Capture phase (below) means we win before CodeMirror/xterm see it.
        event.preventDefault();
        cycleTab(event.shiftKey ? -1 : 1);
      } else if (canUseTerminal && matchesShortcut(event, 'terminal-focus')) {
        // Jump to the terminal from anywhere: open the panel, surface the
        // last-used terminal (creating one if none exist), and focus it.
        event.preventDefault();
        panel.setOpen(true);
        if (!splitActive) files.activateFile(null);
        if (activeTerminalId === null) {
          if (terminals.length > 0) {
            setActiveTerminal(instanceId, terminals[terminals.length - 1].id);
          } else if (cwd) {
            addSessionTerminal(instanceId, termMachineId, cwd);
          }
        }
        focusTerminal(instanceId);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [
    desktop,
    canUseTerminal,
    panel,
    selectFixedTab,
    addTerminal,
    closeTerminal,
    activeTerminalId,
    showTerminal,
    splitActive,
    files,
    terminals,
    setActiveTerminal,
    addSessionTerminal,
    focusTerminal,
    cycleTab,
    instanceId,
    termMachineId,
    cwd,
  ]);

  // Close the "+" menu on any outside click.
  useEffect(() => {
    if (!addMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const insideButton = addMenuRef.current?.contains(target) ?? false;
      const insideMenu = addMenuContentRef.current?.contains(target) ?? false;
      if (!insideButton && !insideMenu) {
        setAddMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [addMenuOpen]);

  // Width of the docked side pane (tree / changed-files) next to an open file.
  // A persisted global preference, like the panel width.
  const [sideWidth, setSideWidthState] = useState(280);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = Number(window.localStorage.getItem('vicoa:files:side-width'));
    if (Number.isFinite(stored) && stored >= 180) setSideWidthState(stored);
  }, []);
  const sideDragRef = useRef(false);
  const onSideResize = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      sideDragRef.current = true;
      const startX = event.clientX;
      const startW = sideWidth;
      // The pane sits on the right, so dragging left grows it.
      const widthAt = (e: PointerEvent) => Math.max(180, Math.round(startW + (startX - e.clientX)));
      const move = (e: PointerEvent) => {
        if (!sideDragRef.current) return;
        setSideWidthState(widthAt(e));
      };
      const up = (e: PointerEvent) => {
        sideDragRef.current = false;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        window.localStorage.setItem('vicoa:files:side-width', String(widthAt(e)));
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [sideWidth],
  );
  // Overflow "⋯" menu on the Changes toolbar (portaled, same reasons as the
  // tab strip's "+" menu — see that comment).
  const [gitMenuOpen, setGitMenuOpen] = useState(false);
  const [gitMenuPos, setGitMenuPos] = useState<{ top: number; right: number } | null>(null);
  const gitMenuRef = useRef<HTMLDivElement>(null);
  const gitMenuContentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!gitMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const insideButton = gitMenuRef.current?.contains(target) ?? false;
      const insideMenu = gitMenuContentRef.current?.contains(target) ?? false;
      if (!insideButton && !insideMenu) setGitMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [gitMenuOpen]);
  // Overflow "⋯" menu on the file-view toolbar — collects the lower-frequency
  // actions (copy, split diff, diff baseline) so the toolbar isn't a wall of
  // icons. Same portaled/outside-click machinery as the Changes menu above.
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [fileMenuPos, setFileMenuPos] = useState<{ top: number; right: number } | null>(null);
  const fileMenuRef = useRef<HTMLDivElement>(null);
  const fileMenuContentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!fileMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const insideButton = fileMenuRef.current?.contains(target) ?? false;
      const insideMenu = fileMenuContentRef.current?.contains(target) ?? false;
      if (!insideButton && !insideMenu) setFileMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [fileMenuOpen]);
  // Which breadcrumb folder currently opened the drawer, so clicking that same
  // folder again toggles it closed (clicking a different one switches to it).
  const [revealedDir, setRevealedDir] = useState<string | null>(null);
  // Markdown files open in the formatted live-preview editor; this flips to the
  // raw source view.
  const [markdownSource, setMarkdownSource] = useState(false);
  // Change-to-change navigation handle published by the open diff surface, so
  // the toolbar's up/down buttons can step through the file's changed chunks.
  // Null whenever no editable diff is mounted (the buttons then sit disabled).
  const [diffNav, setDiffNav] = useState<DiffNav | null>(null);
  // Diff-view layout: inline (single-panel) vs side-by-side (two panels). A
  // persisted global preference, like the git tab's toggles.
  const [diffSideBySide, setDiffSideBySide] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    setDiffSideBySide(window.localStorage.getItem('vicoa:files:diff-side-by-side') === '1');
  }, []);
  const toggleDiffSideBySide = useCallback(() => {
    setDiffSideBySide((v) => {
      const next = !v;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('vicoa:files:diff-side-by-side', next ? '1' : '0');
      }
      return next;
    });
  }, []);
  const [copied, setCopied] = useState(false);
  const [pathCopied, setPathCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  // Wraps the panel's content area (viewer / diff / tree) — scopes the in-file
  // find highlighter and the CodeMirror-vs-read-only surface detection.
  const bodyRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  // In-file find (⌘F): a floating bar over the open file / git diff. It drives
  // CodeMirror (editable files/diffs) or the read-only highlighter (git diff,
  // read-only bodies) depending on the surface, picked when the bar opens.
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState('');
  const [findCase, setFindCase] = useState(false);
  const [findWord, setFindWord] = useState(false);
  const [findRegex, setFindRegex] = useState(false);
  // Whether the surface under find is a CodeMirror editor (vs a read-only DOM
  // surface). Sampled from the DOM when the bar opens; find closes on nav, so
  // it stays valid for the bar's lifetime.
  const [findCmSurface, setFindCmSurface] = useState(false);

  // Collapsible + resizable "Commits" pane at the bottom of the Changes tab.
  const [commitsOpen, setCommitsOpen] = useState(false);
  const [commitsHeight, setCommitsHeight] = useState(260);
  const commitsDragRef = useRef(false);
  const changesSplitRef = useRef<HTMLDivElement>(null);
  const onCommitsResize = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      commitsDragRef.current = true;
      const startY = event.clientY;
      const startH = commitsHeight;
      const move = (e: PointerEvent) => {
        if (!commitsDragRef.current) return;
        const delta = startY - e.clientY; // drag up grows the pane
        // Cap to the split container so the pane can grow to nearly the full
        // panel height (leaving a sliver of the working-tree view) without
        // overflowing it.
        const container = changesSplitRef.current?.clientHeight ?? 0;
        const maxH = container > 0 ? container - 56 : 2000;
        setCommitsHeight(Math.max(120, Math.min(startH + delta, maxH)));
      };
      const up = () => {
        commitsDragRef.current = false;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [commitsHeight],
  );

  // Resize handle
  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      draggingRef.current = true;
      setDragging(true);
      const startX = event.clientX;
      const startWidth = panel.effectiveWidth;
      const move = (e: PointerEvent) => {
        if (!draggingRef.current) return;
        const delta = startX - e.clientX;
        panel.setWidth(startWidth + delta);
      };
      const up = () => {
        draggingRef.current = false;
        setDragging(false);
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [panel],
  );

  // Terminal-dock height resize (split layout). Same idiom as the commits
  // pane: drag toward the files area grows the dock, capped so a sliver of
  // the top region always stays visible.
  const dockDragRef = useRef(false);
  const onDockResize = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      dockDragRef.current = true;
      const startY = event.clientY;
      const startH = panel.splitHeight;
      const dockOnTop = panel.splitTop;
      const move = (e: PointerEvent) => {
        if (!dockDragRef.current) return;
        const delta = dockOnTop ? e.clientY - startY : startY - e.clientY;
        const container = rootRef.current?.clientHeight ?? 0;
        const maxH = container > 0 ? container - 160 : 2000;
        panel.setSplitHeight(Math.min(startH + delta, maxH));
      };
      const up = () => {
        dockDragRef.current = false;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [panel],
  );

  // Refresh on visibility / focus. Terminal tabs need no refresh — their pty
  // stream is push-based.
  useEffect(() => {
    if (!panel.open) return;
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return;
      // Unsplit, an active terminal means no files/git surface is showing. In
      // the split layout the dock's selection is always set, but the top
      // region still shows files/changes — refresh those.
      if (!splitActive && activeTerminalId !== null) return;
      if (panel.activeTab === 'files') files.refreshAll();
      else if (panel.activeTab === 'git') {
        git.refresh();
        commits.refresh();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [panel.open, panel.activeTab, activeTerminalId, splitActive, files, git, commits]);

  // The drawers only exist over a file view — drop them whenever no file is active.
  useEffect(() => {
    if (files.activeFilePath === null) {
      setTreeDrawerOpen(false);
      setChangesDrawerOpen(false);
    }
  }, [files.activeFilePath]);

  // Ordered changed-file paths (staged → unstaged → untracked) backing the
  // changed-files switcher drawer and ⌥⌘↑/↓ cycling.
  const changedFilePaths = useMemo(
    () => changedFileEntries(git.status).map((e) => e.path),
    [git.status],
  );
  const cycleChangedFile = useCallback(
    (direction: 1 | -1) => {
      if (changedFilePaths.length === 0) return;
      const cur = files.activeFilePath;
      const i = cur ? changedFilePaths.indexOf(cur) : -1;
      const next =
        i < 0
          ? changedFilePaths[direction === 1 ? 0 : changedFilePaths.length - 1]
          : changedFilePaths[(i + direction + changedFilePaths.length) % changedFilePaths.length];
      if (!splitActive) setActiveTerminal(instanceId, null);
      files.openFile(next, { mode: 'diff', preview: true });
    },
    [changedFilePaths, files, setActiveTerminal, instanceId, splitActive],
  );
  // ⌥⌘↑/↓ (⌥⌃↑/↓ off-mac) step through the changed files as editable diffs.
  useEffect(() => {
    if (!panel.open) return;
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || !(e.metaKey || e.ctrlKey)) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        cycleChangedFile(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        cycleChangedFile(-1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [panel.open, cycleChangedFile]);

  // Each markdown file opens in the formatted view; reset the source toggle
  // when the active file changes.
  useEffect(() => {
    setMarkdownSource(false);
  }, [files.activeFilePath]);

  // Escape closes whichever right drawer is open. Bubble phase (not capture) so
  // the tree drawer's own search box handles Escape first — FileSearchRow stops
  // propagation to clear a non-empty query, and only an unhandled Escape bubbles
  // up to close here.
  useEffect(() => {
    if (!treeDrawerOpen && !changesDrawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setTreeDrawerOpen(false);
        setChangesDrawerOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [treeDrawerOpen, changesDrawerOpen]);

  // Open the find bar, sampling whether the current surface is a CodeMirror
  // editor so the right engine drives it, and prefilling any selected text.
  const openFind = useCallback(() => {
    setFindCmSurface(!!bodyRef.current?.querySelector('.cm-editor'));
    const selection =
      typeof window !== 'undefined' ? window.getSelection?.()?.toString().trim() ?? '' : '';
    if (selection) setFindQuery(selection.slice(0, 200));
    setFindOpen(true);
  }, []);
  const closeFind = useCallback(() => setFindOpen(false), []);

  // ⌘F inside the files panel searches the open FILE (not the chat transcript,
  // whose global handler yields to us — see the instance page). The bare Files
  // tree instead jumps into the fuzzy file finder.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat) return;
      if (!matchesShortcut(event, 'find-in-page')) return;
      // Only when this panel is the ⌘F target: the maximized overlay always is;
      // the rail only while focus is inside it. Otherwise leave ⌘F to the chat.
      const focusInside = rootRef.current?.contains(document.activeElement as Node) ?? false;
      if (!overlay && !focusInside) return;
      const activeEl = document.activeElement as HTMLElement | null;
      // A live terminal owns its own key handling.
      if (activeEl?.closest('[data-terminal-pane]') || showTerminal) return;

      // Stop the event before it reaches CodeMirror's own `searchKeymap` (which
      // would open its native panel on top of our bar when the editor is focused).
      event.preventDefault();
      event.stopPropagation();
      // Bare Files tree (nothing open) → jump into the fuzzy file finder.
      if (files.activeFilePath === null && panel.activeTab === 'files') {
        panel.setOpen(true);
        requestAnimationFrame(() => {
          const input = rootRef.current?.querySelector<HTMLInputElement>('input[data-file-search]');
          input?.focus();
          input?.select();
        });
        return;
      }
      // Find bar already open → re-focus its input and select the current term
      // so a repeat ⌘F lets the user just type over it to start a new search
      // (previously it was a no-op once the bar was already open).
      if (findOpen) {
        const input = rootRef.current?.querySelector<HTMLInputElement>('input[data-file-find]');
        input?.focus();
        input?.select();
        return;
      }
      openFind();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [overlay, showTerminal, files, panel, openFind, findOpen]);

  // Close the find bar when navigating to another file/tab — the highlighted
  // ranges/selection point into the surface it opened over.
  useEffect(() => {
    setFindOpen(false);
  }, [files.activeFilePath, panel.activeTab]);

  const findOptions = useMemo<FindOptions>(
    () => ({ caseSensitive: findCase, regexp: findRegex, wholeWord: findWord }),
    [findCase, findRegex, findWord],
  );
  const cmFind = useCmFind(bodyRef, findQuery, findOptions, findOpen && findCmSurface);
  const domFind = useInFileFind(
    bodyRef,
    findQuery,
    findOpen && !findCmSurface,
    findOptions,
    `${panel.activeTab}:${files.activeFilePath ?? ''}`,
  );
  const find = findCmSurface ? cmFind : domFind;

  if (!panel.hydrated) {
    return null;
  }

  if (!panel.open) {
    return null;
  }

  const activeFile = files.activeFile;
  const inViewer = activeFile !== null;
  const activeIsMarkdown = activeFile ? isMarkdownPath(basename(activeFile.path)) : false;
  // Editing is offered for any text file whose daemon supports writing (the read
  // returned a content hash). Markdown edits in both surfaces now: the formatted
  // live-preview editor and the raw source view.
  const canEditHere = !!activeFile && isEditable(activeFile);
  // Open files with unsaved edits — dotted in the tab strip and the tree.
  const dirtyPaths = useMemo(
    () => new Set(files.openFiles.filter((f) => f.dirty).map((f) => f.path)),
    [files.openFiles],
  );
  // Git-changed files (working tree): the status letter per path drives the tree
  // row color, and `changedDirs` tints every ancestor folder so a change stays
  // visible when its folder is collapsed (VSCode-style rollup). Untracked dirs
  // (trailing slash) are skipped — they aren't file rows.
  const { changedStatus, changedDirs } = useMemo(() => {
    const statusMap = new Map<string, string>();
    const dirs = new Set<string>();
    const s = git.status;
    if (s) {
      for (const list of [s.staged, s.unstaged, s.untracked]) {
        for (const e of list) {
          if (e.path.endsWith('/')) continue;
          if (!statusMap.has(e.path)) statusMap.set(e.path, e.status);
          const slash = e.path.lastIndexOf('/');
          if (slash > 0) for (const dir of ancestorPaths(e.path.slice(0, slash))) dirs.add(dir);
        }
      }
    }
    return { changedStatus: statusMap, changedDirs: dirs };
  }, [git.status]);
  // The active file's viewer offers a Diff toggle only when it actually has
  // uncommitted changes; `inDiffMode` drives the toggle's icon and the
  // side-by-side control's visibility.
  const activeChanged = !!activeFile && changedStatus.has(activeFile.path);
  const inDiffMode = !!activeFile && activeFile.viewMode === 'diff';
  // Paths with staged content. The diff baseline toggle (HEAD ⇄ staged) is only
  // meaningful for these — with nothing staged the index equals HEAD, so both
  // baselines produce the same diff and the control would be a no-op.
  const stagedPaths = useMemo(() => {
    const set = new Set<string>();
    for (const e of git.status?.staged ?? []) set.add(e.path);
    return set;
  }, [git.status]);
  const activeFileStaged = !!activeFile && stagedPaths.has(activeFile.path);

  // File-open handlers: a single click opens a preview tab (reuses one slot),
  // a double click (`{ newTab: true }`) opens a permanent tab. The tree/search
  // open in edit mode; the Changes list/switcher open the editable diff.
  const openFromTree = (path: string, opts?: { newTab?: boolean }) => {
    if (!splitActive) setActiveTerminal(instanceId, null);
    files.openFile(path, { preview: !opts?.newTab });
  };
  const openFromChanges = (path: string, opts?: { newTab?: boolean }) => {
    if (!splitActive) setActiveTerminal(instanceId, null);
    files.openFile(path, { mode: 'diff', preview: !opts?.newTab });
  };

  // Open the file requested by the ⌘P finder (or any parent). Nonce-guarded so
  // it fires once per request — including on a fresh mount, when the same
  // request that opened the panel is still the current prop. Mirrors
  // `openFromTree` (clear the visible terminal, then open in edit mode).
  const lastOpenFileNonce = useRef(0);
  useEffect(() => {
    if (!openFileRequest || openFileRequest.nonce === lastOpenFileNonce.current) return;
    lastOpenFileNonce.current = openFileRequest.nonce;
    if (!splitActive) setActiveTerminal(instanceId, null);
    files.openFile(openFileRequest.path, { preview: false });
    // `files`/`setActiveTerminal` are stable enough; the nonce guard makes a
    // spurious re-run a no-op, so key the effect on the request identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openFileRequest, instanceId, splitActive]);
  // Commit the staged set; the history pane below shows the new commit, so
  // refresh it on success (the hook already refreshes the working-tree status).
  const handleCommit = () => {
    void git.commit(git.commitMessage).then((ok) => {
      if (ok) commits.refresh();
    });
  };
  const handleCopy = async () => {
    const content = activeFile?.result?.content;
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  const handleCopyPath = async () => {
    const path = activeFile?.path;
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      setPathCopied(true);
      setTimeout(() => setPathCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  const headerLeft = (
    <div className={`flex items-center text-xs font-mono min-w-0 flex-1 overflow-x-auto ${TAB_SCROLL_STYLE}`}>
      <FixedTab active={!showTerminal && !inViewer && panel.activeTab === 'files'} onClick={() => selectFixedTab('files')}>
        Files
      </FixedTab>
      <FixedTab active={!showTerminal && !inViewer && panel.activeTab === 'git'} onClick={() => selectFixedTab('git')}>
        Changes
      </FixedTab>
      {files.openFiles.map((f) => (
        <FileTab
          key={f.path}
          fileName={basename(f.path)}
          active={inViewer && files.activeFilePath === f.path}
          dirty={f.dirty}
          preview={f.preview}
          statusColor={gitStatusColor(changedStatus.get(f.path))}
          onSelect={() => {
            if (!splitActive) setActiveTerminal(instanceId, null);
            files.activateFile(f.path);
          }}
          onOpen={() => files.openFile(f.path, { preview: false })}
          onClose={() => files.closeFileTab(f.path)}
        />
      ))}
      {canUseTerminal &&
        !splitActive &&
        terminals.map((t, i) => (
          <TerminalTab
            key={t.id}
            label={i === 0 ? 'Terminal' : `Terminal ${i + 1}`}
            active={showTerminal && activeTerminalId === t.id}
            onSelect={() => {
              files.activateFile(null);
              setActiveTerminal(instanceId, t.id);
              focusTerminal(instanceId, t.id);
            }}
            onClose={() => closeTerminal(t.id)}
          />
        ))}
      {canUseTerminal && !splitActive && (
        <div className="flex-shrink-0" ref={addMenuRef}>
          <button
            aria-label="Add tab"
            style={NO_DRAG}
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              setAddMenuPos({ top: r.bottom + 4, left: r.left });
              setAddMenuOpen((o) => !o);
            }}
            className="px-2 py-1 text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          {/* Portaled to <body>: the center-overlay panel root is a z-20
              stacking context, which would otherwise trap this fixed z-50 menu
              below the root-level keep-alive terminal overlay (z-45) — so the
              dropdown opened over an active terminal was hidden behind it. The
              menu uses fixed viewport coords, so a portal is a clean escape. */}
          {addMenuOpen &&
            addMenuPos &&
            typeof document !== 'undefined' &&
            createPortal(
              <div
                ref={addMenuContentRef}
                className="fixed z-50 min-w-[8rem] rounded-md border border-border py-1 shadow-lg"
                style={{ top: addMenuPos.top, left: addMenuPos.left, backgroundColor: DROPDOWN_BG }}
              >
                <button
                  onClick={addTerminal}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-foreground hover:bg-muted/40"
                >
                  <TerminalIcon className="h-3.5 w-3.5" />
                  Terminal
                </button>
              </div>,
              document.body,
            )}
        </div>
      )}
    </div>
  );

  const headerRight = (
    <div style={NO_DRAG} className="flex items-center gap-0.5 flex-shrink-0">
      {!inViewer && !showTerminal && panel.activeTab === 'files' && (
        <TipButton label="Refresh" onClick={files.refreshAll}>
          <RefreshCw className="h-4 w-4" />
        </TipButton>
      )}
      {/* Focus mode: fill the window for comfortable reading. Pointless when the
          panel is already a full-screen overlay (narrow viewports), so hide it
          there. */}
      {canMaximize && !panel.isOverlay && (
        <TipButton
          label={panel.maximized ? 'Exit full width' : 'Maximize'}
          active={panel.maximized}
          onClick={panel.toggleMaximized}
          extraClass="ml-1"
        >
          {panel.maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </TipButton>
      )}
      {canUseTerminal && !!cwd && (
        <TipButton
          label={splitActive ? 'Hide terminal panel' : 'Terminal panel'}
          active={splitActive}
          onClick={toggleSplit}
        >
          <PanelBottom className="h-4 w-4" />
        </TipButton>
      )}
      <TipButton label="Close panel" onClick={() => panel.setOpen(false)}>
        <X className="h-4 w-4" />
      </TipButton>
    </div>
  );

  const noMachine = !machineId || !cwd;

  // Contextual toolbar row under the tab strip: breadcrumb + file-view controls
  // when a file is open; branch info + git controls when Changes is active
  // (panel-rendered so the controls work even while the diff list is loading).
  const contextRow =
    inViewer && activeFile ? (
      <div className="flex items-center gap-1 border-b border-border px-2 py-1 flex-shrink-0">
        <FileBreadcrumb
          path={activeFile.path}
          onOpenDir={(dir) => {
            if (treeDrawerOpen && revealedDir === dir) {
              setTreeDrawerOpen(false);
            } else {
              files.revealDir(dir);
              setRevealedDir(dir);
              setChangesDrawerOpen(false);
              setTreeDrawerOpen(true);
            }
          }}
        />
        <div style={NO_DRAG} className="flex items-center gap-0.5 flex-shrink-0">
          {activeFile &&
            activeFile.editing &&
            (canEditHere || activeFile.dirty) &&
            (activeFile.saving ? (
              <TipButton label="Saving…" onClick={() => {}}>
                <Loader2 className="h-4 w-4 animate-spin" />
              </TipButton>
            ) : (
              <TipButton
                label={
                  activeFile.dirty
                    ? `Save (${comboInline({ code: 'KeyS', meta: true, shift: false, alt: false })})`
                    : 'Saved'
                }
                extraClass={activeFile.dirty ? undefined : 'opacity-40'}
                onClick={() => files.saveFile(activeFile.path)}
              >
                <Save className="h-4 w-4" />
              </TipButton>
            ))}
          {activeChanged && (
            <TipButton
              label={inDiffMode ? 'Edit file' : 'View changes'}
              active={inDiffMode}
              onClick={() => files.setViewMode(activeFile.path, inDiffMode ? 'edit' : 'diff')}
            >
              {inDiffMode ? <FileText className="h-4 w-4" /> : <GitCompareArrows className="h-4 w-4" />}
            </TipButton>
          )}
          {inDiffMode && (
            <>
              <TipButton
                label="Previous change"
                disabled={!diffNav || diffNav.count === 0}
                onClick={() => diffNav?.prev()}
              >
                <ArrowUp className="h-4 w-4" />
              </TipButton>
              <TipButton
                label="Next change"
                disabled={!diffNav || diffNav.count === 0}
                onClick={() => diffNav?.next()}
              >
                <ArrowDown className="h-4 w-4" />
              </TipButton>
            </>
          )}
          {activeIsMarkdown && !inDiffMode && (
            <TipButton
              label={markdownSource ? 'Formatted view' : 'Source view'}
              active={markdownSource}
              onClick={() => setMarkdownSource((v) => !v)}
            >
              {markdownSource ? <Eye className="h-4 w-4" /> : <Code className="h-4 w-4" />}
            </TipButton>
          )}
          {changedFilePaths.length > 0 && (
            <TipButton
              label={changesDrawerOpen ? 'Hide changed files' : 'Changed files'}
              active={changesDrawerOpen}
              onClick={() =>
                setChangesDrawerOpen((v) => {
                  if (!v) setTreeDrawerOpen(false);
                  return !v;
                })
              }
            >
              <FileDiff className="h-4 w-4" />
            </TipButton>
          )}
          <TipButton
            label={treeDrawerOpen ? 'Hide file tree' : 'Show in Files'}
            active={treeDrawerOpen}
            onClick={() =>
              setTreeDrawerOpen((v) => {
                if (!v) setChangesDrawerOpen(false);
                return !v;
              })
            }
          >
            <PanelRight className="h-4 w-4" />
          </TipButton>
          <div ref={fileMenuRef}>
            <TipButton
              label="More actions"
              active={fileMenuOpen}
              onClick={() => {
                const r = fileMenuRef.current?.getBoundingClientRect();
                if (r) setFileMenuPos({ top: r.bottom + 4, right: window.innerWidth - r.right });
                setFileMenuOpen((o) => !o);
              }}
            >
              <MoreHorizontal className="h-4 w-4" />
            </TipButton>
          </div>
          {/* Portaled + right-anchored like the Changes menu. Toggles (split
              diff, diff baseline) keep the menu open; Copy is a one-shot action
              so it closes. */}
          {fileMenuOpen &&
            fileMenuPos &&
            typeof document !== 'undefined' &&
            createPortal(
              <div
                ref={fileMenuContentRef}
                className="fixed z-50 min-w-[13rem] rounded-md border border-border py-1 shadow-lg"
                style={{ top: fileMenuPos.top, right: fileMenuPos.right, backgroundColor: DROPDOWN_BG }}
              >
                {inDiffMode && (
                  // Action-worded (not a checkmark toggle): the label says what
                  // the click does, which reads clearer than a static "Split
                  // diff" + check.
                  <GitMenuItem
                    icon={<Columns2 className="h-3.5 w-3.5" />}
                    label={diffSideBySide ? 'Switch to inline diff' : 'Switch to side-by-side diff'}
                    onClick={toggleDiffSideBySide}
                  />
                )}
                {inDiffMode && activeFileStaged && (
                  <GitMenuItem
                    icon={<GitCompareArrows className="h-3.5 w-3.5" />}
                    label="Compare against staged"
                    active={activeFile.baseRef === 'index'}
                    onClick={() =>
                      files.setDiffBaseRef(
                        activeFile.path,
                        activeFile.baseRef === 'index' ? 'HEAD' : 'index',
                      )
                    }
                  />
                )}
                <GitMenuItem
                  icon={copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  label={copied ? 'Copied' : 'Copy file contents'}
                  onClick={() => {
                    void handleCopy();
                    setFileMenuOpen(false);
                  }}
                />
                <GitMenuItem
                  icon={
                    pathCopied ? <Check className="h-3.5 w-3.5" /> : <LinkIcon className="h-3.5 w-3.5" />
                  }
                  label={pathCopied ? 'Copied' : 'Copy file path'}
                  onClick={() => {
                    void handleCopyPath();
                    setFileMenuOpen(false);
                  }}
                />
              </div>,
              document.body,
            )}
        </div>
      </div>
    ) : !showTerminal && !noMachine && panel.activeTab === 'git' ? (
      <div className="flex items-center gap-2 border-b border-border px-3 py-1 flex-shrink-0">
        <BranchInfo status={git.status} />
        <div style={NO_DRAG} className="flex items-center gap-0.5 flex-shrink-0 ml-auto">
          <TipButton label="Refresh" onClick={git.refresh}>
            <RefreshCw className="h-4 w-4" />
          </TipButton>
          <TipButton
            label={git.expanded.size > 0 ? 'Collapse all' : 'Expand all'}
            onClick={git.expanded.size > 0 ? git.collapseAll : git.expandAll}
          >
            {git.expanded.size > 0 ? (
              <ChevronsDownUp className="h-4 w-4" />
            ) : (
              <ChevronsUpDown className="h-4 w-4" />
            )}
          </TipButton>
          <div ref={gitMenuRef}>
            <TipButton
              label="More actions"
              active={gitMenuOpen}
              onClick={() => {
                const r = gitMenuRef.current?.getBoundingClientRect();
                if (r) setGitMenuPos({ top: r.bottom + 4, right: window.innerWidth - r.right });
                setGitMenuOpen((o) => !o);
              }}
            >
              <MoreHorizontal className="h-4 w-4" />
            </TipButton>
          </div>
          {/* Portaled for the same stacking-context reason as the tab strip's
              "+" menu. Right-anchored so it hugs the panel edge. Every item is a
              toggle that keeps the menu open (flipping several at once is the
              common case). */}
          {gitMenuOpen &&
            gitMenuPos &&
            typeof document !== 'undefined' &&
            createPortal(
              <div
                ref={gitMenuContentRef}
                className="fixed z-50 min-w-[13rem] rounded-md border border-border py-1 shadow-lg"
                style={{ top: gitMenuPos.top, right: gitMenuPos.right, backgroundColor: DROPDOWN_BG }}
              >
                <GitMenuItem
                  icon={<ListTree className="h-3.5 w-3.5" />}
                  label={git.treeView ? 'View as list' : 'View as tree'}
                  active={git.treeView}
                  onClick={git.toggleTreeView}
                />
                <GitMenuItem
                  icon={<WrapText className="h-3.5 w-3.5" />}
                  label="Word wrap"
                  active={git.wrapLines}
                  onClick={git.toggleWrap}
                />
                <GitMenuItem
                  icon={<Pilcrow className="h-3.5 w-3.5" />}
                  label="Hide whitespace"
                  active={git.hideWhitespace}
                  onClick={git.toggleHideWhitespace}
                />
                {hasChangedSubmodule && (
                  <GitMenuItem
                    icon={<FolderGit2 className="h-3.5 w-3.5" />}
                    label="Changes inside submodules"
                    active={git.expandSubmodules}
                    onClick={git.toggleExpandSubmodules}
                  />
                )}
                {panel.splitDiffEnabled && (
                  <GitMenuItem
                    icon={<Columns2 className="h-3.5 w-3.5" />}
                    label="Split diff"
                    active={git.splitView}
                    onClick={git.toggleSplitView}
                  />
                )}
              </div>,
              document.body,
            )}
        </div>
      </div>
    ) : null;

  const body = (
    <div ref={bodyRef} className="flex-1 min-h-0 relative">
      {/* Floating in-file find bar (⌘F). Drives CodeMirror or the read-only
          highlighter depending on the surface it opened over. */}
      {findOpen && !showTerminal && (
        <FileFindBar
          query={findQuery}
          onQueryChange={setFindQuery}
          matchCount={find.matchCount}
          activeOrdinal={find.activeOrdinal}
          regexError={find.regexError}
          onNext={find.goNext}
          onPrev={find.goPrev}
          onClose={closeFind}
          caseSensitive={findCase}
          onToggleCase={() => setFindCase((v) => !v)}
          wholeWord={findWord}
          onToggleWholeWord={() => setFindWord((v) => !v)}
          regexp={findRegex}
          onToggleRegexp={() => setFindRegex((v) => !v)}
        />
      )}
      {/* Terminal panes live in the keep-alive TerminalSessionsProvider so
          they survive session switches; this div just marks where the active
          pane should be shown while a terminal tab is selected. */}
      {showTerminal ? (
        <div ref={terminalViewportRef} className="absolute inset-0" />
      ) : noMachine ? (
        <div className="flex items-center justify-center h-full px-4 text-center text-sm text-muted-foreground font-mono">
          Connect a machine to browse files and see git changes.
        </div>
      ) : inViewer && activeFile ? (
        <div className="relative h-full flex flex-col">
          {activeFile.editing && activeFile.externalChange && (
            <div className="flex items-center gap-2 border-b border-amber-500/40 bg-amber-950/40 px-3 py-1.5 text-xs text-amber-200 flex-shrink-0">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="min-w-0 flex-1">This file changed on disk since you opened it.</span>
              <button
                onClick={() => files.reloadFromDisk(activeFile.path)}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-amber-500/20"
              >
                <RotateCcw className="h-3 w-3" /> Reload
              </button>
              <button
                onClick={() => files.saveFile(activeFile.path, { force: true })}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-amber-500/20"
              >
                Overwrite
              </button>
            </div>
          )}
          {activeFile.saveError && (
            <div className="flex items-center gap-2 border-b border-red-500/40 bg-red-950/40 px-3 py-1.5 text-xs text-red-200 flex-shrink-0">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="min-w-0 flex-1">Couldn’t save: {saveErrorMessage(activeFile.saveError)}</span>
            </div>
          )}
          <div className="flex flex-1 min-h-0">
            <div className="relative min-w-0 flex-1">
              <FileViewer
                state={activeFile}
                wrap={true}
                markdownSource={markdownSource}
                diffSideBySide={diffSideBySide}
                onDraftChange={(content) => files.updateDraft(activeFile.path, content)}
                onSave={() => files.saveFile(activeFile.path)}
                onScrollAnchor={files.setScrollAnchor}
                onDiffNav={setDiffNav}
              />
            </div>
            {/* Docked side pane (file tree / changed-files switcher): a real
                split — the viewer gives up the width — with a draggable left
                edge. Persistent: stays open across file switches until its
                toolbar button (or Esc) toggles it off. */}
            {(treeDrawerOpen || changesDrawerOpen) && (
              <div
                className="relative flex h-full flex-shrink-0 flex-col border-l border-border"
                style={{ width: sideWidth, maxWidth: '70%', backgroundColor: PANEL_BG }}
              >
                <div
                  onPointerDown={onSideResize}
                  aria-label="Resize side pane"
                  className="group absolute -left-1 top-0 bottom-0 z-10 w-2 cursor-col-resize"
                  style={NO_DRAG}
                >
                  <div className="absolute inset-y-0 left-1 w-px transition-colors group-hover:bg-muted-foreground/60" />
                </div>
                {treeDrawerOpen ? (
                  <>
                    <FileSearchRow query={fileSearch} onChange={setFileSearch} />
                    {fileSearch.trim() ? (
                      <FileSearchResults
                        files={projectFileIndex.map((f) => f.path)}
                        query={fileSearch}
                        loading={fileIndexLoading}
                        onOpenFile={openFromTree}
                      />
                    ) : (
                      <div className="min-h-0 flex-1">
                        <FilesTab
                          listings={files.listings}
                          expanded={files.expanded}
                          rootError={files.rootError}
                          onToggleDir={files.toggleDir}
                          onOpenFile={openFromTree}
                          dirtyPaths={dirtyPaths}
                          statuses={changedStatus}
                          changedDirs={changedDirs}
                        />
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex flex-shrink-0 items-center justify-between border-b border-border/60 px-3 py-1.5 text-[11px] font-mono text-muted-foreground">
                      <span>Changed files · {changedFilePaths.length}</span>
                      <button
                        type="button"
                        aria-label="Close changed files"
                        onClick={() => setChangesDrawerOpen(false)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <ChangedFilesList
                      status={git.status}
                      activePath={files.activeFilePath}
                      onOpenFile={openFromChanges}
                    />
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      ) : panel.activeTab === 'files' ? (
        <div className="flex h-full min-h-0 flex-col">
          <FileSearchRow query={fileSearch} onChange={setFileSearch} />
          {fileSearch.trim() ? (
            <FileSearchResults
              files={projectFileIndex.map((f) => f.path)}
              query={fileSearch}
              loading={fileIndexLoading}
              onOpenFile={openFromTree}
            />
          ) : (
            <div className="min-h-0 flex-1">
              <FilesTab
                listings={files.listings}
                expanded={files.expanded}
                rootError={files.rootError}
                onToggleDir={files.toggleDir}
                onOpenFile={openFromTree}
                dirtyPaths={dirtyPaths}
                statuses={changedStatus}
                changedDirs={changedDirs}
              />
            </div>
          )}
        </div>
      ) : (
        <div ref={changesSplitRef} className="flex h-full min-h-0 flex-col">
          {/* Working-tree changes (top, scrolls independently) */}
          <div className="min-h-0 flex-1 overflow-hidden">
            <GitTab
              status={git.status}
              statusLoading={git.statusLoading}
              statusError={git.statusError}
              diffs={git.diffs}
              expanded={git.expanded}
              wrapLines={git.wrapLines}
              splitView={git.splitView}
              splitDiffEnabled={panel.splitDiffEnabled}
              treeView={git.treeView}
              submoduleView={{
                enabled: git.expandSubmodules,
                submodules: git.submodules,
                submoduleDiffs: git.submoduleDiffs,
                expandedSubFiles: git.expandedSubFiles,
                onToggleSubFile: git.toggleSubFile,
              }}
              pendingPaths={git.pendingPaths}
              writeError={git.writeError}
              committing={git.committing}
              commitMessage={git.commitMessage}
              onCommitMessageChange={git.setCommitMessage}
              onCommit={handleCommit}
              onDismissWriteError={git.clearWriteError}
              onToggleExpand={git.toggleExpand}
              onStage={git.stagePath}
              onUnstage={git.unstagePath}
              onOpenFile={openFromChanges}
            />
          </div>
          {/* Collapsible + resizable "Commits" history pane pinned at the bottom */}
          <div className="flex flex-shrink-0 flex-col border-t border-border">
            {commitsOpen && (
              <div
                onPointerDown={onCommitsResize}
                className="group h-1.5 cursor-row-resize"
                aria-label="Resize commits"
                style={NO_DRAG}
              >
                <div className="h-px w-full bg-border transition-colors group-hover:bg-muted-foreground/60" />
              </div>
            )}
            <button
              type="button"
              onClick={() => setCommitsOpen((v) => !v)}
              style={NO_DRAG}
              className="flex items-center gap-1 px-3 py-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
            >
              {commitsOpen ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              Changes History
            </button>
            {commitsOpen && (
              <div style={{ height: commitsHeight }} className="min-h-0">
                <CommitsSection
                  commits={commits}
                  wrapLines={git.wrapLines}
                  splitView={git.splitView && panel.splitDiffEnabled}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // Terminal dock (split layout): the session's terminals get an always-
  // visible region with its own mini tab strip, stacked below (default) or
  // above the files/changes area. The keep-alive panes geometry-sync over the
  // viewport div registered here, exactly as in the full-tab presentation —
  // only one of the two viewport divs ever renders (showTerminal is false
  // while split). The resize handle sits on the dock's inner edge and draws
  // the separator line itself, so the container carries no border of its own.
  const dock = splitActive ? (
    <div
      className="flex max-h-[70%] flex-shrink-0 flex-col"
      style={{ height: panel.splitHeight }}
    >
      {!panel.splitTop && (
        <div
          onPointerDown={onDockResize}
          className="group h-1.5 flex-shrink-0 cursor-row-resize"
          aria-label="Resize terminal panel"
          style={NO_DRAG}
        >
          <div className="h-px w-full bg-border transition-colors group-hover:bg-muted-foreground/60" />
        </div>
      )}
      <div className="flex h-8 flex-shrink-0 items-center gap-1 border-b border-border/60 px-1.5">
        <div className={`flex min-w-0 flex-1 items-center overflow-x-auto text-xs font-mono ${TAB_SCROLL_STYLE}`}>
          {terminals.map((t, i) => (
            <TerminalTab
              key={t.id}
              label={i === 0 ? 'Terminal' : `Terminal ${i + 1}`}
              active={activeTerminalId === t.id}
              onSelect={() => {
                setActiveTerminal(instanceId, t.id);
                focusTerminal(instanceId, t.id);
              }}
              onClose={() => closeTerminal(t.id)}
            />
          ))}
          <button
            aria-label="New terminal"
            style={NO_DRAG}
            onClick={addTerminal}
            className="flex-shrink-0 px-2 py-1 text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
        <div style={NO_DRAG} className="flex flex-shrink-0 items-center gap-0.5">
          <TipButton
            label={panel.splitTop ? 'Move terminal below files' : 'Move terminal above files'}
            onClick={panel.toggleSplitTop}
          >
            <ArrowUpDown className="h-4 w-4" />
          </TipButton>
          <TipButton label="Hide terminal panel" onClick={toggleSplit}>
            <X className="h-4 w-4" />
          </TipButton>
        </div>
      </div>
      <div ref={terminalViewportRef} className="min-h-0 flex-1" />
      {panel.splitTop && (
        <div
          onPointerDown={onDockResize}
          className="group h-1.5 flex-shrink-0 cursor-row-resize"
          aria-label="Resize terminal panel"
          style={NO_DRAG}
        >
          <div className="h-px w-full bg-border transition-colors group-hover:bg-muted-foreground/60" />
        </div>
      )}
    </div>
  ) : null;

  // Center-overlay presentation: fill the (relative) parent instead of being a
  // fixed-width rail. Only in the side-by-side layout — a narrow viewport uses
  // the full-screen sheet below, so `panel.isOverlay` wins over `overlay`.
  const centerOverlay = !!overlay && !panel.isOverlay;

  const inner = (
    <TooltipProvider delayDuration={300}>
    <div
      ref={rootRef}
      data-files-panel
      className={`flex flex-col ${
        centerOverlay ? 'absolute inset-0 z-20' : 'relative h-full'
      }`}
      style={{ width: centerOverlay ? undefined : panel.effectiveWidth, backgroundColor: PANEL_BG }}
    >
      {/* Resize handle: a wide, invisible hit area with a thin visible separator
          line that widens + highlights on hover (and while dragging). z-50 so
          it stays grabbable above the keep-alive terminal overlay (z-45).
          Double-click maximizes into the center overlay. Not shown in the
          overlay itself — it fills the width, and the header's restore button
          exits. */}
      {!centerOverlay && (
        <div
          onPointerDown={onPointerDown}
          onDoubleClick={panel.toggleMaximized}
          title="Double-click to maximize"
          className="group absolute left-0 top-0 bottom-0 z-50 w-2 cursor-col-resize"
        >
          <div
            className={`absolute inset-y-0 left-0 w-px transition-colors duration-150 group-hover:bg-muted-foreground/60 ${
              dragging ? 'bg-muted-foreground/60' : 'bg-border'
            }`}
          />
        </div>
      )}
      {/* Windows draws its min/max/close cluster fixed at the window's
          top-right, which lands over this panel while it's the right rail. Give
          the controls their own drag strip ABOVE the tabs (instead of reserving
          width beside them) so the tab row gets the panel's full width below
          the buttons and has room to grow as tabs are added. macOS/web have no
          top-right controls, so they skip the strip and keep the tabs flush at
          the top edge. Skipped in the center overlay — there the session header
          owns the top edge and reserves the controls itself. */}
      {isWindows && !centerOverlay && (
        <div style={DRAG_REGION} className="h-11 shrink-0" aria-hidden />
      )}
      {/* The panel spans the full window height, so its header sits at the top
          edge — make it a window drag region; interactive children opt out. */}
      <div
        style={DRAG_REGION}
        className="flex h-11 items-center justify-between gap-1 border-b border-border px-1.5 flex-shrink-0"
      >
        {headerLeft}
        {headerRight}
      </div>
      {panel.splitTop && dock}
      {contextRow}
      {body}
      {!panel.splitTop && dock}
    </div>
    <Dialog
      open={pendingSetup !== null}
      onOpenChange={(open) => {
        if (!open) setPendingSetup(null);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run this worktree&apos;s setup?</DialogTitle>
          <DialogDescription>
            This repository&apos;s <code className="font-mono">vicoa.json</code> wants to run
            these setup commands in the new worktree. Only run them if you trust this
            repository.
          </DialogDescription>
        </DialogHeader>
        <pre className="custom-scrollbar max-h-48 overflow-auto rounded bg-muted p-3 text-xs font-mono">
          {pendingSetup?.commands.join('\n')}
        </pre>
        <DialogFooter>
          <Button variant="outline" className="cursor-pointer" onClick={() => setPendingSetup(null)}>
            Not now
          </Button>
          <Button className="cursor-pointer" onClick={() => void confirmWorktreeSetup()}>
            Run setup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </TooltipProvider>
  );

  if (panel.isOverlay) {
    return (
      <div className="fixed inset-0 z-40">
        <div
          className="absolute inset-0 bg-black/30"
          onClick={() => panel.setOpen(false)}
          aria-label="Close panel backdrop"
        />
        <div className="absolute right-0 top-0 bottom-0 shadow-xl">{inner}</div>
      </div>
    );
  }

  return inner;
}

/** A fixed (non-closable) tab button — Files / Changes. */
function FixedTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={NO_DRAG}
      className={`px-3 py-1 whitespace-nowrap flex-shrink-0 ${
        active
          ? 'text-foreground font-medium bg-white/[0.06]'
          : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {children}
    </button>
  );
}

/** A dynamic terminal tab: a label that selects it plus an inline close (x). */
function TerminalTab({
  label,
  active,
  onSelect,
  onClose,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
  onClose: () => void;
}) {
  return (
    <div
      style={NO_DRAG}
      className={`group/tab flex items-center pl-3 pr-1 py-1 whitespace-nowrap flex-shrink-0 ${
        active ? 'text-foreground font-medium bg-white/[0.06]' : 'text-muted-foreground'
      }`}
    >
      <button onClick={onSelect} className="mr-1 hover:text-foreground">
        {label}
      </button>
      <button
        aria-label={`Close ${label}`}
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="p-0.5 rounded text-muted-foreground hover:bg-muted-foreground/20 hover:text-foreground opacity-60 group-hover/tab:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

/** A dynamic open-file tab: colored type icon + basename + inline close (x).
 *  A single-click preview tab shows its name in italic; a git-changed file's
 *  name is tinted with its status color (matching the tree / changes switcher). */
function FileTab({
  fileName,
  active,
  dirty = false,
  preview = false,
  statusColor = '',
  onSelect,
  onOpen,
  onClose,
}: {
  fileName: string;
  active: boolean;
  dirty?: boolean;
  preview?: boolean;
  statusColor?: string;
  onSelect: () => void;
  /** Double-click: promote a preview tab to a permanent one. */
  onOpen?: () => void;
  onClose: () => void;
}) {
  return (
    <div
      style={NO_DRAG}
      className={`group/tab flex items-center pl-2.5 pr-1 py-1 whitespace-nowrap flex-shrink-0 ${
        active ? 'text-foreground font-medium bg-white/[0.06]' : 'text-muted-foreground'
      }`}
    >
      <button
        onClick={onSelect}
        onDoubleClick={onOpen}
        title={fileName}
        className="mr-1 flex items-center gap-1.5 hover:text-foreground"
      >
        <FileTypeIcon fileName={fileName} size={14} />
        <span className={`max-w-32 truncate ${statusColor} ${preview ? 'italic' : ''}`}>{fileName}</span>
      </button>
      <button
        aria-label={`Close ${fileName}`}
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted-foreground/20 hover:text-foreground"
      >
        {dirty ? (
          <>
            {/* Unsaved-edit dot; becomes the close affordance on hover. */}
            <span className="block h-1.5 w-1.5 rounded-full bg-foreground/70 group-hover/tab:hidden" />
            <X className="hidden h-3 w-3 group-hover/tab:block" />
          </>
        ) : (
          <X className="h-3 w-3 opacity-60 group-hover/tab:opacity-100" />
        )}
      </button>
    </div>
  );
}

/** The open file's project-relative path as clickable folder crumbs + filename.
 *  Left-truncates (filename stays visible): the crumb row is right-anchored and
 *  clips its overflow on the left. Folder crumbs open the tree drawer at that dir. */
function FileBreadcrumb({
  path,
  onOpenDir,
}: {
  path: string;
  onOpenDir: (dirPath: string) => void;
}) {
  const segments = path.split('/').filter(Boolean);
  return (
    <div className={`flex min-w-0 flex-1 items-center overflow-x-auto ${TAB_SCROLL_STYLE}`} style={NO_DRAG}>
      <div className="flex items-center gap-1 whitespace-nowrap text-xs font-mono">
        {segments.map((seg, i) => {
          const isLast = i === segments.length - 1;
          const dirPath = segments.slice(0, i + 1).join('/');
          return (
            <span key={dirPath} className="flex items-center gap-1">
              {i > 0 && <span className="flex-shrink-0 text-muted-foreground/50">›</span>}
              {isLast ? (
                <span className="text-foreground" title={path}>{seg}</span>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpenDir(dirPath)}
                  className="flex-shrink-0 text-muted-foreground hover:text-foreground"
                  title={`Reveal ${dirPath}`}
                >
                  {seg}
                </button>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** One row of the Changes overflow menu: icon + label, plus a check when the
 *  toggle is on. Omit `active` for plain action rows (Refresh). */
function GitMenuItem({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-foreground hover:bg-muted/40"
    >
      <span className="text-muted-foreground">{icon}</span>
      <span className="flex-1">{label}</span>
      {active && <Check className="h-3.5 w-3.5 text-foreground" />}
    </button>
  );
}

/** Icon button with a radix tooltip label. `active` gives the on-state tint.
 *  Must render inside a TooltipProvider (the panel wraps everything in one). */
function TipButton({
  label,
  active = false,
  disabled = false,
  side = 'bottom',
  extraClass = '',
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  side?: 'top' | 'bottom' | 'left' | 'right';
  extraClass?: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          onClick={onClick}
          disabled={disabled}
          className={`p-1 rounded hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent ${active ? 'text-foreground' : 'text-muted-foreground'} ${extraClass}`}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent
        side={side}
        className="bg-[#1E1E1E] text-foreground border border-foreground/15 shadow-md"
      >
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function FilesGitPanelToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      aria-label={open ? 'Close files & git panel' : 'Open files & git panel'}
      onClick={onToggle}
      className={`h-8 w-8 p-0 rounded inline-flex items-center justify-center hover:bg-muted ${open ? 'text-foreground' : 'text-muted-foreground'}`}
    >
      <PanelIcon />
    </button>
  );
}

function PanelIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  );
}
