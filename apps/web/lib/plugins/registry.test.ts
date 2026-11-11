import { describe, expect, it } from 'vitest';
import { contributingPlugins, getPluginSidebarItems, type RegisteredPlugin } from './registry';
import type { PluginManifest } from './types';

const manifest = (id: string, extra: Partial<PluginManifest> = {}): PluginManifest => ({
  id,
  apiVersion: 1,
  sidebarItems: [{ id: 'open', label: 'Open', action: { type: 'surface', surfaceId: 'home' } }],
  ...extra,
});

function plugin(machineId: string, pluginId: string, over: Partial<RegisteredPlugin> = {}): RegisteredPlugin {
  return {
    machineId,
    pluginId,
    manifest: manifest(pluginId),
    enabled: true,
    trusted: true,
    serverAvailable: false,
    builtin: false,
    ...over,
  };
}

const machines = (list: RegisteredPlugin[]) => list.map((p) => `${p.machineId}:${p.pluginId}`);

describe('contributingPlugins', () => {
  it('keeps one copy of a plugin installed on several machines', () => {
    const all = [plugin('m-b', 'dash'), plugin('m-a', 'dash'), plugin('m-b', 'other')];
    expect(machines(contributingPlugins(all, null))).toEqual(['m-a:dash', 'm-b:other']);
  });

  it("prefers this machine's copy", () => {
    const all = [plugin('m-a', 'dash'), plugin('m-local', 'dash')];
    expect(machines(contributingPlugins(all, 'm-local'))).toEqual(['m-local:dash']);
  });

  it('prefers an installed copy over a built-in of the same id', () => {
    const all = [plugin('builtin', 'dash', { builtin: true }), plugin('m-z', 'dash')];
    expect(machines(contributingPlugins(all, null))).toEqual(['m-z:dash']);
  });

  it('only considers enabled, trusted copies', () => {
    const all = [
      plugin('m-a', 'dash', { trusted: false }),
      plugin('m-local', 'dash', { enabled: false }),
      plugin('m-b', 'dash'),
    ];
    expect(machines(contributingPlugins(all, 'm-local'))).toEqual(['m-b:dash']);
  });
});

describe('getPluginSidebarItems', () => {
  it('shows one row per plugin, not per machine', () => {
    const all = [plugin('m-a', 'dash'), plugin('m-b', 'dash')];
    expect(getPluginSidebarItems('nav', all)).toHaveLength(1);
  });

  it("drops a row whose action this build doesn't run", () => {
    const legacy = plugin('m-a', 'legacy', {
      manifest: manifest('legacy', {
        sidebarItems: [
          // Shape an older daemon may still report.
          { id: 'x', label: 'X', action: { type: 'rpc', method: 'write-file' } as never },
          { id: 'y', label: 'Y', action: { type: 'open-url', url: '/dashboard/tasks' } },
        ],
      }),
    });
    expect(getPluginSidebarItems('nav', [legacy]).map((r) => r.item.id)).toEqual(['y']);
  });
});
