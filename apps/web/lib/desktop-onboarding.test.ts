import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DESKTOP_INTRO_KEY,
  DESKTOP_SETUP_KEY,
  hasCompletedDesktopSetup,
  hasSeenDesktopIntro,
  markDesktopIntroSeen,
  markDesktopSetupDone,
} from './desktop-onboarding';

function stubStorage(impl: Partial<Storage>) {
  vi.stubGlobal('window', { localStorage: impl });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('desktop onboarding flags', () => {
  it('round-trips the intro flag', () => {
    const store: Record<string, string> = {};
    stubStorage({
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
    });

    expect(hasSeenDesktopIntro()).toBe(false);
    markDesktopIntroSeen();
    expect(hasSeenDesktopIntro()).toBe(true);
    expect(store[DESKTOP_INTRO_KEY]).toBe('true');
  });

  it('round-trips the setup flag', () => {
    const store: Record<string, string> = {};
    stubStorage({
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
    });

    expect(hasCompletedDesktopSetup()).toBe(false);
    markDesktopSetupDone();
    expect(hasCompletedDesktopSetup()).toBe(true);
    expect(store[DESKTOP_SETUP_KEY]).toBe('true');
  });

  it('keeps the two flags independent', () => {
    const store: Record<string, string> = {};
    stubStorage({
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
    });

    markDesktopIntroSeen();
    expect(hasSeenDesktopIntro()).toBe(true);
    expect(hasCompletedDesktopSetup()).toBe(false);
  });

  it('reads false when localStorage throws', () => {
    // Private mode / disabled storage. Re-showing the intro is a mild
    // annoyance; throwing here would strand the gate mid-decision.
    stubStorage({
      getItem: () => {
        throw new Error('storage disabled');
      },
      setItem: () => {
        throw new Error('storage disabled');
      },
    });

    expect(hasSeenDesktopIntro()).toBe(false);
    expect(hasCompletedDesktopSetup()).toBe(false);
  });

  it('does not throw when a write fails', () => {
    stubStorage({
      getItem: () => null,
      setItem: () => {
        throw new Error('quota exceeded');
      },
    });

    expect(() => markDesktopIntroSeen()).not.toThrow();
    expect(() => markDesktopSetupDone()).not.toThrow();
  });

  it('treats any non-"true" value as not done', () => {
    stubStorage({ getItem: () => 'yes', setItem: () => {} });
    expect(hasSeenDesktopIntro()).toBe(false);
  });
});
