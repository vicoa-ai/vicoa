import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RpcError } from '@/lib/ws-client';
import type { OpenApp } from './rpc';

const listOpenApps = vi.hoisted(() => vi.fn());
vi.mock('./rpc', () => ({ rpcListOpenApps: listOpenApps }));

const {
  FAILURE_TTL_MS,
  groupOpenApps,
  loadOpenApps,
  openErrorMessage,
  resetOpenAppCache,
} = await import('./open-in-apps');

function app(id: string, kind: OpenApp['kind']): OpenApp {
  return { id, label: id, kind, target: kind === 'terminal' ? 'dir' : 'path' };
}

beforeEach(() => {
  resetOpenAppCache();
  listOpenApps.mockReset();
});

describe('groupOpenApps', () => {
  it('buckets apps into menu order regardless of the order the daemon sent', () => {
    const groups = groupOpenApps([
      app('ghostty', 'terminal'),
      app('vscode', 'editor'),
      app('finder', 'file-manager'),
      app('zed', 'editor'),
    ]);

    expect(groups.map((g) => g.kind)).toEqual(['file-manager', 'editor', 'terminal']);
    expect(groups[1].apps.map((a) => a.id)).toEqual(['vscode', 'zed']);
  });

  it('drops kinds this machine has none of, so no stray separator is rendered', () => {
    // A Linux box with no xdg-open and no terminal emulator installed.
    const groups = groupOpenApps([app('vscode', 'editor')]);

    expect(groups).toHaveLength(1);
    expect(groups[0].kind).toBe('editor');
  });

  it('returns nothing for an empty app list', () => {
    expect(groupOpenApps([])).toEqual([]);
  });
});

describe('openErrorMessage', () => {
  it('maps a known RPC code to actionable copy', () => {
    expect(openErrorMessage(new RpcError('app_not_found'))).toMatch(/no longer installed/);
    expect(openErrorMessage(new RpcError('target_disconnected'))).toMatch(/offline/);
  });

  it('falls back for an unrecognised failure', () => {
    expect(openErrorMessage(new RpcError('some_new_code'))).toBe('Could not open that path.');
    expect(openErrorMessage(new Error('boom'))).toBe('Could not open that path.');
    expect(openErrorMessage(null)).toBe('Could not open that path.');
  });
});

describe('loadOpenApps', () => {
  it('fetches once per machine and serves the rest from cache', async () => {
    listOpenApps.mockResolvedValue({ platform: 'darwin', apps: [app('finder', 'file-manager')] });

    const first = await loadOpenApps('m1');
    const second = await loadOpenApps('m1');

    expect(first).toEqual([app('finder', 'file-manager')]);
    expect(second).toEqual(first);
    expect(listOpenApps).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight request between concurrent callers', async () => {
    // The session header and the files panel mount together.
    listOpenApps.mockResolvedValue({ platform: 'linux', apps: [] });

    const [a, b] = await Promise.all([loadOpenApps('m1'), loadOpenApps('m1')]);

    expect(a).toEqual([]);
    expect(b).toEqual([]);
    expect(listOpenApps).toHaveBeenCalledTimes(1);
  });

  it('caches per machine, not globally', async () => {
    listOpenApps
      .mockResolvedValueOnce({ platform: 'darwin', apps: [app('finder', 'file-manager')] })
      .mockResolvedValueOnce({ platform: 'win32', apps: [app('explorer', 'file-manager')] });

    expect(await loadOpenApps('mac')).toEqual([app('finder', 'file-manager')]);
    expect(await loadOpenApps('pc')).toEqual([app('explorer', 'file-manager')]);
  });

  it('reports a failure as null rather than rejecting', async () => {
    listOpenApps.mockRejectedValue(new RpcError('no_handler'));

    await expect(loadOpenApps('m1')).resolves.toBeNull();
  });

  it('holds a failure only briefly, so an upgraded daemon recovers', async () => {
    listOpenApps.mockRejectedValueOnce(new RpcError('target_disconnected'));
    let now = 1_000_000;

    expect(await loadOpenApps('m1', () => now)).toBeNull();
    // Still inside the negative-cache window: no second round trip.
    expect(await loadOpenApps('m1', () => now)).toBeNull();
    expect(listOpenApps).toHaveBeenCalledTimes(1);

    listOpenApps.mockResolvedValue({ platform: 'darwin', apps: [app('finder', 'file-manager')] });
    now += FAILURE_TTL_MS + 1;

    expect(await loadOpenApps('m1', () => now)).toEqual([app('finder', 'file-manager')]);
    expect(listOpenApps).toHaveBeenCalledTimes(2);
  });
});
