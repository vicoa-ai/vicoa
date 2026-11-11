/**
 * Which bridge method needs which declared permission.
 *
 * The host checks this before running a method; the backend still applies the
 * user's own access rules to whatever the method calls, so a plugin never sees
 * more than its user could. `files` methods additionally need a matching
 * `files` glob, which the daemon checks against the real path.
 */

import type { PluginManifest, PluginPermission } from '../types';

/** `null`: any page may call it. `'files'`: needs a non-empty `files` list. */
export type MethodRequirement = PluginPermission | 'files' | null;

export const METHOD_REQUIREMENTS: Readonly<Record<string, MethodRequirement>> = {
  'context.get': null,

  'projects.list': 'projects:read',

  'tasks.list': 'tasks:read',
  'tasks.get': 'tasks:read',
  'tasks.comments': 'tasks:read',
  'tasks.watch': 'tasks:read',
  'tasks.comment': 'tasks:write',
  'tasks.update': 'tasks:write',
  'tasks.create': 'tasks:write',

  'sessions.list': 'sessions:read',
  'sessions.get': 'sessions:read',
  'sessions.messages': 'sessions:read',
  'sessions.watch': 'sessions:read',
  'sessions.send': 'sessions:write',
  'sessions.start': 'sessions:start',

  'automations.list': 'automations:read',
  'automations.runs': 'automations:read',
  'automations.run': 'automations:run',

  'files.read': 'files',

  'settings.get': null,
  'settings.set': null,

  'open.task': null,
  'open.session': null,
  'open.newSession': null,
  'open.url': null,
  'open.page': null,

  'ui.setHeader': null,
  'ui.toast': null,

  'route.set': null,

  'log.write': null,
  'watch.stop': null,

  'backend.call': 'backend',
};

export type PermissionCheck =
  | { ok: true }
  | { ok: false; code: 'unknown_method' | 'permission_denied'; message: string };

export function checkMethod(method: string, manifest: PluginManifest): PermissionCheck {
  if (!Object.prototype.hasOwnProperty.call(METHOD_REQUIREMENTS, method)) {
    return { ok: false, code: 'unknown_method', message: `vicoa has no method ${method}` };
  }
  const need = METHOD_REQUIREMENTS[method];
  if (need === null) return { ok: true };
  if (need === 'files') {
    return manifest.files?.length
      ? { ok: true }
      : { ok: false, code: 'permission_denied', message: `${method} needs "files" in plugin.json` };
  }
  return manifest.permissions?.includes(need)
    ? { ok: true }
    : { ok: false, code: 'permission_denied', message: `${method} needs the "${need}" permission in plugin.json` };
}

/** Plain words for the trust prompt, one line per permission. */
export const PERMISSION_TEXT: Readonly<Record<PluginPermission, string>> = {
  'projects:read': 'See your projects',
  'tasks:read': 'Read your tasks and their comments',
  'tasks:write': 'Comment on, change and create tasks as you',
  'sessions:read': 'Read your sessions and their messages',
  'sessions:write': 'Send messages to your sessions as you',
  'sessions:start': 'Start new sessions on your machines',
  'automations:read': 'See your automations and their runs',
  'automations:run': 'Run your automations',
  backend: 'Run its own code on this machine',
};
