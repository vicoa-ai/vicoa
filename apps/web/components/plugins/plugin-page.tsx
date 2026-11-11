'use client';

/**
 * The host page around one plugin page (a `surface` of kind `page`).
 *
 * The host owns the chrome: the title bar (title, crumbs, tabs and actions
 * the page asks for through `vicoa.ui.setHeader`), which plugin and machine
 * this is (always visible, so a page can't pass itself off as part of Vicoa),
 * a machine picker when the plugin is on several machines, a reload button,
 * and every state that isn't the page itself: loading, plugin off or not yet
 * trusted, machine offline, daemon too old, page failed. Everything below
 * the title bar belongs to the plugin.
 *
 * The page's own route lives in the URL (`?r=`), so reload, back/forward and
 * shared links keep the place.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Loader2, Puzzle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DesktopCollapsedLead } from '@/components/desktop/window-chrome';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';
import { openExternalUrl } from '@/lib/open-external';
import { getDesktopConfig } from '@/lib/runtime-config';
import { getLocalMachineId } from '@/lib/local-machine';
import { getRpcClient } from '@/lib/ws-client';
import { usePluginRegistry } from '@/lib/plugins/hooks';
import { findPlugin, pluginCopies, pluginRegistry, type RegisteredPlugin } from '@/lib/plugins/registry';
import { pluginSurfacePath } from '@/lib/plugins/sidebar';
import { BRIDGE_API_VERSION } from '@/lib/plugins/bridge/protocol';
import { daemonError, type BridgeContextInfo, type HostUi, type PluginHeader } from '@/lib/plugins/bridge/host';
import { readHostTheme } from '@/lib/plugins/webview/theme';
import { PluginIcon } from './plugin-icon';
import { PluginWebview, type PluginWebviewFailure, type PluginWebviewHandle } from './plugin-webview';

/** How long to wait for a machine's plugin list before calling it unreachable. */
const SYNC_WAIT_MS = 12_000;

type PageLoad =
  | { state: 'loading' }
  | { state: 'ready'; html: string }
  | { state: 'error'; title: string; message: string };

export function machineLabel(plugin: Pick<RegisteredPlugin, 'machineId' | 'machineLabel'>): string {
  const local = plugin.machineId === getLocalMachineId();
  if (plugin.machineLabel) return local ? `${plugin.machineLabel} (this machine)` : plugin.machineLabel;
  return local ? 'This machine' : plugin.machineId;
}

const SETTINGS_HREF = '/dashboard/settings?tab=plugins';

/** Hooks the page shell offers to whoever mounts it (the peek panel, in P2). */
export interface PluginPagePanelHooks {
  openTask?: (id: string, siblings: string[]) => void;
  openSession?: (id: string, siblings: string[]) => void;
}

