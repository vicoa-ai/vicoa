import { describe, expect, it } from 'vitest';
import {
  PROVIDER_CONFIG_CAPABILITY,
  describeProbe,
  machineSupportsProviderConfig,
  readAgentLabels,
  type ProviderProbeResult,
} from './desktop-provider-config';

describe('machineSupportsProviderConfig', () => {
  it('is true only when the daemon advertises the capability', () => {
    expect(
      machineSupportsProviderConfig({ metadata: { capabilities: ['agent-scan', PROVIDER_CONFIG_CAPABILITY] } }),
    ).toBe(true);
    // An old daemon: the page must fall back to copy-the-command text, never
    // offer an Add that would fail `no_handler`.
    expect(machineSupportsProviderConfig({ metadata: { capabilities: ['agent-scan'] } })).toBe(false);
    expect(machineSupportsProviderConfig({ metadata: null })).toBe(false);
    expect(machineSupportsProviderConfig(null)).toBe(false);
  });

  it('reads the WS `machine_metadata` shape too', () => {
    expect(
      machineSupportsProviderConfig({
        metadata: null,
        machine_metadata: { capabilities: [PROVIDER_CONFIG_CAPABILITY] },
      }),
    ).toBe(true);
  });
});

describe('readAgentLabels', () => {
  it('keeps only non-empty string labels', () => {
    expect(
      readAgentLabels({
        metadata: { agent_labels: { goose: 'Goose', cline: '', kimi: 7, cursor: null } },
      }),
    ).toEqual({ goose: 'Goose' });
  });

  it('is empty for an old daemon that does not publish labels', () => {
    expect(readAgentLabels({ metadata: { available_agents: { claude: true } } })).toEqual({});
    expect(readAgentLabels({ metadata: { agent_labels: ['nope'] } })).toEqual({});
  });
});

describe('describeProbe', () => {
  const base: ProviderProbeResult = {
    id: 'goose',
    label: 'goose',
    ok: false,
    stage: 'binary',
    installed: false,
    command: ['goose', 'acp'],
  };

  it('summarises a working agent with who answered, model count and time', () => {
    expect(
      describeProbe({
        ...base,
        ok: true,
        stage: 'ok',
        installed: true,
        agent: { name: 'goose', version: '1.33.1' },
        models: [
          { id: 'a', label: 'A' },
          { id: 'b', label: 'B' },
        ],
        elapsed_ms: 1234,
      }),
    ).toBe('Works (goose 1.33.1) · 2 models · 1.2s');
    expect(describeProbe({ ...base, ok: true, stage: 'ok', installed: true })).toBe('Works');
  });

  it('names the stage a failed probe stopped at, then the daemon’s reason', () => {
    expect(describeProbe({ ...base, error: "'goose' is not installed. brew install goose" })).toBe(
      "Not installed — 'goose' is not installed. brew install goose",
    );
    expect(describeProbe({ ...base, stage: 'initialize', installed: true, error: 'exited with code 2' })).toBe(
      "Didn't answer the ACP handshake — exited with code 2",
    );
    expect(describeProbe({ ...base, stage: 'session_new', installed: true })).toBe("Couldn't open a session");
  });
});
