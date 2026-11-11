'use client';

/**
 * Renders the sidebar rows contributed by active plugins for a given slot.
 * Drops into both dashboard sidebars (the always-expanded `desktop-sidebar` and
 * the collapsible `dashboard-layout` rail). Each host passes its own row, icon
 * and selected-row classes so a plugin row looks like the built-in rows beside
 * it. Renders nothing when no plugin contributes to the slot.
 *
 * A plugin installed on several machines shows one row (see
 * `contributingPlugins`), and the row for the page on screen is selected.
 */

import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePluginSidebarItems } from '@/lib/plugins/hooks';
import { runSidebarAction } from '@/lib/plugins/actions';
import { isSidebarItemActive } from '@/lib/plugins/sidebar';
import { PluginIcon } from './plugin-icon';

export function PluginSidebarItems({
  slot = 'nav',
  collapsed = false,
  rowClassName,
  iconClassName,
  selectedClassName,
  onNavigate,
}: {
  slot?: 'nav' | 'footer';
  /** Icon-only rail: the label becomes screen-reader text. */
  collapsed?: boolean;
  /** The host's classes for one nav row. */
  rowClassName: string;
  /** The host's classes for a row's icon. */
  iconClassName: string;
  /** The host's selected-row classes; omit where the host shows no selection. */
  selectedClassName?: string;
  onNavigate?: () => void;
}) {
  const items = usePluginSidebarItems(slot);
  const router = useRouter();
  const pathname = usePathname();

  if (items.length === 0) return null;

  return (
    <>
      {items.map(({ item, pluginId, machineId }) => {
        const active = isSidebarItemActive(item.action, pluginId, pathname);
        return (
          <Button
            key={`${pluginId}:${item.id}`}
            variant="subtle"
            title={item.label}
            aria-current={active ? 'page' : undefined}
            className={cn(rowClassName, active && selectedClassName)}
            onClick={() => {
              runSidebarAction(item.action, pluginId, {
                machineId,
                navigate: (href) => router.push(href),
              });
              onNavigate?.();
            }}
          >
            <PluginIcon name={item.icon} className={iconClassName} />
            {collapsed ? <span className="sr-only">{item.label}</span> : item.label}
          </Button>
        );
      })}
    </>
  );
}
