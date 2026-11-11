import { afterEach, describe, expect, it, vi } from 'vitest';
import type { getBackendAPI, TaskResponse } from '@/lib/backend-api';
import type { PluginManifest } from '../types';
import { createBridgeHost, daemonError, safeOpenUrl, sanitizeHeader, type HostUi } from './host';
import { BRIDGE_TAG, type HostMessage } from './protocol';

type Api = ReturnType<typeof getBackendAPI>;

function task(id: string, over: Partial<TaskResponse> = {}): TaskResponse {
  return {
    id,
    project_id: 'p1',
    number: 1,
    identifier: `DEMO-${id}`,
    title: `Task ${id}`,
    description: null,
    status: 'todo',
    priority: 'none',
    position: 0,
    parent_task_id: null,
    parent_title: null,
    assignee_type: null,
    assignee_id: null,
    assignee: null,
    labels: [],
    start_date: null,
    due_date: null,
    created_in_instance_id: null,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...over,
  };
}

const ui = (): HostUi => ({
  setHeader: vi.fn(),
  toast: vi.fn(),
  openTask: vi.fn(),
  openSession: vi.fn(),
  openNewSession: vi.fn(),
  openUrl: vi.fn(),
  openPage: vi.fn(),
  setRoute: vi.fn(),
});

type Rpc = (method: string, params: Record<string, unknown>) => Promise<Record<string, unknown>>;

function setup(
  manifest: Partial<PluginManifest>,
  api: Partial<Api> = {},
  rpc: ReturnType<typeof vi.fn<Rpc>> = vi.fn<Rpc>(async () => ({ ok: true })),
) {
  const posted: HostMessage[] = [];
  const hostUi = ui();
  const host = createBridgeHost({
    manifest: { id: 'dash', apiVersion: 2, ...manifest },
    pluginId: 'dash',
    machineId: 'm1',
    getApi: () => api as Api,
    rpc,
    post: (m) => posted.push(m),
    ui: hostUi,
    context: () => ({
      pluginId: 'dash',
      pluginName: 'Dash',
      surfaceId: 'home',
      machineId: 'm1',
      machineName: null,
      platform: 'web',
      theme: 'dark',
      apiVersion: 1,
      permissions: [],
    }),
    deviceSettings: { get: () => ({}), set: vi.fn() },
  });
  let seq = 0;
  const call = async (method: string, params: unknown = {}) => {
    seq += 1;
    await host.handle({ [BRIDGE_TAG]: 1, kind: 'req', id: seq, method, params });
    const res = posted.find((m) => m.kind === 'res' && m.id === seq);
    if (!res || res.kind !== 'res') throw new Error('no response');
    return res;
  };
  return { host, call, posted, ui: hostUi, rpc };
}

afterEach(() => vi.useRealTimers());

describe('bridge host permissions', () => {
  it('refuses a method the manifest did not ask for', async () => {
    const { call } = setup({ permissions: [] }, { listTasks: vi.fn() });
    const res = await call('tasks.list');
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error.code).toBe('permission_denied');
  });

  it('refuses writes when only read was declared', async () => {
    const updateTask = vi.fn();
    const { call } = setup({ permissions: ['tasks:read'] }, { updateTask });
    const res = await call('tasks.update', { id: 't1', patch: { status: 'done' } });
    expect(res.ok).toBe(false);
    expect(updateTask).not.toHaveBeenCalled();
  });

  it('refuses file reads without a files list', async () => {
    const { call, rpc } = setup({ permissions: ['tasks:read'] });
    const res = await call('files.read', { path: '~/x.json' });
    expect(res.ok).toBe(false);
    expect(rpc).not.toHaveBeenCalled();
  });

  it('rejects unknown methods and malformed messages', async () => {
    const { host, call, posted } = setup({});
    const res = await call('tasks.delete', { id: 'x' });
    if (!res.ok) expect(res.error.code).toBe('unknown_method');
    await host.handle({ kind: 'req', id: 99, method: 'context.get' });
    await host.handle('hello');
    expect(posted.filter((m) => m.kind === 'res' && m.id === 99)).toHaveLength(0);
  });

  it('rate-limits a flood of requests', async () => {
    const { call } = setup({});
    const results = [];
    for (let i = 0; i < 70; i++) results.push(await call('context.get'));
    expect(results.filter((r) => !r.ok && r.error.code === 'rate_limited').length).toBeGreaterThan(0);
  });
});