export function PluginPage({
  machineId,
  pluginId,
  surfaceId,
  panel,
  webviewRef: externalRef,
}: {
  machineId: string;
  pluginId: string;
  surfaceId: string;
  panel?: PluginPagePanelHooks;
  webviewRef?: React.MutableRefObject<PluginWebviewHandle | null>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const all = usePluginRegistry();
  const plugin = findPlugin(machineId, pluginId, all);
  const copies = pluginCopies(pluginId, all);
  const synced = pluginRegistry.isMachineSynced(machineId);
  const surface = plugin?.manifest.surfaces?.find((s) => s.id === surfaceId && s.kind === 'page') ?? null;
  const usable = Boolean(plugin && plugin.enabled && plugin.trusted && !plugin.requirementError);
  const pluginName = plugin?.manifest.name ?? pluginId;

  const [header, setHeader] = useState<PluginHeader>({});
  const [load, setLoad] = useState<PageLoad>({ state: 'loading' });
  const [reloadKey, setReloadKey] = useState(0);
  const [failure, setFailure] = useState<PluginWebviewFailure | null>(null);
  const [waitedLong, setWaitedLong] = useState(false);
  // A link to a site the plugin didn't declare, waiting for the user's OK.
  const [pendingLink, setPendingLink] = useState<string | null>(null);
  const ownRef = useRef<PluginWebviewHandle | null>(null);
  const webviewRef = externalRef ?? ownRef;

  const route = searchParams?.get('r') ?? '';
  const initialRoute = useRef(route);
  const lastRoute = useRef(route);

  // A machine that never answers is offline, not "plugin missing".
  useEffect(() => {
    if (synced) return;
    const t = window.setTimeout(() => setWaitedLong(true), SYNC_WAIT_MS);
    return () => window.clearTimeout(t);
  }, [synced]);

  // A new page (route params) starts with a clean title bar.
  useEffect(() => {
    setHeader({});
    setFailure(null);
  }, [machineId, pluginId, surfaceId]);

  const entry = surface?.entry ?? null;
  const reloadNonce = plugin?.reloadNonce ?? 0;
  useEffect(() => {
    if (!usable || !entry) return;
    let cancelled = false;
    setLoad({ state: 'loading' });
    setFailure(null);
    getRpcClient(machineId)
      .callRpc(machineId, 'plugin-file', { plugin_id: pluginId, path: entry })
      .then((res) => {
        if (cancelled) return;
        const err = daemonError(res);
        if (!err) {
          setLoad({ state: 'ready', html: String(res.content ?? '') });
        } else if (err.code === 'daemon_outdated') {
          setLoad({
            state: 'error',
            title: 'This machine needs a newer Vicoa',
            message: 'Plugin pages need the latest Vicoa CLI on the machine the plugin is installed on. Update it, then reload.',
          });
        } else {
          setLoad({ state: 'error', title: "Couldn't open this page", message: err.message });
        }
      })
      .catch(() => {
        if (cancelled) return;
        setLoad({
          state: 'error',
          title: 'Machine offline',
          message: "The machine this plugin is installed on isn't connected. Pages open again when it is.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [usable, entry, machineId, pluginId, reloadKey, reloadNonce]);

  // Back/forward (or a pasted link) changed `?r=`: tell the page.
  useEffect(() => {
    if (route === lastRoute.current) return;
    lastRoute.current = route;
    webviewRef.current?.emit('route', { path: route });
  }, [route, webviewRef]);

  const setRoute = useCallback(
    (path: string, replace: boolean) => {
      lastRoute.current = path;
      const params = new URLSearchParams(window.location.search);
      if (path) params.set('r', path);
      else params.delete('r');
      const qs = params.toString();
      const url = `${pathname}${qs ? `?${qs}` : ''}`;
      // Plain history calls: Next keeps useSearchParams in sync without a
      // server round trip, so the URL moves the moment the page asks.
      if (replace) window.history.replaceState(null, '', url);
      else window.history.pushState(null, '', url);
    },
    [pathname],
  );

  const panelRef = useRef(panel);
  panelRef.current = panel;

  const ui: HostUi = useMemo(
    () => ({
      setHeader,
      toast: (text, kind) => (kind === 'error' ? toast.error(text) : toast.success(text)),
      openTask: (id, siblings) =>
        panelRef.current?.openTask ? panelRef.current.openTask(id, siblings) : router.push(`/dashboard/tasks/${encodeURIComponent(id)}`),
      openSession: (id, siblings) =>
        panelRef.current?.openSession
          ? panelRef.current.openSession(id, siblings)
          : router.push(`/dashboard/sessions/${encodeURIComponent(id)}`),
      openNewSession: (prefill) => {
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(prefill)) if (typeof v === 'string' && v) params.set(k, v);
        router.push(`/dashboard/sessions/new${params.size ? `?${params}` : ''}`);
      },
      // An app path stays in Vicoa. A site the plugin declared in `network`
      // opens straight away; any other site asks first, because a link is a
      // way out: whatever the page put in it goes to that site.
      openUrl: (url) => {
        if (!/^https?:\/\//i.test(url)) {
          router.push(url);
          return;
        }
        const network = findPlugin(machineId, pluginId)?.manifest.network ?? [];
        if (isDeclaredOrigin(url, network)) openExternalUrl(url);
        else setPendingLink((cur) => cur ?? url);
      },
      openPage: (target, params) => {
        const qs = new URLSearchParams(params).toString();
        const r = qs ? `?r=${encodeURIComponent(`?${qs}`)}` : '';
        router.push(`${pluginSurfacePath(machineId, pluginId, target)}${r}`);
      },
      setRoute,
    }),
    [router, machineId, pluginId, setRoute],
  );

  const context = useCallback((): BridgeContextInfo => {
    const p = findPlugin(machineId, pluginId);
    return {
      pluginId,
      pluginName: p?.manifest.name ?? pluginId,
      surfaceId,
      machineId,
      machineName: p ? machineLabel(p) : null,
      platform: getDesktopConfig() ? 'desktop' : 'web',
      theme: readHostTheme().mode,
      apiVersion: BRIDGE_API_VERSION,
      permissions: [...(p?.manifest.permissions ?? [])],
    };
  }, [machineId, pluginId, surfaceId]);

  const emitHeader = (type: 'tab' | 'action' | 'crumb' | 'title', id: string) =>
    webviewRef.current?.emit('header', { type, id });

  const title = header.title || surface?.title || pluginName;
  const icon = surface?.icon ?? plugin?.manifest.sidebarItems?.[0]?.icon;

  let body: React.ReactNode;
  if (!plugin) {
    body =
      !synced && !waitedLong ? (
        <Loading />
      ) : !synced ? (
        <PageState title="Machine offline" message="Couldn't reach the machine this plugin is installed on." />
      ) : (
        <PageState
          title="Plugin not installed here"
          message={`${pluginId} isn't installed on this machine.`}
          others={copies}
          onPickMachine={(id) => router.replace(pluginSurfacePath(id, pluginId, surfaceId))}
        />
      );
  } else if (!plugin.enabled) {
    body = <PageState title={`${pluginName} is turned off`} message="Turn it on in Settings › Plugins to open its pages." settingsLink />;
  } else if (!plugin.trusted) {
    body = (
      <PageState
        title={`${pluginName} isn't trusted yet`}
        message="Review what it asks for and approve it in the prompt, or in Settings › Plugins."
        settingsLink
      />
    );
  } else if (plugin.requirementError) {
    body = <PageState title="This machine needs a newer Vicoa" message={plugin.requirementError} />;
  } else if (!surface) {
    body = <PageState title="Page not found" message={`${pluginName} has no page named "${surfaceId}".`} />;
  } else if (failure === 'navigated') {
    body = (
      <PageState
        title="Vicoa stopped this page"
        message="It tried to open another site inside Vicoa. Reload to start it again."
        onReload={() => setReloadKey((k) => k + 1)}
      />
    );
  } else if (load.state === 'loading') {
    body = <Loading />;
  } else if (load.state === 'error') {
    body = <PageState title={load.title} message={load.message} onReload={() => setReloadKey((k) => k + 1)} settingsLink />;
  } else {
    body = (
      <PluginWebview
        key={`${machineId}:${pluginId}:${surfaceId}:${reloadKey}`}
        ref={webviewRef}
        plugin={plugin}
        surface={surface}
        html={load.html}
        initialRoute={initialRoute.current}
        ui={ui}
        context={context}
        onFailure={setFailure}
      />
    );
  }

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
      <div style={DRAG_REGION} className="flex h-11 shrink-0 items-center gap-2 border-b border-border/60 px-4">
        <DesktopCollapsedLead />
        <PluginIcon name={icon} className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div style={NO_DRAG} className="flex min-w-0 items-center gap-1 text-sm">
          {header.crumbs?.length ? (
            <button
              type="button"
              onClick={() => emitHeader('title', '')}
              className="shrink-0 cursor-pointer font-medium text-muted-foreground hover:text-foreground"
            >
              {title}
            </button>
          ) : (
            <h1 className="truncate font-medium">{title}</h1>
          )}
          {header.crumbs?.map((c, i) => {
            const last = i === (header.crumbs?.length ?? 0) - 1;
            return (
              <span key={c.id} className="flex min-w-0 items-center gap-1">
                <span className="text-muted-foreground/60">/</span>
                {last ? (
                  <span className="truncate font-medium">{c.label}</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => emitHeader('crumb', c.id)}
                    className="cursor-pointer truncate text-muted-foreground hover:text-foreground"
                  >
                    {c.label}
                  </button>
                )}
              </span>
            );
          })}
        </div>
        {header.tabs?.length ? (
          <div style={NO_DRAG} className="ml-2 flex shrink-0 items-center gap-0.5">
            {header.tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => emitHeader('tab', t.id)}
                className={cn(
                  'h-7 cursor-pointer rounded-md px-2.5 text-xs transition-colors',
                  header.activeTab === t.id
                    ? 'bg-foreground/[0.08] text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : null}
        {header.subtitle ? <span className="ml-1 truncate text-xs text-muted-foreground">{header.subtitle}</span> : null}

        <div className="min-w-4 flex-1" />

        <div style={NO_DRAG} className="flex shrink-0 items-center gap-1">
          {header.actions?.map((a) => (
            <Button
              key={a.id}
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => emitHeader('action', a.id)}
            >
              {a.icon ? <PluginIcon name={a.icon} className="size-3.5" /> : null}
              {a.label}
            </Button>
          ))}
          {plugin && copies.length > 1 ? (
            <Select
              value={machineId}
              onValueChange={(id) => router.replace(pluginSurfacePath(id, pluginId, surfaceId))}
            >
              <SelectTrigger className="h-7 max-w-44 cursor-pointer gap-1 text-xs" title="Machine">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {copies.map((c) => (
                  <SelectItem key={c.machineId} value={c.machineId} className="cursor-pointer text-xs">
                    {machineLabel(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <span
            className="hidden items-center gap-1 px-1 text-xs text-muted-foreground sm:flex"
            title={plugin ? `${pluginName} plugin on ${machineLabel(plugin)}` : pluginName}
          >
            <Puzzle className="size-3.5" />
            <span className="max-w-40 truncate">
              {pluginName}
              {plugin && copies.length <= 1 ? ` · ${machineLabel(plugin)}` : ''}
            </span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground"
            title="Reload page"
            aria-label="Reload page"
            disabled={!usable}
            onClick={() => setReloadKey((k) => k + 1)}
          >
            <RefreshCw className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">{body}</div>
      <ConfirmDialog
        open={pendingLink !== null}
        onOpenChange={(open) => !open && setPendingLink(null)}
        title="Open this link?"
        description={`${pluginName} wants to open a site it didn't declare. Anything in the link is sent to that site.`}
        preview={<span className="break-all font-mono text-xs">{pendingLink}</span>}
        confirmLabel="Open link"
        destructive={false}
        onConfirm={() => {
          if (pendingLink) openExternalUrl(pendingLink);
          setPendingLink(null);
        }}
      />
    </main>
  );
}

/** Whether `url` is on one of the plugin's declared `network` origins. */
export function isDeclaredOrigin(url: string, network: readonly string[]): boolean {
  try {
    const origin = new URL(url).origin;
    return network.some((o) => o.replace(/\/$/, '') === origin);
  } catch {
    return false;
  }
}

function Loading() {
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
    </div>
  );
}

function PageState({
  title,
  message,
  onReload,
  settingsLink,
  others,
  onPickMachine,
}: {
  title: string;
  message: string;
  onReload?: () => void;
  settingsLink?: boolean;
  others?: RegisteredPlugin[];
  onPickMachine?: (machineId: string) => void;
}) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-sm space-y-3 text-center">
        <div className="text-sm font-medium">{title}</div>
        <p className="text-sm text-muted-foreground">{message}</p>
        {others?.length && onPickMachine ? (
          <div className="flex flex-col items-center gap-1 pt-1">
            {others.map((o) => (
              <button
                key={o.machineId}
                type="button"
                onClick={() => onPickMachine(o.machineId)}
                className="cursor-pointer text-sm underline underline-offset-4"
              >
                Open it on {machineLabel(o)}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-center justify-center gap-2 pt-1">
          {onReload ? (
            <Button size="sm" variant="secondary" onClick={onReload}>
              Reload
            </Button>
          ) : null}
          {settingsLink ? (
            <Button asChild size="sm" variant="ghost">
              <Link href={SETTINGS_HREF}>Settings › Plugins</Link>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
