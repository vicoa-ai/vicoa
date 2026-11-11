import { describe, expect, it } from 'vitest';
import { describeAccess, describeContributions, joinWords, snippet, summarizeTrust } from './trust-summary';

describe('describeContributions', () => {
  it('says what each contribution does', () => {
    const lines = describeContributions({
      id: 'demo',
      apiVersion: 1,
      themes: [{ id: 't', label: 'Emerald', base: 'dark', tokens: { primary: '1 2% 3%' } }],
      sidebarItems: [
        { id: 'a', label: 'Docs', action: { type: 'open-url', url: 'https://vicoa.ai/docs', external: true } },
        { id: 'b', label: 'Tasks', action: { type: 'open-url', url: '/dashboard/tasks' } },
        { id: 'c', label: 'Dashboard', action: { type: 'surface', surfaceId: 'home' } },
        { id: 'd', label: 'Old', action: { type: 'rpc', method: 'write-file' } as never },
      ],
      composerActions: [
        { id: 'e', label: 'Sign-off', placement: 'toolbar', behavior: { type: 'insert-text', text: 'hi' } },
        { id: 'f', label: 'Notes', behavior: { type: 'insert-path-ref', path: '/notes' } },
      ],
      slashCommands: [{ id: 's', command: '/x', insertText: 'x' }],
    });
    expect(lines).toEqual([
      { kind: 'Theme', label: 'Emerald', detail: 'A dark theme in the theme picker' },
      { kind: 'Sidebar row', label: 'Docs', detail: 'Opens https://vicoa.ai/docs in your browser' },
      { kind: 'Sidebar row', label: 'Tasks', detail: 'Opens /dashboard/tasks in Vicoa' },
      { kind: 'Sidebar row', label: 'Dashboard', detail: 'Opens the plugin\'s "home" page' },
      { kind: 'Composer button', label: 'Sign-off', detail: 'Inserts text: hi' },
      { kind: 'Composer menu item', label: 'Notes', detail: 'Inserts a reference to /notes' },
    ]);
  });
});

describe('snippet', () => {
  it('flattens whitespace and caps the length', () => {
    expect(snippet('## Summary\n\n## Testing\n')).toBe('## Summary ## Testing');
    expect(snippet('x'.repeat(100))).toHaveLength(60);
  });
});

describe('describeAccess', () => {
  it('lists permissions in plain words, files and sites', () => {
    const a = describeAccess({
      id: 'd',
      apiVersion: 2,
      permissions: ['tasks:read', 'sessions:write'],
      files: ['~/**/.vicoa/dashboard.local.json'],
      surfaces: [{ id: 'home', kind: 'page', entry: 'pages/index.html' }],
    });
    expect(a.permissions).toEqual(['Read your tasks and their comments', 'Send messages to your sessions as you']);
    expect(a.files).toEqual(['~/**/.vicoa/dashboard.local.json']);
    expect(a.network).toEqual([]);
    expect(a.any).toBe(true);
    expect(a.runsCode).toBe(false);
  });

  it('says nothing extra for a plugin without pages or access', () => {
    expect(describeAccess({ id: 'v1', apiVersion: 1 }).any).toBe(false);
  });

  it('flags a plugin that runs code on the machine', () => {
    expect(describeAccess({ id: 'b', apiVersion: 2, server: 'server.js' }).runsCode).toBe(true);
  });
});

describe('summarizeTrust', () => {
  const dashboard = {
    id: 'dashboard',
    apiVersion: 2,
    permissions: ['projects:read', 'tasks:read', 'sessions:read', 'automations:read'] as const,
    files: ['~/**/.vicoa/dashboard.local.json'],
    surfaces: [{ id: 'home', kind: 'page' as const, entry: 'pages/index.html' }],
    sidebarItems: [{ id: 'open', label: 'Dashboard', action: { type: 'surface' as const, surfaceId: 'home' } }],
  };

  it('says it in a few short lines', () => {
    expect(summarizeTrust({ ...dashboard, permissions: [...dashboard.permissions] })).toEqual([
      { kind: 'adds', text: 'Adds a page and a sidebar row' },
      { kind: 'reads', text: 'Reads your projects, tasks, sessions and automations' },
      { kind: 'files', text: 'Reads', code: '~/**/.vicoa/dashboard.local.json' },
      { kind: 'network', text: 'No internet access' },
    ]);
  });

  it('calls out acting as the user, sites and code', () => {
    const lines = summarizeTrust({
      id: 'x',
      apiVersion: 2,
      permissions: ['tasks:read', 'tasks:write', 'sessions:start'],
      network: ['https://cdn.example.com', 'https://api.example.com', 'https://img.example.com'],
      surfaces: [{ id: 'home', kind: 'page', entry: 'pages/index.html' }],
      server: 'server.js',
    });
    expect(lines.find((l) => l.kind === 'acts')).toEqual({ kind: 'acts', text: 'Can change tasks and start sessions as you', tone: 'warn' });
    expect(lines.find((l) => l.kind === 'network')?.text).toBe('Loads from cdn.example.com, api.example.com and 1 more');
    expect(lines.find((l) => l.kind === 'code')?.tone).toBe('danger');
  });

  it('keeps a theme-only plugin to one line', () => {
    expect(
      summarizeTrust({ id: 't', apiVersion: 1, themes: [{ id: 'a', label: 'A', base: 'dark', tokens: {} }, { id: 'b', label: 'B', base: 'light', tokens: {} }] }),
    ).toEqual([{ kind: 'adds', text: 'Adds 2 themes' }]);
  });

  it('joins words the way a person would', () => {
    expect(joinWords(['a'])).toBe('a');
    expect(joinWords(['a', 'b'])).toBe('a and b');
    expect(joinWords(['a', 'b', 'c'])).toBe('a, b and c');
  });
});
