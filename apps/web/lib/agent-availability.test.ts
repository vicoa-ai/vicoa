import { describe, expect, it } from 'vitest';
import { agentAvailability, firstInstalledAgent, providerSetupHref, splitByInstalled } from './agent-availability';

const entries = [
  { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'opencode', label: 'OpenCode' },
  { id: 'gemini', label: 'Gemini CLI' },
];
const ids = entries.map((e) => e.id);

describe('agentAvailability', () => {
  it('gates nothing when the daemon does not report installs', () => {
    const availability = agentAvailability(null);
    expect(availability.known).toBe(false);
    expect(availability.isInstalled('claude')).toBe(true);
  });

  it('counts only an explicit true as installed', () => {
    const availability = agentAvailability({ claude: false, codex: true });
    expect(availability.known).toBe(true);
    expect(availability.isInstalled('codex')).toBe(true);
    expect(availability.isInstalled('claude')).toBe(false);
    // An agent the daemon never mentioned cannot be launched by it either.
    expect(availability.isInstalled('gemini')).toBe(false);
  });
});

describe('splitByInstalled', () => {
  it('keeps the picker order inside each group', () => {
    const { installed, missing } = splitByInstalled(
      entries,
      agentAvailability({ claude: false, codex: true, opencode: false, gemini: true }),
    );
    expect(installed.map((e) => e.id)).toEqual(['codex', 'gemini']);
    expect(missing.map((e) => e.id)).toEqual(['claude', 'opencode']);
  });
});

describe('firstInstalledAgent', () => {
  it('prefers the plan choices, in their order', () => {
    expect(firstInstalledAgent(ids, agentAvailability({ gemini: true, opencode: true }))).toBe('opencode');
  });

  it('falls back to the first installed entry', () => {
    expect(firstInstalledAgent(ids, agentAvailability({ gemini: true }))).toBe('gemini');
  });

  it('is null when nothing is installed', () => {
    expect(firstInstalledAgent(ids, agentAvailability({}))).toBeNull();
  });

  it('never picks an agent the picker does not list', () => {
    expect(firstInstalledAgent(['gemini'], agentAvailability({ claude: true }))).toBeNull();
  });
});

describe('providerSetupHref', () => {
  it('opens Providers on the agent and the machine', () => {
    expect(providerSetupHref('claude', 'm-1')).toBe('/dashboard/settings?tab=providers&agent=claude&machine=m-1');
  });

  it('leaves the machine to Providers when none is selected', () => {
    expect(providerSetupHref('codex', null)).toBe('/dashboard/settings?tab=providers&agent=codex');
  });
});
