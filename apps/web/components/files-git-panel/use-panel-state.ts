'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DEFAULT_PANEL_STATE,
  DEFAULT_PANEL_SESSION_VIEW,
  PanelTab,
  clampPanelWidth,
  loadPanelState,
  savePanelState,
  loadPanelSessionView,
  savePanelSessionView,
  MIN_PANEL_WIDTH,
  MIN_SPLIT_HEIGHT,
} from './panel-storage';

const OVERLAY_BREAKPOINT_PX = 900;

interface PanelStateApi {
  hydrated: boolean;
  open: boolean;
  width: number;
  effectiveWidth: number;
  isOverlay: boolean;
  splitDiffEnabled: boolean;
  activeTab: PanelTab;
  /** Focus mode: the panel fills the window (only meaningful when not overlay). */
  maximized: boolean;
  /** Split layout: this session's terminals live in an always-visible dock
   *  stacked with the files/changes area (per-session, like open/maximized). */
  split: boolean;
  /** Dock stacked above the files area instead of below it. */
  splitTop: boolean;
  /** Dock height in px — a global preference, like `width`. */
  splitHeight: number;
  setOpen: (next: boolean) => void;
  toggleOpen: () => void;
  setWidth: (next: number) => void;
  setActiveTab: (next: PanelTab) => void;
  toggleMaximized: () => void;
  setSplit: (next: boolean) => void;
  toggleSplitTop: () => void;
  setSplitHeight: (next: number) => void;
}

/**
 * Panel state for one session. `width` and `activeTab` are global preferences;
 * `open` and `maximized` (focus mode) are per-session view state keyed by
 * `instanceId` — opening/focusing one session never touches another, and
 * returning to a session restores how you left it. Pass a stable synthetic id
 * (e.g. "new-session") for panels not tied to a real session.
 */
export function usePanelState(instanceId: string): PanelStateApi {
  const [hydrated, setHydrated] = useState(false);
  const [width, setWidthState] = useState(DEFAULT_PANEL_STATE.width);
  const [activeTab, setActiveTabState] = useState<PanelTab>(DEFAULT_PANEL_STATE.lastTab);
  const [splitHeight, setSplitHeightState] = useState(DEFAULT_PANEL_STATE.splitHeight);
  // Per-session view (open + focus + split).
  const [open, setOpenState] = useState(DEFAULT_PANEL_SESSION_VIEW.open);
  const [maximized, setMaximizedState] = useState(DEFAULT_PANEL_SESSION_VIEW.maximized);
  const [split, setSplitState] = useState(DEFAULT_PANEL_SESSION_VIEW.split);
  const [splitTop, setSplitTopState] = useState(DEFAULT_PANEL_SESSION_VIEW.splitTop);
  // Which session `open`/`maximized` currently reflect. Lets us swap in the new
  // session's stored view synchronously on a session switch (see below).
  const [viewInstance, setViewInstance] = useState(instanceId);
  const [viewport, setViewport] = useState(
    typeof window === 'undefined' ? 1440 : window.innerWidth,
  );
  const storageRef = useRef<Storage | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    storageRef.current = window.localStorage;
    const loaded = loadPanelState(window.localStorage);
    setWidthState(loaded.width);
    setActiveTabState(loaded.lastTab);
    setSplitHeightState(loaded.splitHeight);
    const view = loadPanelSessionView(window.localStorage, instanceId);
    setOpenState(view.open);
    setMaximizedState(view.maximized);
    setSplitState(view.split);
    setSplitTopState(view.splitTop);
    setViewInstance(instanceId);
    setHydrated(true);
    // Mount-only: later session switches are handled by the render-time reset
    // below (storageRef is populated by then, so the read is synchronous).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Switched sessions: adopt the new session's stored view *during render*, so
  // the panel never flashes the previous session's open/focus state before an
  // effect could correct it. Guarded on the id, so this can't loop.
  if (instanceId !== viewInstance) {
    setViewInstance(instanceId);
    const view = storageRef.current
      ? loadPanelSessionView(storageRef.current, instanceId)
      : DEFAULT_PANEL_SESSION_VIEW;
    setOpenState(view.open);
    setMaximizedState(view.maximized);
    setSplitState(view.split);
    setSplitTopState(view.splitTop);
  }

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onResize = () => setViewport(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Persist this session's view whenever it changes — but only once open/
  // maximized reflect the current session (viewInstance has caught up), so a
  // mid-switch render can't write one session's state under another's key.
  useEffect(() => {
    if (!hydrated || !storageRef.current) return;
    if (viewInstance !== instanceId) return;
    savePanelSessionView(storageRef.current, instanceId, { open, maximized, split, splitTop });
  }, [open, maximized, split, splitTop, instanceId, viewInstance, hydrated]);

  const effectiveWidth = clampPanelWidth(width, viewport);
  const isOverlay = viewport < OVERLAY_BREAKPOINT_PX;
  const splitDiffEnabled = effectiveWidth > 600;

  // open/maximized/split persist via the effect above; these just move the state.
  const setOpen = useCallback((next: boolean) => setOpenState(next), []);
  const toggleOpen = useCallback(() => setOpenState((prev) => !prev), []);
  const toggleMaximized = useCallback(() => setMaximizedState((prev) => !prev), []);
  const setSplit = useCallback((next: boolean) => setSplitState(next), []);
  const toggleSplitTop = useCallback(() => setSplitTopState((prev) => !prev), []);

  const setWidth = useCallback((next: number) => {
    const clamped = Math.max(MIN_PANEL_WIDTH, Math.round(next));
    setWidthState(clamped);
    if (storageRef.current) savePanelState(storageRef.current, { width: clamped });
  }, []);

  const setSplitHeight = useCallback((next: number) => {
    const clamped = Math.max(MIN_SPLIT_HEIGHT, Math.round(next));
    setSplitHeightState(clamped);
    if (storageRef.current) savePanelState(storageRef.current, { splitHeight: clamped });
  }, []);

  const setActiveTab = useCallback((next: PanelTab) => {
    setActiveTabState(next);
    if (storageRef.current) savePanelState(storageRef.current, { lastTab: next });
  }, []);

  return {
    hydrated,
    open,
    width,
    effectiveWidth,
    isOverlay,
    splitDiffEnabled,
    activeTab,
    maximized,
    split,
    splitTop,
    splitHeight,
    setOpen,
    toggleOpen,
    setWidth,
    setActiveTab,
    toggleMaximized,
    setSplit,
    toggleSplitTop,
    setSplitHeight,
  };
}
