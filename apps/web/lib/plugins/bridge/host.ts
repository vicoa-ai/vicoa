/**
 * The host end of the bridge: answers one plugin page's requests.
 *
 * Every request is checked in order: well-formed, small enough, within the
 * rate limit, and allowed by the plugin's declared permissions
 * (`permissions.ts`). Then the method runs with the user's own API client, so
 * the backend applies the same access rules it applies to the user. Pages
 * never see a token: they get plain data back.
 *
 * Opening things (a task, a session, a URL) goes through `HostUi`, which the
 * page shell implements with Vicoa's own UI. Local files and settings go to
 * the plugin's machine over `rpc`, where the daemon checks paths again.
 *
 * Framework-free and dependency-injected, so it can be unit-tested.
 */

import type { getBackendAPI, TaskStatus, TaskPriority } from '@/lib/backend-api';
import { continueSession, ContinueSessionError } from '@/lib/session-continue';
import type { PluginManifest } from '../types';
import {
  BRIDGE_LIMITS,
  BridgeError,
  RateLimiter,
  errorResponse,
  eventMessage,
  isBridgeRequest,
  okResponse,
  type BridgeErrorBody,
  type BridgeErrorCode,
  type HostMessage,
} from './protocol';
import { checkMethod } from './permissions';
import { isAppPath } from '../sidebar';
import {
  clampLimit,
  filterTasks,
  mapAutomation,
  mapComment,
  mapMessage,
  mapProject,
  mapRun,
  mapSession,
  mapSessionDetail,
  mapTask,
  parseSessionFilter,
  parseTaskFilter,
  sessionMatches,
  type PluginSession,
  type PluginTask,
} from './data';

type Api = ReturnType<typeof getBackendAPI>;

export interface HeaderItem {
  id: string;
  label: string;
}

/** What a page may put in the host's title bar. Clicks come back as `header` events. */
export interface PluginHeader {
  title?: string;
  subtitle?: string;
  crumbs?: HeaderItem[];
  tabs?: HeaderItem[];
  activeTab?: string;
  actions?: (HeaderItem & { icon?: string })[];
}

export interface NewSessionPrefill {
  machineId?: string;
  directory?: string;
  projectId?: string;
  agent?: string;
  prompt?: string;
  taskId?: string;
}

/** Host UI the bridge drives. Every one of these only opens Vicoa's own UI. */
export interface HostUi {
  setHeader(header: PluginHeader): void;
  toast(text: string, kind: 'success' | 'error'): void;
  openTask(id: string, siblings: string[]): void;
  openSession(id: string, siblings: string[]): void;
  openNewSession(prefill: NewSessionPrefill): void;
  openUrl(url: string): void;
  openPage(surfaceId: string, params: Record<string, string>): void;
  setRoute(path: string, replace: boolean): void;
}

export interface BridgeContextInfo {
  pluginId: string;
  pluginName: string;
  surfaceId: string;
  machineId: string;
  machineName: string | null;
  platform: 'desktop' | 'web';
  theme: 'dark' | 'light';
  apiVersion: number;
  permissions: string[];
}

/** Device-scope settings, kept by the browser (not the daemon). */
export interface DeviceSettingsStore {
  get(): Record<string, unknown>;
  set(patch: Record<string, unknown>): void;
}

export interface BridgeHostDeps {
  manifest: PluginManifest;
  /** The plugin's on-disk id on its machine (what the daemon RPCs take). */
  pluginId: string;
  machineId: string;
  getApi: () => Api | null;
  /** A daemon RPC on the plugin's machine. */
  rpc: (method: string, params: Record<string, unknown>) => Promise<Record<string, unknown>>;
  post: (message: HostMessage) => void;
  ui: HostUi;
  context: () => BridgeContextInfo;
  deviceSettings: DeviceSettingsStore;
  /** Called on any live session change, so session watches refresh promptly. */
  subscribeSessionUpdates?: (onChange: () => void) => () => void;
  now?: () => number;
}

