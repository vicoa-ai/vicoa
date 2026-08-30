import { describe, it, expect } from 'vitest';
import { cliButtonLabel, cliRowDescription, type CliLinkStatus } from '@/lib/desktop-cli';

const base: CliLinkStatus = {
  installed: false,
  foreign: false,
  available: true,
  path: '/Users/x/.local/bin/vicoa',
};

describe('cliRowDescription', () => {
  it('prompts to install when available and not yet installed', () => {
    expect(cliRowDescription(base)).toMatch(/task, automation, and session/);
  });

  it('shows the installation location when installed (not a command to run)', () => {
    const desc = cliRowDescription({ ...base, installed: true });
    expect(desc).toContain(base.path);
    expect(desc).toMatch(/Installed at/);
    expect(desc).not.toMatch(/task ls/);
  });

  it('warns about a foreign vicoa and names its path', () => {
    const desc = cliRowDescription({ ...base, foreign: true });
    expect(desc).toMatch(/Another "vicoa"/);
    expect(desc).toContain(base.path);
  });

  it('explains the not-yet-available state', () => {
    expect(cliRowDescription({ ...base, available: false })).toMatch(/Finishing agent setup/);
  });

  it('falls back to the install prompt on a null (web/SSR) status', () => {
    expect(cliRowDescription(null)).toMatch(/task, automation, and session/);
  });
});

describe('cliButtonLabel', () => {
  it('shows progress while busy', () => {
    expect(cliButtonLabel(base, true)).toBe('Installing…');
  });

  it('says Install when absent, Reinstall when present', () => {
    expect(cliButtonLabel(base, false)).toBe('Install');
    expect(cliButtonLabel({ ...base, installed: true }, false)).toBe('Reinstall');
  });
});
