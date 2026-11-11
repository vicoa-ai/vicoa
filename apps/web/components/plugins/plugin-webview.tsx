'use client';

/**
 * A plugin page in sandboxed iframes, wired to its bridge host.
 *
 * Two frames, both `sandbox="allow-scripts"` only (no `allow-same-origin`, so
 * each gets an opaque origin and can't read the app's cookies, storage, token
 * or DOM; no popups, top navigation or forms):
 *
 * - the **shell**, the host's own tiny document, whose `frame-src 'none'`
 *   policy stops the page inside it from navigating anywhere;
 * - the **page**, the plugin's HTML with the host's preamble, whose policy
 *   limits its network to the declared origins.
 *
 * The bridge runs over a MessageChannel: the host sends one port to the shell
 * when it loads, the shell hands it to the page once the page has loaded, and
 * the host only ever reads and writes that port. Nothing else that runs in the
 * page (or replaces it) can reach the host. If the page frame loads a second
 * time, the shell removes it and tells the host, which shows an error.
 *
 * See `lib/plugins/webview/srcdoc.ts` for both documents.
 */

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { getBackendAPI } from '@/lib/backend-api';
import { getRpcClient, getWsClient } from '@/lib/ws-client';
import {
  createBridgeHost,
  type BridgeContextInfo,
  type BridgeHost,
  type HostUi,
} from '@/lib/plugins/bridge/host';
import { deviceSettingsStore } from '@/lib/plugins/device-settings';
import { buildShell, buildSrcdoc } from '@/lib/plugins/webview/srcdoc';
import { readHostTheme } from '@/lib/plugins/webview/theme';
import type { RegisteredPlugin } from '@/lib/plugins/registry';
import type { PluginSurface } from '@/lib/plugins/types';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';

export interface PluginWebviewHandle {
  emit(name: string, payload: unknown): void;
}

export type PluginWebviewFailure = 'navigated';

let pageSeq = 0;

export const PluginWebview = forwardRef<
  PluginWebviewHandle,
  {
    plugin: RegisteredPlugin;
    surface: PluginSurface;
    html: string;
    /** The in-page route when the frame first loads; later changes go as events. */
    initialRoute: string;
    ui: HostUi;
    context: () => BridgeContextInfo;
    onFailure: (reason: PluginWebviewFailure) => void;
  }
>(function PluginWebview({ plugin, surface, html, initialRoute, ui, context, onFailure }, ref) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const hostRef = useRef<BridgeHost | null>(null);
  const { api } = useAgentDashboard();
  const apiRef = useRef(api);
  apiRef.current = api;
  // Latest callbacks without rebuilding the host (that would drop watches).
  const uiRef = useRef(ui);
  uiRef.current = ui;
  const contextRef = useRef(context);
  contextRef.current = context;
  const onFailureRef = useRef(onFailure);
  onFailureRef.current = onFailure;
  const routeRef = useRef(initialRoute);
  // The registry hands out a new object whenever the catalog changes; the
  // page must not reload for that, so read the latest through a ref.
  const pluginRef = useRef(plugin);
  pluginRef.current = plugin;
  const { machineId, pluginId } = plugin;
  const networkKey = (plugin.manifest.network ?? []).join(' ');

  // One page load: a new document reloads the frame (new key) and gets a new
  // bridge host. Nothing else rebuilds either, so watches survive re-renders.
  const title = surface.title ?? plugin.manifest.name ?? plugin.pluginId;
  const page = useMemo(() => {
    pageSeq += 1;
    const network = networkKey ? networkKey.split(' ') : [];
    const inner = buildSrcdoc({
      html,
      network,
      init: { pluginId, surfaceId: surface.id, route: routeRef.current, theme: readHostTheme() },
    });
    return { key: `${pluginId}:${surface.id}:${pageSeq}`, srcDoc: buildShell(inner, title, network) };
  }, [html, networkKey, pluginId, surface.id, title]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    // The page's only line to the host; see the top of this file.
    const channel = new MessageChannel();
    const host = createBridgeHost({
      get manifest() {
        return pluginRef.current.manifest;
      },
      pluginId,
      machineId,
      getApi: () => apiRef.current ?? getBackendAPI(),
      rpc: (method, params) => getRpcClient(machineId).callRpc(machineId, method, params),
      post: (message) => channel.port1.postMessage(message),
      ui: {
        setHeader: (h) => uiRef.current.setHeader(h),
        toast: (t, k) => uiRef.current.toast(t, k),
        openTask: (id, s) => uiRef.current.openTask(id, s),
        openSession: (id, s) => uiRef.current.openSession(id, s),
        openNewSession: (p) => uiRef.current.openNewSession(p),
        openUrl: (u) => uiRef.current.openUrl(u),
        openPage: (id, p) => uiRef.current.openPage(id, p),
        setRoute: (path, replace) => {
          routeRef.current = path;
          uiRef.current.setRoute(path, replace);
        },
      },
      context: () => contextRef.current(),
      deviceSettings: deviceSettingsStore(pluginId),
      subscribeSessionUpdates: (onChange) =>
        getWsClient().subscribe((payload) => {
          if (/instance/i.test(payload.entity)) onChange();
        }),
    });
    hostRef.current = host;

    channel.port1.onmessage = (event: MessageEvent) => void host.handle(event.data);

    let stopped = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      frame.removeAttribute('srcdoc');
      frame.src = 'about:blank';
      host.dispose();
      channel.port1.close();
      onFailureRef.current('navigated');
    };
    // From the shell only: the page frame loaded a second time.
    const onMessage = (event: MessageEvent) => {
      const m = event.data as { __vicoa?: unknown; kind?: unknown } | null;
      if (event.source === frame.contentWindow && m && m.__vicoa === 1 && m.kind === 'stopped') stop();
    };
    window.addEventListener('message', onMessage);

    let loads = 0;
    const onLoad = () => {
      loads += 1;
      if (loads === 1) {
        frame.contentWindow?.postMessage({ __vicoa: 1, kind: 'port' }, '*', [channel.port2]);
      } else {
        stop();
      }
    };
    frame.addEventListener('load', onLoad);

    const onFocus = () => host.refreshWatches();
    const onVisibility = () => host.emit('visibility', { visible: document.visibilityState === 'visible' });
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);

    // Follow the app's theme (light/dark or a plugin theme) as it changes.
    let lastTheme = '';
    const theme = new MutationObserver(() => {
      const next = readHostTheme();
      if (next.css === lastTheme) return;
      lastTheme = next.css;
      host.emit('theme', next);
    });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style'] });

    return () => {
      window.removeEventListener('message', onMessage);
      frame.removeEventListener('load', onLoad);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
      theme.disconnect();
      host.dispose();
      channel.port1.close();
      hostRef.current = null;
    };
  }, [page, machineId, pluginId]);

  useImperativeHandle(
    ref,
    () => ({
      emit(name, payload) {
        if (name === 'route' && payload && typeof payload === 'object') {
          routeRef.current = String((payload as { path?: unknown }).path ?? '');
        }
        hostRef.current?.emit(name, payload);
      },
    }),
    [],
  );

  return (
    <iframe
      ref={frameRef}
      key={page.key}
      title={title}
      sandbox="allow-scripts"
      srcDoc={page.srcDoc}
      referrerPolicy="no-referrer"
      className="h-full w-full border-0 bg-background"
    />
  );
});
