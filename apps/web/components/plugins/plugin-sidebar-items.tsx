'use client';

/**
 * Renders the sidebar rows contributed by active plugins for a given slot.
 * Drops into both dashboard sidebars (the always-expanded `desktop-sidebar` and
 * the collapsible `dashboard-layout` rail) — pass `collapsed` to match the host.
 * Renders nothing when no plugin contributes to the slot.
 */

import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePluginSidebarItems } from '@/lib/plugins/hooks';
import { runSidebarAction } from '@/lib/plugins/actions';
import { PluginIcon } from './plugin-icon';

export function PluginSidebarItems({
  slot = 'nav',
  collapsed = false,
  onNavigate,
}: {
  slot?: 'nav' | 'footer';
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const items = usePluginSidebarItems(slot);
  const router = useRouter();

  if (items.length === 0) return null;

  return (
    <>
      {items.map(({ item, pluginId, machineId }) => (
        <Button
          key={`${machineId}:${pluginId}:${item.id}`}
          variant="subtle"
          title={item.label}
          className={cn(
            collapsed
              ? 'h-9 w-9 justify-center rounded-lg px-0 bg-transparent'
              : 'w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal',
          )}
          onClick={() => {
            void runSidebarAction(item.action, pluginId, {
              machineId,
              navigate: (href) => router.push(href),
            });
            onNavigate?.();
          }}
        >
          <PluginIcon name={item.icon} className={cn('h-4 w-4', !collapsed && 'mr-1.5')} />
          {collapsed ? <span className="sr-only">{item.label}</span> : item.label}
        </Button>
      ))}
    </>
  );
}
