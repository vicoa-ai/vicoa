import { describe, expect, it, vi } from 'vitest';

import { openCreatedSession, shouldOpenCreatedSession } from './new-session-navigation';

describe('shouldOpenCreatedSession', () => {
  it('opens when the user is still on the page they launched from', () => {
    expect(shouldOpenCreatedSession('/dashboard/agents/new-session', '/dashboard/agents/new-session')).toBe(true);
  });

  it('stays put when the user has navigated to another page', () => {
    expect(shouldOpenCreatedSession('/dashboard/agents/new-session', '/dashboard/agents/other-id')).toBe(false);
    expect(shouldOpenCreatedSession('/dashboard', '/dashboard/settings')).toBe(false);
  });
});

describe('openCreatedSession', () => {
  it('pushes to the target when the pathname is unchanged', () => {
    const router = { push: vi.fn() };
    vi.stubGlobal('window', { location: { pathname: '/dashboard/agents/new-session' } });

    openCreatedSession(router, '/dashboard/agents/new-session', '/dashboard/agents/new-id');

    expect(router.push).toHaveBeenCalledWith('/dashboard/agents/new-id');
    vi.unstubAllGlobals();
  });

  it('does not push when the user navigated away during the spawn', () => {
    const router = { push: vi.fn() };
    vi.stubGlobal('window', { location: { pathname: '/dashboard/agents/some-other-session' } });

    openCreatedSession(router, '/dashboard/agents/new-session', '/dashboard/agents/new-id');

    expect(router.push).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
