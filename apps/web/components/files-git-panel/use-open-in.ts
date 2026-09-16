'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { rpcOpenPath, type OpenApp } from './rpc';
import { appsForTarget, groupOpenApps, loadOpenApps, openErrorMessage } from './open-in-apps';

export interface OpenInTarget {
  machineId: string | null;
  /** The session's project directory (the daemon expands a leading `~`). */
  cwd: string | null;
  /** Project-relative path to open. `''` (the default) is the project root. */
  path?: string;
}

/**
 * Loads the machine's app list and launches one — the state behind every
 * "Open in…" surface (the two menus and the binary-file placeholder).
 *
 * `apps` is null while loading and when there is nothing to offer — callers
 * render nothing in both cases. File-only apps are already dropped when the
 * target is the project root (see `appsForTarget`).
 *
 * `onOpened` fires only on a confirmed launch, so a caller that controls menu
 * state can leave the menu open to show `error` instead of closing on failure.
 */
export function useOpenIn({ machineId, cwd, path = '' }: OpenInTarget, onOpened: () => void) {
  const [loaded, setLoaded] = useState<OpenApp[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Survives the async open: a menu unmounted mid-flight must not setState.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setLoaded(null);
    if (!machineId || !cwd) return;
    let cancelled = false;
    void loadOpenApps(machineId).then((apps) => {
      if (!cancelled) setLoaded(apps);
    });
    return () => {
      cancelled = true;
    };
  }, [machineId, cwd]);

  const openWith = useCallback(
    (appId: string) => {
      if (!machineId || !cwd) return;
      rpcOpenPath(machineId, cwd, path, appId)
        .then(() => {
          if (mounted.current) onOpened();
        })
        .catch((err: unknown) => {
          if (mounted.current) setError(openErrorMessage(err));
        });
    },
    [machineId, cwd, path, onOpened],
  );

  const apps = useMemo(() => appsForTarget(loaded ?? [], path), [loaded, path]);
  const groups = useMemo(() => groupOpenApps(apps), [apps]);
  const ready = !!machineId && !!cwd && apps.length > 0;
  return { apps, groups, ready, error, setError, openWith };
}
