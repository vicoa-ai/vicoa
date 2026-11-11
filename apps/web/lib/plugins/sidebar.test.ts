import { describe, expect, it } from 'vitest';
import {
  isAppPath,
  isSidebarItemActive,
  isSupportedSidebarAction,
  pluginSurfacePath,
  sidebarItemHref,
} from './sidebar';

describe('isAppPath', () => {
  it('accepts app routes and rejects protocol-relative ones', () => {
    expect(isAppPath('/dashboard/tasks')).toBe(true);
    expect(isAppPath('//evil.example')).toBe(false);
    expect(isAppPath('/\\evil.example')).toBe(false);
    expect(isAppPath('dashboard')).toBe(false);
  });

  it('refuses control characters, which URL parsing drops', () => {
    // "/\t/evil.example" would become "//evil.example": another site.
    expect(isAppPath('/\t/evil.example/login')).toBe(false);
    expect(isAppPath('/\n/evil.example')).toBe(false);
    expect(isAppPath('/dashboard\u007f')).toBe(false);
  });
});

describe('isSupportedSidebarAction', () => {
  it('drops the removed rpc action an older daemon may still report', () => {
    expect(isSupportedSidebarAction({ type: 'rpc', method: 'write-file' })).toBe(false);
  });

  it('keeps open-url and surface actions', () => {
    expect(isSupportedSidebarAction({ type: 'open-url', url: 'https://vicoa.ai' })).toBe(true);
    expect(isSupportedSidebarAction({ type: 'open-url', url: '/dashboard/tasks' })).toBe(true);
    expect(isSupportedSidebarAction({ type: 'surface', surfaceId: 'home' })).toBe(true);
  });

  it('rejects URLs and page ids the daemon would also reject', () => {
    expect(isSupportedSidebarAction({ type: 'open-url', url: '//evil.example' })).toBe(false);
    expect(isSupportedSidebarAction({ type: 'open-url', url: 'javascript:alert(1)' })).toBe(false);
    expect(isSupportedSidebarAction({ type: 'surface', surfaceId: '../settings' })).toBe(false);
    expect(isSupportedSidebarAction(null)).toBe(false);
  });
});

describe('sidebarItemHref', () => {
  it('routes a page to the plugin route and an app path to itself', () => {
    expect(sidebarItemHref({ type: 'surface', surfaceId: 'home' }, 'dash', 'm-1')).toBe(
      '/dashboard/plugin/m-1/dash/home',
    );
    expect(sidebarItemHref({ type: 'open-url', url: '/dashboard/tasks' }, 'dash', 'm-1')).toBe(
      '/dashboard/tasks',
    );
    expect(sidebarItemHref({ type: 'open-url', url: 'https://vicoa.ai' }, 'dash', 'm-1')).toBeNull();
  });

  it('encodes each route segment', () => {
    expect(pluginSurfacePath('a/b', 'dash', 'home')).toBe('/dashboard/plugin/a%2Fb/dash/home');
  });
});

describe('isSidebarItemActive', () => {
  const page = { type: 'surface', surfaceId: 'home' } as const;

  it('selects a page row on any machine', () => {
    expect(isSidebarItemActive(page, 'dash', '/dashboard/plugin/m-1/dash/home')).toBe(true);
    expect(isSidebarItemActive(page, 'dash', '/dashboard/plugin/m-2/dash/home')).toBe(true);
  });

  it('does not select another plugin or page', () => {
    expect(isSidebarItemActive(page, 'dash', '/dashboard/plugin/m-1/other/home')).toBe(false);
    expect(isSidebarItemActive(page, 'dash', '/dashboard/plugin/m-1/dash/week')).toBe(false);
    expect(isSidebarItemActive(page, 'dash', '/dashboard/tasks')).toBe(false);
    expect(isSidebarItemActive(page, 'dash', null)).toBe(false);
  });

  it('selects an app-path row on its route, ignoring the query', () => {
    const tasks = { type: 'open-url', url: '/dashboard/tasks?view=board' } as const;
    expect(isSidebarItemActive(tasks, 'p', '/dashboard/tasks')).toBe(true);
    expect(isSidebarItemActive(tasks, 'p', '/dashboard/automation')).toBe(false);
    expect(isSidebarItemActive({ type: 'open-url', url: 'https://vicoa.ai' }, 'p', '/')).toBe(false);
  });
});