describe('bridge host data', () => {
  it('filters tasks by label and status and maps them', async () => {
    const listTasks = vi.fn(async () => [
      task('1', { labels: [{ id: 'l', name: 'needs-human', color: '#000000' }] }),
      task('2'),
      task('3', { status: 'done', labels: [{ id: 'l', name: 'needs-human', color: '#000000' }] }),
    ]);
    const { call } = setup({ permissions: ['tasks:read'] }, { listTasks });
    const res = await call('tasks.list', { label: 'Needs-Human', status: ['todo'] });
    expect(res.ok && (res.result as { id: string; labels: string[] }[]).map((t) => t.id)).toEqual(['1']);
  });

  it('pages sessions until it passes `since`', async () => {
    const row = (id: string, started: string) => ({
      id,
      agent_type_id: 'a',
      agent_type_name: 'claude',
      name: id,
      status: 'COMPLETED' as const,
      started_at: started,
      ended_at: null,
      latest_message: `done ${id}`,
      latest_message_at: started,
      chat_length: 3,
    });
    const listAllAgentInstancesPage = vi.fn(async ({ offset = 0 }: { offset?: number }) => ({
      items:
        offset === 0
          ? [row('a', '2026-11-10T10:00:00Z'), row('b', '2026-11-10T09:00:00Z')]
          : [row('c', '2026-11-09T01:00:00Z'), row('d', '2026-11-08T01:00:00Z')],
      total: 4,
      limit: 2,
      offset,
      hasMore: offset === 0,
      isPaginated: true,
    }));
    const { call } = setup({ permissions: ['sessions:read'] }, { listAllAgentInstancesPage } as Partial<Api>);
    const res = await call('sessions.list', { since: '2026-11-09T00:00:00Z' });
    expect(res.ok && (res.result as { id: string; lastMessage: string }[]).map((s) => s.id)).toEqual(['a', 'b', 'c']);
    expect(listAllAgentInstancesPage).toHaveBeenCalledTimes(2);
  });

  it('reads declared files through the daemon and maps its errors', async () => {
    const rpc = vi.fn<Rpc>(async (_method, params) =>
      params.path === '~/ok.json' ? { ok: true, content: '{"a":1}', size: 7, mtime: 1 } : { error: 'not_allowed' },
    );
    const { call } = setup({ files: ['~/*.json'] }, {}, rpc);
    const ok = await call('files.read', { path: '~/ok.json' });
    expect(ok.ok && (ok.result as { content: string }).content).toBe('{"a":1}');
    expect(rpc).toHaveBeenCalledWith('plugin-data-read', { plugin_id: 'dash', path: '~/ok.json' });
    const denied = await call('files.read', { path: '/etc/passwd' });
    if (!denied.ok) expect(denied.error.code).toBe('not_allowed');
  });

  it('tells the page to update an old daemon', async () => {
    const rpc = vi.fn<Rpc>(async () => ({ error: 'unknown RPC method: plugin-data-read' }));
    const { call } = setup({ files: ['~/*.json'] }, {}, rpc);
    const res = await call('files.read', { path: '~/ok.json' });
    if (!res.ok) expect(res.error.code).toBe('daemon_outdated');
  });

  it('splits settings between the machine and this device', async () => {
    const rpc = vi.fn<Rpc>(async (method) =>
      method === 'plugin-settings-get' ? { ok: true, values: { label: 'stored' } } : { ok: true },
    );
    const { call } = setup(
      {
        settings: {
          label: { type: 'string', default: 'needs-human', scope: 'machine' },
          collapsed: { type: 'array', items: 'string', default: [], scope: 'device' },
        },
      },
      {},
      rpc,
    );
    const got = await call('settings.get');
    expect(got.ok && got.result).toEqual({ label: 'stored', collapsed: [] });
    await call('settings.set', { patch: { label: 'x', collapsed: ['a'] } });
    expect(rpc).toHaveBeenCalledWith('plugin-settings-set', { plugin_id: 'dash', values: { label: 'x' } });
    const bad = await call('settings.set', { patch: { nope: 1 } });
    expect(bad.ok).toBe(false);
  });
});

describe('bridge host UI', () => {
  it('only opens http(s) links and app paths', async () => {
    const { call, ui: hostUi } = setup({});
    expect((await call('open.url', { url: 'javascript:alert(1)' })).ok).toBe(false);
    expect((await call('open.url', { url: '//evil.example' })).ok).toBe(false);
    expect((await call('open.url', { url: 'https://vicoa.ai' })).ok).toBe(true);
    expect(hostUi.openUrl).toHaveBeenCalledWith('https://vicoa.ai');
  });

  it('opens tasks with their siblings for J/K', async () => {
    const { call, ui: hostUi } = setup({});
    await call('open.task', { id: 't2', siblings: ['t1', 't2', 3, 't3'] });
    expect(hostUi.openTask).toHaveBeenCalledWith('t2', ['t1', 't2', 't3']);
  });

  it('only opens declared pages', async () => {
    const { call, ui: hostUi } = setup({
      surfaces: [{ id: 'home', kind: 'page', entry: 'pages/index.html' }],
    });
    expect((await call('open.page', { surfaceId: 'week' })).ok).toBe(false);
    await call('open.page', { surfaceId: 'home', params: { project: 'hab', n: 3 } });
    expect(hostUi.openPage).toHaveBeenCalledWith('home', { project: 'hab' });
  });
});

describe('helpers', () => {
  it('sanitizes header items', () => {
    const h = sanitizeHeader({ title: 'x'.repeat(500), tabs: [{ id: 'a', label: 'A' }, { id: 1 }], actions: [{ id: 'r', label: 'Refresh', icon: 'refresh-cw' }] });
    expect(h.title).toHaveLength(120);
    expect(h.tabs).toEqual([{ id: 'a', label: 'A' }]);
    expect(h.actions).toEqual([{ id: 'r', label: 'Refresh', icon: 'refresh-cw' }]);
  });

  it('maps daemon errors', () => {
    expect(daemonError({ ok: true })).toBeNull();
    expect(daemonError({ error: 'not_trusted' })?.code).toBe('permission_denied');
    expect(safeOpenUrl('/dashboard/tasks')).toBe('/dashboard/tasks');
    expect(safeOpenUrl('/\t/evil.example/login')).toBeNull();
    expect(safeOpenUrl('https://ok.example/a b')).toBeNull();
    expect(safeOpenUrl('https://ok.example/\u0001')).toBeNull();
  });
});
