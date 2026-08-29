import { describe, expect, it } from 'vitest';
import {
  AGENT_SCAN_CAPABILITY,
  buildScannedAgents,
  machineSupportsAgentScan,
  readAvailableAgents,
} from './desktop-agent-scan';

const CATALOG = [
  { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'opencode', label: 'OpenCode' },
];

describe('readAvailableAgents', () => {
  it('reads the REST `metadata` shape', () => {
    expect(readAvailableAgents({ metadata: { available_agents: { claude: true } } })).toEqual({
      claude: true,
    });
  });

  it('falls back to the WS `machine_metadata` shape', () => {
    // machine-update frames use machine_metadata; REST uses metadata. Both
    // reach this reader.
    expect(
      readAvailableAgents({ metadata: null, machine_metadata: { available_agents: { codex: true } } })
    ).toEqual({ codex: true });
  });

  it('returns null when the key is absent — "unknown", not "none installed"', () => {
    // An older daemon registers without available_agents. Rendering that as 8
    // red rows would tell the user to install agents they may already have.
    expect(readAvailableAgents({ metadata: { capabilities: ['worktree'] } })).toBeNull();
    expect(readAvailableAgents({ metadata: null })).toBeNull();
  });

  it('distinguishes an empty probe from an absent one', () => {
    expect(readAvailableAgents({ metadata: { available_agents: {} } })).toEqual({});
  });

  it('ignores non-boolean values rather than coercing them', () => {
    expect(
      readAvailableAgents({
        metadata: { available_agents: { claude: true, codex: 'yes', opencode: 1 } },
      })
    ).toEqual({ claude: true });
  });

  it('rejects an array — available_agents is an object map', () => {
    expect(readAvailableAgents({ metadata: { available_agents: ['claude'] } })).toBeNull();
  });
});

describe('buildScannedAgents', () => {
  it('joins detection onto the catalog, installed first', () => {
    const rows = buildScannedAgents(CATALOG, { claude: false, codex: true, opencode: true });
    expect(rows.map((r) => r.id)).toEqual(['codex', 'opencode', 'claude']);
    expect(rows.map((r) => r.installed)).toEqual([true, true, false]);
  });

  it('preserves catalog order within each group so the list is stable', () => {
    const rows = buildScannedAgents(CATALOG, { claude: true, codex: false, opencode: true });
    expect(rows.map((r) => r.id)).toEqual(['claude', 'opencode', 'codex']);
  });

  it('renders every catalog agent as not-installed when detection is unknown', () => {
    const rows = buildScannedAgents(CATALOG, null);
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => !r.installed)).toBe(true);
  });

  it('carries catalog labels through', () => {
    expect(buildScannedAgents(CATALOG, { claude: true })[0].label).toBe('Claude Code');
  });

  it('ignores detected agents the catalog does not know', () => {
    // The daemon may report an agent from a newer catalog than this build.
    const rows = buildScannedAgents(CATALOG, { claude: true, someFutureAgent: true });
    expect(rows.map((r) => r.id)).toEqual(['claude', 'codex', 'opencode']);
  });
});

describe('machineSupportsAgentScan', () => {
  it('is true when the daemon advertises the capability', () => {
    expect(
      machineSupportsAgentScan({ metadata: { capabilities: ['worktree', AGENT_SCAN_CAPABILITY] } })
    ).toBe(true);
  });

  it('is false for an older daemon that omits it', () => {
    // Such a daemon answers no_handler, so the button must not render.
    expect(machineSupportsAgentScan({ metadata: { capabilities: ['worktree'] } })).toBe(false);
  });

  it('is false when metadata or the machine is missing', () => {
    expect(machineSupportsAgentScan({ metadata: null })).toBe(false);
    expect(machineSupportsAgentScan(null)).toBe(false);
    expect(machineSupportsAgentScan(undefined)).toBe(false);
  });

  it('reads the WS metadata shape too', () => {
    expect(
      machineSupportsAgentScan({
        metadata: null,
        machine_metadata: { capabilities: [AGENT_SCAN_CAPABILITY] },
      })
    ).toBe(true);
  });
});
