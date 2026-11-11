'use client';

/**
 * A plugin page plus the host's peek panel beside it. The page asks to open a
 * task or session (`vicoa.open.task` / `vicoa.open.session`); the panel shows
 * it next to the page instead of navigating away, and the page hears what is
 * open through `panel` events (to highlight the row).
 */

import { useCallback, useMemo, useRef } from 'react';
import { PeekLayout, usePeekPanel, type PeekItem } from '@/components/peek/peek-panel';
import { PluginPage, type PluginPagePanelHooks } from './plugin-page';
import type { PluginWebviewHandle } from './plugin-webview';

export function PluginPageView(props: { machineId: string; pluginId: string; surfaceId: string }) {
  const webviewRef = useRef<PluginWebviewHandle | null>(null);
  const onChange = useCallback((item: PeekItem | null) => {
    webviewRef.current?.emit('panel', item ? { kind: item.kind, id: item.id } : { kind: null, id: null });
  }, []);
  const peek = usePeekPanel(onChange);
  const { open } = peek;
  const panel: PluginPagePanelHooks = useMemo(
    () => ({
      openTask: (id, siblings) => open('task', id, siblings),
      openSession: (id, siblings) => open('session', id, siblings),
    }),
    [open],
  );

  return (
    <PeekLayout item={peek.item} onOpen={(kind, id) => open(kind, id)} onClose={peek.close} onStep={peek.step}>
      <PluginPage {...props} panel={panel} webviewRef={webviewRef} />
    </PeekLayout>
  );
}