export interface BridgeHost {
  /** Feed every `message` event whose source is the page's frame. */
  handle(data: unknown): Promise<void>;
  emit(name: string, payload: unknown): void;
  /** Re-run watches now, e.g. when the window regains focus. */
  refreshWatches(): void;
  dispose(): void;
}

const WATCH_POLL_MS = 60_000;
const MAX_BODY = 20_000;
const TASK_STATUSES: ReadonlySet<string> = new Set([
  'backlog',
  'todo',
  'in_progress',
  'in_review',
  'done',
  'blocked',
  'cancelled',
]);
const TASK_PRIORITIES: ReadonlySet<string> = new Set(['urgent', 'high', 'medium', 'low', 'none']);

// --- param helpers ----------------------------------------------------------

type Params = Record<string, unknown>;

const asParams = (raw: unknown): Params =>
  raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Params) : {};

function str(params: Params, key: string, { max = 500, optional = false } = {}): string | undefined {
  const v = params[key];
  if (v === undefined || v === null) {
    if (optional) return undefined;
    throw new BridgeError('invalid_params', `"${key}" is required`);
  }
  if (typeof v !== 'string' || v.length === 0 || v.length > max) {
    throw new BridgeError('invalid_params', `"${key}" must be a non-empty string of at most ${max} characters`);
  }
  return v;
}

const reqStr = (params: Params, key: string, max = 500): string => str(params, key, { max }) as string;
const optStr = (params: Params, key: string, max = 500): string | undefined =>
  str(params, key, { max, optional: true });

function idList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === 'string' && x.length > 0 && x.length <= 100).slice(0, 500);
}

function headerItems(v: unknown, max: number): HeaderItem[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: HeaderItem[] = [];
  for (const item of v.slice(0, max)) {
    const p = asParams(item);
    if (typeof p.id === 'string' && typeof p.label === 'string' && p.id && p.label) {
      out.push({ id: p.id.slice(0, 100), label: p.label.slice(0, 80) });
    }
  }
  return out;
}

export function sanitizeHeader(raw: unknown): PluginHeader {
  const p = asParams(raw);
  const text = (k: string, max: number) => (typeof p[k] === 'string' ? (p[k] as string).slice(0, max) : undefined);
  const actions = Array.isArray(p.actions)
    ? (headerItems(p.actions, 6) ?? []).map((item, i) => {
        const icon = asParams((p.actions as unknown[])[i]).icon;
        return typeof icon === 'string' ? { ...item, icon: icon.slice(0, 40) } : item;
      })
    : undefined;
  return {
    title: text('title', 120),
    subtitle: text('subtitle', 200),
    crumbs: headerItems(p.crumbs, 6),
    tabs: headerItems(p.tabs, 8),
    activeTab: text('activeTab', 100),
    actions,
  };
}

/** An http(s) URL or an in-app path (see `isAppPath`), else null. */
export function safeOpenUrl(url: string): string | null {
  if (/[\u0000-\u0020\u007f]/.test(url)) return null;
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? url : null;
    } catch {
      return null;
    }
  }
  return isAppPath(url) ? url : null;
}

// --- errors -------------------------------------------------------------------

function toErrorBody(err: unknown): BridgeErrorBody {
  if (err instanceof BridgeError) return { code: err.code, message: err.message };
  if (err instanceof ContinueSessionError) {
    return { code: err.reason === 'machine-offline' ? 'machine_offline' : 'not_available', message: err.message };
  }
  const e = err as { status?: unknown; detail?: unknown; message?: unknown; code?: unknown };
  if (typeof e?.status === 'number') {
    const detail = typeof e.detail === 'string' ? e.detail : `Request failed (${e.status})`;
    if (e.status === 404) return { code: 'not_found', message: detail };
    if (e.status === 401 || e.status === 403) return { code: 'permission_denied', message: detail };
    if (e.status >= 400 && e.status < 500) return { code: 'invalid_params', message: detail };
    return { code: 'failed', message: detail };
  }
  // RpcError from the WebSocket layer: the machine isn't reachable.
  if (typeof e?.code === 'string' && /^(no_handler|target_disconnected|not_connected|timeout)$/.test(e.code)) {
    return { code: 'machine_offline', message: "The plugin's machine isn't reachable" };
  }
  return { code: 'failed', message: typeof e?.message === 'string' ? e.message : 'Request failed' };
}

