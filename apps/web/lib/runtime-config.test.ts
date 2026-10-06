import { afterEach, describe, expect, it, vi } from 'vitest';
import { getDesktopTelemetryConfig, getDesktopWindowChrome } from './runtime-config';

/** Stub the preload-injected globals for one assertion. */
function stubWindow(injected: Record<string, unknown>) {
  vi.stubGlobal('window', injected);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('getDesktopWindowChrome', () => {
  it('uses the chrome the shell created the window with', () => {
    // Linux user who kept their desktop environment's title bar: we must draw
    // no window controls even though the platform would default to frameless.
    stubWindow({ __VICOA_PLATFORM__: 'linux', __VICOA_WINDOW_CHROME__: 'system' });
    expect(getDesktopWindowChrome()).toBe('system');

    stubWindow({ __VICOA_PLATFORM__: 'linux', __VICOA_WINDOW_CHROME__: 'custom' });
    expect(getDesktopWindowChrome()).toBe('custom');

    stubWindow({ __VICOA_PLATFORM__: 'darwin', __VICOA_WINDOW_CHROME__: 'mac' });
    expect(getDesktopWindowChrome()).toBe('mac');
  });

  it('falls back to the platform default when the shell injected nothing', () => {
    stubWindow({ __VICOA_PLATFORM__: 'darwin' });
    expect(getDesktopWindowChrome()).toBe('mac');

    stubWindow({ __VICOA_PLATFORM__: 'win32' });
    expect(getDesktopWindowChrome()).toBe('custom');

    stubWindow({ __VICOA_PLATFORM__: 'linux' });
    expect(getDesktopWindowChrome()).toBe('custom');
  });

  it('ignores a value it does not understand', () => {
    stubWindow({ __VICOA_PLATFORM__: 'linux', __VICOA_WINDOW_CHROME__: 'gnome' });
    expect(getDesktopWindowChrome()).toBe('custom');
  });

  it('is the macOS shape on plain web (no platform signal)', () => {
    stubWindow({});
    expect(getDesktopWindowChrome()).toBe('mac');
  });
});

describe('getDesktopTelemetryConfig', () => {
  it('never carries the daemon nonce', () => {
    stubWindow({
      __VICOA_DESKTOP__: {
        mode: 'local',
        wsUrl: 'ws://127.0.0.1:43118/ws',
        apiBase: 'http://127.0.0.1:43118',
        token: 'per-launch-secret-nonce',
        cloudApiBase: 'https://vicoa.example.com',
      },
    });
    const config = getDesktopTelemetryConfig();
    expect(config).toEqual({
      mode: 'local',
      wsUrl: 'ws://127.0.0.1:43118/ws',
      apiBase: 'http://127.0.0.1:43118',
      cloudApiBase: 'https://vicoa.example.com',
      cloudWsUrl: undefined,
    });
    expect(JSON.stringify(config)).not.toContain('per-launch-secret-nonce');
  });

  it('is null on plain web', () => {
    stubWindow({});
    expect(getDesktopTelemetryConfig()).toBeNull();
  });
});
