'use client';

/**
 * Plugin-contributed composer actions (Tier 1).
 *
 * - `<PluginComposerActions>` renders the `placement:"toolbar"` actions as small
 *   icon buttons alongside the composer's own controls.
 * - `usePluginComposerMenuItems(ctx)` builds `placement:"menu"` actions into the
 *   `AddToChatMenu` `extraItems` shape.
 *
 * Both run their behavior through the narrowed `ComposerContext`, so a plugin
 * only ever inserts text or opens an existing picker — never touches composer
 * internals.
 */

import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { usePluginComposerActions } from '@/lib/plugins/hooks';
import { applyComposerBehavior, type ComposerContext } from '@/lib/plugins/composer';
import type { AddToChatExtraItem } from '@/components/dashboard/add-to-chat-menu';
import { PluginIcon } from './plugin-icon';

export function PluginComposerActions({
  ctx,
  disabled,
}: {
  ctx: ComposerContext;
  disabled?: boolean;
}) {
  const actions = usePluginComposerActions('toolbar');
  if (actions.length === 0) return null;
  return (
    <>
      {actions.map(({ action, pluginId, machineId }) => (
        <Button
          key={`${machineId}:${pluginId}:${action.id}`}
          type="button"
          variant="ghost"
          size="icon"
          disabled={disabled}
          title={action.label}
          className="shrink-0 rounded-full w-8 h-8 p-0 border-0 outline-none ring-0 hover:bg-muted-foreground/10 focus-visible:ring-0"
          onClick={() => applyComposerBehavior(action.behavior, ctx)}
        >
          <PluginIcon name={action.icon} className="w-4 h-4" />
        </Button>
      ))}
    </>
  );
}

/** The `placement:"menu"` composer actions as AddToChatMenu extra rows. */
export function usePluginComposerMenuItems(ctx: ComposerContext): AddToChatExtraItem[] {
  const actions = usePluginComposerActions('menu');
  return useMemo(
    () =>
      actions.map(({ action }) => ({
        id: action.id,
        label: action.label,
        icon: <PluginIcon name={action.icon} className="h-3.5 w-3.5" />,
        onSelect: () => applyComposerBehavior(action.behavior, ctx),
      })),
    [actions, ctx],
  );
}