/** Map a daemon RPC `{error}` result onto a bridge error. */
export function daemonError(result: Record<string, unknown>): BridgeError | null {
  const raw = result.error;
  if (raw === undefined || raw === null) return null;
  const code = String(raw);
  if (code.startsWith('unknown RPC method')) {
    return new BridgeError('daemon_outdated', 'Update Vicoa on the machine this plugin is installed on');
  }
  const known: Partial<Record<string, BridgeErrorCode>> = {
    not_found: 'not_found',
    not_allowed: 'not_allowed',
    invalid_path: 'not_allowed',
    not_trusted: 'permission_denied',
    too_large: 'too_large',
    not_a_file: 'not_found',
    not_utf8: 'invalid_params',
    invalid_setting: 'invalid_params',
  };
  const message = typeof result.message === 'string' ? result.message : code;
  return new BridgeError(known[code] ?? 'failed', message);
}

// --- the host -------------------------------------------------------------------

interface Watch {
  kind: 'tasks' | 'sessions';
  run: () => Promise<unknown>;
  last: string;
  busy: boolean;
}

export function createBridgeHost(deps: BridgeHostDeps): BridgeHost {
  const now = deps.now ?? (() => Date.now());
  const limiter = new RateLimiter(BRIDGE_LIMITS.maxRequestsPerSecond);
  const watches = new Map<string, Watch>();
  let watchSeq = 0;
  let disposed = false;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let unsubscribeSessions: (() => void) | null = null;
  let sessionRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  const api = (): Api => {
    const a = deps.getApi();
    if (!a) throw new BridgeError('not_available', 'Sign in to Vicoa to use this');
    return a;
  };

  const rpc = async (method: string, params: Params): Promise<Record<string, unknown>> => {
    const result = await deps.rpc(method, { plugin_id: deps.pluginId, ...params });
    const err = daemonError(result);
    if (err) throw err;
    return result;
  };

  const post = (message: HostMessage) => {
    if (!disposed) deps.post(message);
  };

  // --- data ---

  async function listTasks(raw: unknown): Promise<PluginTask[]> {
    const filter = parseTaskFilter(raw);
    const single = filter.status?.length === 1 ? (filter.status[0] as TaskStatus) : undefined;
    const rows = await api().listTasks({ projectId: filter.projectId, status: single });
    return filterTasks(rows.map(mapTask), filter);
  }

  async function listSessions(raw: unknown): Promise<PluginSession[]> {
    const filter = parseSessionFilter(raw);
    const out: PluginSession[] = [];
    const pageSize = 100;
    // Newest first by start time, so stop at the first page that reaches past `since`.
    for (let page = 0, offset = 0; page < 20 && out.length < filter.limit; page++) {
      const res = await api().listAllAgentInstancesPage({ limit: pageSize, offset });
      let reachedEnd = false;
      for (const row of res.items) {
        const s = mapSession(row);
        if (filter.since !== undefined && Date.parse(s.startedAt) < filter.since) {
          reachedEnd = true;
          break;
        }
        if (sessionMatches(s, filter)) out.push(s);
        if (out.length >= filter.limit) break;
      }
      if (reachedEnd || !res.hasMore || res.items.length === 0) break;
      offset += res.items.length;
    }
    return out;
  }

  async function readSettings(): Promise<Record<string, unknown>> {
    const schema = deps.manifest.settings ?? {};
    const values: Record<string, unknown> = {};
    for (const [key, spec] of Object.entries(schema)) values[key] = spec.default;
    if (Object.values(schema).some((s) => s.scope === 'machine')) {
      try {
        const res = await rpc('plugin-settings-get', {});
        Object.assign(values, asParams(res.values));
      } catch (err) {
        // Defaults keep the page usable on a machine that can't answer.
        if (!(err instanceof BridgeError && err.code === 'daemon_outdated')) throw err;
      }
    }
    const device = deps.deviceSettings.get();
    for (const [key, spec] of Object.entries(schema)) {
      if (spec.scope === 'device' && key in device) values[key] = device[key];
    }
    return values;
  }

  async function writeSettings(raw: unknown): Promise<Record<string, unknown>> {
    const patch = asParams(asParams(raw).patch);
    const schema = deps.manifest.settings ?? {};
    const machine: Params = {};
    const device: Params = {};
    for (const [key, value] of Object.entries(patch)) {
      const spec = schema[key];
      if (!spec) throw new BridgeError('invalid_params', `"${key}" is not a declared setting`);
      if (spec.scope === 'device') device[key] = value;
      else machine[key] = value;
    }
    if (Object.keys(machine).length) await rpc('plugin-settings-set', { values: machine });
    if (Object.keys(device).length) deps.deviceSettings.set(device);
    const values = await readSettings();
    emit('settings', values);
    return values;
  }

  // --- watches ---

  async function runWatch(id: string, w: Watch): Promise<void> {
    if (w.busy || disposed) return;
    w.busy = true;
    try {
      const data = await w.run();
      const hash = JSON.stringify(data);
      if (hash !== w.last && watches.has(id)) {
        w.last = hash;
        post(eventMessage('watch', { watchId: id, data }));
      }
    } catch {
      // A failed refresh keeps the last result; the next tick tries again.
    } finally {
      w.busy = false;
    }
  }

  function ensureWatchTimers(): void {
    if (!pollTimer) {
      pollTimer = setInterval(() => {
        for (const [id, w] of watches) void runWatch(id, w);
      }, WATCH_POLL_MS);
    }
    if (!unsubscribeSessions && deps.subscribeSessionUpdates) {
      unsubscribeSessions = deps.subscribeSessionUpdates(() => {
        if (sessionRefreshTimer) return;
        sessionRefreshTimer = setTimeout(() => {
          sessionRefreshTimer = null;
          for (const [id, w] of watches) if (w.kind === 'sessions') void runWatch(id, w);
        }, 1000);
      });
    }
  }

  async function startWatch(kind: Watch['kind'], run: () => Promise<unknown>): Promise<unknown> {
    if (watches.size >= BRIDGE_LIMITS.maxWatches) {
      throw new BridgeError('rate_limited', `At most ${BRIDGE_LIMITS.maxWatches} watches per page`);
    }
    const data = await run();
    watchSeq += 1;
    const watchId = `w${watchSeq}`;
    watches.set(watchId, { kind, run, last: JSON.stringify(data), busy: false });
    ensureWatchTimers();
    return { watchId, data };
  }

  // --- methods ---

  async function run(method: string, raw: unknown): Promise<unknown> {
    const p = asParams(raw);
    switch (method) {
      case 'context.get':
        return deps.context();

      case 'projects.list':
        return (await api().listProjects()).map(mapProject);

      case 'tasks.list':
        return listTasks(raw);
      case 'tasks.get':
        return mapTask(await api().getTask(reqStr(p, 'id', 100)));
      case 'tasks.comments':
        return (await api().getTaskTimeline(reqStr(p, 'id', 100))).comments.map(mapComment);
      case 'tasks.watch':
        return startWatch('tasks', () => listTasks(raw));
      case 'tasks.comment': {
        const timeline = await api().createTaskComment(reqStr(p, 'id', 100), reqStr(p, 'body', MAX_BODY));
        return timeline.comments.map(mapComment);
      }
      case 'tasks.update': {
        const patch = asParams(p.patch);
        const body: Parameters<Api['updateTask']>[1] = {};
        if (patch.title !== undefined) body.title = reqStr(patch, 'title', 500);
        if (patch.description !== undefined) body.description = patch.description === null ? null : reqStr(patch, 'description', MAX_BODY);
        if (patch.status !== undefined) {
          if (typeof patch.status !== 'string' || !TASK_STATUSES.has(patch.status)) {
            throw new BridgeError('invalid_params', `"status" must be one of ${[...TASK_STATUSES].join(', ')}`);
          }
          body.status = patch.status as TaskStatus;
        }
        if (patch.priority !== undefined) {
          if (typeof patch.priority !== 'string' || !TASK_PRIORITIES.has(patch.priority)) {
            throw new BridgeError('invalid_params', `"priority" must be one of ${[...TASK_PRIORITIES].join(', ')}`);
          }
          body.priority = patch.priority as TaskPriority;
        }
        if (patch.dueDate !== undefined) body.due_date = patch.dueDate === null ? null : reqStr(patch, 'dueDate', 40);
        if (patch.startDate !== undefined) body.start_date = patch.startDate === null ? null : reqStr(patch, 'startDate', 40);
        if (Object.keys(body).length === 0) throw new BridgeError('invalid_params', 'Nothing to update');
        return mapTask(await api().updateTask(reqStr(p, 'id', 100), body));
      }
      case 'tasks.create': {
        const status = optStr(p, 'status', 20);
        if (status && !TASK_STATUSES.has(status)) throw new BridgeError('invalid_params', 'Unknown status');
        const priority = optStr(p, 'priority', 20);
        if (priority && !TASK_PRIORITIES.has(priority)) throw new BridgeError('invalid_params', 'Unknown priority');
        const created = await api().createTask({
          title: reqStr(p, 'title', 500),
          description: optStr(p, 'description', MAX_BODY) ?? null,
          project_id: optStr(p, 'projectId', 100) ?? null,
          ...(status ? { status: status as TaskStatus } : {}),
          ...(priority ? { priority: priority as TaskPriority } : {}),
          due_date: optStr(p, 'dueDate', 40) ?? null,
        });
        return mapTask(created);
      }

      case 'sessions.list':
        return listSessions(raw);
      case 'sessions.get':
        return mapSessionDetail(await api().getInstanceDetail(reqStr(p, 'id', 100), 1));
      case 'sessions.messages': {
        const rows = (await api().getInstanceMessagesPaginated(
          reqStr(p, 'id', 100),
          clampLimit(p.limit, 50, 200),
          optStr(p, 'before', 100),
        )) as Parameters<typeof mapMessage>[0][];
        return rows.map(mapMessage);
      }
      case 'sessions.watch':
        return startWatch('sessions', () => listSessions(raw));
      case 'sessions.send':
        return { outcome: await continueSession(api(), reqStr(p, 'id', 100), reqStr(p, 'text', MAX_BODY)) };
      case 'sessions.start': {
        const res = await api().spawnRemoteSession(reqStr(p, 'machineId', 100), {
          directory: reqStr(p, 'directory', 2000),
          ...(optStr(p, 'agent', 40) ? { agent: optStr(p, 'agent', 40) as never } : {}),
          prompt: optStr(p, 'prompt', MAX_BODY),
        });
        return { sessionId: res.agent_instance_id };
      }

      case 'automations.list': {
        const projectId = optStr(p, 'projectId', 100);
        const rows = await api().listAutomations({ scope: p.scope === 'all' ? 'all' : 'me', projectId });
        return rows.map(mapAutomation);
      }
      case 'automations.runs': {
        const rows = await api().listAutomationRuns(reqStr(p, 'id', 100));
        return rows.slice(0, clampLimit(p.limit, 20, 200)).map(mapRun);
      }
      case 'automations.run':
        throw new BridgeError('not_available', 'vicoa.automations.run is not available yet');

      case 'files.read': {
        const res = await rpc('plugin-data-read', { path: reqStr(p, 'path', 1000) });
        return { content: String(res.content ?? ''), size: res.size ?? null, mtime: res.mtime ?? null };
      }

      case 'settings.get':
        return readSettings();
      case 'settings.set':
        return writeSettings(raw);

      case 'open.task':
        deps.ui.openTask(reqStr(p, 'id', 100), idList(p.siblings));
        return null;
      case 'open.session':
        deps.ui.openSession(reqStr(p, 'id', 100), idList(p.siblings));
        return null;
      case 'open.newSession':
        deps.ui.openNewSession({
          machineId: optStr(p, 'machineId', 100),
          directory: optStr(p, 'directory', 2000),
          projectId: optStr(p, 'projectId', 100),
          agent: optStr(p, 'agent', 40),
          prompt: optStr(p, 'prompt', MAX_BODY),
          taskId: optStr(p, 'taskId', 100),
        });
        return null;
      case 'open.url': {
        const url = safeOpenUrl(reqStr(p, 'url', 4000));
        if (!url) throw new BridgeError('invalid_params', 'Only http(s) links and app paths can be opened');
        deps.ui.openUrl(url);
        return null;
      }
      case 'open.page': {
        const surfaceId = reqStr(p, 'surfaceId', 64);
        const surface = deps.manifest.surfaces?.find((s) => s.id === surfaceId && s.kind === 'page');
        if (!surface) throw new BridgeError('not_found', `No page "${surfaceId}" in plugin.json`);
        const params: Record<string, string> = {};
        for (const [k, v] of Object.entries(asParams(p.params)).slice(0, 20)) {
          if (typeof v === 'string' && k.length <= 40) params[k] = v.slice(0, 500);
        }
        deps.ui.openPage(surfaceId, params);
        return null;
      }

      case 'ui.setHeader':
        deps.ui.setHeader(sanitizeHeader(raw));
        return null;
      case 'ui.toast':
        deps.ui.toast(reqStr(p, 'text', 300), p.kind === 'error' ? 'error' : 'success');
        return null;

      case 'route.set': {
        const path = typeof p.path === 'string' ? p.path.slice(0, 2000) : '';
        deps.ui.setRoute(path, p.replace === true);
        return null;
      }

      case 'log.write': {
        const entries = Array.isArray(p.entries) ? p.entries.slice(0, 50) : [];
        if (entries.length) await rpc('plugin-log', { entries }).catch(() => undefined);
        return null;
      }
      case 'watch.stop':
        watches.delete(reqStr(p, 'watchId', 20));
        return null;

      case 'backend.call':
        throw new BridgeError('not_available', 'Plugin backends are not available yet');
    }
    throw new BridgeError('unknown_method', `vicoa has no method ${method}`);
  }

  function emit(name: string, payload: unknown): void {
    post(eventMessage(name, payload));
  }

  async function handle(data: unknown): Promise<void> {
    if (disposed || !isBridgeRequest(data)) return;
    const { id, method } = data;
    let size: number;
    try {
      size = JSON.stringify(data.params ?? null).length;
    } catch {
      post(errorResponse(id, { code: 'invalid_params', message: 'Arguments must be plain JSON data' }));
      return;
    }
    if (size > BRIDGE_LIMITS.maxMessageBytes) {
      post(errorResponse(id, { code: 'too_large', message: 'Request is too large' }));
      return;
    }
    if (!limiter.take(now())) {
      post(errorResponse(id, { code: 'rate_limited', message: 'Too many requests; slow down' }));
      return;
    }
    const check = checkMethod(method, deps.manifest);
    if (!check.ok) {
      post(errorResponse(id, { code: check.code, message: check.message }));
      return;
    }
    try {
      post(okResponse(id, await run(method, data.params)));
    } catch (err) {
      post(errorResponse(id, toErrorBody(err)));
    }
  }

  return {
    handle,
    emit,
    refreshWatches() {
      for (const [id, w] of watches) void runWatch(id, w);
    },
    dispose() {
      disposed = true;
      watches.clear();
      if (pollTimer) clearInterval(pollTimer);
      if (sessionRefreshTimer) clearTimeout(sessionRefreshTimer);
      unsubscribeSessions?.();
    },
  };
}

