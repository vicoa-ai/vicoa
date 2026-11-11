import { describe, expect, it } from 'vitest';
import { describeAccess, describeContributions, snippet } from './trust-summary';

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
